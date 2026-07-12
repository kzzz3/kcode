"""Inline slash-command autocomplete overlay -- dropdown below InputArea."""
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, ListItem, ListView


@dataclass(frozen=True)
class SlashCommand:
  """A single slash-command entry with rich metadata."""
  id: str
  label: str
  description: str
  category: str = "general"
  alias: str = ""
  icon: str = ">"
  shortcut: str = ""


# ── Built-in command catalogue ──────────────────────────────────────────

SLASH_COMMANDS: list[SlashCommand] = [
  # Session
  SlashCommand("new_session",  "New Session",  "Start a new chat session",             "session", icon="+", shortcut="Ctrl+N"),
  SlashCommand("refresh",      "Refresh",       "Reload sessions list",                "session", icon="R"),
  # View
  SlashCommand("sidebar",      "Toggle Sidebar","Show/hide sidebar panel",             "view",    alias="sb", icon="#", shortcut="Ctrl+B"),
  SlashCommand("clear",        "Clear Chat",    "Clear the chat display",              "view",    icon="C", shortcut="Ctrl+L"),
  # Model
  SlashCommand("model",        "Switch Model",  "Change the active model",             "model",   alias="m", icon="M"),
  # Config
  SlashCommand("approval",     "Approval Mode", "Switch between ask/auto approval",    "config",  alias="ap", icon="A"),
  # Theme
  SlashCommand("theme",        "Theme",         "Switch light/dark theme",             "config",  icon="T"),
  # Help
  SlashCommand("help",         "Help",          "Show available commands and shortcuts","help",    alias="h", icon="?", shortcut="Ctrl+H"),
  # Compact
  SlashCommand("compact",      "Compact",       "Compact conversation context",        "session", icon="K"),
  # App
  SlashCommand("quit",         "Quit",          "Exit KCode TUI",                      "app",     alias="q", icon="X", shortcut="Ctrl+Q"),
]


# ── Filtering ───────────────────────────────────────────────────────────

CATEGORY_ICONS: dict[str, str] = {
  "session": "S",
  "view":    "V",
  "model":   "M",
  "config":  "C",
  "help":    "H",
  "app":     "A",
  "general": "G",
}


def filter_slash_commands(
  commands: list[SlashCommand],
  query: str,
) -> list[SlashCommand]:
  """Filter by id / label / description / alias / category -- fuzzy-friendly."""
  q = (query or "").strip().lower().lstrip("/")
  if not q:
    return list(commands)
  results: list[SlashCommand] = []
  for c in commands:
    searchable = " ".join([
      c.id, c.label.lower(), c.description.lower(),
      c.alias, c.category,
    ])
    if q in searchable:
      results.append(c)
  return results


# ── Rendering helpers ────────────────────────────────────────────────────

def _render_command_row(cmd: SlashCommand) -> str:
  """Render one command as a single-line row for the overlay list."""
  shortcut_part = f"  [{cmd.shortcut}]" if cmd.shortcut else ""
  alias_part = f" /{cmd.alias}" if cmd.alias else ""
  return f" {cmd.icon} /{cmd.id}{alias_part}  {cmd.description}{shortcut_part}"


# ── Widget ───────────────────────────────────────────────────────────────

class SlashOverlay(Widget):
  """Floating autocomplete list that appears below the input when '/' is typed.

  NOT a modal screen -- it's a child widget that shows/hides dynamically.
  """

  DEFAULT_CSS = """
  SlashOverlay {
    height: auto;
    max-height: 12;
    display: none;
    layer: overlay;
    dock: bottom;
    background: $surface;
    border: tall $accent;
    margin: 0 1 0 1;
    padding: 0;
  }

  SlashOverlay.visible {
    display: block;
  }

  #slash-hint {
    height: 1;
    color: $text-muted;
    padding: 0 1;
    background: $surface;
  }

  #slash-list {
    height: auto;
    max-height: 10;
    overflow-y: auto;
  }

  #slash-list ListItem {
    height: 1;
    padding: 0 1;
  }

  #slash-list ListItem.--highlighted {
    background: $accent;
    color: $text;
  }

  #slash-list ListItem:hover {
    background: $accent 50%;
  }
  """

  selected_id: reactive[str | None] = reactive(None)
  visible: reactive[bool] = reactive(False)

  def __init__(self, commands: list[SlashCommand] | None = None) -> None:
    super().__init__()
    self._commands = commands or SLASH_COMMANDS
    self._filtered: list[SlashCommand] = list(self._commands)
    self._cursor: int = 0

  class CommandSelected:
    """Posted when user confirms a command (Enter / Tab / click)."""
    def __init__(self, command_id: str) -> None:
      self.command_id = command_id

  class Dismissed:
    """Posted when user cancels the overlay (Escape)."""
    pass

  def compose(self) -> ComposeResult:
    yield Static("Type / to search commands", id="slash-hint")
    yield ListView(id="slash-list")

  def show_overlay(self, query: str = "") -> None:
    """Show the overlay with optional initial filter."""
    self._update_filter(query)
    self.visible = True
    self.add_class("visible")

  def hide_overlay(self) -> None:
    """Hide the overlay and reset state."""
    self.visible = False
    self.remove_class("visible")
    self._cursor = 0

  def update_filter(self, query: str) -> None:
    """Update the filter text and rebuild the list."""
    self._update_filter(query)

  def move_up(self) -> None:
    """Move selection up."""
    if not self._filtered:
      return
    self._cursor = (self._cursor - 1) % len(self._filtered)
    self._highlight_current()

  def move_down(self) -> None:
    """Move selection down."""
    if not self._filtered:
      return
    self._cursor = (self._cursor + 1) % len(self._filtered)
    self._highlight_current()

  def get_selected(self) -> SlashCommand | None:
    """Return the currently highlighted command, or None."""
    if 0 <= self._cursor < len(self._filtered):
      return self._filtered[self._cursor]
    return None

  def confirm_selection(self) -> str | None:
    """Return the selected command id, or None."""
    cmd = self.get_selected()
    return cmd.id if cmd else None

  # ── internals ──────────────────────────────────────────────────────

  def _update_filter(self, query: str) -> None:
    self._filtered = filter_slash_commands(self._commands, query)
    self._cursor = min(self._cursor, max(0, len(self._filtered) - 1))
    self._rebuild_list()

  def _rebuild_list(self) -> None:
    list_view = self.query_one("#slash-list", ListView)
    list_view.clear()
    if not self._filtered:
      list_view.append(ListItem(Static("  No matching commands")))
      self.selected_id = None
      hint = self.query_one("#slash-hint", Static)
      hint.update("No matches")
      return

    for i, cmd in enumerate(self._filtered):
      row_text = _render_command_row(cmd)
      item = ListItem(Static(row_text))
      if i == self._cursor:
        item.add_class("--highlighted")
      list_view.append(item)

    self.selected_id = self._filtered[self._cursor].id
    hint = self.query_one("#slash-hint", Static)
    hint.update(f" {len(self._filtered)} commands  |  arrow keys: navigate  |  enter: select  |  esc: cancel")

  def _highlight_current(self) -> None:
    list_view = self.query_one("#slash-list", ListView)
    for i, item in enumerate(list_view.query(ListItem)):
      if i == self._cursor:
        item.add_class("--highlighted")
      else:
        item.remove_class("--highlighted")
    if 0 <= self._cursor < len(self._filtered):
      self.selected_id = self._filtered[self._cursor].id
