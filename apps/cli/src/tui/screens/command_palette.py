"""Slash command palette for TUI."""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListView, ListItem, Label


@dataclass(frozen=True)
class CommandItem:
  """A single slash command entry."""
  id: str
  label: str
  description: str
  category: str = "general"


BUILTIN_COMMANDS: list[CommandItem] = [
  # Session
  CommandItem("new_session", "New Session", "Start a new chat session", "session"),
  CommandItem("refresh_sessions", "Refresh Sessions", "Reload sessions list", "session"),
  # View
  CommandItem("toggle_sidebar", "Toggle Sidebar", "Show/hide sidebar panel", "view"),
  CommandItem("clear", "Clear Chat", "Clear the chat display", "view"),
  # Model
  CommandItem("model", "Switch Model", "Change the active model", "model"),
  CommandItem("approval", "Toggle Approval", "Switch between ask/auto approval", "config"),
  # Help
  CommandItem("help", "Help", "Show available commands and shortcuts", "help"),
  # App
  CommandItem("quit", "Quit", "Exit KCode TUI", "app"),
]


def filter_commands(commands: list[CommandItem], query: str) -> list[CommandItem]:
  """Filter commands by query string (matches id, label, description, or category)."""
  q = (query or "").strip().lower()
  if not q:
    return list(commands)
  return [
    c for c in commands
    if q in c.id or q in c.label.lower() or q in c.description.lower() or q in c.category
  ]


class CommandPalette(ModalScreen[str | None]):
  """Modal palette that appears when user types '/'."""

  DEFAULT_CSS = """
  CommandPalette {
    align: center top;
  }

  #palette {
    width: 64;
    max-width: 80;
    height: auto;
    max-height: 70%;
    border: thick $accent;
    background: $surface;
    padding: 1 1;
  }

  #palette Input {
    margin: 0 0 1 0;
  }

  #palette ListView {
    height: 1fr;
  }
  """

  def __init__(self, commands: list[CommandItem] | None = None) -> None:
    super().__init__()
    self._commands = commands or BUILTIN_COMMANDS

  def compose(self) -> ComposeResult:
    with Vertical(id="palette"):
      yield Input(placeholder="Type a command...", id="cmd-input")
      yield ListView(id="cmd-list")

  def on_mount(self) -> None:
    self._rebuild_list("")
    self.query_one(Input).focus()

  def on_input_changed(self, event: Input.Changed) -> None:
    self._rebuild_list(event.value)

  def on_input_submitted(self, event: Input.Submitted) -> None:
    """Enter selects the first matching command."""
    filtered = self._filtered_commands(event.value)
    if filtered:
      self.dismiss(filtered[0].id)
    else:
      self.dismiss(None)

  def on_list_view_selected(self, event: ListView.Selected) -> None:
    list_view = self.query_one(ListView)
    idx = list_view.index
    if idx is None:
      return
    filtered = self._filtered_commands(self.query_one(Input).value)
    if 0 <= idx < len(filtered):
      self.dismiss(filtered[idx].id)
    else:
      self.dismiss(None)

  def on_key(self, event) -> None:
    if event.key == "escape":
      self.dismiss(None)

  def _rebuild_list(self, query: str) -> None:
    list_view = self.query_one(ListView)
    list_view.clear()
    for cmd in self._filtered_commands(query):
      list_view.append(ListItem(Label(f"/{cmd.id}  {cmd.description}")))

  def _filtered_commands(self, query: str) -> list[CommandItem]:
    return filter_commands(self._commands, query)
