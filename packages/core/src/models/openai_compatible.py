"""OpenAI-compatible model client with SSE streaming support."""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Iterator, Optional, List

import httpx

from packages.core.src.config.loader import ModelProviderConfig
from packages.core.src.models.interfaces import (
  ChunkType,
  Message,
  ModelClient,
  ModelInfo,
  ModelResponse,
  StreamChunk,
  ToolSpec,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_base_url(url: str) -> str:
  """Return base_url with a single trailing slash for httpx base URLs."""
  return url.rstrip("/") + "/"


def _messages_to_payload(messages: list[Message]) -> list[dict[str, Any]]:
  """Convert internal Message objects to OpenAI API payload format."""
  payload: list[dict[str, Any]] = []
  for message in messages:
    entry: dict[str, Any] = {"role": message.role}
    if message.content is not None:
      entry["content"] = message.content
    if message.tool_calls:
      sanitized: list[dict[str, Any]] = []
      for tc in message.tool_calls:
        tc_copy = dict(tc)
        fn = dict(tc_copy.get("function", {}))
        args = fn.get("arguments", "{}")
        if args is None or (isinstance(args, str) and not args):
          fn["arguments"] = "{}"
        elif isinstance(args, dict):
          fn["arguments"] = json.dumps(args, ensure_ascii=False)
        elif not isinstance(args, str):
          fn["arguments"] = json.dumps(args, ensure_ascii=False)
        tc_copy["function"] = fn
        sanitized.append(tc_copy)
      entry["tool_calls"] = sanitized
    if message.tool_call_id:
      entry["tool_call_id"] = message.tool_call_id
    payload.append(entry)
  return payload


def _tools_to_payload(tools: Optional[Iterable[ToolSpec]]) -> Optional[List[dict[str, Any]]]:
  """Convert ToolSpec objects to OpenAI API tools payload."""
  if not tools:
    return None
  return [
    {
      "type": "function",
      "function": {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
      },
    }
    for tool in tools
  ]


def _build_request_payload(
  *,
  model: str,
  messages: list[Message],
  tools: Optional[Iterable[ToolSpec]] = None,
  temperature: Optional[float] = None,
  stop: Optional[list[str]] = None,
  stream: bool = False,
) -> dict[str, Any]:
  """Build the JSON payload for a chat completion request."""
  payload: dict[str, Any] = {
    "model": model,
    "messages": _messages_to_payload(messages),
    "stream": stream,
  }
  tools_payload = _tools_to_payload(tools)
  if tools_payload:
    payload["tools"] = tools_payload
  if temperature is not None:
    payload["temperature"] = temperature
  if stop:
    payload["stop"] = stop
  return payload


def _parse_sse_line(line: str) -> dict[str, Any] | None:
  """Parse a single SSE data line. Returns parsed JSON or None for non-data lines."""
  line = line.strip()
  if not line:
    return None
  if line.startswith("data: "):
    data_str = line[6:]
    if data_str == "[DONE]":
      return {"__done__": True}
    try:
      return json.loads(data_str)
    except json.JSONDecodeError:
      _LOGGER.debug("Failed to parse SSE data line: %s", data_str[:200])
      return None
  return None


# Module-level index->id mapping for streaming tool calls
_tc_index_to_id: dict[int, str] = {}
_tc_index_to_name: dict[int, str] = {}


def _extract_stream_chunks(data: dict[str, Any]) -> Iterator[StreamChunk]:
  """Extract StreamChunk objects from a parsed SSE data payload."""
  choices = data.get("choices", [])
  if not choices:
    usage = data.get("usage")
    if usage:
      yield StreamChunk(type=ChunkType.USAGE, usage=usage)
    return

  choice = choices[0]
  delta = choice.get("delta", {})
  finish_reason = choice.get("finish_reason")

  content = delta.get("content")
  if content:
    yield StreamChunk(type=ChunkType.TEXT, delta=content)

  tool_calls = delta.get("tool_calls") or []
  for tc_delta in tool_calls:
    tc_index = tc_delta.get("index", 0)
    tc_id = tc_delta.get("id", "")
    fn = tc_delta.get("function", {})
    fn_name = fn.get("name", "")
    fn_args_delta = fn.get("arguments", "")

    # Track id/name by index so subsequent chunks without id resolve correctly
    if tc_id:
      _tc_index_to_id[tc_index] = tc_id
    if fn_name:
      _tc_index_to_name[tc_index] = fn_name

    effective_id = _tc_index_to_id.get(tc_index, f"__tc_{tc_index}__")
    effective_name = _tc_index_to_name.get(tc_index, "")

    if tc_id and fn_name:
      yield StreamChunk(
        type=ChunkType.TOOL_CALL_START,
        tool_call_id=effective_id,
        tool_name=effective_name,
      )
    if fn_args_delta:
      yield StreamChunk(
        type=ChunkType.TOOL_CALL_ARGS,
        tool_call_id=effective_id,
        delta=fn_args_delta,
      )

  if finish_reason == "tool_calls":
    pass

  usage = data.get("usage")
  if usage:
    yield StreamChunk(type=ChunkType.USAGE, usage=usage)


class OpenAICompatibleClient(ModelClient):
  """Client for OpenAI-compatible HTTP endpoints with SSE streaming."""

  def __init__(self, config: ModelProviderConfig) -> None:
    if "/chat/completions" in config.base_url:
      raise ValueError(
        "ModelProviderConfig.base_url must be the API root (e.g. https://host/v1), "
        "not the chat/completions endpoint."
      )

    self._config = config
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key:
      headers["Authorization"] = f"Bearer {config.api_key}"
    self._client = httpx.Client(
      base_url=_normalize_base_url(config.base_url),
      headers=headers,
      timeout=httpx.Timeout(
        connect=10.0,
        read=config.timeout_seconds,
        write=10.0,
        pool=10.0,
      ),
    )

  def list_models(self) -> list[ModelInfo]:
    """Fetch available models via GET /v1/models (OpenAI-compatible).

    Returns a list of ModelInfo sorted by id.
    Raises httpx.HTTPStatusError on non-200 responses.
    """
    response = self._client.get("/models")
    response.raise_for_status()
    data = response.json()

    raw_models = data.get("data", [])
    models: list[ModelInfo] = []
    for entry in raw_models:
      models.append(ModelInfo(
        id=entry.get("id", ""),
        owned_by=entry.get("owned_by", ""),
        created=entry.get("created", 0),
        capabilities={k: v for k, v in entry.items() if k not in ("id", "owned_by", "created", "object")},
      ))
    models.sort(key=lambda m: m.id)
    return models

  def complete(
    self,
    *,
    model: str,
    messages: list[Message],
    tools: Optional[Iterable[ToolSpec]] = None,
    temperature: Optional[float] = None,
    stop: Optional[list[str]] = None,
  ) -> ModelResponse:
    payload = _build_request_payload(
      model=model, messages=messages, tools=tools,
      temperature=temperature, stop=stop, stream=False,
    )
    response = self._client.post("/chat/completions", json=payload)
    response.raise_for_status()
    data = response.json()
    choice = data["choices"][0]["message"]
    message = Message(
      role=choice.get("role", "assistant"),
      content=choice.get("content"),
      tool_calls=choice.get("tool_calls"),
    )
    return ModelResponse(message=message, usage=data.get("usage", {}), raw=data)

  def complete_stream(
    self,
    *,
    model: str,
    messages: list[Message],
    tools: Optional[Iterable[ToolSpec]] = None,
    temperature: Optional[float] = None,
    stop: Optional[list[str]] = None,
  ) -> Iterator[StreamChunk]:
    """Stream model output via SSE."""
    payload = _build_request_payload(
      model=model, messages=messages, tools=tools,
      temperature=temperature, stop=stop, stream=True,
    )

    try:
      # Reset index->id mapping for each new stream
      _tc_index_to_id.clear()
      _tc_index_to_name.clear()

      with self._client.stream("POST", "/chat/completions", json=payload) as response:
        if response.is_error:
          # Read the full body before raising so httpx can build the error message
          error_body = response.read()
          _LOGGER.error("Stream request failed: %s %s", response.status_code, error_body[:500])
          response.raise_for_status()

        active_tool_ids: list[str] = []
        seen_start_ids: set[str] = set()

        for raw_line in response.iter_lines():
          data = _parse_sse_line(raw_line)
          if data is None:
            continue
          if data.get("__done__"):
            for tc_id in active_tool_ids:
              yield StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id=tc_id)
            yield StreamChunk(type=ChunkType.DONE)
            return

          for chunk in _extract_stream_chunks(data):
            if chunk.type == ChunkType.TOOL_CALL_START:
              if chunk.tool_call_id not in seen_start_ids:
                seen_start_ids.add(chunk.tool_call_id)
                active_tool_ids.append(chunk.tool_call_id)
            elif chunk.type == ChunkType.TOOL_CALL_ARGS:
              if chunk.tool_call_id not in seen_start_ids:
                seen_start_ids.add(chunk.tool_call_id)
                active_tool_ids.append(chunk.tool_call_id)
                # Use resolved name from _tc_index_to_name if available
                resolved_name = _tc_index_to_name.get(
                  int(chunk.tool_call_id.replace("__tc_", "").replace("__", "")) if chunk.tool_call_id.startswith("__tc_") else -1,
                  f"tool_{len(active_tool_ids) - 1}",
                )
                yield StreamChunk(
                  type=ChunkType.TOOL_CALL_START,
                  tool_call_id=chunk.tool_call_id,
                  tool_name=resolved_name,
                )
            yield chunk

        for tc_id in active_tool_ids:
          yield StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id=tc_id)
        yield StreamChunk(type=ChunkType.DONE)
    except Exception as exc:
      _LOGGER.debug("Streaming request failed: %s", exc)
      raise
