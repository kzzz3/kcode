from __future__ import annotations

import pytest
from packages.core.src.models.interfaces import StreamChunk, ChunkType

from apps.cli.src.commands.chat import ApprovalMode, _approval_handler, _stream_to_terminal
from packages.core.src.runtime.contracts import AgentSnapshot, AgentState


def test_approval_handler_auto_approves_all() -> None:
  handler = _approval_handler(ApprovalMode.auto)
  assert handler("create_file", "write", {"path": "x"}) is True
  assert handler("run_command", "system", {"command": "ls"}) is True


def test_approval_handler_manual_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
  handler = _approval_handler(ApprovalMode.manual)
  monkeypatch.setattr("apps.cli.src.commands.chat.Confirm.ask", lambda *a, **k: True)
  assert handler("create_file", "write", {"path": "x"}) is True


def test_approval_handler_manual_denies(monkeypatch: pytest.MonkeyPatch) -> None:
  handler = _approval_handler(ApprovalMode.manual)
  monkeypatch.setattr("apps.cli.src.commands.chat.Confirm.ask", lambda *a, **k: False)
  assert handler("run_command", "system", {"command": "rm -rf /"}) is False


def test_stream_to_terminal_collects_text_and_usage() -> None:
  chunks = [
    StreamChunk(type=ChunkType.TEXT, delta="hi"),
    StreamChunk(type=ChunkType.USAGE, usage={"tokens": 1}),
    AgentSnapshot(state=AgentState.FINISHED, step_index=1, messages=[], tool_runs=[], metadata={}),
  ]

  result = _stream_to_terminal(chunks)
  assert "hi" in result["text"]
  assert result["usage"] == {"tokens": 1}
  assert result["snapshot"] is not None
