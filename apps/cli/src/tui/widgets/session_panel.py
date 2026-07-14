"""Session management panel -- list, create, select sessions.

Also serves as Activity Rail with current session marker support.
"""
from __future__ import annotations

from textual.widgets import ListView, ListItem, Label, Button, Static
from textual.containers import Vertical
from textual.message import Message


class SessionPanel(Vertical):
  """Sidebar panel for session management."""

  DEFAULT_CSS = """
  SessionPanel {
    width: 30;
    min-width: 20;
    border: solid #8b929c;
    padding: 0 1;
  }

  #session-list {
    height: 1fr;
  }

  #session-buttons {
    height: auto;
    dock: bottom;
    padding: 1 0;
  }

  #session-buttons Button {
    width: 100%;
    margin: 0 0 1 0;
  }

  .panel-title {
    height: 1;
    padding: 0 0 0 0;
    text-style: bold;
  }
  """

  class SessionSelected(Message):
    """Emitted when user selects a session."""
    def __init__(self, session_id: str) -> None:
      self.session_id = session_id
      super().__init__()

  class NewSession(Message):
    """Emitted when user clicks New Session."""
    pass

  class RefreshSessions(Message):
    """Emitted when user clicks Refresh."""
    pass

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    self._sessions: list[tuple[str, str]] = []  # (id, title)
    self._current_session_id: str | None = None

  def compose(self):
    yield Static("Sessions", classes="panel-title")
    yield Static("No sessions yet.", id="session-empty")
    yield ListView(id="session-list")
    with Vertical(id="session-buttons"):
      yield Button("+ New", variant="primary", id="btn-new-session")
      yield Button("Refresh", variant="default", id="btn-refresh")

  def set_sessions(self, sessions: list[tuple[str, str]]) -> None:
    """Replace the session list with (id, title) pairs."""
    self._sessions = sessions
    self._rebuild_list()

  # Alias so MainScreen._on_sessions_updated works
  refresh_list = set_sessions

  def add_session(self, session_id: str, title: str) -> None:
    """Add a session to the top of the list."""
    self._sessions.insert(0, (session_id, title))
    self._rebuild_list()

  def set_current_session(self, session_id: str | None) -> None:
    """Mark a session as the current active one (shows marker)."""
    self._current_session_id = session_id
    self._rebuild_list()

  def _rebuild_list(self) -> None:
    """Rebuild the ListView from stored sessions."""
    list_view = self.query_one("#session-list", ListView)
    list_view.clear()
    # Show/hide empty state
    try:
      empty = self.query_one("#session-empty")
      empty.display = len(self._sessions) == 0
      list_view.display = len(self._sessions) > 0
    except Exception:
      pass
    for sid, title in self._sessions:
      short_id = sid[:8]
      marker = "● " if sid == self._current_session_id else ""
      label = f"{marker}{short_id} | {title}" if title else f"{marker}{short_id}"
      list_view.append(ListItem(Label(label)))

  def on_resize(self, event) -> None:
    """Adapt layout for narrow screens."""
    if event.size.width < 60:
      self.add_class("narrow")
    else:
      self.remove_class("narrow")

  def on_list_view_selected(self, event: ListView.Selected) -> None:
    """Handle session selection."""
    list_view = self.query_one("#session-list", ListView)
    idx = list_view.index
    if idx is not None and 0 <= idx < len(self._sessions):
      session_id = self._sessions[idx][0]
      self.post_message(self.SessionSelected(session_id))

  def on_button_pressed(self, event: Button.Pressed) -> None:
    """Handle button presses."""
    if event.button.id == "btn-new-session":
      self.post_message(self.NewSession())
    elif event.button.id == "btn-refresh":
      self.post_message(self.RefreshSessions())
