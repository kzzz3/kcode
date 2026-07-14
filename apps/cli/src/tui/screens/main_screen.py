"""Main TUI screen -- thin orchestrator wired to controllers."""
from __future__ import annotations

import logging
import threading

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

# Slash handler -> action mapping for UI-only actions
_SLASH_ACTIONS: dict[str, str] = {
  "model_picker": "open_model_picker",
  "help": "show_help",
  "clear": "clear_chat",
  "sessions": "list_sessions",
  "theme": "cycle_theme",
  "sidebar": "toggle_sidebar",
}


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
    self._approval._ask_approval = self._ask_approval_from_thread
    self._runtime._on_approve = self._approval.request
    self._sessions.refresh()
    self._load_custom_commands()
    self.query_one(ChatArea).show_welcome()

  # ── Approval bridge ──────────────────────────────────────────────

  def _ask_approval_from_thread(self, req):
    """Bridge worker-thread approval request to a Textual modal dialog."""
    result_holder: list[bool] = []
    ready = threading.Event()

    def _show() -> None:
      async def _inner() -> None:
        approved = await self.app.push_screen_wait(
          ApprovalDialog(req.tool_name, req.arguments, req.safety_class)
        )
        result_holder.append(approved)
        ready.set()
      self.run_worker(_inner())

    self.app.call_from_thread(_show)
    ready.wait(timeout=120)
    return result_holder[0] if result_holder else False

  # ── Turn callbacks ───────────────────────────────────────────────

  def _build_turn_callbacks(self) -> TurnCallbacks:
    chat = self.query_one(ChatArea)
    status = self.query_one(StatusBar)

    def on_text(ev):
      chat.add_stream_chunk(ev.delta, ev.turn_id)

    def on_tool_start(ev):
      chat.add_tool_call_start(ev.tool_name, ev.tool_call_id, ev.turn_id)

    def on_tool_args(ev):
      chat.add_tool_call_args(ev.tool_call_id, ev.delta, ev.turn_id)

    def on_tool_end(ev):
      chat.add_tool_call_end(ev.tool_call_id, ev.result, ev.turn_id)
      self._agent_step += 1
      status.set_step_count(self._agent_step)

    def on_finished(ev):
      chat.end_stream(ev.turn_id)
      status.set_step_count(self._agent_step)

    def on_failed(ev):
      chat.cancel_stream()
      chat.add_message(f"Agent error: {ev.message}", "assistant")

    return TurnCallbacks(
      on_text=on_text, on_tool_start=on_tool_start,
      on_tool_args=on_tool_args, on_tool_end=on_tool_end,
      on_finished=on_finished, on_failed=on_failed,
    )

  # ── Controller callbacks ─────────────────────────────────────────

  def _on_sessions_updated(self, infos):
    panel = self.query_one(SessionPanel)
    panel.set_sessions([
      {"id": i.id, "title": i.title, "updated_at": i.updated_at,
       "message_count": i.message_count, "is_current": i.is_current}
      for i in infos
    ])

  def _on_session_loaded(self, session_id, messages):
    chat = self.query_one(ChatArea)
    chat.clear()
    self._agent_step = 0
    self.query_one(StatusBar).set_step_count(0)
    for msg in messages:
      role, content = msg.get("role", "user"), msg.get("content", "")
      if content and role in ("user", "assistant"):
        chat.add_message(content, role)
    if session_id:
      self.notify(f"Session {session_id[:8]} loaded")

  def _on_model_changed(self, model_name: str) -> None:
    self.query_one(StatusBar).update_status(model_name=model_name)
    self.notify(f"Model: {model_name}")

  def _on_approval_toggled(self, mode: str) -> None:
    self.query_one(StatusBar).update_status(approval_mode=mode)
    self.notify(f"Approval mode: {mode}")

  def _on_doctor_output(self, summary: str) -> None:
    self.query_one(ChatArea).add_message(
      f"**Doctor Results:**\n```\n{summary}\n```", "assistant"
    )

  # ── Slash overlay events ─────────────────────────────────────────

  def on_input_area_open_slash_overlay(self, event: InputArea.OpenSlashOverlay) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.show_overlay(event.query)
    self.query_one(InputArea).activate_slash_overlay()

  def on_input_area_update_slash_filter(self, event: InputArea.UpdateSlashFilter) -> None:
    overlay = self.query_one(SlashOverlay)
    if overlay.visible:
      overlay.update_filter(event.query)

  def on_input_area_navigate_slash(self, event: InputArea.NavigateSlash) -> None:
    overlay = self.query_one(SlashOverlay)
    (overlay.select_previous if event.direction == "up" else overlay.select_next)()

  def on_input_area_select_slash(self, event: InputArea.SelectSlash) -> None:
    self.query_one(SlashOverlay).apply_selected()

  def on_input_area_dismiss_slash(self, event: InputArea.DismissSlash) -> None:
    self._dismiss_overlay()

  def on_slash_overlay_slash_command(self, event: SlashOverlay.SlashCommand) -> None:
    self._dismiss_overlay()
    cmd = event.command
    if not cmd.handler:
      return
    if cmd.requires_input:
      self.query_one(InputArea).focus()
      return
    action = self._tools.dispatch_slash(cmd.handler)
    if action:
      getattr(self, f"_do_{action}", lambda: None)()

  def _dismiss_overlay(self) -> None:
    self.query_one(SlashOverlay).hide_overlay()
    self.query_one(InputArea).input.read_only = False
    self.query_one(InputArea).focus()

  # ── Main send flow ───────────────────────────────────────────────

  def on_input_area_user_message(self, event: InputArea.UserMessage) -> None:
    text = event.text.strip()
    if not text:
      return
    chat, input_area, status = self.query_one(ChatArea), self.query_one(InputArea), self.query_one(StatusBar)
    chat.add_message(text, "user")
    input_area.clear()
    input_area.show_thinking()
    self._is_streaming = True
    status.set_streaming_hint(True)
    status.set_step_count(self._agent_step)
    self.run_worker(self._stream_agent(text))

  async def _stream_agent(self, user_input: str) -> None:
    chat, input_area, status = self.query_one(ChatArea), self.query_one(InputArea), self.query_one(StatusBar)
    try:
      import asyncio
      loop = asyncio.get_running_loop()
      self._turn = TurnController(self._runtime, self._build_turn_callbacks(), loop)
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
    if self.query_one(SlashOverlay).visible:
      self._dismiss_overlay()
      return
    if self._is_streaming and self._turn:
      self._turn.cancel()
      self.query_one(ChatArea).cancel_stream()
      self.query_one(StatusBar).set_streaming_hint(False)
      self._is_streaming = False
      self.notify("Cancelled")

  def on_key(self, event) -> None:
    if event.key == "escape":
      self._handle_escape()
      event.prevent_default()

  # ── Session panel events ─────────────────────────────────────────

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
      overlay.add_commands(load_project_commands(self._runtime._workspace_root) + load_user_commands())
    except Exception as exc:
      _log.error("Failed to load custom commands: %s", exc)

  # ── Slash action handlers ────────────────────────────────────────

  def _do_open_model_picker(self) -> None:
    async def _run() -> None:
      models = self._tools.list_models()
      chosen = await self.app.push_screen_wait(ModelPicker(models, self._tools.current_model))
      if chosen and chosen != self._tools.current_model:
        self._tools.set_model(chosen)
      self.query_one(InputArea).focus()
    self.run_worker(_run())

  def _do_show_help(self) -> None:
    async def _show() -> None:
      await self.app.push_screen_wait(HelpScreen())
      self.query_one(InputArea).focus()
    self.run_worker(_show())

  def _do_list_sessions(self) -> None:
    sidebar = self.query_one("#sidebar")
    if not sidebar.display:
      sidebar.display = True
    self._sessions.refresh()
    self.notify("Sessions refreshed")

  def _do_cycle_theme(self) -> None:
    themes = self.app.available_themes
    names = [t.name for t in themes] if themes else []
    next_theme = self._tools.cycle_theme(names, self.app.theme or "textual-dark")
    if next_theme:
      self.app.theme = next_theme
      self.notify(f"Theme: {next_theme}")
    else:
      self.notify("No themes available")

  def _do_toggle_sidebar(self) -> None:
    sidebar = self.query_one("#sidebar")
    sidebar.display = not sidebar.display
    self.notify("Sidebar " + ("shown" if sidebar.display else "hidden"))

  # ── Actions (keyboard bindings) ──────────────────────────────────

  def action_new_session(self) -> None:
    self._agent_step = 0
    self.query_one(StatusBar).set_step_count(0)
    self._sessions.create_new()

  def action_toggle_sidebar(self) -> None:
    self._do_toggle_sidebar()

  def action_help(self) -> None:
    self._do_show_help()

  def action_model_picker(self) -> None:
    self._do_open_model_picker()

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
