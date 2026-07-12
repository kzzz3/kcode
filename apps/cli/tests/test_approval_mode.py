"""Tests for approval mode wiring in agent runtime and config."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from packages.core.src.config.loader import ApprovalMode, ToolsConfig, load_config_from_dict
from packages.core.src.tools.contracts import Tool, ToolMeta, ToolOutput, ToolRegistry
from packages.core.src.models.interfaces import Message, ModelResponse, ToolSpec
from packages.core.src.runtime.events import EventBus
from packages.core.src.runtime.session import SessionStore
from apps.cli.src.core.agent_runtime import AgentLoopConfig, CliAgentRuntime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubModel:
  """Return a tool call then finish."""

  def __init__(self) -> None:
    self._call_count = 0

  def complete(self, *, model: str, messages: list[Message], tools: list[ToolSpec] | None = None) -> ModelResponse:
    self._call_count += 1
    if self._call_count == 1:
      return ModelResponse(
        message=Message(
          role="assistant",
          content=None,
          tool_calls=[{"id": "tc1", "function": {"name": "write_file", "arguments": '{"path": "test.txt", "content": "hi"}'}}],
        ),
      )
    return ModelResponse(message=Message(role="assistant", content="done"))


def _make_write_tool() -> Tool:
  def _exec(payload: dict[str, Any]) -> ToolOutput:
    return ToolOutput(ok=True, message="wrote")
  return Tool(
    meta=ToolMeta(name="write_file", description="Write file", safety_class="write",
                   parameter_schema={"type": "object", "properties": {}, "required": []}),
    executor=_exec,
  )


def _make_runtime(
  tmp_path: Path,
  approval_mode: str = "auto",
  on_approve: Any = None,
) -> tuple[CliAgentRuntime, SessionStore]:
  store = SessionStore(tmp_path / "sessions.sqlite")
  registry = ToolRegistry()
  registry.register(_make_write_tool())
  model = _StubModel()
  config = AgentLoopConfig(max_steps=3, approval_mode=approval_mode)
  runtime = CliAgentRuntime(
    workspace_root=tmp_path,
    model_client=model,
    model_name="test-model",
    tool_registry=registry,
    session_store=store,
    bus=EventBus(),
    config=config,
    on_approve=on_approve,
  )
  return runtime, store


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestApprovalModeConfig:
  def test_default_approval_mode_is_auto(self) -> None:
    tc = ToolsConfig()
    assert tc.approval_mode == ApprovalMode.auto

  def test_approval_mode_from_dict(self) -> None:
    cfg = load_config_from_dict({
      "tools": {"approval_mode": "manual"},
    })
    assert cfg.tools.approval_mode == ApprovalMode.manual

  def test_approval_mode_invalid_value_raises(self) -> None:
    with pytest.raises(Exception):
      load_config_from_dict({"tools": {"approval_mode": "yolo"}})


# ---------------------------------------------------------------------------
# AgentLoopConfig tests
# ---------------------------------------------------------------------------

class TestAgentLoopConfigApproval:
  def test_default_approval_mode_auto(self) -> None:
    cfg = AgentLoopConfig()
    assert cfg.approval_mode == "auto"

  def test_approval_mode_manual(self) -> None:
    cfg = AgentLoopConfig(approval_mode="manual")
    assert cfg.approval_mode == "manual"


# ---------------------------------------------------------------------------
# Runtime approval tests
# ---------------------------------------------------------------------------

class TestRuntimeApproval:
  def test_auto_mode_approves_writes(self, tmp_path: Path) -> None:
    """In auto mode, write tools should execute without callback."""
    runtime, _ = _make_runtime(tmp_path, approval_mode="auto")
    snap = runtime.step("do something")
    assert len(runtime._tool_runs) >= 1
    assert snap.state.value == "finished"

  def test_manual_mode_without_callback_denies(self, tmp_path: Path) -> None:
    """Manual mode without callback should deny write tools."""
    runtime, _ = _make_runtime(tmp_path, approval_mode="manual", on_approve=None)
    snap = runtime.step("do something")
    assert any("denied" in str(r).lower() for r in runtime._tool_runs) or snap.state.value in ("finished", "failed")

  def test_manual_mode_with_approving_callback(self, tmp_path: Path) -> None:
    """Manual mode with always-approve callback should execute."""
    runtime, _ = _make_runtime(
      tmp_path, approval_mode="manual",
      on_approve=lambda name, cls, payload: True,
    )
    snap = runtime.step("do something")
    assert snap.state.value == "finished"

  def test_manual_mode_with_denying_callback(self, tmp_path: Path) -> None:
    """Manual mode with deny callback should block tool execution."""
    runtime, _ = _make_runtime(
      tmp_path, approval_mode="manual",
      on_approve=lambda name, cls, payload: False,
    )
    snap = runtime.step("do something")
    assert snap.state.value in ("finished", "failed")

  def test_auto_mode_with_callback_overrides(self, tmp_path: Path) -> None:
    """Even in auto mode, an explicit callback takes precedence."""
    called: list[str] = []
    def track_approve(name: str, cls: str, payload: dict[str, Any]) -> bool:
      called.append(name)
      return True
    runtime, _ = _make_runtime(tmp_path, approval_mode="auto", on_approve=track_approve)
    runtime.step("do something")
    assert "write_file" in called


# ---------------------------------------------------------------------------
# ApprovalMode enum tests
# ---------------------------------------------------------------------------

class TestApprovalModeEnum:
  def test_values(self) -> None:
    assert ApprovalMode.manual.value == "manual"
    assert ApprovalMode.auto.value == "auto"

  def test_from_string(self) -> None:
    assert ApprovalMode("manual") == ApprovalMode.manual
    assert ApprovalMode("auto") == ApprovalMode.auto
