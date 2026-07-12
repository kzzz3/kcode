from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.cli.src.config.resolution import resolve_config
from packages.core.src.models.interfaces import Message, ChunkType
from packages.core.src.models.openai_compatible import (
  OpenAICompatibleClient,
  _build_request_payload,
  _messages_to_payload,
  _tools_to_payload,
  _parse_sse_line,
  _extract_stream_chunks,
)


def test_messages_to_payload_includes_fields() -> None:
  msgs = [Message(role="user", content="hi", tool_call_id=None)]
  out = _messages_to_payload(msgs)
  assert out[0]["role"] == "user"
  assert out[0]["content"] == "hi"


def test_tools_to_payload_none_when_empty() -> None:
  assert _tools_to_payload(None) is None
  assert _tools_to_payload([]) is None


def test_build_request_payload_minimal() -> None:
  payload = _build_request_payload(model="m", messages=[Message(role="user", content="hi")])
  assert payload["model"] == "m"
  assert payload["stream"] is False
  assert isinstance(payload["messages"], list)


def test_parse_sse_line_variants() -> None:
  assert _parse_sse_line("") is None
  assert _parse_sse_line("event: x") is None
  assert _parse_sse_line("data: [DONE]") == {"__done__": True}
  assert _parse_sse_line('data: {"choices":[{"delta":{"content":"a"}}]}') is not None


def test_extract_stream_chunks_text_and_usage() -> None:
  data = {
    "choices": [{"delta": {"content": "x"}, "finish_reason": None}],
    "usage": {"prompt_tokens": 1},
  }
  chunks = list(_extract_stream_chunks(data))
  assert any(c.type == ChunkType.TEXT and c.delta == "x" for c in chunks)
  assert any(c.type == ChunkType.USAGE and c.usage == {"prompt_tokens": 1} for c in chunks)


def test_client_complete_uses_mock_transport(monkeypatch, tmp_path: Path) -> None:
  config = resolve_config(tmp_path)
  client = OpenAICompatibleClient(config.model)

  class FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
      return None

    def json(self) -> dict[str, Any]:
      return {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {}}

  def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
    return FakeResponse()

  monkeypatch.setattr(client._client, "post", fake_post)
  out = client.complete(model="m", messages=[Message(role="user", content="hi")])
  assert out.message.content == "ok"
