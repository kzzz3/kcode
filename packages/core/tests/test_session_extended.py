"""Extended tests for packages/core/src/runtime/session.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from packages.core.src.runtime.session import SessionStore


def _frozen_time() -> float:
    return 1700000000.0


def test_get_latest_session_returns_none_when_stale(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        store.create_session(workspace_root=tmp_path, title="old")

    # Now pretend it's 2 days later
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time() + 200_000):
        result = store.get_latest_session(workspace_root=tmp_path, max_age_seconds=86400)
    assert result is None
    store.close()


def test_get_latest_session_returns_recent_session(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        sess = store.create_session(workspace_root=tmp_path, title="recent")

    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time() + 60):
        result = store.get_latest_session(workspace_root=tmp_path, max_age_seconds=86400)
    assert result is not None
    assert result.id == sess.id
    store.close()


def test_get_latest_session_wrong_workspace_returns_none(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        store.create_session(workspace_root=tmp_path, title="ws1")

    other = tmp_path / "other"
    other.mkdir()
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        result = store.get_latest_session(workspace_root=other)
    assert result is None
    store.close()


def test_list_sessions_respects_limit(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        for i in range(5):
            store.create_session(workspace_root=tmp_path, title=f"s{i}")

    result = store.list_sessions(limit=3)
    assert len(result) == 3
    store.close()


def test_record_tool_start_and_completion(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        sess = store.create_session(workspace_root=tmp_path)
        run = store.record_tool_start(sess.id, "my_tool", {"a": 1})
        assert run.status == "running"
        assert run.output is None

        completed = store.record_tool_completion(run.id, {"result": "ok"})
        assert completed.status == "completed"
        assert completed.output == {"result": "ok"}
    store.close()


def test_record_tool_completion_raises_on_missing_run(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    try:
        store.record_tool_completion("nonexistent_id", {"r": 1})
        assert False, "Should have raised"
    except KeyError:
        pass
    store.close()


def test_get_messages_with_limit(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    with patch("packages.core.src.runtime.session._now", return_value=_frozen_time()):
        sess = store.create_session(workspace_root=tmp_path)
        for i in range(10):
            store.append_message(sess.id, "user", f"msg {i}")

    msgs = store.get_messages(sess.id, limit=3)
    assert len(msgs) == 3
    store.close()


def test_get_messages_ordered_by_creation(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    base = _frozen_time()
    with patch("packages.core.src.runtime.session._now", return_value=base):
        sess = store.create_session(workspace_root=tmp_path)
    with patch("packages.core.src.runtime.session._now", return_value=base + 1):
        store.append_message(sess.id, "user", "first")
    with patch("packages.core.src.runtime.session._now", return_value=base + 2):
        store.append_message(sess.id, "assistant", "second")

    msgs = store.get_messages(sess.id)
    assert [m.content for m in msgs] == ["first", "second"]
    store.close()


def test_append_message_updates_session_timestamp(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    base = _frozen_time()
    with patch("packages.core.src.runtime.session._now", return_value=base):
        sess = store.create_session(workspace_root=tmp_path)

    with patch("packages.core.src.runtime.session._now", return_value=base + 500):
        store.append_message(sess.id, "user", "hello")

    updated = store.get_session(sess.id)
    assert updated is not None
    assert updated.updated_at == base + 500
    store.close()


def test_get_tool_runs_returns_all(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "s.sqlite")
    base = _frozen_time()
    with patch("packages.core.src.runtime.session._now", return_value=base):
        sess = store.create_session(workspace_root=tmp_path)
        r1 = store.record_tool_start(sess.id, "tool_a", {"x": 1})
        r2 = store.record_tool_start(sess.id, "tool_b", {"y": 2})
        store.record_tool_completion(r1.id, {"done": True})
        store.record_tool_completion(r2.id, {"done": True})

    runs = store.get_tool_runs(sess.id)
    assert len(runs) == 2
    assert {r.tool_name for r in runs} == {"tool_a", "tool_b"}
    store.close()
