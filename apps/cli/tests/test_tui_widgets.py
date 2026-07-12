"""Tests for TUI widgets."""
from __future__ import annotations

import pytest


# --- StatusBar tests ---

class TestStatusBar:
  def test_default_state(self):
    from apps.cli.src.tui.widgets.status_bar import StatusBar
    bar = StatusBar()
    assert bar.state == "IDLE"
    assert bar.tokens == 0
    assert bar.model_name == ""

  def test_update_status_keywords_only(self):
    from apps.cli.src.tui.widgets.status_bar import StatusBar
    bar = StatusBar()
    bar.update_status(state="THINKING", tokens=1234, model_name="gpt-4o")
    assert bar.state == "THINKING"
    assert bar.tokens == 1234
    assert bar.model_name == "gpt-4o"

  def test_render_shows_parts(self):
    from apps.cli.src.tui.widgets.status_bar import StatusBar
    bar = StatusBar()
    bar.update_status(state="IDLE", model_name="gpt-4o")
    text = bar.render()
    assert "IDLE" in text
    assert "gpt-4o" in text

  def test_render_hides_zero_tokens(self):
    from apps.cli.src.tui.widgets.status_bar import StatusBar
    bar = StatusBar()
    text = bar.render()
    assert "Tokens" not in text


# --- InputArea tests ---

class TestInputArea:
  def test_submitted_message(self):
    from apps.cli.src.tui.widgets.input_area import InputArea
    msg = InputArea.Submitted("hello world")
    assert msg.value == "hello world"


# --- ChatArea tests ---

class TestChatArea:
  def test_submitted_message_fields(self):
    from apps.cli.src.tui.widgets.chat_area import ChatArea
    msg = ChatArea.Submitted("content", "user")
    assert msg.content == "content"
    assert msg.role == "user"

  def test_stream_buffer_starts_empty(self):
    from apps.cli.src.tui.widgets.chat_area import ChatArea
    area = ChatArea()
    assert area._stream_parts == []
    assert area._stream_role == ""

  def test_cancel_stream_clears_buffer(self):
    from apps.cli.src.tui.widgets.chat_area import ChatArea
    area = ChatArea()
    area.start_stream("assistant")
    area.add_stream_chunk("hello")
    assert len(area._stream_parts) == 1
    area.cancel_stream()
    assert area._stream_parts == []
    assert area._stream_role == ""


# --- SessionPanel tests ---

class TestSessionPanel:
  def test_session_selected_message(self):
    from apps.cli.src.tui.widgets.session_panel import SessionPanel
    msg = SessionPanel.SessionSelected("abc123")
    assert msg.session_id == "abc123"

  def test_new_session_message(self):
    from apps.cli.src.tui.widgets.session_panel import SessionPanel
    msg = SessionPanel.NewSession()
    assert msg is not None

  def test_refresh_sessions_message(self):
    from apps.cli.src.tui.widgets.session_panel import SessionPanel
    msg = SessionPanel.RefreshSessions()
    assert msg is not None


# --- ApprovalDialog tests ---

class TestApprovalDialog:
  def test_dialog_fields(self):
    from apps.cli.src.tui.widgets.approval_dialog import ApprovalDialog
    dialog = ApprovalDialog("run_command", {"cmd": "ls"}, "system")
    assert dialog.tool_name == "run_command"
    assert dialog.tool_args == {"cmd": "ls"}
    assert dialog.safety_class == "system"


# --- message_formatter tests ---

class TestMessageFormatter:
  def test_format_user_message(self):
    from apps.cli.src.tui.utils.message_formatter import format_user_message
    panel = format_user_message("hello")
    assert panel is not None

  def test_format_assistant_message(self):
    from apps.cli.src.tui.utils.message_formatter import format_assistant_message
    panel = format_assistant_message("**bold** text")
    assert panel is not None

  def test_format_tool_call(self):
    from apps.cli.src.tui.utils.message_formatter import format_tool_call
    text = format_tool_call("run_command")
    assert text is not None

  def test_format_tool_result_success(self):
    from apps.cli.src.tui.utils.message_formatter import format_tool_result
    text = format_tool_result("read_file", "file contents here")
    assert text is not None

  def test_format_tool_result_error(self):
    from apps.cli.src.tui.utils.message_formatter import format_tool_result
    text = format_tool_result("read_file", "not found", is_error=True)
    assert text is not None

  def test_format_code_block(self):
    from apps.cli.src.tui.utils.message_formatter import format_code_block
    syntax = format_code_block("print('hi')", "python")
    assert syntax is not None
