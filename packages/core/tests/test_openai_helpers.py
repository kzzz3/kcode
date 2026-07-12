from __future__ import annotations

from packages.core.src.models.interfaces import Message, ToolSpec, ChunkType
from packages.core.src.models.openai_compatible import (
    _messages_to_payload,
    _tools_to_payload,
    _build_request_payload,
    _parse_sse_line,
    _extract_stream_chunks,
)


def test_messages_to_payload_round_trip() -> None:
    msg = Message(role="assistant", content="hi", tool_calls=[{"id": "1"}], tool_call_id="x")
    payload = _messages_to_payload([msg])

    assert payload[0]["role"] == "assistant"
    assert payload[0]["content"] == "hi"
    assert payload[0]["tool_calls"] == [{"id": "1", "function": {}}]
    assert payload[0]["tool_call_id"] == "x"


def test_tools_to_payload_none_when_empty() -> None:
    assert _tools_to_payload(None) is None
    assert _tools_to_payload([]) is None


def test_tools_to_payload_includes_parameters() -> None:
    tool = ToolSpec(name="t", description="d", parameters={"type": "object"})
    payload = _tools_to_payload([tool])
    assert payload is not None
    assert payload[0]["type"] == "function"
    assert payload[0]["function"]["parameters"]["type"] == "object"


def test_build_request_payload_minimal() -> None:
    payload = _build_request_payload(model="m", messages=[Message(role="user", content="a")])
    assert payload["model"] == "m"
    assert payload["stream"] is False
    assert "tools" not in payload


def test_build_request_payload_includes_optional_fields() -> None:
    payload = _build_request_payload(
        model="m",
        messages=[Message(role="user", content="a")],
        temperature=0.2,
        stop=["END"],
        stream=True,
    )
    assert payload["temperature"] == 0.2
    assert payload["stop"] == ["END"]
    assert payload["stream"] is True


def test_parse_sse_line_handles_done() -> None:
    assert _parse_sse_line("data: [DONE]") == {"__done__": True}


def test_parse_sse_line_ignores_noise() -> None:
    assert _parse_sse_line("") is None
    assert _parse_sse_line("event: ping") is None


def test_parse_sse_line_parses_json() -> None:
    assert _parse_sse_line('data: {"ok": true}') == {"ok": True}


def test_extract_stream_chunks_emits_text_and_usage() -> None:
    data = {
        "choices": [
            {
                "delta": {"content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1},
    }
    chunks = list(_extract_stream_chunks(data))
    assert chunks[0].type == ChunkType.TEXT
    assert any(c.type == ChunkType.USAGE for c in chunks)


def test_extract_stream_chunks_emits_usage_when_no_choices() -> None:
    data = {"usage": {"prompt_tokens": 2}}
    chunks = list(_extract_stream_chunks(data))
    assert chunks[0].type == ChunkType.USAGE