"""Tests for CliAgentRuntime.step_stream() with a stub streaming model."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Optional

from packages.core.src.models.interfaces import (
  ChunkType,
  Message,
  ModelClient,
  ModelResponse,
  StreamChunk,
  ToolSpec,
)
from packages.core.src.runtime.contracts import AgentSnapshot, AgentState
from packages.core.src.runtime.events import EventBus
from packages.core.src.runtime.session import SessionStore
from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.core.agent_runtime import AgentLoopConfig, CliAgentRuntime
from apps.cli.src.tools.builtin_readonly import register_readonly_tools


class StubStreamingModel(ModelClient):
  """Stub that yields predetermined chunks for complete_stream."""

  def __init__(self, chunk_sequences: list[list[StreamChunk]]) -> None:
    self._sequences = list(chunk_sequences)

  def complete(self, *, model: str, messages: list[Message], tools: Optional[Iterable[ToolSpec]] = None, temperature: Optional[float] = None, stop: Optional[list[str]] = None) -> ModelResponse:
    return ModelResponse(
      message=Message(role="assistant", content="fallback"),
      usage={"prompt_tokens": 0, "completion_tokens": 0},
    )

  def complete_stream(
    self,
    *,
    model: str,
    messages: list[Message],
    tools: Optional[Iterable[ToolSpec]] = None,
    temperature: Optional[float] = None,
    stop: Optional[list[str]] = None,
  ) -> Iterator[StreamChunk]:
    yield from self._sequences.pop(0)


def test_step_stream_text_reply(tmp_path: Path) -> None:
  """Streaming a simple text reply yields TEXT chunks then AgentSnapshot."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  chunks = [
    StreamChunk(type=ChunkType.TEXT, delta="Hello "),
    StreamChunk(type=ChunkType.TEXT, delta="world"),
    StreamChunk(type=ChunkType.USAGE, usage={"prompt_tokens": 5, "completion_tokens": 2}),
    StreamChunk(type=ChunkType.DONE),
  ]
  client = StubStreamingModel([chunks])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
  )
  items = list(runtime.step_stream("hi"))
  # Should have: TEXT, TEXT, USAGE, AgentSnapshot
  text_chunks = [i for i in items if isinstance(i, StreamChunk) and i.type == ChunkType.TEXT]
  assert len(text_chunks) == 2
  assert text_chunks[0].delta == "Hello "
  assert text_chunks[1].delta == "world"
  snapshots = [i for i in items if isinstance(i, AgentSnapshot)]
  assert len(snapshots) == 1
  assert snapshots[0].state.value == "finished"


def test_step_stream_with_tool_call(tmp_path: Path) -> None:
  """Streaming with tool call executes tool then continues."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  # Create a file for the tool to read
  (tmp_path / "test.txt").write_text("file content", encoding="utf-8")

  # First response: tool call
  tool_chunks = [
    StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="tc1", tool_name="read_file"),
    StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="tc1", delta=f'{{"workspace_root":"{tmp_path.as_posix()}","path":"{(tmp_path / "test.txt").as_posix()}"}}'),
    StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="tc1"),
    StreamChunk(type=ChunkType.DONE),
  ]
  # Second response: text reply after tool execution
  text_chunks = [
    StreamChunk(type=ChunkType.TEXT, delta="I read the file."),
    StreamChunk(type=ChunkType.DONE),
  ]
  client = StubStreamingModel([tool_chunks, text_chunks])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
    config=AgentLoopConfig(max_steps=4),
  )
  items = list(runtime.step_stream("read test.txt"))
  # Should have tool call chunks, then tool result, then text chunks, then snapshot
  snapshots = [i for i in items if isinstance(i, AgentSnapshot)]
  assert len(snapshots) == 1
  assert snapshots[0].state.value == "finished"
  # The final message should be the text reply
  assert snapshots[0].messages[-1].get("content") == "I read the file."
  # There should be a tool run recorded
  assert len(snapshots[0].tool_runs) >= 1


def test_step_stream_denied_tool(tmp_path: Path) -> None:
  """Streaming with denied tool returns denial message and continues."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_chunks = [
    StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="tc2", tool_name="read_file"),
    StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="tc2", delta='{"workspace_root":"x","path":"x"}'),
    StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="tc2"),
    StreamChunk(type=ChunkType.DONE),
  ]
  text_chunks = [
    StreamChunk(type=ChunkType.TEXT, delta="OK, skipping."),
    StreamChunk(type=ChunkType.DONE),
  ]
  client = StubStreamingModel([tool_chunks, text_chunks])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
    config=AgentLoopConfig(max_steps=4, approval_required_classes=("read",)),
    on_approve=lambda *_a: False,
  )
  items = list(runtime.step_stream("read it"))
  snapshots = [i for i in items if isinstance(i, AgentSnapshot)]
  assert len(snapshots) == 1
  assert snapshots[0].state.value == "finished"
  # Tool message should indicate denial
  tool_msgs = [m for m in snapshots[0].messages if m.get("role") == "tool"]
  assert any("denied" in (m.get("content") or "") for m in tool_msgs)


def test_step_stream_fails_after_max_steps(tmp_path: Path) -> None:
  """Streaming should return FAILED snapshot when max_steps exhausted."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_chunks = [
    StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="tc", tool_name="read_file"),
    StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="tc", delta='{"workspace_root":"x","path":"x"}'),
    StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="tc"),
    StreamChunk(type=ChunkType.DONE),
  ]
  client = StubStreamingModel([tool_chunks, tool_chunks, tool_chunks])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
    config=AgentLoopConfig(max_steps=3, approval_required_classes=("read",)),
    on_approve=lambda *_a: False,
  )
  items = list(runtime.step_stream("spam tools"))
  snapshots = [i for i in items if isinstance(i, AgentSnapshot)]
  assert len(snapshots) == 1
  assert snapshots[0].state == AgentState.FAILED
  assert snapshots[0].state.value == "failed"
  assert "max steps" in (snapshots[0].messages[-1].get("content") or "").lower()


def test_step_stream_handles_malformed_tool_arguments(tmp_path: Path) -> None:
  """Malformed streaming tool args should not crash runtime."""
  registry = ToolRegistry()
  register_readonly_tools(registry)
  store = SessionStore(tmp_path / "s.sqlite")
  tool_chunks = [
    StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="bad", tool_name="read_file"),
    StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="bad", delta="not-json"),
    StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="bad"),
    StreamChunk(type=ChunkType.DONE),
  ]
  text_chunks = [
    StreamChunk(type=ChunkType.TEXT, delta="continued"),
    StreamChunk(type=ChunkType.DONE),
  ]
  client = StubStreamingModel([tool_chunks, text_chunks])
  runtime = CliAgentRuntime(
    workspace_root=tmp_path, model_client=client, model_name="stub",
    tool_registry=registry, session_store=store, bus=EventBus(),
    config=AgentLoopConfig(max_steps=4),
  )
  items = list(runtime.step_stream("break args"))
  snapshots = [i for i in items if isinstance(i, AgentSnapshot)]
  assert len(snapshots) == 1
  assert snapshots[0].state.value == "finished"
  tool_messages = [m for m in snapshots[0].messages if m.get("role") == "tool"]
  assert any("Tool error" in (m.get("content") or "") for m in tool_messages)
