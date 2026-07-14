"""Main TUI screen -- layout, streaming, tool approval, session management."""
from __future__ import annotations

import asyncio
import logging
import threading

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
from ..widgets.slash_overlay import SlashOverlay
from ..utils.custom_commands import load_user_commands, load_project_commands
from ..widgets.approval_dialog import ApprovalDialog
from ..controllers.approval_controller import ApprovalController
from ..controllers.session_controller import SessionController
from .model_picker import ModelPicker
from .help_screen import HelpScreen

_log = logging.getLogger(__name__)


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
    ("ctrl+t", "model_picker", "Model"),
    ("ctrl+q", "Quit"),
  ]

  def __init__(self, runtime: CliAgentRuntime) -> None:
    super().__init__()
    self._runtime = runtime
    self._is_streaming = False
    self._agent_step = 0
    self._cancel_event: threading.Event | None = None

    mode_str = runtime._config.approval_mode if isinstance(runtime._config.approval_mode, str) else runtime._config.approval_mode.value
    self._approval = ApprovalController(mode=mode_str)  # type: ignore[arg-type]

    self._sessions = SessionController(
      runtime,
      on_sessions_changed=self._on_sessions_updated,
      on_session_loaded=self._on_session_loaded,
      on_error=lambda msg: self.notify(msg, severity="error"),
    )

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
    """Initialize status bar with model info, load sessions, and wire custom commands."""
    status = self.query_one(StatusBar)
    status.update_status(
      model_name=self._runtime._model_name,
      state="IDLE",
      approval_mode=self._approval.mode,
    )
    self._sessions.refresh()
    self._load_custom_commands()

    # Wire approval callback into the runtime (P0 #3)
    self._approval._ask_approval = self._ask_approval_from_thread
    self._runtime._on_approve = self._approval.request

    chat = self.query_one(ChatArea)
    chat.show_welcome()

  # ─── Approval gate (P0 #3) ────────────────────────────────────────

  def _ask_approval_from_thread(self, req):
    """Bridge worker-thread approval request to a Textual modal dialog."""
    result_holder: list[bool] = []
    ready = threading.Event()

    def _show_dialog() -> None:
      async def _inner() -> None:
        approved = await self.app.push_screen_wait(
          ApprovalDialog(req.tool_name, req.arguments, req.safety_class)
        )
        result_holder.append(approved)
        ready.set()
      self.run_worker(_inner())

    self.app.call_from_thread(_show_dialog)
    ready.wait(timeout=120)
    return result_holder[0] if result_holder else False

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
      overlay.select_previous()
    else:
      overlay.select_next()

  def on_input_area_select_slash(self, event: InputArea.SelectSlash) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.apply_selected()

  def on_input_area_dismiss_slash(self, event: InputArea.DismissSlash) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.hide_overlay()
    input_area = self.query_one(InputArea)
    input_area.input.read_only = False
    input_area.focus()

  def on_slash_overlay_slash_command(self, event: SlashOverlay.SlashCommand) -> None:
    """Handle slash command selection."""
    overlay = self.query_one(SlashOverlay)
    overlay.hide_overlay()
    input_area = self.query_one(InputArea)
    input_area.input.read_only = False
    input_area.focus()

    cmd = event.command
    if cmd.handler:
      if cmd.requires_input:
        input_area.focus()
      else:
        if cmd.handler == "model_picker":
          self._open_model_picker()
        elif cmd.handler == "help":
          self._show_help()
        elif cmd.handler == "compact":
          self._compact_context()
        elif cmd.handler == "clear":
          self.action_clear_chat()
        elif cmd.handler == "sessions":
          self._list_sessions()
        elif cmd.handler == "doctor":
          self._run_doctor()
        elif cmd.handler == "theme":
          self._cycle_theme()
        elif cmd.handler == "approval":
          self._toggle_approval()
        elif cmd.handler == "sidebar":
          self._toggle_sidebar()

  # ─── Main send flow ────────────────────────────────────────────────

  def on_input_area_user_message(self, event: InputArea.UserMessage) -> None:
    """User submitted a message -- start streaming from the agent."""
    text = event.text.strip()
    if not text:
      return

    chat = self.query_one(ChatArea)
    input_area = self.query_one(InputArea)
    status = self.query_one(StatusBar)

    chat.add_message(text, "user")
    input_area.clear()
    input_area.show_thinking()
    self._is_streaming = True
    status.set_streaming_hint(True)
    status.set_step_count(self._agent_step)

    self.run_worker(self._stream_agent(text))

  async def _stream_agent(self, user_input: str) -> None:
    """Async wrapper that consumes the sync step_stream() generator via a thread."""
    chat = self.query_one(ChatArea)
    input_area = self.query_one(InputArea)
    status = self.query_one(StatusBar)

    try:
      loop = asyncio.get_running_loop()
      queue: asyncio.Queue[StreamChunk | AgentSnapshot | Exception | None] = asyncio.Queue()
      cancel = threading.Event()
      self._cancel_event = cancel
      turn_id = id(cancel)

      def _producer() -> None:
        try:
          for item in self._runtime.step_stream(user_input):
            if cancel.is_set():
              break
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:
          if not cancel.is_set():
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
          loop.call_soon_threadsafe(queue.put_nowait, None)

      threading.Thread(target=_producer, daemon=True).start()
      await self._consume_queue(cancel, chat, status, input_area, turn_id, queue)

    except Exception as exc:
      _log.error("Streaming failed: %s", exc)
      chat.add_message(f"Streaming failed: {exc}", "assistant")
    finally:
      self._is_streaming = False
      self._cancel_event = None
      input_area.show_send()
      input_area.focus()
      status.set_streaming_hint(False)

  async def _consume_queue(self, cancel, chat, status, input_area, turn_id, queue):
    while True:
      item = await queue.get()
      if item is None:
        break
      if cancel.is_set():
        chat.cancel_stream()
        break

      if isinstance(item, Exception):
        chat.cancel_stream()
        chat.add_message(f"Agent error: {item}", "assistant")
        break

      if isinstance(item, StreamChunk):
        if item.type == ChunkType.TEXT and item.delta:
          chat.add_stream_chunk(item.delta, turn_id)
        elif item.type == ChunkType.TOOL_CALL_START:
          chat.add_tool_call_start(
            item.tool_name or "tool",
            item.tool_call_id or "",
            turn_id,
          )
        elif item.type == ChunkType.TOOL_CALL_ARGS and item.delta:
          chat.add_tool_call_args(item.tool_call_id or "", item.delta, turn_id)
        elif item.type == ChunkType.TOOL_CALL_END:
          chat.add_tool_call_end(item.tool_call_id or "", item.delta or "", turn_id)
          self._agent_step += 1
          status.set_step_count(self._agent_step)
      elif isinstance(item, AgentSnapshot):
        chat.end_stream(turn_id)
        status.set_step_count(self._agent_step)

  # ─── Cancel ────────────────────────────────────────────────────────

  def _handle_escape(self) -> None:
    """Handle Escape key press."""
    overlay = self.query_one(SlashOverlay)
    if overlay.visible:
      overlay.hide_overlay()
      input_area = self.query_one(InputArea)
      input_area.input.read_only = False
      input_area.focus()
      return

    if self._is_streaming and self._cancel_event:
      self._cancel_event.set()
      chat = self.query_one(ChatArea)
      chat.cancel_stream()
      status = self.query_one(StatusBar)
      status.set_streaming_hint(False)
      self._is_streaming = False
      self.notify("Cancelled")
      return

  def on_key(self, event) -> None:
    if event.key == "escape":
      self._handle_escape()
      event.prevent_default()

  # ─── Session management ────────────────────────────────────────────

  def on_session_panel_session_selected(self, event: SessionPanel.SessionSelected) -> None:
    """Load a session from the sidebar."""
    session_id = event.session_id
    try:
      session = self._runtime.load_session(session_id)
      chat = self.query_one(ChatArea)
      chat.clear()
      for msg in session.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content and role in ("user", "assistant"):
          chat.add_message(content, role)
      self.notify(f"Session {session_id[:8]} loaded")
    except Exception as exc:
      _log.error("Failed to load session %s: %s", session_id, exc)
      self.notify(f"Failed to load session: {exc}", severity="error")

  def on_session_panel_new_session(self, event: SessionPanel.NewSession) -> None:
    """Create a new session."""
    try:
      self._runtime.new_session()
      chat = self.query_one(ChatArea)
      chat.clear()
      self._agent_step = 0
      status = self.query_one(StatusBar)
      status.set_step_count(0)
      self._sessions.refresh()
      self.notify("New session created")
    except Exception as exc:
      _log.error("Failed to create session: %s", exc)
      self.notify(f"Failed to create session: {exc}", severity="error")

  def on_session_panel_refresh_sessions(self, event: SessionPanel.RefreshSessions) -> None:
    self._sessions.refresh()

  def _refresh_sessions(self) -> None:
    try:
      sessions = self._runtime.session_store.list_sessions()
      panel = self.query_one(SessionPanel)
      current_id = self._runtime.session.session_id if self._runtime.session else None
      session_data = []
      for s in sessions[:50]:
        session_data.append({
          "id": s.id,
          "title": s.title or "Untitled",
          "updated_at": s.updated_at,
          "message_count": 0,
          "is_current": s.id == current_id,
        })
      panel.set_sessions(session_data)
    except Exception as exc:
      _log.error("Failed to refresh sessions: %s", exc)

  # ─── Custom commands ───────────────────────────────────────────────

  def _load_custom_commands(self) -> None:
    try:
      overlay = self.query_one(SlashOverlay)
      project = load_project_commands(self._runtime._workspace_root)
      user = load_user_commands()
      overlay.add_commands(project + user)
    except Exception as exc:
      _log.error("Failed to load custom commands: %s", exc)

  # ─── Sidebar toggle ───────────────────────────────────────────────

  def _toggle_sidebar(self) -> None:
    sidebar = self.query_one("#sidebar")
    sidebar.display = not sidebar.display
    self.notify("Sidebar " + ("shown" if sidebar.display else "hidden"))

  # ─── Model picker ─────────────────────────────────────────────────

  def _list_available_models(self) -> list[str]:
    try:
      from apps.cli.src.config.resolution import resolve_config
      config = resolve_config(self._runtime._workspace_root)
      models = config.model.extra.get("models", [])
      if isinstance(models, list) and models:
        return [str(m) for m in models]
    except Exception:
      pass
    current = self._runtime._model_name
    return [current] if current else ["gpt-4o"]

  def _open_model_picker(self) -> None:
    self.action_model_picker()

  def action_model_picker(self) -> None:
    async def _run() -> None:
      current = self._runtime._model_name
      models = self._list_available_models()
      chosen = await self.app.push_screen_wait(ModelPicker(models, current))
      if chosen and chosen != current:
        self._runtime._model_name = chosen
        status = self.query_one(StatusBar)
        status.update_status(model_name=chosen)
        self.notify(f"Model: {chosen}")
      input_area = self.query_one(InputArea)
      input_area.focus()
    self.run_worker(_run())

  def _toggle_approval(self) -> None:
    current = self._approval.mode
    new_mode = "manual" if current == "auto" else "auto"
    self._approval.mode = new_mode  # type: ignore[assignment]
    status = self.query_one(StatusBar)
    status.update_status(approval_mode=new_mode)
    self.notify(f"Approval mode: {new_mode}")

  def _cycle_theme(self) -> None:
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
    async def _show() -> None:
      await self.app.push_screen_wait(HelpScreen())
      input_area = self.query_one(InputArea)
      input_area.focus()
    self.run_worker(_show())

  def _compact_context(self) -> None:
    try:
      if self._runtime.compact():
        self.notify("Context compacted")
      else:
        self.notify("Nothing to compact")
    except Exception as exc:
      _log.error("Compact failed: %s", exc)
      self.notify(f"Compact failed: {exc}", severity="error")

  def _list_sessions(self) -> None:
    sidebar = self.query_one("#sidebar")
    if not sidebar.display:
      sidebar.display = True
    self._sessions.refresh()
    self.notify("Sessions refreshed")

  def _run_doctor(self) -> None:
    from apps.cli.src.commands.doctor import run_doctor
    chat = self.query_one(ChatArea)
    try:
      import io
      import contextlib
      buf = io.StringIO()
      with contextlib.redirect_stdout(buf):
        run_doctor()
      output = buf.getvalue()
      lines = output.strip().split("\n")
      summary = "\n".join(lines[:20])
      chat.add_message(f"**Doctor Results:**\n```\n{summary}\n```", "assistant")
    except Exception as exc:
      _log.error("Doctor check failed: %s", exc)
      chat.add_message(f"Doctor check failed: {exc}", "assistant")

  def action_new_session(self) -> None:
    self._agent_step = 0
    status = self.query_one(StatusBar)
    status.set_step_count(0)
    self._sessions.create_new()

  def action_toggle_sidebar(self) -> None:
    self._toggle_sidebar()

  def action_help(self) -> None:
    self._show_help()

  def action_command_palette(self) -> None:
    input_area = self.query_one(InputArea)
    input_area.focus()
    overlay = self.query_one(SlashOverlay)
    overlay.show_overlay("")
    input_area.activate_slash_overlay()

  def action_compact(self) -> None:
    self._compact_context()

  def action_quit(self) -> None:
    self.app.exit()
