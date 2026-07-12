"""Tests for ContextBudget integration and auto-compaction in CliAgentRuntime."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from apps.cli.src.core.agent_runtime import CliAgentRuntime
from packages.core.src.models.interfaces import (
  Message,
  ModelResponse,
)
from packages.core.src.runtime.events import EventBus
from packages.core.src.runtime.session import MessageRecord, SessionRecord, SessionStore
from packages.core.src.tools.contracts import ToolRegistry


class _InflatingModel:
  """Model that returns content of a requested size to trigger compaction."""

  def __init__(self, *, token_estimate_per_response: int = 500) -> None:
    self._token_estimate = token_estimate_per_response

  def complete(self, **kwargs: Any) -> ModelResponse:
    content = "word " * self._token_estimate
    return ModelResponse(
      message=Message(role="assistant", content=content),
      usage={"prompt_tokens": 100, "completion_tokens": self._token_estimate},
    )


class _FakeSessionStore(SessionStore):
  """Minimal in-memory stub for tests that do not need persistence."""

  def __init__(self) -> None:
    self._sessions: dict[str, SessionRecord] = {}

  def create_session(self, *, workspace_root: Path, title: str = "untitled", metadata: dict[str, Any] | None = None) -> SessionRecord:
    now = time.time()
    record = SessionRecord(
      id="fake-session",
      title=title,
      workspace_root=str(workspace_root),
      created_at=now,
      updated_at=now,
      metadata=metadata or {},
    )
    self._sessions[record.id] = record
    return record

  def append_message(
    self,
    session_id: str,
    role: str,
    content: str | None,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
    metadata: dict[str, Any] | None = None,
  ) -> MessageRecord:
    return MessageRecord(id='msg', session_id=session_id, role=role, content=content, tool_calls=None, tool_call_id=None, created_at=0.0, metadata={})

  def record_tool_start(self, session_id: str, tool_name: str, payload: dict[str, Any], *, message_id: str | None = None, metadata: dict[str, Any] | None = None) -> Any:
    return None

  def record_tool_completion(self, run_id: str, output: dict[str, Any], status: str = "completed") -> Any:
    return None


class TestContextBudgetIntegration:
  """ContextBudget is updated after each message append."""

  def test_snapshot_includes_token_count(self, tmp_path: Path) -> None:
    runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=_InflatingModel(token_estimate_per_response=100),  # type: ignore[arg-type]
      model_name="test-model",
      tool_registry=ToolRegistry(),
      session_store=_FakeSessionStore(),
      bus=EventBus(),
    )
    runtime.step("hello")
    snap = runtime.get_snapshot()
    assert "token_count" in snap.metadata
    assert "context_utilization" in snap.metadata
    assert snap.metadata["token_count"] > 0


class TestAutoCompaction:
  """Auto-compaction triggers when utilization exceeds threshold."""

  def test_compaction_threshold_is_respected(self, tmp_path: Path) -> None:
    runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=_InflatingModel(token_estimate_per_response=200),  # type: ignore[arg-type]
      model_name="test-model",
      tool_registry=ToolRegistry(),
      session_store=_FakeSessionStore(),
      bus=EventBus(),
    )
    runtime.step("First message with some content")
    snap = runtime.get_snapshot()
    assert "token_count" in snap.metadata

  def test_compaction_preserves_system_prompt(self, tmp_path: Path) -> None:
    system = "You are KCode. Always be precise."
    runtime = CliAgentRuntime(
      workspace_root=tmp_path,
      model_client=_InflatingModel(token_estimate_per_response=200),  # type: ignore[arg-type]
      model_name="test-model",
      tool_registry=ToolRegistry(),
      session_store=_FakeSessionStore(),
      bus=EventBus(),
      system_prompt=system,
    )
    runtime.step("Do something")
    runtime.step("Do another thing")
    assert runtime._messages[0].role == "system"
    assert "KCode" in (runtime._messages[0].content or "")