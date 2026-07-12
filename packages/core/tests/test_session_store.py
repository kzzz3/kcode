from __future__ import annotations

import time
from pathlib import Path

import pytest

from packages.core.src.runtime.session import SessionStore


def test_session_roundtrip(tmp_path: Path) -> None:
  store = SessionStore(tmp_path / "s.sqlite")
  session = store.create_session(workspace_root=tmp_path)
  msg = store.append_message(session.id, "user", "hello")
  run = store.record_tool_start(session.id, "echo", {"x": 1}, message_id=msg.id)
  run = store.record_tool_completion(run.id, {"ok": True})

  assert store.get_session(session.id) is not None
  assert len(store.get_messages(session.id)) == 1
  runs = store.get_tool_runs(session.id)
  assert len(runs) == 1
  assert runs[0].status == "completed"


def test_list_sessions_respects_limit(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "limit.sqlite")
    for _ in range(3):
        store.create_session(workspace_root=tmp_path)

    assert len(store.list_sessions(limit=2)) == 2


def test_get_latest_session_returns_none_when_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.core.src.runtime.session as session_mod

    store = SessionStore(tmp_path / "age.sqlite")
    fixed_now = time.time()
    monkeypatch.setattr(session_mod, "_now", lambda: fixed_now)
    store.create_session(workspace_root=tmp_path)

    monkeypatch.setattr(session_mod, "_now", lambda: fixed_now + 9999)

    assert store.get_latest_session(workspace_root=tmp_path, max_age_seconds=1) is None


def test_get_latest_session_returns_session_when_fresh(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "fresh.sqlite")
    expected = store.create_session(workspace_root=tmp_path)

    actual = store.get_latest_session(workspace_root=tmp_path, max_age_seconds=3600)
    assert actual is not None
    assert actual.id == expected.id


def test_get_latest_session_filters_workspace(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "ws.sqlite")
    store.create_session(workspace_root=tmp_path)

    other = tmp_path / "other"
    other.mkdir()
    assert store.get_latest_session(workspace_root=other) is None


def test_get_messages_respects_limit(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "msg_limit.sqlite")
    session = store.create_session(workspace_root=tmp_path)
    for i in range(5):
        store.append_message(session.id, "user", f"m{i}")

    messages = store.get_messages(session.id, limit=3)
    assert len(messages) == 3
    assert [m.content for m in messages] == ["m0", "m1", "m2"]


def test_get_tool_runs_orders_by_start_time(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "tool_order.sqlite")
    session = store.create_session(workspace_root=tmp_path)
    first = store.record_tool_start(session.id, "alpha", {})
    second = store.record_tool_start(session.id, "beta", {})
    store.record_tool_completion(first.id, {"a": 1})
    store.record_tool_completion(second.id, {"b": 1}, status="failed")

    runs = store.get_tool_runs(session.id)
    assert [r.tool_name for r in runs] == ["alpha", "beta"]
    assert [r.status for r in runs] == ["completed", "failed"]
