"""CLI agent runtime with durable sessions, tool dispatch, and streaming."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from packages.core.src.runtime.contracts import AgentRuntime, AgentSnapshot, AgentState
from packages.core.src.runtime.events import Event, EventBus
from packages.core.src.runtime.session import SessionStore, SessionRecord, ToolRunRecord
from packages.core.src.models.interfaces import (
  ChunkType,
  Message,
  ModelClient,
  StreamAccumulator,
  StreamChunk,
  ToolSpec,
)
from packages.core.src.tools.contracts import ToolOutput, ToolRegistry
from packages.core.src.context.tokens import TokenCounter, ContextBudget


@dataclass(frozen=True)
class AgentLoopConfig:
  max_steps: int = 8
  approval_required_classes: tuple[str, ...] = ("write", "system", "network")
  approval_mode: str = "auto"
  reuse_session_max_age_seconds: float = 86400.0
  context_reserve_tokens: int = 4096
  compaction_threshold: float = 0.80


ApprovalCallback = Callable[[str, str, dict[str, Any]], bool]


class CliAgentRuntime(AgentRuntime):
  """Production-oriented CLI runtime backed by a model client and tool registry."""

  def __init__(
    self,
    *,
    workspace_root: Path,
    model_client: ModelClient,
    model_name: str,
    tool_registry: ToolRegistry,
    session_store: SessionStore,
    bus: EventBus | None = None,
    config: AgentLoopConfig | None = None,
    on_approve: ApprovalCallback | None = None,
    system_prompt: str | None = None,
    session: SessionRecord | None = None,
    initial_messages: list[Message] | None = None,
  ) -> None:
    super().__init__(bus=bus)
    self._workspace_root = workspace_root.resolve()
    self._client = model_client
    self._model_name = model_name
    self._tools = tool_registry
    self._session_store = session_store
    self._config = config or AgentLoopConfig()
    self._on_approve = on_approve
    self._system_prompt = system_prompt or self._default_system_prompt()

    # Context budget tracking
    self._token_counter = TokenCounter(model=model_name)
    self._context_budget = ContextBudget(
      model=model_name,
      reserve_tokens=self._config.context_reserve_tokens,
    )

    if session is not None:
      self._session = session
      self._replay_messages(initial_messages or [])
    else:
      self._session = session_store.create_session(
        workspace_root=self._workspace_root, title="cli-session",
      )
      self._bootstrap_messages()

  def _default_system_prompt(self) -> str:
    ws = str(self._workspace_root)
    return (
      "You are KCode, a precise coding agent.\n"
      "Use tools when they materially improve accuracy.\n"
      "Prefer minimal, reversible changes.\n"
      "Return concise answers unless the user requests depth.\n"
      "\n"
      f"WORKSPACE: {ws}\n"
      "You MUST always use this exact workspace_root path when calling any tool "
      "that requires a workspace_root parameter. Never invent or guess a different path.\n"
      "\n"
      "When creating files, use paths relative to the workspace root. For example, "
      "if the workspace is 'C:\\project' and you want to create 'src/main.py', "
      "call create_file with workspace_root='C:\\project' and path='src/main.py'.\n"
    )

  def _bootstrap_messages(self) -> None:
    self._messages: list[Message] = []
    self._snapshot_messages: list[dict[str, Any]] = []
    self._tool_runs: list[dict[str, Any]] = []
    self._step_index = 0
    self._state = AgentState.IDLE
    if self._system_prompt:
      self._append_message(Message(role="system", content=self._system_prompt), persist=False)

  def _replay_messages(self, initial_messages: list[Message]) -> None:
    self._messages = []
    self._snapshot_messages = []
    self._tool_runs = []
    self._step_index = 0
    self._state = AgentState.IDLE
    for message in initial_messages:
      self._append_message(message, persist=False)

  def get_snapshot(self) -> AgentSnapshot:
    return AgentSnapshot(
      state=self._state,
      step_index=self._step_index,
      messages=list(self._snapshot_messages),
      tool_runs=list(self._tool_runs),
      metadata={
        "workspace_root": str(self._workspace_root),
        "session_id": self._session.id,
        "model": self._model_name,
        "token_count": self._token_counter.count_messages(self._messages),
        "context_utilization": self._context_budget.utilization,
      },
    )

  def _emit(self, name: str, payload: dict[str, Any] | None = None) -> None:
    self.bus.emit(Event(name=name, payload=payload or {}))

  def _append_message(self, message: Message, *, persist: bool = True) -> None:
    self._messages.append(message)
    serialized: dict[str, Any] = {"role": message.role}
    if message.content is not None:
      serialized["content"] = message.content
    if message.tool_calls:
      serialized["tool_calls"] = message.tool_calls
    if message.tool_call_id:
      serialized["tool_call_id"] = message.tool_call_id
    self._snapshot_messages.append(serialized)
    if persist:
      self._session_store.append_message(
        self._session.id,
        message.role,
        message.content,
        tool_calls=message.tool_calls,
        tool_call_id=message.tool_call_id,
      )
    self._update_context()

  def _update_context(self) -> None:
    count = self._token_counter.count_messages(self._messages)
    self._context_budget.update(count)

  def _maybe_compact(self) -> None:
    if self._context_budget.utilization < self._config.compaction_threshold:
      return
    if len(self._messages) <= 3:
      return
    summary_parts: list[str] = []
    for msg in self._messages[1:-2]:
      if msg.role == "user" and msg.content:
        summary_parts.append(f"User: {msg.content[:120]}")
      elif msg.role == "assistant" and msg.content:
        summary_parts.append(f"Assistant: {msg.content[:120]}")
      elif msg.role == "tool" and msg.content:
        summary_parts.append(f"Tool result: {msg.content[:80]}")
    if not summary_parts:
      return
    summary_text = "[Previous conversation summary]\n" + "\n".join(summary_parts[-20:])
    self._messages = [self._messages[0], Message(role="user", content=summary_text), self._messages[-1]]
    self._update_context()

  def _approve(self, tool_name: str, safety_class: str, payload: dict[str, Any]) -> bool:
    if self._on_approve is not None:
      return self._on_approve(tool_name, safety_class, payload)
    return self._config.approval_mode == "auto"

  def _tool_specs(self) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for meta in self._tools.list_tools():
      specs.append(ToolSpec(
        name=meta.name,
        description=meta.description,
        parameters=meta.parameter_schema,
      ))
    return specs

  def _run_tool(self, tool_name: str, payload: dict[str, Any]) -> tuple[ToolOutput, ToolRunRecord]:
    tool = self._tools.get(tool_name)
    meta = tool.meta if tool else None

    # --- Unknown tool: record start + immediate failure ---
    if meta is None:
      run = self._session_store.record_tool_start(
        self._session.id, tool_name, payload,
      )
      output = ToolOutput(ok=False, message=f"Unknown tool: {tool_name}")
      self._session_store.record_tool_completion(
        run.id,
        output={"ok": False, "message": output.message},
        status="failed",
      )
      return output, run

    # --- Approval gate ---
    if meta.safety_class in self._config.approval_required_classes:
      if not self._approve(tool_name, meta.safety_class, payload):
        run = self._session_store.record_tool_start(
          self._session.id, tool_name, payload,
        )
        output = ToolOutput(ok=False, message="Tool execution denied by user.")
        self._session_store.record_tool_completion(
          run.id,
          output={"ok": False, "message": output.message},
          status="failed",
        )
        return output, run

    # --- Normal execution ---
    self._state = AgentState.TOOL_RUNNING
    self._emit("tool.start", {"tool_name": tool_name})

    run = self._session_store.record_tool_start(
      self._session.id, tool_name, payload,
    )
    assert tool is not None  # guaranteed by meta check above
    output = tool.run(payload)

    self._session_store.record_tool_completion(
      run.id,
      output={"ok": output.ok, "message": output.message},
      status="completed" if output.ok else "failed",
    )
    self._emit("tool.end", {"tool_name": tool_name, "success": output.ok})
    return output, run

  def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
    """Execute a batch of tool calls and append results to message history."""
    for tool_call in tool_calls:
      content = self._process_single_tool_call(tool_call)
      self._append_message(
        Message(role="tool", content=content, tool_call_id=tool_call.get("id")),
        persist=True,
      )

  def _process_single_tool_call(self, tool_call: dict[str, Any]) -> str:
    """Parse, execute, and record a single tool call. Returns the result content."""
    fn = tool_call.get("function") or {}
    tool_name = fn.get("name") or tool_call.get("name") or "unknown"
    raw_args = fn.get("arguments") or tool_call.get("arguments") or "{}"
    if isinstance(raw_args, str):
      try:
        payload = json.loads(raw_args)
      except json.JSONDecodeError:
        payload = {"raw": raw_args}
    else:
      payload = dict(raw_args)
    self._tool_runs.append({
      "tool_name": tool_name, "input": payload, "step_index": self._step_index,
    })
    try:
      output, _ = self._run_tool(tool_name, payload)
      content = output.message
    except Exception as exc:  # noqa: BLE001
      content = f"Tool error: {exc}"
      self._tool_runs.append({
        "tool_name": tool_name, "input": payload, "error": str(exc),
        "step_index": self._step_index,
      })
    return content

  def step(self, user_input: str) -> AgentSnapshot:
    """Execute a single user turn - non-streaming variant."""
    self._state = AgentState.THINKING
    self._step_index += 1
    self._emit("agent.step", {"index": self._step_index})
    self._append_message(Message(role="user", content=user_input))
    self._maybe_compact()

    for _ in range(self._config.max_steps):
      response = self._client.complete(
        model=self._model_name,
        messages=self._messages,
        tools=self._tool_specs(),
      )
      self._append_message(response.message)
      if response.usage:
        self._emit("usage", response.usage)

      if response.message.tool_calls:
        self._execute_tool_calls(response.message.tool_calls)
        continue

      self._state = AgentState.FINISHED
      return self.get_snapshot()

    self._state = AgentState.FAILED
    self._append_message(Message(role="assistant", content="Agent stopped after reaching max steps."))
    return self.get_snapshot()

  def step_stream(self, user_input: str) -> Iterator[StreamChunk | AgentSnapshot]:
    """Execute one user turn with streaming model output.

    Yields StreamChunk objects as they arrive from the model. When tool calls
    are detected, executes them and emit event-like chunks. Yields the final
    AgentSnapshot when the turn is complete.

    The caller should check isinstance(item, AgentSnapshot) to detect completion.
    """
    self._state = AgentState.THINKING
    self._step_index += 1
    self._emit("agent.step", {"index": self._step_index})
    self._append_message(Message(role="user", content=user_input))
    self._maybe_compact()

    for _ in range(self._config.max_steps):
      accumulator = StreamAccumulator()

      for chunk in self._client.complete_stream(
        model=self._model_name,
        messages=self._messages,
        tools=self._tool_specs(),
      ):
        accumulator.feed(chunk)

        # Forward non-terminal chunks to caller
        if chunk.type in (ChunkType.TEXT, ChunkType.USAGE):
          yield chunk
        elif chunk.type == ChunkType.TOOL_CALL_START:
          self._emit("tool.detected", {"tool_call_id": chunk.tool_call_id, "tool_name": chunk.tool_name})
          yield chunk
        elif chunk.type == ChunkType.TOOL_CALL_ARGS:
          yield chunk
        elif chunk.type == ChunkType.TOOL_CALL_END:
          yield chunk
        elif chunk.type == ChunkType.DONE:
          # Build the complete message and append to history
          assistant = accumulator.to_message()
          self._append_message(assistant)

          # Record usage if available
          if accumulator.usage:
            self._emit("usage", accumulator.usage)

          if assistant.tool_calls:
            # Execute tools using the shared helper
            for tool_call in assistant.tool_calls:
              content = self._process_single_tool_call(tool_call)
              # Yield tool result event
              yield StreamChunk(
                type=ChunkType.TOOL_CALL_END,
                tool_call_id=tool_call.get("id", ""),
                delta=content,
              )
              self._append_message(
                Message(role="tool", content=content, tool_call_id=tool_call.get("id")),
                persist=True,
              )
            # Continue the loop for another model turn after tool execution
            break
          else:
            # No tool calls - turn is complete
            self._state = AgentState.FINISHED
            yield self.get_snapshot()
            return

    # Exhausted max steps
    self._state = AgentState.FAILED
    self._append_message(Message(role="assistant", content="Agent stopped after reaching max steps."))
    yield self.get_snapshot()


  # ─── Public session management (for TUI and external callers) ──────

  @property
  def session(self) -> SessionRecord:
    """Return the current session record."""
    return self._session

  @property
  def session_store(self) -> SessionStore:
    """Return the session store."""
    return self._session_store

  def new_session(self) -> SessionRecord:
    """Create a fresh session and reset internal state."""
    self._session = self._session_store.create_session(
      workspace_root=self._workspace_root, title="tui-session",
    )
    self._bootstrap_messages()
    return self._session

  def load_session(self, session_id: str) -> SessionRecord | None:
    """Load an existing session by id. Returns None if not found."""
    session = self._session_store.get_session(session_id)
    if session is None:
      return None
    self._session = session
    # Replay stored messages into runtime
    stored = self._session_store.get_messages(session_id)
    self._messages = []
    self._snapshot_messages = []
    self._tool_runs = []
    self._step_index = 0
    self._state = AgentState.IDLE
    # Re-bootstrap system prompt
    if self._system_prompt:
      self._append_message(Message(role="system", content=self._system_prompt), persist=False)
    for mr in stored:
      msg = Message(
        role=mr.role,
        content=mr.content,
        tool_calls=mr.tool_calls,
        tool_call_id=mr.tool_call_id,
      )
      self._append_message(msg, persist=False)
    return session

  def compact(self) -> bool:
    """Manually trigger context compaction. Returns True if compacted."""
    before = len(self._messages)
    self._maybe_compact()
    return len(self._messages) < before
