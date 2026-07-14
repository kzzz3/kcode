"""Main TUI screen -- thin orchestrator wired to controllers."""
from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer

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
from ..controllers.turn_controller import TurnController, TurnCallbacks
from ..controllers.tool_controller import ToolController
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

    # ── Controllers ────────────────────────────────────────────────
    self._approval = ApprovalController(mode="manual")
    self._sessions = SessionController(
      runtime,
      on_sessions_changed=self._on_sessions_updated,
      on_session_loaded=self._on_session_loaded,
      on_error=lambda msg: self.notify(msg, severity="error"),
    )
    self._tools = ToolController(
      runtime,
      self._approval,
      on_notify=lambda msg, sev: self.notify(msg, severity=sev),
      on_model_changed=self._on_model_changed,
      on_approval_toggled=self._on_approval_toggled,
      on_doctor_output=self._on_doctor_output,
    )
    self._turn: TurnController | None = None

  # ── Compose ──────────────────────────────────────────────────────

  def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal(id="main-container"):
      yield SessionPanel(id="sidebar")
      with Vertical(id="chat-container"):
        yield ChatArea(id="chat")
        with Vertical(id="input-wrapper"):
          yield SlashOverlay(id="slash-overlay")
          yield InputArea(id="input")
    yield StatusBar(id="status")
    yield Footer()

  def on_mount(self) -> None:
    # Wire approval callback into the runtime
    self._approval._ask_approval = self._ask_approval_from_thread
    self._runtime._on_approve = self._approval.request
    self._sessions.refresh()
    self._load_custom_commands()
    chat = self.query_one(ChatArea)
    chat.show_welcome()

  # ── Approval bridge ──────────────────────────────────────────────

  def _ask_approval_from_thread(self, req):
    """Bridge worker-thread approval request to a Textual modal dialog."""
    import threading
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

  # ── Turn controller callbacks ────────────────────────────────────

  def _build_turn_callbacks(self) -> TurnCallbacks:
    chat = self.query_one(ChatArea)
    status = self.query_one(StatusBar)

    def on_text(event):
      chat.add_stream_chunk(event.delta, event.turn_id)

    def on_tool_start(event):
      chat.add_tool_call_start(event.tool_name, event.tool_call_id, event.turn_id)

    def on_tool_args(event):
      chat.add_tool_call_args(event.tool_call_id, event.delta, event.turn_id)

    def on_tool_end(event):
      chat.add_tool_call_end(event.tool_call_id, event.result, event.turn_id)
      self._agent_step += 1
      status.set_step_count(self._agent_step)

    def on_finished(event):
      chat.end_stream(event.turn_id)
      status.set_step_count(self._agent_step)

    def on_failed(event):
      chat.cancel_stream()
      chat.add_message(f"Agent error: {event.message}", "assistant")

    return TurnCallbacks(
      on_text=on_text,
      on_tool_start=on_tool_start,
      on_tool_args=on_tool_args,
      on_tool_end=on_tool_end,
      on_finished=on_finished,
      on_failed=on_failed,
    )

  # ── Session callbacks ────────────────────────────────────────────

  def _on_sessions_updated(self, infos):
    panel = self.query_one(SessionPanel)
    panel.set_sessions([
      {
        "id": info.id,
        "title": info.title,
        "updated_at": info.updated_at,
        "message_count": info.message_count,
        "is_current": info.is_current,
      }
      for info in infos
    ])

  def _on_session_loaded(self, session_id, messages):
    chat = self.query_one(ChatArea)
    chat.clear()
    self._agent_step = 0
    status = self.query_one(StatusBar)
    status.set_step_count(0)
    for msg in messages:
      role = msg.get("role", "user")
      content = msg.get("content", "")
      if content and role in ("user", "assistant"):
        chat.add_message(content, role)
    if session_id:
      self.notify(f"Session {session_id[:8]} loaded")

  # ── Tool callbacks ───────────────────────────────────────────────

  def _on_model_changed(self, model_name: str) -> None:
    status = self.query_one(StatusBar)
    status.update_status(model_name=model_name)
    self.notify(f"Model: {model_name}")

  def _on_approval_toggled(self, mode: str) -> None:
    status = self.query_one(StatusBar)
    status.update_status(approval_mode=mode)
    self.notify(f"Approval mode: {mode}")

  def _on_doctor_output(self, summary: str) -> None:
    chat = self.query_one(ChatArea)
    chat.add_message(f"**Doctor Results:**\n```\n{summary}\n```", "assistant")

  # ── Slash overlay integration ────────────────────────────────────

  def on_input_area_open_slash_overlay(self, event: InputArea.OpenSlashOverlay) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.show_overlay(event.query)
    input_area = self.query_one(InputArea)
    input_area.activate_slash_overlay()

  def on_input_area_update_slash_filter(self, event: InputArea.UpdateSlashFilter) -> None:
    overlay = self.query_one(SlashOverlay)
    if overlay.visible:
      overlay.update_filter(event.query)

  def on_input_area_navigate_slash(self, event: InputArea.NavigateSlash) -> None:
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
        result = self._tools.dispatch_slash(cmd.handler)
        if result == "open_model_picker":
          self._open_model_picker()
        elif result == "show_help":
          self._show_help()
        elif result == "clear_chat":
          self.action_clear_chat()
        elif result == "list_sessions":
          self._list_sessions()
        elif result == "cycle_theme":
          self._cycle_theme()
        elif result == "toggle_sidebar":
          self._toggle_sidebar()

  # ── Main send flow ───────────────────────────────────────────────

  def on_input_area_user_message(self, event: InputArea.UserMessage) -> None:
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
    chat = self.query_one(ChatArea)
    input_area = self.query_one(InputArea)
    status = self.query_one(StatusBar)
    try:
      import asyncio
      loop = asyncio.get_running_loop()
      callbacks = self._build_turn_callbacks()
      self._turn = TurnController(self._runtime, callbacks, loop)
      await self._turn.start(user_input)
    except Exception as exc:
      _log.error("Streaming failed: %s", exc)
      chat.add_message(f"Streaming failed: {exc}", "assistant")
    finally:
      self._is_streaming = False
      self._turn = None
      input_area.show_send()
      input_area.focus()
      status.set_streaming_hint(False)

  # ── Cancel ───────────────────────────────────────────────────────

  def _handle_escape(self) -> None:
    overlay = self.query_one(SlashOverlay)
    if overlay.visible:
      overlay.hide_overlay()
      input_area = self.query_one(InputArea)
      input_area.input.read_only = False
      input_area.focus()
      return

    if self._is_streaming and self._turn:
      self._turn.cancel()
      chat = self.query_one(ChatArea)
      chat.cancel_stream()
      status = self.query_one(StatusBar)
      status.set_streaming_hint(False)
      self._is_streaming = False
      self.notify("Cancelled")

  def on_key(self, event) -> None:
    if event.key == "escape":
      self._handle_escape()
      event.prevent_default()

  # ── Session events ───────────────────────────────────────────────

  def on_session_panel_session_selected(self, event: SessionPanel.SessionSelected) -> None:
    self._sessions.load(event.session_id)

  def on_session_panel_new_session(self, event: SessionPanel.NewSession) -> None:
    self._sessions.create_new()

  def on_session_panel_refresh_sessions(self, event: SessionPanel.RefreshSessions) -> None:
    self._sessions.refresh()

  # ── Custom commands ──────────────────────────────────────────────

  def _load_custom_commands(self) -> None:
    try:
      overlay = self.query_one(SlashOverlay)
      project = load_project_commands(self._runtime._workspace_root)
      user = load_user_commands()
      overlay.add_commands(project + user)
    except Exception as exc:
      _log.error("Failed to load custom commands: %s", exc)

  # ── UI helpers ───────────────────────────────────────────────────

  def _toggle_sidebar(self) -> None:
    sidebar = self.query_one("#sidebar")
    sidebar.display = not sidebar.display
    self.notify("Sidebar " + ("shown" if sidebar.display else "hidden"))

  def _open_model_picker(self) -> None:
    self.action_model_picker()

  def action_model_picker(self) -> None:
    async def _run() -> None:
      current = self._tools.current_model
      models = self._tools.list_models()
      chosen = await self.app.push_screen_wait(ModelPicker(models, current))
      if chosen and chosen != current:
        self._tools.set_model(chosen)
      input_area = self.query_one(InputArea)
      input_area.focus()
    self.run_worker(_run())

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

  def _list_sessions(self) -> None:
    sidebar = self.query_one("#sidebar")
    if not sidebar.display:
      sidebar.display = True
    self._sessions.refresh()
    self.notify("Sessions refreshed")

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
    self._tools.compact_context()

  def action_quit(self) -> None:
    self.app.exit()
