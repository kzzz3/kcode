"""Main TUI screen — layout, streaming, tool approval, session management."""
from __future__ import annotations



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


class MainScreen(Screen):
  """Primary screen: chat + input + sidebar + status bar."""

  CSS = """
  #main-container {
    width: 100%;
    height: 1fr;
  }

  #chat-container {
    width: 1fr;
    height: 100%;
  }

  #sidebar {
    width: 30;
    min-width: 20;
    height: 100%;
  }
  """

  BINDINGS = [
    ("ctrl+n", "new_session", "New Session"),
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
        yield InputArea()
      with Vertical(id="sidebar"):
        yield SessionPanel()
    yield StatusBar()
    yield Footer()

  def on_mount(self) -> None:
    """Initialize status bar with model info and load sessions."""
    status = self.query_one(StatusBar)
    status.update_status(
      model_name=self._runtime._model_name,
      state="IDLE",
    )
    self._refresh_sessions()

  # --- Input handling ---

  def on_input_area_submitted(self, event: InputArea.Submitted) -> None:
    """Handle user message submission."""
    if self._is_streaming:
      self.notify("Agent is busy — wait for it to finish.", severity="warning")
      return

    chat = self.query_one(ChatArea)
    chat.add_message(event.value, "user")
    self.run_worker(self._stream_worker(event.value), exclusive=True)

  # --- Streaming (runs in worker thread) ---

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
          pass  # Args accumulated by runtime; not displayed raw

        elif chunk.type == ChunkType.TOOL_CALL_END:
          # Only show tool result when delta is non-empty (i.e. after execution)
          if chunk.delta:
            chat.add_tool_call_end(
              tool_name=chunk.tool_name or "tool",
              tool_call_id=chunk.tool_call_id,
              result=chunk.delta,
              is_error=chunk.delta.startswith("Tool error"),
            )
            # Restart stream buffer for next model turn
            chat.start_stream("assistant")
            status.update_status(state="THINKING")

        elif chunk.type == ChunkType.USAGE:
          usage = chunk.usage
          prompt_tok = usage.get("prompt_tokens") or 0
          comp_tok = usage.get("completion_tokens") or 0
          status.update_status(tokens=prompt_tok + comp_tok)

        elif chunk.type == ChunkType.DONE:
          pass  # Handled by AgentSnapshot

    except Exception as exc:
      chat.add_message(f"Error: {exc}", "system")
      status.update_status(state="ERROR")
    finally:
      self._is_streaming = False

  # --- Approval gate ---

  async def _request_approval(self, tool_name: str, tool_args: dict, safety_class: str) -> bool:
    """Show modal approval dialog and return True if approved."""
    dialog = ApprovalDialog(tool_name, tool_args, safety_class)
    result = await self.app.push_screen_wait(dialog)
    return bool(result)

  # --- Session management ---

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
      pass  # Non-critical

  def on_session_panel_new_session(self, event: SessionPanel.NewSession) -> None:
    """Handle new session request."""
    self._runtime._bootstrap_messages()
    chat = self.query_one(ChatArea)
    chat.clear()
    chat.add_message("New session started.", "system")
    self.notify("New session created")

  def on_session_panel_session_selected(self, event: SessionPanel.SessionSelected) -> None:
    """Handle session selection — reload conversation history."""
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

  # --- Actions ---

  def action_new_session(self) -> None:
    self.on_session_panel_new_session(SessionPanel.NewSession())

  def action_quit(self) -> None:
    self.app.exit()

