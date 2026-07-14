"""Tests for ToolController."""
from __future__ import annotations

from unittest.mock import MagicMock

from apps.cli.src.tui.controllers.tool_controller import ToolController
from apps.cli.src.tui.controllers.approval_controller import ApprovalController


def _make_tc(**kwargs):
  runtime = MagicMock()
  runtime._workspace_root = None
  runtime._model_name = "gpt-4o"
  approval = ApprovalController(mode="manual")
  return ToolController(runtime, approval, **kwargs), runtime, approval


def test_dispatch_slash_returns_action_ids():
  tc, _, _ = _make_tc()
  assert tc.dispatch_slash("model_picker") == "open_model_picker"
  assert tc.dispatch_slash("help") == "show_help"
  assert tc.dispatch_slash("clear") == "clear_chat"
  assert tc.dispatch_slash("sessions") == "list_sessions"
  assert tc.dispatch_slash("theme") == "cycle_theme"
  assert tc.dispatch_slash("sidebar") == "toggle_sidebar"


def test_dispatch_slash_compact_calls_runtime():
  tc, rt, _ = _make_tc()
  rt.compact.return_value = True
  result = tc.dispatch_slash("compact")
  assert result is None
  rt.compact.assert_called_once()


def test_dispatch_slash_doctor_runs():
  tc, _, _ = _make_tc()
  result = tc.dispatch_slash("doctor")
  assert result is None


def test_list_models_fallback():
  tc, rt, _ = _make_tc()
  rt._model_name = "test-model"
  models = tc.list_models()
  assert models == ["test-model"]


def test_current_model_property():
  tc, rt, _ = _make_tc()
  rt._model_name = "my-model"
  assert tc.current_model == "my-model"


def test_set_model():
  changed = []
  tc, rt, _ = _make_tc(on_model_changed=lambda m: changed.append(m))
  tc.set_model("new-model")
  assert rt._model_name == "new-model"
  assert changed == ["new-model"]


def test_toggle_approval_manual_to_auto():
  toggled = []
  tc, _, approval = _make_tc(on_approval_toggled=lambda m: toggled.append(m))
  assert approval.mode == "manual"
  tc.toggle_approval()
  assert approval.mode == "auto"
  assert toggled == ["auto"]


def test_toggle_approval_auto_to_manual():
  toggled = []
  tc, _, approval = _make_tc(on_approval_toggled=lambda m: toggled.append(m))
  approval.mode = "auto"
  tc.toggle_approval()
  assert approval.mode == "manual"
  assert toggled == ["manual"]


def test_compact_context_success():
  notified = []
  tc, rt, _ = _make_tc(on_notify=lambda msg, sev: notified.append((msg, sev)))
  rt.compact.return_value = True
  tc.compact_context()
  assert ("Context compacted", "info") in notified


def test_compact_context_nothing():
  notified = []
  tc, rt, _ = _make_tc(on_notify=lambda msg, sev: notified.append((msg, sev)))
  rt.compact.return_value = False
  tc.compact_context()
  assert ("Nothing to compact", "info") in notified


def test_compact_context_error():
  notified = []
  tc, rt, _ = _make_tc(on_notify=lambda msg, sev: notified.append((msg, sev)))
  rt.compact.side_effect = RuntimeError("boom")
  tc.compact_context()
  assert any("boom" in msg for msg, _ in notified)
