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

from ..widgets.slash_overlay import SlashOverlay

from ..utils.custom_commands import load_user_commands, load_project_commands

from ..widgets.slash_overlay import SlashCommand

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

    ("ctrl+q", "Quit"),

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

    """Initialize status bar with model info, load sessions, and wire custom commands."""

    status = self.query_one(StatusBar)

    approval = self._runtime._config.approval_mode

    status.update_status(

      model_name=self._runtime._model_name,

      state="IDLE",

      approval_mode=approval if isinstance(approval, str) else approval.value,

    )

    self._refresh_sessions()

    self._load_custom_commands()

    # Show welcome banner in chat area

    chat = self.query_one(ChatArea)

    chat.show_welcome()

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

    cmd_id, content = overlay.confirm_selection()

    overlay.hide_overlay()

    input_area = self.query_one(InputArea)

    input_area.deactivate_slash_overlay()

    input_area.clear_slash_text()

    if cmd_id:

      self._dispatch_command(cmd_id, content)

  def _load_custom_commands(self) -> None:

    """Load user-level and workspace-level custom commands into the overlay."""

    try:

      overlay = self.query_one(SlashOverlay)

      workspace_root = Path(self._runtime._config.workspace_root) if self._runtime._config.workspace_root else Path.cwd()

      user_cmds = load_user_commands()

      project_cmds = load_project_commands(workspace_root)

      custom: list[SlashCommand] = []

      for cmd in (*user_cmds, *project_cmds):

        custom.append(

          SlashCommand(

            id=cmd.id,

            label=cmd.title,

            description=cmd.description,

            content=cmd.content,

            category="Custom",

            icon="#",

            argument_names=cmd.argument_names,

            is_custom=True,

          )

        )

      overlay.set_custom_commands(custom)

    except Exception:

      # Custom commands are optional; do not break mount if loader fails.

      pass

  def _dispatch_command(self, cmd_id: str, content: str | None) -> None:

    """Dispatch a command, showing argument dialog if placeholders are present."""

    if content:

      placeholders = SlashOverlay.ArgumentDialog.extract_placeholders(content)

      if placeholders:

        self._show_argument_dialog(cmd_id, content, placeholders)

        return

    self._run_command(cmd_id, content=content)

  def _show_argument_dialog(

    self, cmd_id: str, content: str, arg_names: list[str]

  ) -> None:

    """Show inline argument dialog for $NAME placeholders."""

    # Remove any existing dialog first

    try:

      old = self.query_one("#arg-dialog")

      old.remove()

    except Exception:

      pass

    new_dialog = SlashOverlay.ArgumentDialog(cmd_id, arg_names, id="arg-dialog")

    new_dialog._template_content = content

    container = self.query_one("#chat-container")

    container.mount(new_dialog)

    new_dialog.add_class("visible")

    new_dialog.focus()

  def on_argument_dialog_args_submitted(

    self, event: SlashOverlay.ArgumentDialog.ArgsSubmitted

  ) -> None:

    """User filled in arguments -- apply and execute."""

    template = None

    try:

      dialog = self.query_one("#arg-dialog", SlashOverlay.ArgumentDialog)

      template = getattr(dialog, "_template_content", None)

      dialog.remove()

    except Exception:

      pass

    if template:

      resolved = SlashOverlay.ArgumentDialog.apply_arguments(template, event.args)

      self._run_command(event.command_id, content=resolved)

  def on_argument_dialog_cancelled(

    self, event: SlashOverlay.ArgumentDialog.Cancelled

  ) -> None:

    """User cancelled the argument dialog."""

    try:

      dialog = self.query_one("#arg-dialog", SlashOverlay.ArgumentDialog)

      dialog.remove()

    except Exception:

      pass

    self.notify("Command cancelled.", severity="information")

  def on_input_area_dismiss_slash(self, event: InputArea.DismissSlash) -> None:

    """Escape while overlay is open -- dismiss it."""

    overlay = self.query_one(SlashOverlay)

    overlay.hide_overlay()

    input_area = self.query_one(InputArea)

    input_area.deactivate_slash_overlay()

  def on_slash_overlay_command_selected(self, event: SlashOverlay.CommandSelected) -> None:

    """Click on a slash command item -- execute it."""

    overlay = self.query_one(SlashOverlay)

    overlay.hide_overlay()

    input_area = self.query_one(InputArea)

    input_area.deactivate_slash_overlay()

    input_area.clear_slash_text()

    self._dispatch_command(event.command_id, event.content)

  # ─── Text submission ────────────────────────────────────────────────

  def on_input_area_submitted(self, event: InputArea.Submitted) -> None:

    """Handle user message submission.

    Guard: if the slash overlay is active we must not treat the keystroke as

    a chat submission. InputArea already confirms the overlay on Enter, but

    the Submitted message can still bubble in edge cases; drop it here.

    """

    input_area = self.query_one(InputArea)

    if input_area.is_slash_active:

      return

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

      self._is_streaming = False

      status = self.query_one(StatusBar)

      status.update_status(state="IDLE")

      self.notify("Streaming cancelled")

  # ─── Streaming agent loop ──────────────────────────────────────────

  async def _stream_worker(self, user_input: str) -> None:

    """Run the agent loop with streaming output."""

    self._is_streaming = True

    status = self.query_one(StatusBar)

    status.update_status(state="THINKING")

    chat = self.query_one(ChatArea)

    chat.start_stream("assistant")

    try:

      async for chunk in self._runtime.step_stream(user_input):

        if isinstance(chunk, StreamChunk):

          if chunk.type == ChunkType.TEXT and chunk.delta:

            chat.add_stream_chunk(chunk.delta)

          elif chunk.type == ChunkType.TOOL_CALL_START:

            chat.add_tool_call_start(

              chunk.tool_name or "tool",

              chunk.tool_call_id or "",

            )

            status.update_status(state="TOOL_RUNNING")

          elif chunk.type == ChunkType.TOOL_CALL_ARGS and chunk.delta:

            chat.add_tool_call_args(

              chunk.tool_name or "tool",

              chunk.delta,

              tool_call_id=chunk.tool_call_id or "",

            )

          elif chunk.type == ChunkType.TOOL_CALL_END:

            chat.add_tool_call_end(

              chunk.tool_name or "tool",

              chunk.tool_call_id or "",

              result=chunk.delta or "",

              is_error=False,

            )

            status.update_status(state="THINKING")

        elif isinstance(chunk, AgentSnapshot):

          chat.end_stream()

          tokens = chunk.tokens_used or 0

          cost = chunk.cost_usd

          ctx = chunk.context_usage

          status.update_status(

            state="IDLE",

            tokens=tokens,

            cost=cost,

            context_usage=ctx,

          )

    except Exception as e:

      chat.cancel_stream()

      chat.add_message(f"Error: {e}", "assistant")

      status.update_status(state="IDLE")

    finally:

      self._is_streaming = False

  # ─── Session management ────────────────────────────────────────────

  def _refresh_sessions(self) -> None:

    """Reload sessions into the sidebar."""

    try:

      panel = self.query_one(SessionPanel)

      sessions = self._runtime._session_store.list_sessions(limit=30)

      panel.sessions = [

        {"id": s.session_id, "label": s.title or s.session_id[:12], "ts": s.started_at}

        for s in sessions

      ]

    except Exception:

      pass

  def on_session_panel_new_session(self, event: SessionPanel.NewSession) -> None:

    """Start a new session."""

    self._runtime._session = None

    chat = self.query_one(ChatArea)

    chat.clear()

    self.notify("New session started")

    self._refresh_sessions()

  def on_session_panel_session_selected(self, event: SessionPanel.SessionSelected) -> None:

    """Load a previous session."""

    try:

      store = self._runtime._session_store

      session = store.get_session(event.session_id)

      if session is None:

        self.notify("Session not found", severity="warning")

        return

      messages = store.get_messages(event.session_id)

      initial = []

      from packages.core.src.runtime.session import MessageRecord

      for mr in messages:

        initial.append(MessageRecord(

          session_id=mr.session_id,

          role=mr.role,

          content=mr.content,

          timestamp=mr.timestamp,

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

    except Exception as e:

      self.notify(f"Failed to load session: {e}", severity="error")

  def on_session_panel_refresh_sessions(self, event: SessionPanel.RefreshSessions) -> None:

    """Handle refresh request."""

    self._refresh_sessions()

  # ─── Slash command execution ────────────────────────────────────────

  def _run_command(self, cmd_id: str, *, content: str | None = None) -> None:

    """Execute a slash command by id."""

    # Custom commands: send content as user message to agent

    if cmd_id.startswith("user:") or cmd_id.startswith("project:"):

      if content:

        self._run_custom_command(content)

        return

      self.notify(f"Custom command {cmd_id} has no content", severity="warning")

      return

    dispatch = {

      "new":       self.action_new_session,

      "refresh":   self._refresh_sessions,

      "sidebar":   self._toggle_sidebar,

      "clear":     self.action_clear_chat,

      "model":     self._open_model_picker,

      "approval":  self._toggle_approval,

      "theme":     self._cycle_theme,

      "help":      self._show_help,

      "compact":   self._compact_context,

      "sessions":  self._list_sessions,

      "doctor":    self._run_doctor,

      "init":      self._run_init,

      "quit":      self.action_quit,

    }

    handler = dispatch.get(cmd_id)

    if handler:

      handler()

    else:

      self.notify(f"Unknown command: {cmd_id}", severity="warning")

  def _run_custom_command(self, content: str) -> None:

    """Send custom command content as a user message to the agent."""

    if self._is_streaming:

      self.notify("Agent is busy -- wait for it to finish.", severity="warning")

      return

    chat = self.query_one(ChatArea)

    chat.add_message(content, "user")

    self.run_worker(self._stream_worker(content), exclusive=True)

  def _run_init(self) -> None:

    """Initialize .kcode/ workspace."""

    try:

      from apps.cli.src.commands.init import run_init

      workspace = self._runtime._config.workspace_root or Path.cwd()

      run_init(workspace)

      self.notify(f"Initialized .kcode/ in {workspace}")

    except Exception as e:

      self.notify(f"Init failed: {e}", severity="error")

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

      result = self._runtime.compact()

      if result:

        self.notify("Context compacted")

      else:

        self.notify("Nothing to compact")

    except Exception as e:

      self.notify(f"Compact failed: {e}", severity="error")

  def _list_sessions(self) -> None:

    """Show sessions info in the sidebar."""

    sidebar = self.query_one("#sidebar")

    if not sidebar.display:

      sidebar.display = True

    self._refresh_sessions()

    self.notify("Sessions refreshed")

  def _run_doctor(self) -> None:

    """Run a quick health check and show result."""

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

    except Exception as e:

      chat.add_message(f"Doctor check failed: {e}", "assistant")

  # ─── Actions ────────────────────────────────────────────────────────

  def action_new_session(self) -> None:

    self.on_session_panel_new_session(SessionPanel.NewSession())

  def action_toggle_sidebar(self) -> None:

    self._toggle_sidebar()

  def action_help(self) -> None:

    self._show_help()

  def action_command_palette(self) -> None:

    """Ctrl+K -- open the slash overlay as a command palette.

    Note: Ctrl+K is now handled directly by InputArea which sets

    palette_mode=True. This action is kept for programmatic use.

    """

    input_area = self.query_one(InputArea)

    input_area.focus()

    # InputArea.on_key handles Ctrl+K directly now

    # This method is a fallback for programmatic invocation

    overlay = self.query_one(SlashOverlay)

    overlay.show_overlay("")

    input_area.activate_slash_overlay()

  def action_compact(self) -> None:

    """Compact the conversation context."""

    if self._runtime.compact():

      self.notify("Context compacted")

    else:

      self.notify("Nothing to compact")

  def action_quit(self) -> None:

    self.app.exit()

