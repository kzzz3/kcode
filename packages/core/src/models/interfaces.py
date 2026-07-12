"""Provider-agnostic message and model abstractions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator, Optional, List


@dataclass(frozen=True)
class ToolSpec:
    """Schema for exposing a tool to the model."""
    name: str
    description: str
    parameters: dict[str, Any]
    safety_class: str = "read"


@dataclass
class Message:
    """Unified message type for agent/model interactions."""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Normalized model response envelope."""
    message: Message
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


# --- Model listing ---


@dataclass
class ModelInfo:
    """Metadata for a single model returned by the provider."""
    id: str
    owned_by: str = ""
    created: int = 0
    capabilities: dict[str, Any] = field(default_factory=dict)


# --- Streaming types ---


class ChunkType(str, Enum):
    """Discriminator for stream chunk variants."""
    TEXT = "text"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS = "tool_call_args"
    TOOL_CALL_END = "tool_call_end"
    USAGE = "usage"
    DONE = "done"


@dataclass(frozen=True)
class StreamChunk:
    """A single chunk emitted during streaming.

    Variants:
      - TEXT:              type=TEXT, delta=<text fragment>
      - TOOL_CALL_START:   type=TOOL_CALL_START, tool_call_id=<id>, tool_name=<name>
      - TOOL_CALL_ARGS:    type=TOOL_CALL_ARGS, tool_call_id=<id>, delta=<args fragment>
      - TOOL_CALL_END:     type=TOOL_CALL_END, tool_call_id=<id>
      - USAGE:             type=USAGE, usage=<dict with prompt_tokens, completion_tokens>
      - DONE:              type=DONE — stream finished
    """
    type: ChunkType
    delta: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamAccumulator:
    """Reassembles a full Message from a stream of StreamChunks.

    This is the canonical way to turn streaming chunks back into a complete
    Message that can be appended to conversation history.
    """
    _text_parts: list[str] = field(default_factory=list)
    _tool_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    _usage: dict[str, Any] = field(default_factory=dict)

    def feed(self, chunk: StreamChunk) -> None:
        """Process one chunk and update internal state."""
        if chunk.type == ChunkType.TEXT:
            self._text_parts.append(chunk.delta)
        elif chunk.type == ChunkType.TOOL_CALL_START:
            self._tool_calls[chunk.tool_call_id] = {
                "id": chunk.tool_call_id,
                "type": "function",
                "function": {"name": chunk.tool_name, "arguments": ""},
            }
        elif chunk.type == ChunkType.TOOL_CALL_ARGS:
            if chunk.tool_call_id in self._tool_calls:
                self._tool_calls[chunk.tool_call_id]["function"]["arguments"] += chunk.delta
        elif chunk.type == ChunkType.TOOL_CALL_END:
            pass  # nothing additional to do
        elif chunk.type == ChunkType.USAGE:
            self._usage = chunk.usage

    def to_message(self) -> Message:
        """Build a complete Message from accumulated chunks."""
        text = "".join(self._text_parts) or None
        tool_calls: list[dict[str, Any]] | None = None
        if self._tool_calls:
            tool_calls = list(self._tool_calls.values())
            import json
            for tc in tool_calls:
                raw_args = tc["function"].get("arguments", "")
                if not raw_args:
                    tc["function"]["arguments"] = "{}"
                else:
                    try:
                        json.loads(raw_args)
                        tc["function"]["arguments"] = raw_args
                    except json.JSONDecodeError:
                        tc["function"]["arguments"] = json.dumps({"raw": raw_args})
        return Message(role="assistant", content=text, tool_calls=tool_calls)

    @property
    def usage(self) -> dict[str, Any]:
        return dict(self._usage)

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return list(self._tool_calls.values())


class ModelClient(ABC):
    """Abstract model client interface."""

    @abstractmethod
    def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: Optional[Iterable[ToolSpec]] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> ModelResponse:
        raise NotImplementedError

    def list_models(self) -> list[ModelInfo]:
        """List available models from the provider.

        Override in subclasses that support GET /v1/models.
        Default returns empty list for providers that don't support discovery.
        """
        return []

    def complete_stream(
        self,
        *,
        model: str,
        messages: list[Message],
        tools: Optional[Iterable[ToolSpec]] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> Iterator[StreamChunk]:
        """Stream model output as chunks. Default falls back to complete().

        Subclasses should override for native SSE streaming.
        """
        response = self.complete(
            model=model, messages=messages, tools=tools,
            temperature=temperature, stop=stop,
        )
        msg = response.message
        if msg.content:
            yield StreamChunk(type=ChunkType.TEXT, delta=msg.content)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn = tc.get("function", {})
                tid = tc.get("id", "")
                yield StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id=tid, tool_name=fn.get("name", ""))
                import json
                args = fn.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                yield StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id=tid, delta=args_str)
                yield StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id=tid)
        if response.usage:
            yield StreamChunk(type=ChunkType.USAGE, usage=response.usage)
        yield StreamChunk(type=ChunkType.DONE)