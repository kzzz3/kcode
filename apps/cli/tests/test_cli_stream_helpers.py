from __future__ import annotations

from packages.core.src.models.interfaces import ChunkType, StreamChunk
from apps.cli.src.commands.chat import _stream_to_terminal


def test_stream_to_terminal_collects_text() -> None:
    def iterator():
        yield StreamChunk(type=ChunkType.TEXT, delta="a")
        yield StreamChunk(type=ChunkType.TEXT, delta="b")
        yield StreamChunk(type=ChunkType.DONE)

    result = _stream_to_terminal(iterator())
    assert result["text"] == "ab"


def test_stream_to_terminal_records_usage() -> None:
    usage = {"prompt_tokens": 3}

    def iterator():
        yield StreamChunk(type=ChunkType.USAGE, usage=usage)
        yield StreamChunk(type=ChunkType.DONE)

    result = _stream_to_terminal(iterator())
    assert result["usage"] is usage
