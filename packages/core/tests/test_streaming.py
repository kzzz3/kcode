"""Tests for streaming types: StreamChunk, StreamAccumulator, SSE parsing."""
from __future__ import annotations

import json
from typing import Iterable, Optional

from packages.core.src.models.interfaces import (
  ChunkType,
  Message,
  ModelClient,
  ModelResponse,
  StreamAccumulator,
  StreamChunk,
  ToolSpec,
)
from packages.core.src.models.openai_compatible import (
  _extract_stream_chunks,
  _parse_sse_line,
)


# ---------------------------------------------------------------------------
# StreamAccumulator tests
# ---------------------------------------------------------------------------


def test_accumulator_text_only() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TEXT, delta="Hello "))
  acc.feed(StreamChunk(type=ChunkType.TEXT, delta="world"))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  msg = acc.to_message()
  assert msg.role == "assistant"
  assert msg.content == "Hello world"
  assert msg.tool_calls is None


def test_accumulator_tool_call_full_cycle() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="call_1", tool_name="read_file"))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="call_1", delta='{"path":'))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="call_1", delta='"/tmp/foo"}'))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="call_1"))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  msg = acc.to_message()
  assert msg.content is None
  assert msg.tool_calls is not None
  assert len(msg.tool_calls) == 1
  tc = msg.tool_calls[0]
  assert tc["id"] == "call_1"
  assert tc["type"] == "function"
  assert tc["function"]["name"] == "read_file"
  assert tc["function"]["arguments"] == '{"path":"/tmp/foo"}'


def test_accumulator_mixed_text_and_tool() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TEXT, delta="Let me check "))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="c1", tool_name="search"))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="c1", delta='{"q":"test"}'))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  msg = acc.to_message()
  assert msg.content == "Let me check "
  assert msg.tool_calls is not None
  assert len(msg.tool_calls) == 1
  assert msg.tool_calls[0]["function"]["arguments"] == '{"q":"test"}'


def test_accumulator_usage_tracking() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TEXT, delta="hi"))
  acc.feed(StreamChunk(type=ChunkType.USAGE, usage={"prompt_tokens": 10, "completion_tokens": 5}))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  assert acc.usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_accumulator_multiple_tool_calls() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="a", tool_name="tool_a"))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="a", delta='{"x":1}'))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="b", tool_name="tool_b"))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="b", delta='{"y":2}'))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  msg = acc.to_message()
  assert msg.tool_calls is not None
  assert len(msg.tool_calls) == 2
  names = {tc["function"]["name"] for tc in msg.tool_calls}
  assert names == {"tool_a", "tool_b"}


def test_accumulator_malformed_json_args() -> None:
  acc = StreamAccumulator()
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="x", tool_name="bad"))
  acc.feed(StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="x", delta="not json"))
  acc.feed(StreamChunk(type=ChunkType.DONE))
  msg = acc.to_message()
  assert msg.tool_calls is not None
  # Malformed JSON should fall back to {"raw": "..."}
  assert msg.tool_calls[0]["function"]["arguments"] == '{"raw": "not json"}'


# ---------------------------------------------------------------------------
# SSE parsing tests
# ---------------------------------------------------------------------------


def test_parse_sse_line_data() -> None:
  data = {"choices": [{"delta": {"content": "hi"}}]}
  result = _parse_sse_line(f"data: {json.dumps(data)}")
  assert result is not None
  assert result["choices"][0]["delta"]["content"] == "hi"


def test_parse_sse_line_done() -> None:
  result = _parse_sse_line("data: [DONE]")
  assert result is not None
  assert result.get("__done__") is True


def test_parse_sse_line_empty() -> None:
  assert _parse_sse_line("") is None
  assert _parse_sse_line("   ") is None


def test_parse_sse_line_non_data() -> None:
  assert _parse_sse_line("event: ping") is None


def test_parse_sse_line_malformed_json() -> None:
  assert _parse_sse_line("data: {broken") is None


# ---------------------------------------------------------------------------
# _extract_stream_chunks tests
# ---------------------------------------------------------------------------


def test_extract_text_delta() -> None:
  data = {"choices": [{"delta": {"content": "hello"}}]}
  chunks = list(_extract_stream_chunks(data))
  assert len(chunks) == 1
  assert chunks[0].type == ChunkType.TEXT
  assert chunks[0].delta == "hello"


def test_extract_tool_call_start() -> None:
  data = {
    "choices": [{
      "delta": {
        "tool_calls": [{
          "index": 0,
          "id": "call_abc",
          "type": "function",
          "function": {"name": "read_file", "arguments": ""},
        }],
      },
    }],
  }
  chunks = list(_extract_stream_chunks(data))
  assert len(chunks) == 1
  assert chunks[0].type == ChunkType.TOOL_CALL_START
  assert chunks[0].tool_call_id == "call_abc"
  assert chunks[0].tool_name == "read_file"


def test_extract_tool_call_args_delta() -> None:
  data = {
    "choices": [{
      "delta": {
        "tool_calls": [{
          "index": 0,
          "function": {"arguments": '{"path":'},
        }],
      },
    }],
  }
  chunks = list(_extract_stream_chunks(data))
  assert len(chunks) == 1
  assert chunks[0].type == ChunkType.TOOL_CALL_ARGS
  assert chunks[0].delta == '{"path":'


def test_extract_usage_chunk() -> None:
  data = {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
  chunks = list(_extract_stream_chunks(data))
  assert len(chunks) == 1
  assert chunks[0].type == ChunkType.USAGE
  assert chunks[0].usage["prompt_tokens"] == 100


def test_extract_empty_choices_with_usage() -> None:
  data = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
  chunks = list(_extract_stream_chunks(data))
  # Should have a USAGE chunk
  usage_chunks = [c for c in chunks if c.type == ChunkType.USAGE]
  assert len(usage_chunks) == 1


# ---------------------------------------------------------------------------
# ModelClient.complete_stream fallback test
# ---------------------------------------------------------------------------


class StubModel(ModelClient):
  def __init__(self, msg: Message) -> None:
    self._msg = msg

  def complete(self, *, model: str, messages: list[Message], tools: Optional[Iterable[ToolSpec]] = None, temperature: Optional[float] = None, stop: Optional[list[str]] = None) -> ModelResponse:
    return ModelResponse(message=self._msg, usage={"prompt_tokens": 1, "completion_tokens": 1})


def test_fallback_stream_text_only() -> None:
  client = StubModel(Message(role="assistant", content="hello"))
  chunks = list(client.complete_stream(model="m", messages=[]))
  types = [c.type for c in chunks]
  assert types == [ChunkType.TEXT, ChunkType.USAGE, ChunkType.DONE]


def test_fallback_stream_with_tool_calls() -> None:
  tc = {"id": "c1", "type": "function", "function": {"name": "foo", "arguments": {"x": 1}}}
  client = StubModel(Message(role="assistant", content=None, tool_calls=[tc]))
  chunks = list(client.complete_stream(model="m", messages=[]))
  types = [c.type for c in chunks]
  assert ChunkType.TOOL_CALL_START in types
  assert ChunkType.TOOL_CALL_ARGS in types
  assert ChunkType.TOOL_CALL_END in types
  assert ChunkType.DONE in types
