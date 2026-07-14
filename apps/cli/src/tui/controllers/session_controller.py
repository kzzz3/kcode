"""SessionController -- manages session list, create, load, and refresh.

Extracts session management logic from MainScreen so the screen only does
message routing and layout orchestration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from apps.cli.src.core.agent_runtime import CliAgentRuntime

_log = logging.getLogger(__name__)


# ── Session info for UI ─────────────────────────────────────────────


@dataclass(frozen=True)
class SessionInfo:
  """Compact session representation for the sidebar."""
  id: str
  title: str
  updated_at: float
  message_count: int
  is_current: bool


# ── Controller ──────────────────────────────────────────────────────


class SessionController:
  """Manages session CRUD and listing, delegating persistence to SessionStore.

  Usage::

    sc = SessionController(runtime, on_sessions_changed=panel.set_sessions)
    sc.refresh()
    sc.create_new()
    sc.load(session_id)
  """

  def __init__(
    self,
    runtime: CliAgentRuntime,
    *,
    on_sessions_changed: Callable[[list[SessionInfo]], None] | None = None,
    on_session_loaded: Callable[[str, list[dict[str, Any]]], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    limit: int = 50,
  ) -> None:
    self._runtime = runtime
    self._on_sessions_changed = on_sessions_changed
    self._on_session_loaded = on_session_loaded
    self._on_error = on_error
    self._limit = limit

  # ── Properties ────────────────────────────────────────────────────

  @property
  def current_session_id(self) -> str | None:
    """The currently active session id, or None."""
    return self._runtime.session.session_id if self._runtime.session else None

  # ── Helpers ───────────────────────────────────────────────────────

  def _build_session_infos(self) -> list[SessionInfo]:
    """Load sessions from store and build SessionInfo list with message counts."""
    store = self._runtime.session_store
    sessions = store.list_sessions(limit=self._limit)
    if not sessions:
      return []

    counts = store.get_message_counts([s.id for s in sessions])
    current_id = self.current_session_id
    return [
      SessionInfo(
        id=s.id,
        title=s.title or "Untitled",
        updated_at=s.updated_at,
        message_count=counts.get(s.id, 0),
        is_current=s.id == current_id,
      )
      for s in sessions
    ]

  # ── Public API ────────────────────────────────────────────────────

  def refresh(self) -> None:
    """Reload the session list from the store and notify the UI."""
    try:
      infos = self._build_session_infos()
      if self._on_sessions_changed:
        self._on_sessions_changed(infos)
    except Exception as exc:
      _log.error("Failed to refresh sessions: %s", exc)
      if self._on_error:
        self._on_error(f"Failed to refresh sessions: {exc}")

  def create_new(self) -> None:
    """Create a new session and refresh the list."""
    try:
      self._runtime.new_session()
      if self._on_session_loaded:
        self._on_session_loaded("", [])  # empty chat for new session
      self.refresh()
    except Exception as exc:
      _log.error("Failed to create session: %s", exc)
      if self._on_error:
        self._on_error(f"Failed to create session: {exc}")

  def load(self, session_id: str) -> None:
    """Load an existing session by id and replay its messages."""
    try:
      session = self._runtime.load_session(session_id)
      messages = [
        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
        for msg in session.messages
        if msg.get("content") and msg.get("role") in ("user", "assistant")
      ]
      if self._on_session_loaded:
        self._on_session_loaded(session_id, messages)
      self.refresh()
    except Exception as exc:
      _log.error("Failed to load session %s: %s", session_id, exc)
      if self._on_error:
        self._on_error(f"Failed to load session: {exc}")

  def get_session_data(self) -> list[dict[str, Any]]:
    """Return session list as raw dicts for the SessionPanel widget."""
    infos = self._build_session_infos()
    return [
      {
        "id": info.id,
        "title": info.title,
        "updated_at": info.updated_at,
        "message_count": info.message_count,
        "is_current": info.is_current,
      }
      for info in infos
    ]
