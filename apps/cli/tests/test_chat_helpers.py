"""Tests for apps.cli.src.commands.chat helper functions."""
from __future__ import annotations

from typing import Any

from apps.cli.src.commands.chat import (
    ApprovalMode,
    _approval_handler,
    _estimate_cost,
    _format_usage_line,
    _stream_to_terminal,
)
from packages.core.src.models.interfaces import ChunkType, StreamChunk
from packages.core.src.runtime.contracts import AgentSnapshot, AgentState


def test_estimate_cost_gpt4o() -> None:
    # GPT-4o: $2.50 input, $10.00 output per 1M tokens
    cost = _estimate_cost("gpt-4o", 1000, 2000)
    assert cost is not None
    assert abs(cost - 0.0225) < 1e-6  # (1000*2.5 + 2000*10) / 1M


def test_estimate_cost_unknown_model() -> None:
    cost = _estimate_cost("unknown-model", 1000, 2000)
    assert cost is None


def test_format_usage_line_with_cost() -> None:
    usage = {"prompt_tokens": 100, "completion_tokens": 200}
    line = _format_usage_line(usage, "gpt-4o")
    assert "100 in / 200 out" in line
    assert "~$" in line


def test_format_usage_line_without_cost() -> None:
    usage = {"prompt_tokens": 100, "completion_tokens": 200}
    line = _format_usage_line(usage, "unknown-model")
    assert "100 in / 200 out" in line
    assert "~$" not in line


def test_format_usage_line_zero_tokens() -> None:
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    line = _format_usage_line(usage, "gpt-4o")
    assert "0 in / 0 out" in line


def test_approval_mode_enum_values() -> None:
    assert ApprovalMode.manual.value == "manual"
    assert ApprovalMode.auto.value == "auto"


def test_approval_handler_auto_approves() -> None:
    handler = _approval_handler(ApprovalMode.auto)
    assert callable(handler)
    result = handler("create_file", "write", {"path": "test.py"})
    assert result is True


def test_approval_handler_auto_approves_system() -> None:
    handler = _approval_handler(ApprovalMode.auto)
    result = handler("run_command", "system", {"command": "ls"})
    assert result is True


def test_approval_handler_manual_is_callable() -> None:
    handler = _approval_handler(ApprovalMode.manual)
    assert callable(handler)


def test_approval_handler_manual_prompts(monkeypatch: Any) -> None:
    """Manual mode calls Confirm.ask — simulate user saying yes."""
    from unittest.mock import patch

    handler = _approval_handler(ApprovalMode.manual)
    with patch("apps.cli.src.commands.chat.Confirm.ask", return_value=True):
        result = handler("edit_file", "write", {"path": "test.py"})
    assert result is True


def test_approval_handler_manual_denies(monkeypatch: Any) -> None:
    """Manual mode — user says no."""
    from unittest.mock import patch

    handler = _approval_handler(ApprovalMode.manual)
    with patch("apps.cli.src.commands.chat.Confirm.ask", return_value=False):
        result = handler("run_command", "system", {"command": "rm -rf /"})
    assert result is False


def test_stream_to_terminal_text_chunks(capsys: Any) -> None:
    def chunk_iter():
        yield StreamChunk(type=ChunkType.TEXT, delta="Hello ")
        yield StreamChunk(type=ChunkType.TEXT, delta="world!")
        yield StreamChunk(type=ChunkType.DONE)

    result = _stream_to_terminal(chunk_iter(), model="gpt-4o")
    assert result["text"] == "Hello world!"
    captured = capsys.readouterr()
    assert "Hello world!" in captured.out


def test_stream_to_terminal_tool_calls(capsys: Any) -> None:
    def chunk_iter():
        yield StreamChunk(type=ChunkType.TOOL_CALL_START, tool_call_id="call_1", tool_name="read_file")
        yield StreamChunk(type=ChunkType.TOOL_CALL_ARGS, tool_call_id="call_1", delta='{"path": "test.py"}')
        yield StreamChunk(type=ChunkType.TOOL_CALL_END, tool_call_id="call_1")
        yield StreamChunk(type=ChunkType.DONE)

    _stream_to_terminal(chunk_iter(), model="gpt-4o")
    captured = capsys.readouterr()
    assert "tool:" in captured.out
    assert "read_file" in captured.out


def test_stream_to_terminal_with_usage(capsys: Any) -> None:
    def chunk_iter():
        yield StreamChunk(type=ChunkType.TEXT, delta="ok")
        yield StreamChunk(type=ChunkType.USAGE, usage={"prompt_tokens": 10, "completion_tokens": 20})
        yield StreamChunk(type=ChunkType.DONE)

    result = _stream_to_terminal(chunk_iter(), model="gpt-4o")
    assert result["usage"]["prompt_tokens"] == 10
    captured = capsys.readouterr()
    assert "tokens:" in captured.out


def test_stream_to_terminal_with_snapshot() -> None:
    snapshot = AgentSnapshot(
        state=AgentState.FINISHED,
        step_index=0,
        messages=[{"role": "assistant", "content": "done"}],
        tool_runs=[],
        metadata={"session_id": "test-123", "context_utilization": 0.75},
    )

    def chunk_iter():
        yield StreamChunk(type=ChunkType.TEXT, delta="done")
        yield snapshot
        yield StreamChunk(type=ChunkType.DONE)

    result = _stream_to_terminal(chunk_iter(), model="gpt-4o")
    assert result["snapshot"] is not None
    assert result["snapshot"].metadata["session_id"] == "test-123"


def test_stream_to_terminal_empty_iterator() -> None:
    def chunk_iter():
        yield from ()

    result = _stream_to_terminal(chunk_iter(), model="gpt-4o")
    assert result["text"] == ""
    assert result["usage"] == {}
    assert result["snapshot"] is None
