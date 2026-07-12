"""Inline slash-command autocomplete overlay -- dropdown below InputArea.

Inspired by OpenCode/Crush command palette: typed '/' opens a non-modal
overlay that filters in real time, grouped by category with icons, aliases,
keyboard shortcuts, and rich visual hints. Supports both built-in and
custom commands from user/project directories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Rule


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
  is_custom: bool = False
  content: str | None = None  # For custom commands, the template content


# ── Built-in command catalogue ──────────────────────────────────────────

SLASH_COMMANDS: list[SlashCommand] = [
  # Session
  SlashCommand("new",      "New Session",   "Start a fresh chat session",            "session",  icon="\u2795", shortcut="Ctrl+N"),
  SlashCommand("compact",  "Compact",       "Compact conversation to save tokens",   "session",  icon="\u267b", shortcut="Ctrl+K"),
  SlashCommand("clear",    "Clear Chat",    "Clear the current chat display",        "session",  icon="\u2716", shortcut="Ctrl+L"),
  SlashCommand("sessions", "Sessions",      "List and switch between sessions",      "session",  icon="\U0001f4cb"),
  SlashCommand("refresh",  "Refresh",       "Reload sessions list",                  "session",  icon="\U0001f504"),
  # View
  SlashCommand("sidebar",  "Toggle Sidebar","Show / hide the sidebar panel",         "view",     alias="sb", icon="\u25a0", shortcut="Ctrl+B"),
  SlashCommand("theme",    "Cycle Theme",   "Switch between available themes",       "view",     alias="t",  icon="\U0001f3a8"),
  # Model
  SlashCommand("model",    "Switch Model",  "Change the active LLM model",           "model",    alias="m",  icon="\U0001f916"),
  # Config
  SlashCommand("approval", "Approval Mode", "Toggle ask / auto approval",            "config",   alias="ap", icon="\U0001f6e1"),
  # Help
  SlashCommand("help",     "Help",          "Show keyboard shortcuts and commands",  "help",     alias="h",  icon="\u2753", shortcut="Ctrl+H"),
  SlashCommand("doctor",   "Doctor",        "Check runtime health status",           "help",     alias="dr", icon="\u2695"),
  SlashCommand("init",     "Init Project",  "Create/Update kcode.workspace.md",      "project",  icon="\U0001f4c1"),
  # App
  SlashCommand("quit",     "Quit",          "Exit KCode TUI",                        "app",      alias="q",  icon="\u2716", shortcut="Ctrl+Q"),
]

# Category display order, labels, and icons
CATEGORY_META: list[tuple[str, str, str]] = [
  ("session", "Session",  "\U0001f4ac"),
  ("view",    "View",     "\U0001f441"),
  ("model",   "Model",    "\U0001f916"),
  ("config",  "Config",   "\u2699"),
  ("project", "Project",  "\U0001f4c1"),
  ("help",    "Help",     "\u2753"),
  ("app",     "App",      "\U0001f680"),
]


# ── Filtering ───────────────────────────────────────────────────────────

def filter_slash_commands(
  commands: list[SlashCommand],
  query: str,
) -> list[SlashCommand]:
  """Filter by id / label / description / alias / category -- fuzzy-friendly.

  Supports multi-word queries: each space-separated token must appear
  somewhere in the searchable text (AND logic).
  """
  q = (query or "").strip().lower().lstrip("/")
  if not q:
    return list(commands)

  tokens = q.split()
  results: list[SlashCommand] = []
  for c in commands:
    searchable = " ".join([
      c.id, c.label.lower(), c.description.lower(),
      c.alias, c.category,
    ])
    if all(tok in searchable for tok in tokens):
      results.append(c)
  return results


def group_by_category(
  commands: list[SlashCommand],
) -> list[tuple[str, str, list[SlashCommand]]]:
  """Group commands by category, preserving CATEGORY_META order.

  Returns list of (label, icon, commands) tuples.
  """
  by_cat: dict[str, list[SlashCommand]] = {}
  for cmd in commands:
    by_cat.setdefault(cmd.category, []).append(cmd)

  result: list[tuple[str, str, list[SlashCommand]]] = []
  seen: set[str] = set()
  for cat_key, cat_label, cat_icon in CATEGORY_META:
    if cat_key in by_cat:
      result.append((cat_label, cat_icon, by_cat[cat_key]))
      seen.add(cat_key)
  # Any leftover categories not in CATEGORY_META
  for cat_key, cmds in by_cat.items():
    if cat_key not in seen:
      result.append((cat_key.title(), "\u25cf", cmds))
  return result


# ── Widget ────────────────────────────────────────────────────────────

class SlashOverlay(Widget):
  """Inline dropdown overlay that appears below the input area.

  Renders category-grouped commands with icons, aliases, descriptions,
  and keyboard shortcuts. Supports arrow-key navigation, real-time
  filtering, click/enter/tab confirmation, and custom commands.
  """

  DEFAULT_CSS = """
  SlashOverlay {
    height: 0;
    display: none;
    overflow: hidden;
    background: $surface;
    border: tall $accent;
    margin: 0 1;
  }

  SlashOverlay.visible {
    height: auto;
    max-height: 24;
    display: block;
  }

  #slash-header {
    height: 1;
    padding: 0 1;
    color: $text-muted;
  }

  #slash-commands {
    height: auto;
    overflow-y: auto;
    max-height: 18;
  }

  #slash-empty {
    height: 1;
    display: none;
    padding: 0 1;
    color: $text-muted;
    text-style: italic;
  }

  #slash-footer {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    text-style: dim;
  }

  SlashOverlay.no-results #slash-empty {
    display: block;
  }

  .slash-category {
    height: 1;
    padding: 0 1;
    color: $accent;
    text-style: bold;
  }

  .slash-divider {
    height: 1;
    margin: 0 1;
  }

  .slash-item {
    height: 1;
    padding: 0 1;
  }

  .slash-item.selected {
    background: $accent;
    color: $background;
  }

  .slash-icon {
    width: 3;
    text-align: center;
  }

  .slash-name {
    width: 16;
    color: $text;
  }

  .slash-alias {
    width: 6;
    color: $text-muted;
    text-style: dim;
  }

  .slash-desc {
    width: 1fr;
    color: $text-muted;
  }

  .slash-shortcut {
    width: 10;
    text-align: right;
    color: $text-muted;
    text-style: dim;
  }

  .slash-custom-badge {
    width: 6;
    color: $warning;
    text-style: italic;
  }
  """

  selected_id: reactive[str | None] = reactive(None)

  def __init__(self, commands: list[SlashCommand] | None = None, workspace_root: Path | None = None) -> None:
    super().__init__()
    self._commands = commands or list(SLASH_COMMANDS)
    self._filtered: list[SlashCommand] = list(self._commands)
    self._selected_idx: int = 0
    self._nav_items: list[tuple[str, SlashCommand | None]] = []
    self._workspace_root = workspace_root

    # Load custom commands
    self._load_custom_commands()

  class CommandSelected:
    """Posted when user confirms a command (Enter / Tab / click)."""
    def __init__(self, command_id: str, content: str | None = None) -> None:
      self.command_id = command_id
      self.content = content  # For custom commands

  class Dismissed:
    """Posted when user cancels the overlay (Escape)."""
    pass

  def _load_custom_commands(self) -> None:
    """Load custom commands from user and project directories."""
    try:
      from apps.cli.src.tui.utils.custom_commands import load_all_custom_commands
      custom_commands = load_all_custom_commands(self._workspace_root)
      
      for cmd in custom_commands:
        slash_cmd = SlashCommand(
          id=cmd.id,
          title=cmd.title,
          description=cmd.description,
          category="custom",
          icon="\u270d",  # ✍
          is_custom=True,
          content=cmd.content,
        )
        self._commands.append(slash_cmd)
      
      # Update filtered list
      self._filtered = list(self._commands)
    except Exception as e:
      # Log error but continue with built-in commands only
      print(f"Warning: Failed to load custom commands: {e}")

  def compose(self) -> ComposeResult:
    yield Static("Type to filter commands...", id="slash-header")
    with Vertical(id="slash-commands"):
      pass  # Populated dynamically
    yield Static("  No matching commands found", id="slash-empty")
    yield Static(
      " \u2191\u2193 navigate  \u21b5 select  esc cancel  \u2022 type to filter",
      id="slash-footer",
    )

  def show_overlay(self, query: str = "") -> None:
    """Show the overlay with optional initial filter."""
    # Reload custom commands in case they changed
    self._load_custom_commands()
    self._update_filter(query)
    self.visible = True
    self.add_class("visible")

  def hide_overlay(self) -> None:
    """Hide the overlay."""
    self.visible = False
    self.remove_class("visible")

  def update_filter(self, query: str) -> None:
    """Update the command filter from external input."""
    self._update_filter(query)

  def move_up(self) -> None:
    """Move selection up, skipping category headers."""
    if not self._nav_items:
      return
    for _ in range(len(self._nav_items)):
      self._selected_idx = (self._selected_idx - 1) % len(self._nav_items)
      if self._nav_items[self._selected_idx][1] is not None:
        break
    self._update_selection_visual()

  def move_down(self) -> None:
    """Move selection down, skipping category headers."""
    if not self._nav_items:
      return
    for _ in range(len(self._nav_items)):
      self._selected_idx = (self._selected_idx + 1) % len(self._nav_items)
      if self._nav_items[self._selected_idx][1] is not None:
        break
    self._update_selection_visual()

  def get_selected(self) -> SlashCommand | None:
    """Return the currently highlighted command, or None."""
    if 0 <= self._selected_idx < len(self._nav_items):
      return self._nav_items[self._selected_idx][1]
    return None

  def confirm_selection(self) -> tuple[str | None, str | None]:
    """Return the selected command id and content, or (None, None)."""
    cmd = self.get_selected()
    if cmd:
      return cmd.id, cmd.content if cmd.is_custom else None
    return None, None

  # ── internals ──────────────────────────────────────────────────────

  def _update_filter(self, query: str) -> None:
    self._filtered = filter_slash_commands(self._commands, query)
    self._selected_idx = 0
    self._rebuild_list()
    # Select first non-header item
    for i, (_, cmd) in enumerate(self._nav_items):
      if cmd is not None:
        self._selected_idx = i
        break
    self._update_selection_visual()

    # Update header
    try:
      header = self.query_one("#slash-header", Static)
      q = (query or "").strip().lstrip("/")
      if q:
        header.update(f"Filter: {q}  ({len(self._filtered)} results)")
      else:
        header.update(f"{len(self._filtered)} commands available")
    except Exception:
      pass

    # Toggle no-results state
    if self._filtered:
      self.remove_class("no-results")
      self.add_class("has-results")
    else:
      self.remove_class("has-results")
      self.add_class("no-results")

  def _rebuild_list(self) -> None:
    """Rebuild the command list from scratch."""
    container = self.query_one("#slash-commands", Vertical)
    # Remove all children
    for child in list(container.children):
      child.remove()
    self._nav_items = []

    if not self._filtered:
      return

    groups = group_by_category(self._filtered)

    for cat_idx, (cat_label, cat_icon, cmds) in enumerate(groups):
      if cat_idx > 0:
        # Add a thin separator between categories
        sep = Rule(style="dim")
        sep.add_class("slash-divider")
        container.mount(sep)

      # Category header
      header = Static(f" {cat_icon} {cat_label}", classes="slash-category")
      container.mount(header)
      self._nav_items.append((f"cat-{cat_label}", None))

      for cmd in cmds:
        widget_id = f"cmd-{cmd.id}"
        item = self._make_command_row(cmd, widget_id)
        container.mount(item)
        self._nav_items.append((widget_id, cmd))

  def _make_command_row(self, cmd: SlashCommand, widget_id: str) -> Widget:
    """Create a single command row widget."""
    alias_text = f"/{cmd.alias}" if cmd.alias else ""
    shortcut_text = cmd.shortcut or ""
    custom_badge = "custom" if cmd.is_custom else ""

    row = Horizontal(
      Static(f" {cmd.icon}", classes="slash-icon"),
      Static(f"/{cmd.id}", classes="slash-name"),
      Static(alias_text, classes="slash-alias"),
      Static(cmd.description, classes="slash-desc"),
      Static(shortcut_text, classes="slash-shortcut"),
      Static(custom_badge, classes="slash-custom-badge"),
      classes="slash-item",
      id=widget_id,
    )

    # Store cmd_id on the row for click handling
    row._cmd_id = cmd.id  # type: ignore[attr-defined]
    row._cmd_content = cmd.content if cmd.is_custom else None  # type: ignore[attr-defined]
    return row

  def _update_selection_visual(self) -> None:
    """Update CSS classes to reflect the current selection."""
    try:
      container = self.query_one("#slash-commands", Vertical)
      for item in container.query(".slash-item"):
        if self._nav_items and 0 <= self._selected_idx < len(self._nav_items):
          selected_wid = self._nav_items[self._selected_idx][0]
          if item.id == selected_wid:
            item.add_class("selected")
          else:
            item.remove_class("selected")
        else:
          item.remove_class("selected")

      # Update selected_id reactive
      cmd = self.get_selected()
      self.selected_id = cmd.id if cmd else None
    except Exception:
      pass

  def on_click(self, event) -> None:
    """Handle clicks on command items."""
    # Walk up from the click target to find a .slash-item
    target = event.widget
    while target is not None and not target.has_class("slash-item"):
      target = target.parent  # type: ignore[assignment]
    if target is not None and hasattr(target, "_cmd_id"):
      cmd_id = target._cmd_id
      content = getattr(target, "_cmd_content", None)
      self.selected_id = cmd_id
      # Post the selection
      self.post_message(self.CommandSelected(cmd_id, content))