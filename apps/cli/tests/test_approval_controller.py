"""Tests for ApprovalController."""
from __future__ import annotations

from apps.cli.src.tui.controllers.approval_controller import ApprovalController


def test_auto_approve():
    controller = ApprovalController(mode="auto")
    assert controller.request("run_command", "system", {"cmd": "echo hi"}) is True


def test_manual_approve_when_callback_returns_true():
    def fake(req):
        return True

    controller = ApprovalController(mode="manual", ask_approval=fake)
    assert controller.request("run_command", "system", {"cmd": "ls"}) is True


def test_manual_deny_when_callback_returns_false():
    def fake(req):
        return False

    controller = ApprovalController(mode="manual", ask_approval=fake)
    assert controller.request("write_file", "write", {"path": "x"}) is False


def test_manual_deny_when_no_callback():
    controller = ApprovalController(mode="manual")
    assert controller.request("write_file", "write", {"path": "x"}) is False
