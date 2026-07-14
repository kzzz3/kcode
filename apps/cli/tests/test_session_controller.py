"""Tests for SessionController."""
from __future__ import annotations

from unittest.mock import MagicMock

from apps.cli.src.tui.controllers.session_controller import SessionController, SessionInfo
from packages.core.src.runtime.session import SessionRecord


def _make_session_record(sid: str = "abc123", title: str = "Test") -> SessionRecord:
  return SessionRecord(
    id=sid,
    title=title,
    workspace_root="/tmp/ws",
    created_at=1000.0,
    updated_at=2000.0,
    metadata={},
  )


class TestSessionControllerRefresh:
  def test_refresh_calls_on_sessions_changed(self) -> None:
    runtime = MagicMock()
    runtime.session = MagicMock()
    runtime.session.session_id = "current"
    runtime.session_store.list_sessions.return_value = [
      _make_session_record("abc", "Session 1"),
      _make_session_record("def", "Session 2"),
    ]

    changed: list[list[SessionInfo]] = []
    sc = SessionController(runtime, on_sessions_changed=lambda infos: changed.append(infos))
    sc.refresh()

    assert len(changed) == 1
    assert len(changed[0]) == 2
    assert changed[0][0].id == "abc"
    assert changed[0][0].title == "Session 1"
    assert changed[0][0].is_current is False
    assert changed[0][1].id == "def"

  def test_refresh_marks_current_session(self) -> None:
    runtime = MagicMock()
    runtime.session = MagicMock()
    runtime.session.session_id = "abc"
    runtime.session_store.list_sessions.return_value = [
      _make_session_record("abc", "Current"),
      _make_session_record("def", "Other"),
    ]

    changed: list[list[SessionInfo]] = []
    sc = SessionController(runtime, on_sessions_changed=lambda infos: changed.append(infos))
    sc.refresh()

    assert changed[0][0].is_current is True
    assert changed[0][1].is_current is False

  def test_refresh_no_current_session(self) -> None:
    runtime = MagicMock()
    runtime.session = None
    runtime.session_store.list_sessions.return_value = [_make_session_record("abc")]

    changed: list[list[SessionInfo]] = []
    sc = SessionController(runtime, on_sessions_changed=lambda infos: changed.append(infos))
    sc.refresh()

    assert changed[0][0].is_current is False

  def test_refresh_handles_error(self) -> None:
    runtime = MagicMock()
    runtime.session = None
    runtime.session_store.list_sessions.side_effect = RuntimeError("db error")

    errors: list[str] = []
    sc = SessionController(runtime, on_error=lambda msg: errors.append(msg))
    sc.refresh()

    assert len(errors) == 1
    assert "db error" in errors[0]


class TestSessionControllerCreateNew:
  def test_create_new_calls_runtime_and_refreshes(self) -> None:
    runtime = MagicMock()
    runtime.session = MagicMock()
    runtime.session.session_id = "new-id"
    runtime.session_store.list_sessions.return_value = []

    loaded: list[tuple[str, list]] = []
    sc = SessionController(
      runtime,
      on_session_loaded=lambda sid, msgs: loaded.append((sid, msgs)),
    )
    sc.create_new()

    runtime.new_session.assert_called_once()
    assert len(loaded) == 1
    assert loaded[0] == ("", [])  # empty chat for new session

  def test_create_new_handles_error(self) -> None:
    runtime = MagicMock()
    runtime.new_session.side_effect = RuntimeError("create failed")

    errors: list[str] = []
    sc = SessionController(runtime, on_error=lambda msg: errors.append(msg))
    sc.create_new()

    assert len(errors) == 1
    assert "create failed" in errors[0]


class TestSessionControllerLoad:
  def test_load_replays_messages(self) -> None:
    runtime = MagicMock()
    mock_session = MagicMock()
    mock_session.messages = [
      {"role": "user", "content": "hello"},
      {"role": "assistant", "content": "hi there"},
      {"role": "user", "content": ""},  # should be skipped
      {"role": "tool", "content": "tool output"},  # should be skipped
    ]
    runtime.load_session.return_value = mock_session
    runtime.session = MagicMock()
    runtime.session.session_id = "loaded-id"
    runtime.session_store.list_sessions.return_value = []

    loaded: list[tuple[str, list]] = []
    sc = SessionController(
      runtime,
      on_session_loaded=lambda sid, msgs: loaded.append((sid, msgs)),
    )
    sc.load("loaded-id")

    assert len(loaded) == 1
    sid, messages = loaded[0]
    assert sid == "loaded-id"
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "hello"}
    assert messages[1] == {"role": "assistant", "content": "hi there"}

  def test_load_handles_error(self) -> None:
    runtime = MagicMock()
    runtime.load_session.side_effect = RuntimeError("not found")

    errors: list[str] = []
    sc = SessionController(runtime, on_error=lambda msg: errors.append(msg))
    sc.load("bad-id")

    assert len(errors) == 1
    assert "not found" in errors[0]


class TestSessionControllerGetSessionData:
  def test_get_session_data_returns_dicts(self) -> None:
    runtime = MagicMock()
    runtime.session = MagicMock()
    runtime.session.session_id = "abc"
    runtime.session_store.list_sessions.return_value = [
      _make_session_record("abc", "Session A"),
    ]

    sc = SessionController(runtime)
    data = sc.get_session_data()

    assert len(data) == 1
    assert data[0]["id"] == "abc"
    assert data[0]["title"] == "Session A"
    assert data[0]["is_current"] is True


class TestSessionControllerSessionId:
  def test_current_session_id_when_active(self) -> None:
    runtime = MagicMock()
    runtime.session = MagicMock()
    runtime.session.session_id = "xyz"

    sc = SessionController(runtime)
    assert sc.current_session_id == "xyz"

  def test_current_session_id_when_none(self) -> None:
    runtime = MagicMock()
    runtime.session = None

    sc = SessionController(runtime)
    assert sc.current_session_id is None
