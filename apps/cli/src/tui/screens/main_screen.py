"""Main TUI screen -- layout, streaming, tool approval, session management."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer

from packages.core.src.models.interfaces import StreamChunk, ChunkType
from packages.core.src.runtime.contracts import AgentSnapshot
from apps.cli.src.core.agent_runtime import CliAgentRuntime

from ..widgets.chat_area import ChatArea
from ..widgets.input_area import InputArea
from ..widgets.status_bar import StatusBar
from ..widgets.session_panel import SessionPanel
from ..widgets.approval_dialog import ApprovalDialog
from ..widgets.slash_overlay import SlashOverlay

from .model_picker import ModelPicker
from .help_screen import HelpScreen


class MainScreen(Screen):
  """Primary screen: chat + input + sidebar + inline slash overlay + status bar."""

  CSS = """
  #main-container {
    width: 100%;
    height: 1fr;
  }

  #chat-container {
    width: 1fr;
    height: 100%;
  }

  #input-wrapper {
    height: auto;
  }

  #sidebar {
    width: 30;
    min-width: 20;
    height: 100%;
  }
  """

  BINDINGS = [
    ("ctrl+n", "new_session", "New Session"),
    ("ctrl+l", "clear_chat", "Clear Chat"),
    ("ctrl+b", "toggle_sidebar", "Sidebar"),
    ("ctrl+h", "help", "Help"),
    ("ctrl+q", "quit", "Quit"),
  ]

  def __init__(self, runtime: CliAgentRuntime) -> None:
    super().__init__()
    self._runtime = runtime
    self._is_streaming = False

  def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal(id="main-container"):
      with Vertical(id="chat-container"):
        yield ChatArea()
        with Vertical(id="input-wrapper"):
          yield SlashOverlay()
          yield InputArea()
      with Vertical(id="sidebar"):
        yield SessionPanel()
    yield StatusBar()
    yield Footer()

  def on_mount(self) -> None:
    """Initialize status bar with model info and load sessions."""
    status = self.query_one(StatusBar)
    approval = self._runtime._config.approval_mode
    status.update_status(
      model_name=self._runtime._model_name,
      state="IDLE",
      approval_mode=approval if isinstance(approval, str) else approval.value,
    )
    self._refresh_sessions()

  # ─── Slash overlay integration ─────────────────────────────────────

  def on_input_area_open_slash_overlay(self, event: InputArea.OpenSlashOverlay) -> None:
    """User typed '/' -- show the inline overlay."""
    overlay = self.query_one(SlashOverlay)
    overlay.show_overlay(event.query)
    input_area = self.query_one(InputArea)
    input_area.activate_slash_overlay()

  def on_input_area_update_slash_filter(self, event: InputArea.UpdateSlashFilter) -> None:
    """User typed more after '/' -- update overlay filter."""
    overlay = self.query_one(SlashOverlay)
    if overlay.visible:
      overlay.update_filter(event.query)

  def on_input_area_navigate_slash(self, event: InputArea.NavigateSlash) -> None:
    """Arrow key navigation inside overlay."""
    overlay = self.query_one(SlashOverlay)
    if event.direction == "up":
      overlay.move_up()
    else:
      overlay.move_down()

  def on_input_area_confirm_slash(self, event: InputArea.ConfirmSlash) -> None:
    """Tab or Enter while overlay is open -- confirm the selected command."""
    overlay = self.query_one(SlashOverlay)
    cmd_id = overlay.confirm_selection()
    overlay.hide_overlay()
    input_area = self.query_one(InputArea)
    input_area.deactivate_slash_overlay()
    input_area.clear_slash_text()
    if cmd_id:
      self._run_command(cmd_id)

  def on_input_area_dismiss_slash(self, event: InputArea.DismissSlash) -> None:
    """Escape while overlay is open -- dismiss it."""
    overlay = self.query_one(SlashOverlay)
    overlay.hide_overlay()
    input_area = self.query_one(InputArea)
    input_area.deactivate_slash_overlay()

  # ─── Text submission ────────────────────────────────────────────────

  def on_input_area_submitted(self, event: InputArea.Submitted) -> None:
    """Handle user message submission."""
    if self._is_streaming:
      self.notify("Agent is busy -- wait for it to finish.", severity="warning")
      return

    chat = self.query_one(ChatArea)
    chat.add_message(event.value, "user")
    self.run_worker(self._stream_worker(event.value), exclusive=True)

  def on_input_area_cancel_requested(self, event: InputArea.CancelRequested) -> None:
    """Escape when overlay closed -- cancel streaming if active."""
    if self._is_streaming:
      chat = self.query_one(ChatArea)
      chat.cancel_stream()
      chat.add_message("Cancelled.", "system")
      status = self.query_one(StatusBar)
      status.update_status(state="IDLE")
      self._is_streaming = False
      self.notify("Streaming cancelled")

  # ─── Streaming ──────────────────────────────────────────────────────

  async def _stream_worker(self, user_input: str) -> None:
    """Stream agent response in a background worker."""
    self._is_streaming = True
    chat = self.query_one(ChatArea)
    status = self.query_one(StatusBar)

    try:
      status.update_status(state="THINKING")
      chat.start_stream("assistant")

      for item in self._runtime.step_stream(user_input):
        if isinstance(item, AgentSnapshot):
          chat.end_stream()
          meta = item.metadata
          status.update_status(
            state=item.state.name,
            tokens=meta.get("token_count"),
            context_utilization=meta.get("context_utilization"),
          )
          break

        if not isinstance(item, StreamChunk):
          continue

        chunk: StreamChunk = item

        if chunk.type == ChunkType.TEXT:
          chat.add_stream_chunk(chunk.delta)

        elif chunk.type == ChunkType.TOOL_CALL_START:
          chat.end_stream()
          chat.add_tool_call_start(chunk.tool_name, chunk.tool_call_id)
          status.update_status(state="TOOL_RUNNING")

        elif chunk.type == ChunkType.TOOL_CALL_ARGS:
          pass

        elif chunk.type == ChunkType.TOOL_CALL_END:
          if chunk.delta:
            chat.add_tool_call_end(
              tool_name=chunk.tool_name or "tool",
              tool_call_id=chunk.tool_call_id,
              result=chunk.delta,
              is_error=chunk.delta.startswith("Tool error"),
            )
            chat.start_stream("assistant")
            status.update_status(state="THINKING")

        elif chunk.type == ChunkType.USAGE:
          status.update_status(tokens=chunk.usage)

    except Exception as exc:
      chat.end_stream()
      chat.add_message(f"Error: {exc}", "system")
      status.update_status(state="ERROR")
    finally:
      self._is_streaming = False

  # ─── Approval gate ──────────────────────────────────────────────────

  async def _request_approval(self, tool_name: str, tool_args: dict, safety_class: str) -> bool:
    """Show modal approval dialog and return True if approved."""
    dialog = ApprovalDialog(tool_name, tool_args, safety_class)
    result = await self.app.push_screen_wait(dialog)
    return bool(result)

  # ─── Session management ─────────────────────────────────────────────

  def _refresh_sessions(self) -> None:
    """Load sessions from SessionStore into the sidebar."""
    try:
      store = self._runtime._session_store
      sessions = store.list_sessions(limit=50)
      panel = self.query_one(SessionPanel)
      panel.set_sessions([
        (s.id, s.title) for s in sessions
      ])
    except Exception:
      pass

  def on_session_panel_new_session(self, event: SessionPanel.NewSession) -> None:
    """Handle new session request."""
    self._runtime._bootstrap_messages()
    chat = self.query_one(ChatArea)
    chat.clear()
    chat.add_message("New session started.", "system")
    self.notify("New session created")

  def on_session_panel_session_selected(self, event: SessionPanel.SessionSelected) -> None:
    """Handle session selection -- reload conversation history."""
    store = self._runtime._session_store
    session = store.get_session(event.session_id)
    if not session:
      self.notify("Session not found", severity="error")
      return

    messages = store.get_messages(event.session_id)
    from packages.core.src.models.interfaces import Message

    initial: list[Message] = []
    for mr in messages:
      initial.append(Message(
        role=mr.role,
        content=mr.content,
        tool_calls=mr.tool_calls,
        tool_call_id=mr.tool_call_id,
      ))

    self._runtime._session = session
    self._runtime._replay_messages(initial)

    chat = self.query_one(ChatArea)
    chat.clear()
    for mr in messages:
      if mr.role == "user" and mr.content:
        chat.add_message(mr.content, "user")
      elif mr.role == "assistant" and mr.content:
        chat.add_message(mr.content, "assistant")

    self.notify(f"Loaded session {event.session_id[:8]}")

  def on_session_panel_refresh_sessions(self, event: SessionPanel.RefreshSessions) -> None:
    """Handle refresh request."""
    self._refresh_sessions()

  # ─── Slash command execution ────────────────────────────────────────

  def _run_command(self, cmd_id: str) -> None:
    """Execute a slash command by id."""
    dispatch = {
      "new_session":  self.action_new_session,
      "refresh":      self._refresh_sessions,
      "sidebar":      self._toggle_sidebar,
      "clear":        self.action_clear_chat,
      "model":        self._open_model_picker,
      "approval":     self._toggle_approval,
      "theme":        self._cycle_theme,
      "help":         self._show_help,
      "compact":      self._compact_context,
      "quit":         self.action_quit,
    }
    handler = dispatch.get(cmd_id)
    if handler:
      handler()
    else:
      self.notify(f"Unknown command: {cmd_id}", severity="warning")

  def _toggle_sidebar(self) -> None:
    """Toggle sidebar visibility."""
    sidebar = self.query_one("#sidebar")
    sidebar.display = not sidebar.display

  def action_clear_chat(self) -> None:
    """Clear the chat display."""
    chat = self.query_one(ChatArea)
    chat.clear()
    self.notify("Chat cleared")

  def _open_model_picker(self) -> None:
    """Open the model picker modal."""
    async def _run() -> None:
      current = self._runtime._model_name
      models = self._list_available_models()
      chosen = await self.app.push_screen_wait(ModelPicker(models, current))
      if chosen and chosen != current:
        self._runtime._model_name = chosen
        status = self.query_one(StatusBar)
        status.update_status(model_name=chosen)
        self.notify(f"Model: {chosen}")
    self.run_worker(_run())

  def _list_available_models(self) -> list[str]:
    """Return list of available model names."""
    try:
      from apps.cli.src.config.resolution import resolve_config
      config = resolve_config(Path.cwd())
      models = config.model.extra.get("models", [])
      if isinstance(models, list) and models:
        return [str(m) for m in models]
    except Exception:
      pass
    current = self._runtime._model_name
    return [current] if current else ["gpt-4o"]

  def _toggle_approval(self) -> None:
    """Toggle between ask and auto approval mode."""
    current = self._runtime._config.approval_mode
    current_str = current if isinstance(current, str) else current.value
    new_mode = "manual" if current_str == "auto" else "auto"
    from packages.core.src.config.loader import ApprovalMode
    self._runtime._config.approval_mode = ApprovalMode(new_mode)
    status = self.query_one(StatusBar)
    status.update_status(approval_mode=new_mode)
    self.notify(f"Approval mode: {new_mode}")

  def _cycle_theme(self) -> None:
    """Cycle through available themes."""
    themes = self.app.available_themes
    names = [t.name for t in themes] if themes else []
    if not names:
      self.notify("No themes available")
      return
    current = self.app.theme or "textual-dark"
    try:
      idx = names.index(current)
      next_theme = names[(idx + 1) % len(names)]
    except ValueError:
      next_theme = names[0]
    self.app.theme = next_theme
    self.notify(f"Theme: {next_theme}")

  def _show_help(self) -> None:
    """Show the help screen."""
    self.app.push_screen(HelpScreen())

  def _compact_context(self) -> None:
    """Compact the conversation context."""
    try:
      self._runtime._maybe_compact()
      self.notify("Context compacted")
    except Exception as e:
      self.notify(f"Compact failed: {e}", severity="error")

  # ─── Actions ────────────────────────────────────────────────────────

  def action_new_session(self) -> None:
    self.on_session_panel_new_session(SessionPanel.NewSession())

  def action_toggle_sidebar(self) -> None:
    self._toggle_sidebar()

  def action_help(self) -> None:
    self._show_help()

  def action_quit(self) -> None:
    self.app.exit()


