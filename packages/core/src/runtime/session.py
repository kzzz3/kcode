"""Persistent session storage for agent conversations."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  workspace_root TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT,
  tool_calls TEXT,
  tool_call_id TEXT,
  created_at REAL NOT NULL,
  metadata TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at, id);

CREATE TABLE IF NOT EXISTS tool_runs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  message_id TEXT,
  tool_name TEXT NOT NULL,
  input TEXT NOT NULL,
  output TEXT,
  status TEXT NOT NULL,
  started_at REAL NOT NULL,
  completed_at REAL,
  metadata TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tool_runs_session ON tool_runs(session_id, started_at, id);
"""


def _now() -> float:
  return time.time()


def _uuid() -> str:
  return uuid.uuid4().hex


def _json(obj: Any) -> str:
  return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _loads(text: str | None) -> Any:
  return json.loads(text) if text else None


@dataclass(frozen=True)
class SessionRecord:
  id: str
  title: str
  workspace_root: str
  created_at: float
  updated_at: float
  metadata: dict[str, Any]


@dataclass(frozen=True)
class MessageRecord:
  id: str
  session_id: str
  role: str
  content: str | None
  tool_calls: list[dict[str, Any]] | None
  tool_call_id: str | None
  created_at: float
  metadata: dict[str, Any]


@dataclass(frozen=True)
class ToolRunRecord:
  id: str
  session_id: str
  message_id: str | None
  tool_name: str
  input: dict[str, Any]
  output: dict[str, Any] | None
  status: str
  started_at: float
  completed_at: float | None
  metadata: dict[str, Any]


class SessionStore:
  """SQLite-backed storage for durable conversation state."""

  def __init__(self, path: Path) -> None:
    self._path = path
    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(str(self._path))
    self._conn.execute("PRAGMA journal_mode=WAL")
    self._conn.execute("PRAGMA foreign_keys=ON")
    self._conn.executescript(_DDL)

  @property
  def path(self) -> Path:
    return self._path

  def __enter__(self) -> SessionStore:
    return self

  def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
    self.close()

  def close(self) -> None:
    self._conn.close()

  def create_session(self, *, workspace_root: Path, title: str = "untitled", metadata: dict[str, Any] | None = None) -> SessionRecord:
    now = _now()
    session = SessionRecord(
      id=_uuid(),
      title=title,
      workspace_root=str(workspace_root),
      created_at=now,
      updated_at=now,
      metadata=metadata or {},
    )
    self._conn.execute(
      "INSERT INTO sessions(id, title, workspace_root, created_at, updated_at, metadata) VALUES(?,?,?,?,?,?)",
      (session.id, session.title, session.workspace_root, session.created_at, session.updated_at, _json(session.metadata)),
    )
    self._conn.commit()
    return session

  def get_latest_session(self, *, workspace_root: Path, max_age_seconds: float = 86400.0) -> SessionRecord | None:
    row = self._conn.execute(
      "SELECT id, title, workspace_root, created_at, updated_at, metadata FROM sessions WHERE workspace_root=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
      (str(workspace_root),),
    ).fetchone()
    if not row:
      return None
    session = SessionRecord(id=row[0], title=row[1], workspace_root=row[2], created_at=row[3], updated_at=row[4], metadata=_loads(row[5]) or {})
    if (_now() - session.updated_at) > max_age_seconds:
      return None
    return session

  def get_session(self, session_id: str) -> SessionRecord | None:
    row = self._conn.execute("SELECT id, title, workspace_root, created_at, updated_at, metadata FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
      return None
    return SessionRecord(id=row[0], title=row[1], workspace_root=row[2], created_at=row[3], updated_at=row[4], metadata=_loads(row[5]) or {})

  def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
    rows = self._conn.execute("SELECT id, title, workspace_root, created_at, updated_at, metadata FROM sessions ORDER BY updated_at DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
    return [SessionRecord(id=r[0], title=r[1], workspace_root=r[2], created_at=r[3], updated_at=r[4], metadata=_loads(r[5]) or {}) for r in rows]

  def append_message(self, session_id: str, role: str, content: str | None, *, tool_calls: list[dict[str, Any]] | None = None, tool_call_id: str | None = None, metadata: dict[str, Any] | None = None) -> MessageRecord:
    now = _now()
    message = MessageRecord(
      id=_uuid(),
      session_id=session_id,
      role=role,
      content=content,
      tool_calls=tool_calls or None,
      tool_call_id=tool_call_id,
      created_at=now,
      metadata=metadata or {},
    )
    self._conn.execute(
      "INSERT INTO messages(id, session_id, role, content, tool_calls, tool_call_id, created_at, metadata) VALUES(?,?,?,?,?,?,?,?)",
      (
        message.id,
        message.session_id,
        message.role,
        message.content,
        _json(message.tool_calls) if message.tool_calls else None,
        message.tool_call_id,
        message.created_at,
        _json(message.metadata),
      ),
    )
    self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    self._conn.commit()
    return message

  def record_tool_start(self, session_id: str, tool_name: str, payload: dict[str, Any], *, message_id: str | None = None, metadata: dict[str, Any] | None = None) -> ToolRunRecord:
    now = _now()
    run = ToolRunRecord(
      id=_uuid(),
      session_id=session_id,
      message_id=message_id,
      tool_name=tool_name,
      input=payload,
      output=None,
      status="running",
      started_at=now,
      completed_at=None,
      metadata=metadata or {},
    )
    self._conn.execute(
      "INSERT INTO tool_runs(id, session_id, message_id, tool_name, input, output, status, started_at, completed_at, metadata) VALUES(?,?,?,?,?,?,?,?,?,?)",
      (run.id, run.session_id, run.message_id, run.tool_name, _json(run.input), None, run.status, run.started_at, None, _json(run.metadata)),
    )
    self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    self._conn.commit()
    return run

  def record_tool_completion(self, run_id: str, output: dict[str, Any], status: str = "completed") -> ToolRunRecord:
    row = self._conn.execute("SELECT id, session_id, message_id, tool_name, input, output, status, started_at, completed_at, metadata FROM tool_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
      raise KeyError(f"tool run not found: {run_id}")
    now = _now()
    self._conn.execute("UPDATE tool_runs SET output=?, status=?, completed_at=? WHERE id=?", (_json(output), status, now, run_id))
    self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, row[1]))
    self._conn.commit()
    return ToolRunRecord(id=row[0], session_id=row[1], message_id=row[2], tool_name=row[3], input=_loads(row[4]) or {}, output=output, status=status, started_at=row[7], completed_at=now, metadata=_loads(row[9]) or {})

  def get_message_counts(self, session_ids: list[str]) -> dict[str, int]:
    """Return message counts for the given session ids."""
    if not session_ids:
      return {}
    placeholders = ",".join("?" for _ in session_ids)
    rows = self._conn.execute(
      f"SELECT session_id, COUNT(*) FROM messages WHERE session_id IN ({placeholders}) GROUP BY session_id",
      session_ids,
    ).fetchall()
    return {r[0]: r[1] for r in rows}
  def get_messages(self, session_id: str, limit: int | None = None) -> list[MessageRecord]:
    query = "SELECT id, session_id, role, content, tool_calls, tool_call_id, created_at, metadata FROM messages WHERE session_id=? ORDER BY created_at, id"
    params: tuple[Any, ...] = (session_id,)
    if limit is not None:
      query += " LIMIT ?"
      params = (session_id, limit)
    rows = self._conn.execute(query, params).fetchall()
    return [
      MessageRecord(id=r[0], session_id=r[1], role=r[2], content=r[3], tool_calls=_loads(r[4]), tool_call_id=r[5], created_at=r[6], metadata=_loads(r[7]) or {})
      for r in rows
    ]

  def get_tool_runs(self, session_id: str) -> list[ToolRunRecord]:
    rows = self._conn.execute("SELECT id, session_id, message_id, tool_name, input, output, status, started_at, completed_at, metadata FROM tool_runs WHERE session_id=? ORDER BY started_at, id", (session_id,)).fetchall()
    return [ToolRunRecord(id=r[0], session_id=r[1], message_id=r[2], tool_name=r[3], input=_loads(r[4]) or {}, output=_loads(r[5]), status=r[6], started_at=r[7], completed_at=r[8], metadata=_loads(r[9]) or {}) for r in rows]
