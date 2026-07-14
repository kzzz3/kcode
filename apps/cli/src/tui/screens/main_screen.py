"""Main TUI screen -- thin orchestrator wired to controllers.

Uses external theme.tcss + workbench.tcss for styling.
Responsive layout: narrow (<90), medium (90-139), wide (>=140).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

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

# Responsive breakpoints (columns)
_NARROW_MAX = 89
_MEDIUM_MAX = 139


class WorkspaceBar(Static):
  """Top bar showing repo, branch, model and session info."""

  def __init__(self, workspace: Path, model: str = "", **kwargs) -> None:
    super().__init__(**kwargs)
    self._workspace = workspace
    self._model = model
    self._session_title = ""

  def set_model(self, model: str) -> None:
    self._model = model
    self._refresh()

  def set_session(self, title: str) -> None:
    self._session_title = title
    self._refresh()

  def _refresh(self) -> None:
    parts = [f"  {self._workspace.name}"]
    if self._model:
      parts.append(f"  {self._model}")
    if self._session_title:
      parts.append(f"  {self._session_title}")
    self.update("".join(parts))


class MainScreen(Screen):
  """Primary screen: workspace-bar + body + composer + status."""

  CSS_PATH = Path(__file__).parent.parent / "styles" / "kcode.tcss"

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
    yield WorkspaceBar(
      self._runtime._workspace_root,
      model=self._runtime._model_name,
      id="workspace-bar",
    )
    with Horizontal(id="main-body"):
      yield ChatArea(id="chat")
      yield SessionPanel(id="activity-rail")
    with Vertical(id="composer-dock"):
      yield SlashOverlay(id="slash-overlay")
      yield InputArea(id="input")
    yield StatusBar(id="status")

  def on_mount(self) -> None:
    self._approval._ask_approval = self._ask_approval_from_thread
    self._runtime._on_approve = self._approval.request
    self._sessions.refresh()
    self._load_custom_commands()
    self.query_one(ChatArea).show_welcome(
        workspace=str(getattr(self._runtime, '_workspace_root', '')),
        model=getattr(self._runtime, '_model', ''),
        approval=getattr(self._approval, 'mode', 'manual'),
      )
    self._apply_responsive_class()

  # ── Responsive layout ────────────────────────────────────────────

  def on_resize(self, event) -> None:
    self._apply_responsive_class()

  def _apply_responsive_class(self) -> None:
    w = self.size.width
    new_cls = (
      "narrow" if w <= _NARROW_MAX
      else "medium" if w <= _MEDIUM_MAX
      else "wide"
    )
    for cls in ("narrow", "medium", "wide"):
      if cls == new_cls:
        self.add_class(cls)
      else:
        self.remove_class(cls)

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
      chat.add_tool_call_args(ev.tool_call_id, ev.arguments)

    def on_tool_result(ev):
      chat.add_tool_call_result(ev.tool_call_id, ev.result, ev.duration_ms)

    def on_token_count(ev):
      status.set_token_info(ev.prompt_tokens, ev.completion_tokens, ev.total_cost)

    def on_context_usage(ev):
      status.set_context_usage(ev.used, ev.budget)

    def on_turn_complete(ev):
      self._agent_step += 1
      status.set_step_count(self._agent_step)
      if ev.model:
        status.set_model(ev.model)

    return TurnCallbacks(
      on_text_delta=on_text,
      on_tool_start=on_tool_start,
      on_tool_args_delta=on_tool_args,
      on_tool_result=on_tool_result,
      on_token_count=on_token_count,
      on_context_usage=on_context_usage,
      on_turn_complete=on_turn_complete,
    )

  # ── Message routing ──────────────────────────────────────────────

  def on_input_area_submit(self, event: InputArea.Submit) -> None:
    text = event.value.strip()
    if not text:
      return
    if text.startswith("/"):
      self._handle_slash(text)
      return
    self._send_to_agent(text)

  def on_input_area_slash_filter(self, event: InputArea.SlashFilter) -> None:
    self.query_one(SlashOverlay).update_filter(event.filter_text)

  def on_input_area_slash_select(self, event: InputArea.SlashSelect) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.select_current()

  def on_slash_overlay_command_selected(self, event: SlashOverlay.CommandSelected) -> None:
    self._dismiss_overlay()
    handler = event.handler
    if handler in _SLASH_ACTIONS:
      action = _SLASH_ACTIONS[handler]
      getattr(self, f"_do_{action}")()
    else:
      result = self._tools.dispatch_slash(handler)
      if result:
        self.query_one(ChatArea).add_message(result, "system")

  def _handle_slash(self, text: str) -> None:
    cmd = text.split()[0].lstrip("/").lower()
    if cmd in _SLASH_ACTIONS:
      self._dismiss_overlay()
      getattr(self, f"_do_{_SLASH_ACTIONS[cmd]}")()
    else:
      self._send_to_agent(text)

  def _dismiss_overlay(self) -> None:
    overlay = self.query_one(SlashOverlay)
    overlay.hide_overlay()
    self.query_one(InputArea).focus()

  # ── Agent interaction ────────────────────────────────────────────

  def _send_to_agent(self, text: str) -> None:
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
      overlay.set_custom_commands(
        load_project_commands(self._runtime._workspace_root) + load_user_commands()
      )
    except Exception as exc:
      _log.error("Failed to load custom commands: %s", exc)

  # ── Slash action handlers ────────────────────────────────────────

  def _do_open_model_picker(self) -> None:
    async def _run() -> None:
      models = self._tools.list_models()
      chosen = await self.app.push_screen_wait(
        ModelPicker(models, self._tools.current_model)
      )
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
    sidebar = self.query_one("#activity-rail")
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
    sidebar = self.query_one("#activity-rail")
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

  def action_clear_chat(self) -> None:
    chat = self.query_one(ChatArea)
    chat.clear()
    self._agent_step = 0
    self.query_one(StatusBar).set_step_count(0)

  def action_quit(self) -> None:
    self.app.exit()

  # ── Controller callbacks ─────────────────────────────────────────

  def _on_sessions_updated(self, infos: list | None = None) -> None:
    sessions = infos if infos is not None else self._sessions.list_sessions()
    self.query_one(SessionPanel).refresh_list(sessions)

  def _on_session_loaded(self, title: str) -> None:
    self.query_one(ChatArea).clear()
    self._agent_step = 0
    self.query_one(StatusBar).set_step_count(0)
    ws_bar = self.query_one(WorkspaceBar)
    ws_bar.set_session(title)
    self.notify(f"Loaded: {title}")

  def _on_model_changed(self, model: str) -> None:
    self.query_one(StatusBar).set_model(model)
    ws_bar = self.query_one(WorkspaceBar)
    ws_bar.set_model(model)
    self.notify(f"Model: {model}")

  def _on_approval_toggled(self, mode: str) -> None:
    self._approval.set_mode(mode)
    self.query_one(StatusBar).set_approval_mode(mode)
    self.notify(f"Approval: {mode}")

  def _on_doctor_output(self, output: str) -> None:
    self.query_one(ChatArea).add_message(output, "system")
