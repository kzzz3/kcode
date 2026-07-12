"""Extended tests for packages/core/src/models/openai_compatible.py.

Covers SSE parsing, _extract_stream_chunks with tool-call deltas, and
edge cases in _messages_to_payload / _tools_to_payload / _build_request_payload.
"""
from __future__ import annotations

from typing import Any

from packages.core.src.models.interfaces import ChunkType, Message, ToolSpec
from packages.core.src.models.openai_compatible import (
    _build_request_payload,
    _extract_stream_chunks,
    _messages_to_payload,
    _parse_sse_line,
    _tools_to_payload,
)


# ---------------------------------------------------------------------------
# _parse_sse_line
# ---------------------------------------------------------------------------

def test_parse_sse_line_data_with_json() -> None:
    line = 'data: {"choices":[{"delta":{"content":"hi"}}]}'
    result = _parse_sse_line(line)
    assert result is not None
    assert result["choices"][0]["delta"]["content"] == "hi"


def test_parse_sse_line_done_marker() -> None:
    result = _parse_sse_line("data: [DONE]")
    assert result == {"__done__": True}


def test_parse_sse_line_empty_returns_none() -> None:
    assert _parse_sse_line("") is None
    assert _parse_sse_line("   ") is None


def test_parse_sse_line_non_data_returns_none() -> None:
    assert _parse_sse_line("event: ping") is None


def test_parse_sse_line_malformed_json_returns_none() -> None:
    assert _parse_sse_line("data: {not-json}") is None


# ---------------------------------------------------------------------------
# _extract_stream_chunks
# ---------------------------------------------------------------------------

def test_extract_chunks_text_delta() -> None:
    data: dict[str, Any] = {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
    chunks = list(_extract_stream_chunks(data))
    assert len(chunks) == 1
    assert chunks[0].type == ChunkType.TEXT
    assert chunks[0].delta == "hello"


def test_extract_chunks_no_choices_with_usage() -> None:
    data: dict[str, Any] = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    chunks = list(_extract_stream_chunks(data))
    assert len(chunks) == 1
    assert chunks[0].type == ChunkType.USAGE
    assert chunks[0].usage["prompt_tokens"] == 10


def test_extract_chunks_empty_choices_no_usage() -> None:
    data: dict[str, Any] = {"choices": []}
    chunks = list(_extract_stream_chunks(data))
    assert len(chunks) == 0


def test_extract_chunks_tool_call_start() -> None:
    data: dict[str, Any] = {
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "id": "call_abc", "type": "function", "function": {"name": "search", "arguments": ""}},
                ]
            },
            "finish_reason": None,
        }]
    }
    chunks = list(_extract_stream_chunks(data))
    start_chunks = [c for c in chunks if c.type == ChunkType.TOOL_CALL_START]
    assert len(start_chunks) == 1
    assert start_chunks[0].tool_call_id == "call_abc"
    assert start_chunks[0].tool_name == "search"


def test_extract_chunks_tool_call_args_with_real_id() -> None:
    data: dict[str, Any] = {
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "id": "call_123", "function": {"arguments": '{"q":"test"}'}},
                ]
            },
            "finish_reason": None,
        }]
    }
    chunks = list(_extract_stream_chunks(data))
    args_chunks = [c for c in chunks if c.type == ChunkType.TOOL_CALL_ARGS]
    assert len(args_chunks) == 1
    assert args_chunks[0].tool_call_id == "call_123"
    assert args_chunks[0].delta == '{"q":"test"}'


def test_extract_chunks_tool_call_args_with_index_key() -> None:
    """When id is empty but index is present, uses __tc_<index>__ as key."""
    data: dict[str, Any] = {
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": '{"a":'}},
                ]
            },
            "finish_reason": None,
        }]
    }
    chunks = list(_extract_stream_chunks(data))
    args_chunks = [c for c in chunks if c.type == ChunkType.TOOL_CALL_ARGS]
    assert len(args_chunks) == 1
    assert args_chunks[0].tool_call_id == "call_123"


def test_extract_chunks_usage_with_finish() -> None:
    data: dict[str, Any] = {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8},
    }
    chunks = list(_extract_stream_chunks(data))
    usage_chunks = [c for c in chunks if c.type == ChunkType.USAGE]
    assert len(usage_chunks) == 1


# ---------------------------------------------------------------------------
# _messages_to_payload
# ---------------------------------------------------------------------------

def test_messages_to_payload_basic() -> None:
    msgs = [Message(role="user", content="hi")]
    payload = _messages_to_payload(msgs)
    assert payload == [{"role": "user", "content": "hi"}]


def test_messages_to_payload_with_tool_calls() -> None:
    tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    msgs = [Message(role="assistant", content=None, tool_calls=tc)]
    payload = _messages_to_payload(msgs)
    assert payload[0]["tool_calls"] == tc
    assert "content" not in payload[0]


def test_messages_to_payload_with_tool_call_id() -> None:
    msgs = [Message(role="tool", content="result", tool_call_id="c1")]
    payload = _messages_to_payload(msgs)
    assert payload[0]["tool_call_id"] == "c1"


# ---------------------------------------------------------------------------
# _tools_to_payload
# ---------------------------------------------------------------------------

def test_tools_to_payload_none() -> None:
    assert _tools_to_payload(None) is None


def test_tools_to_payload_empty() -> None:
    assert _tools_to_payload([]) is None


def test_tools_to_payload_conversion() -> None:
    tools = [ToolSpec(name="search", description="Search", parameters={"type": "object"})]
    result = _tools_to_payload(tools)
    assert result is not None
    assert result[0]["function"]["name"] == "search"
    assert result[0]["type"] == "function"


# ---------------------------------------------------------------------------
# _build_request_payload
# ---------------------------------------------------------------------------

def test_build_request_payload_minimal() -> None:
    payload = _build_request_payload(
        model="gpt-4o",
        messages=[Message(role="user", content="hi")],
    )
    assert payload["model"] == "gpt-4o"
    assert payload["stream"] is False
    assert "tools" not in payload
    assert "temperature" not in payload


def test_build_request_payload_with_all_options() -> None:
    tools = [ToolSpec(name="t", description="d", parameters={})]
    payload = _build_request_payload(
        model="gpt-4o",
        messages=[Message(role="user", content="x")],
        tools=tools,
        temperature=0.7,
        stop=["END"],
        stream=True,
    )
    assert payload["stream"] is True
    assert payload["temperature"] == 0.7
    assert payload["stop"] == ["END"]
    assert "tools" in payload