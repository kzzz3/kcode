from __future__ import annotations

import json
from typing import Iterable, Optional

import httpx
import pytest

from packages.core.src.config.loader import ModelProviderConfig
from packages.core.src.models.interfaces import (
    ChunkType,
    Message,
    ModelClient,
    ModelResponse,
    ToolSpec,
)
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


def _config() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider_type="openai_compatible",
        base_url="https://example.invalid/v1",
        api_key="test-key",
        default_model="gpt-4o",
        timeout_seconds=5,
        max_retries=0,
    )


class RecordingFallbackClient(ModelClient):
    def __init__(self, response: ModelResponse) -> None:
        self._response = response
        self.calls: list[str] = []

    def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: Optional[Iterable[ToolSpec]] = None,
        temperature: Optional[float] = None,
        stop: Optional[list[str]] = None,
    ) -> ModelResponse:
        self.calls.append("complete")
        return self._response


class FakeStreamTransport(httpx.BaseTransport):
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self._status_code = status_code

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._status_code != 200:
            return httpx.Response(
                self._status_code,
                json={"error": "bad"},
                request=request,
            )

        body = "\n".join(self._lines) + "\n"
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
            request=request,
        )


def _open_client(transport: httpx.BaseTransport) -> OpenAICompatibleClient:
    client = OpenAICompatibleClient(_config())
    client._client = httpx.Client(
        base_url="https://example.invalid/v1",
        transport=transport,
        headers={"Content-Type": "application/json", "Authorization": "Bearer test-key"},
    )
    return client


def test_complete_stream_emits_text_chunks() -> None:
    payload = {"choices": [{"delta": {"content": "Hello "}}]}
    lines = [f"data: {json.dumps(payload)}", "data: [DONE]"]

    client = _open_client(FakeStreamTransport(lines))
    chunks = list(client.complete_stream(model="m", messages=[Message(role="user", content="hi")]))

    assert chunks[0].type == ChunkType.TEXT
    assert chunks[0].delta == "Hello "
    assert chunks[-1].type == ChunkType.DONE


def test_complete_stream_emits_tool_call_end_on_done() -> None:
    start_payload = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": ""},
                        }
                    ]
                }
            }
        ]
    }
    args_payload = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": '{"path":'},
                        }
                    ]
                }
            }
        ]
    }
    lines = [f"data: {json.dumps(start_payload)}", f"data: {json.dumps(args_payload)}", "data: [DONE]"]

    client = _open_client(FakeStreamTransport(lines))
    chunks = list(client.complete_stream(model="m", messages=[Message(role="user", content="hi")]))

    types = [c.type for c in chunks]
    assert ChunkType.TOOL_CALL_START in types
    assert ChunkType.TOOL_CALL_ARGS in types
    assert ChunkType.TOOL_CALL_END in types
    assert types[-1] == ChunkType.DONE


def test_complete_stream_handles_missing_done_marker() -> None:
    payload = {"choices": [{"delta": {"content": "ok"}}]}
    lines = [f"data: {json.dumps(payload)}"]

    client = _open_client(FakeStreamTransport(lines))
    chunks = list(client.complete_stream(model="m", messages=[Message(role="user", content="hi")]))

    assert any(c.type == ChunkType.TEXT for c in chunks)
    assert chunks[-1].type == ChunkType.DONE


def test_complete_stream_http_error_raises_for_stream() -> None:
    client = _open_client(FakeStreamTransport([], status_code=500))

    with pytest.raises(httpx.HTTPStatusError):
        list(client.complete_stream(model="m", messages=[Message(role="user", content="hi")]))


def test_complete_success_returns_parsed_message() -> None:
    transport_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": {"path": "a"}},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1},
    }

    class SuccessTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=transport_payload, request=request)

    client = _open_client(SuccessTransport())
    response = client.complete(model="m", messages=[Message(role="user", content="hi")])

    assert response.message.role == "assistant"
    assert response.message.content == "ok"
    assert response.message.tool_calls is not None
    assert response.message.tool_calls[0]["id"] == "call_1"
    assert response.usage["prompt_tokens"] == 2

