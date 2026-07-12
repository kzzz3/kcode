from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from packages.core.src.models.interfaces import Message, ModelClient, ModelResponse, ToolSpec
from packages.core.src.runtime.events import EventBus
from packages.core.src.runtime.session import SessionStore
from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.core.agent_runtime import AgentLoopConfig, AgentState, CliAgentRuntime
from apps.cli.src.tools.builtin_readonly import register_readonly_tools


class StubModel(ModelClient):
  def __init__(self, responses: list[Message]) -> None:
    self._responses = list(responses)
    self._calls: list[list[Message]] = []

  def complete(self, *, model: str, messages: list[Message], tools: Optional[Iterable[ToolSpec]] = None, temperature: Optional[float] = None, stop: Optional[list[str]] = None) -> ModelResponse:
    self._calls.append(list(messages))
    return ModelResponse(message=self._responses.pop(0), usage={"prompt_tokens": 0, "completion_tokens": 0})


def test_runtime_finalizes_text_reply(tmp_path: Path) -> None:
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  client = StubModel([Message(role="assistant", content="done")])
  runtime = CliAgentRuntime(workspace_root=tmp_path, model_client=client, model_name="stub", tool_registry=registry, session_store=store, bus=EventBus())
  snapshot = runtime.step("hi")
  assert snapshot.state.value == "finished"
  assert snapshot.messages[-1]["content"] == "done"
  assert len(store.get_messages(snapshot.metadata["session_id"])) >= 2


def test_runtime_executes_tool_loop(tmp_path: Path) -> None:
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  file = tmp_path / "a.txt"
  file.write_text("hello", encoding="utf-8")
  tool_call = {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": {"workspace_root": str(tmp_path), "path": str(file)}}}
  client = StubModel([Message(role="assistant", tool_calls=[tool_call]), Message(role="assistant", content="read ok")])
  runtime = CliAgentRuntime(workspace_root=tmp_path, model_client=client, model_name="stub", tool_registry=registry, session_store=store, bus=EventBus(), config=AgentLoopConfig(max_steps=4))
  snapshot = runtime.step("read file")
  assert snapshot.state.value == "finished"
  assert snapshot.messages[-1]["content"] == "read ok"
  assert len(snapshot.tool_runs) >= 1


def test_runtime_respects_approval_gate(tmp_path: Path) -> None:
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_call = {"id": "c2", "type": "function", "function": {"name": "read_file", "arguments": {"workspace_root": str(tmp_path), "path": str(tmp_path / "missing.txt")}}}
  client = StubModel([Message(role="assistant", tool_calls=[tool_call]), Message(role="assistant", content="after-tool")])
  runtime = CliAgentRuntime(workspace_root=tmp_path, model_client=client, model_name="stub", tool_registry=registry, session_store=store, bus=EventBus(), config=AgentLoopConfig(max_steps=4, approval_required_classes=("read",)), on_approve=lambda *_a: False)
  snapshot = runtime.step("please read")
  assert snapshot.state.value == "finished"
  assert any(m.get("role") == "tool" and "denied" in (m.get("content") or "") for m in snapshot.messages)


def test_denied_tool_no_orphan_record(tmp_path: Path) -> None:
  """Denying a tool should NOT leave an orphan 'running' record in session store."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_call = {"id": "c3", "type": "function", "function": {"name": "read_file", "arguments": {"workspace_root": str(tmp_path), "path": str(tmp_path / "x.txt")}}}
  client = StubModel([Message(role="assistant", tool_calls=[tool_call]), Message(role="assistant", content="done")])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
    config=AgentLoopConfig(max_steps=4, approval_required_classes=("read",)),
    on_approve=lambda *_a: False,
  )
  snapshot = runtime.step("read x")
  runs = store.get_tool_runs(snapshot.metadata["session_id"])
  assert all(r.status != "running" for r in runs), f"Orphan running records found: {runs}"


def test_runtime_fails_after_max_steps(tmp_path: Path) -> None:
  """Agent should transition to FAILED when max_steps is exhausted."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_calls = [
      {
          "id": "tc",
          "type": "function",
          "function": {
              "name": "read_file",
              "arguments": {
                  "workspace_root": str(tmp_path),
                  "path": str(tmp_path / "missing.txt"),
              },
          },
      }
  ]
  client = StubModel(
      [Message(role="assistant", tool_calls=tool_calls) for _ in range(3)]
  )
  runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=client,
      model_name="stub",
      tool_registry=registry,
      session_store=store,
      bus=EventBus(),
      config=AgentLoopConfig(max_steps=3),
  )
  snapshot = runtime.step("loop forever")
  assert snapshot.state == AgentState.FAILED
  assert snapshot.state.value == "failed"
  assert "max steps" in (snapshot.messages[-1].get("content") or "").lower()


def test_runtime_handles_malformed_tool_arguments(tmp_path: Path) -> None:
  """Malformed JSON tool args should not crash and should be surfaced to model."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_call = {
      "id": "bad",
      "type": "function",
      "function": {"name": "read_file", "arguments": "not-json"},
  }
  client = StubModel(
      [
          Message(role="assistant", tool_calls=[tool_call]),
          Message(role="assistant", content="recovered"),
      ]
  )
  runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=client,
      model_name="stub",
      tool_registry=registry,
      session_store=store,
      bus=EventBus(),
      config=AgentLoopConfig(max_steps=4),
  )
  snapshot = runtime.step("break args")
  assert snapshot.state.value == "finished"
  tool_messages = [m for m in snapshot.messages if m.get("role") == "tool"]
  assert len(tool_messages) >= 1
  assert any("Tool error" in (m.get("content") or "") for m in tool_messages)


def test_runtime_executes_multiple_tool_calls_in_one_turn(tmp_path: Path) -> None:
  """Multiple tool calls returned by model should execute sequentially."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  file_a = tmp_path / "a.txt"
  file_b = tmp_path / "b.txt"
  file_a.write_text("a", encoding="utf-8")
  file_b.write_text("b", encoding="utf-8")
  tool_calls = [
      {
          "id": "m1",
          "type": "function",
          "function": {
              "name": "read_file",
              "arguments": {"workspace_root": str(tmp_path), "path": str(file_a)},
          },
      },
      {
          "id": "m2",
          "type": "function",
          "function": {
              "name": "read_file",
              "arguments": {"workspace_root": str(tmp_path), "path": str(file_b)},
          },
      },
  ]
  client = StubModel(
      [
          Message(role="assistant", tool_calls=tool_calls),
          Message(role="assistant", content="both read"),
      ]
  )
  runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=client,
      model_name="stub",
      tool_registry=registry,
      session_store=store,
      bus=EventBus(),
      config=AgentLoopConfig(max_steps=4),
  )
  snapshot = runtime.step("read both")
  assert snapshot.state.value == "finished"
  tool_messages = [m for m in snapshot.messages if m.get("role") == "tool"]
  assert len(tool_messages) >= 2
  assert len(snapshot.tool_runs) >= 2
