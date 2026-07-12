"""Inline slash-command autocomplete overlay -- dropdown below InputArea.

Inspired by OpenCode/Crush command palette: typed '/' opens a non-modal
overlay that filters in real time, grouped by category with icons, aliases,
keyboard shortcuts, and rich visual hints. Supports both built-in and
custom commands from user/project directories.

Visual enhancements:
  - Two-line rendering: title (bold) + description (muted)
  - Selected item with primary background highlight
  - No-results placeholder with hint
  - Category section headers with icons
  - Proper overlay positioning with shadow effect
"""
from __future__ import annotations

from dataclasses import dataclass
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.message import Message
from textual.widgets import Static, Rule, Input


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


# ── Widget ──────────────────────────────────────────────────────────────

class SlashOverlay(Widget):
  """Non-modal inline overlay that appears above the input area.

  Shows a filterable, grouped list of slash commands with keyboard
  navigation, real-time search, and mouse/click support.
  """

  DEFAULT_CSS = """
  SlashOverlay {
    display: none;
    height: auto;
    max-height: 24;
    margin: 0 1;
    padding: 0;
    background: $surface;
    border: tall $primary;
    layer: overlay;
    overflow-y: auto;
  }

  SlashOverlay.visible {
    display: block;
  }

  /* ── Header ── */
  #slash-header {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    background: $primary 20%;
  }

  /* ── Command list container ── */
  #slash-commands {
    height: auto;
    max-height: 20;
    overflow-y: auto;
  }

  /* ── Category header ── */
  .slash-category {
    height: 1;
    padding: 0 1;
    color: $accent;
    text-style: bold;
    background: $primary 10%;
  }

  /* ── Divider ── */
  .slash-divider {
    height: 1;
    margin: 0 1;
  }

  /* ── Command row (two-line: title + description) ── */
  .slash-item {
    height: auto;
    min-height: 2;
    padding: 0 1;
    background: transparent;
  }

  .slash-item:hover {
    background: $primary 15%;
  }

  .slash-item.selected {
    background: $primary 30%;
  }

  /* Top row: icon + name + alias + shortcut */
  .slash-item .slash-row-top {
    height: 1;
    width: 1fr;
  }

  /* Bottom row: description */
  .slash-item .slash-row-bottom {
    height: 1;
    width: 1fr;
  }

  .slash-icon {
    width: 3;
    min-width: 3;
    text-align: center;
  }

  .slash-name {
    width: 14;
    min-width: 14;
    text-style: bold;
    color: $text;
  }

  .slash-item.selected .slash-name {
    color: $text;
    text-style: bold;
  }

  .slash-alias {
    width: 6;
    min-width: 6;
    color: $text-muted;
  }

  .slash-shortcut {
    width: 10;
    min-width: 10;
    text-align: right;
    color: $text-muted;
  }

  .slash-desc {
    width: 1fr;
    color: $text-muted;
    text-style: italic;
  }

  .slash-item.selected .slash-desc {
    color: $text;
  }

  .slash-custom-badge {
    width: 7;
    min-width: 7;
    text-align: center;
    color: $warning;
  }

  /* ── No results ── */
  .slash-no-results {
    height: 3;
    padding: 1 2;
    color: $text-muted;
    text-style: italic;
    text-align: center;
  }

  /* ── Argument dialog ── */
  #arg-dialog {
    display: none;
    height: auto;
    margin: 1 2;
    padding: 1 2;
    background: $surface;
    border: tall $warning;
  }

  #arg-dialog.visible {
    display: block;
  }

  .arg-prompt {
    height: auto;
    color: $text;
    margin-bottom: 1;
  }

  .arg-input {
    height: 3;
    margin: 0;
  }
  """

  DEFAULT_CLASSES = ""

  # ── Reactives ──────────────────────────────────────────────────────

  selected_id: reactive[str | None] = reactive(None)

  # ── Messages ───────────────────────────────────────────────────────

  class CommandSelected(Message):
    """Posted when user clicks a command item."""
    def __init__(self, command_id: str, content: str | None) -> None:
      self.command_id = command_id
      self.content = content
      super().__init__()

  # ── Init ───────────────────────────────────────────────────────────

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    self._commands: list[SlashCommand] = list(SLASH_COMMANDS)
    self._filtered: list[SlashCommand] = list(SLASH_COMMANDS)
    self._selected_idx: int = 0
    self._nav_items: list[tuple[str, SlashCommand | None]] = []  # (widget_id, cmd_or_none)

  def _load_custom_commands(self) -> None:
    """Load custom commands from user/project dirs."""
    try:
      from apps.cli.src.tui.utils.custom_commands import load_all_custom_commands
      from pathlib import Path
      workspace = Path.cwd()
      customs = load_all_custom_commands(workspace)
      custom_slash = [
        SlashCommand(
          id=c.id,
          label=c.title,
          description=c.description or c.content[:60] if c.content else "",
          category="custom",
          icon="\U0001f4dd",
          is_custom=True,
          content=c.content,
        )
        for c in customs
      ]
      self._commands = list(SLASH_COMMANDS) + custom_slash
      self._filtered = list(self._commands)
    except Exception:
      self._commands = list(SLASH_COMMANDS)
      self._filtered = list(SLASH_COMMANDS)

  # ── Compose ────────────────────────────────────────────────────────

  def compose(self) -> ComposeResult:
    yield Static(f"{len(self._commands)} commands available", id="slash-header")
    with Vertical(id="slash-commands"):
      pass  # Populated dynamically

  def on_mount(self) -> None:
    self._load_custom_commands()
    self._filtered = list(self._commands)
    self._rebuild_list()

  # ── Public API ─────────────────────────────────────────────────────

  def show_overlay(self, query: str = "") -> None:
    """Show the overlay and apply initial filter."""
    self._load_custom_commands()
    self.add_class("visible")
    self._update_filter(query)
    # Focus management -- let input area keep focus
    self.scroll_visible()

  def hide_overlay(self) -> None:
    """Hide the overlay."""
    self.remove_class("visible")

  def update_filter(self, query: str) -> None:
    """Update the filter text and rebuild list."""
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
    self._scroll_to_selected()

  def move_down(self) -> None:
    """Move selection down, skipping category headers."""
    if not self._nav_items:
      return
    for _ in range(len(self._nav_items)):
      self._selected_idx = (self._selected_idx + 1) % len(self._nav_items)
      if self._nav_items[self._selected_idx][1] is not None:
        break
    self._update_selection_visual()
    self._scroll_to_selected()

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

  def _rebuild_list(self) -> None:
    """Rebuild the command list from scratch."""
    container = self.query_one("#slash-commands", Vertical)
    # Remove all children
    for child in list(container.children):
      child.remove()
    self._nav_items = []

    if not self._filtered:
      # Show no-results placeholder
      no_results = Static(
        "  No matching commands  \n  Try a different search term",
        classes="slash-no-results",
      )
      container.mount(no_results)
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
    """Create a single command row widget with two-line layout."""
    alias_text = f"/{cmd.alias}" if cmd.alias else ""
    shortcut_text = cmd.shortcut or ""
    custom_badge = "custom" if cmd.is_custom else ""

    # Top row: icon + name + alias + shortcut + custom badge
    top_row = Horizontal(
      Static(f" {cmd.icon}", classes="slash-icon"),
      Static(f"/{cmd.id}", classes="slash-name"),
      Static(alias_text, classes="slash-alias"),
      Static(shortcut_text, classes="slash-shortcut"),
      Static(custom_badge, classes="slash-custom-badge"),
      classes="slash-row-top",
    )

    # Bottom row: description
    bottom_row = Horizontal(
      Static("   ", classes="slash-icon"),  # Indent to align with name
      Static(cmd.description, classes="slash-desc"),
      classes="slash-row-bottom",
    )

    row = Vertical(
      top_row,
      bottom_row,
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

  def _scroll_to_selected(self) -> None:
    """Scroll the overlay to make the selected item visible."""
    try:
      if self._nav_items and 0 <= self._selected_idx < len(self._nav_items):
        selected_wid = self._nav_items[self._selected_idx][0]
        widget = self.query_one(f"#{selected_wid}")
        widget.scroll_visible()
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
  # ── Argument dialog support ──────────────────────────────────────────

  class ArgumentDialog(Widget):
    """Inline dialog for filling $NAME placeholders in custom commands.

    Shows an Input widget for each argument. Tab cycles between fields,
    Enter submits all values, Escape cancels.
    """

    DEFAULT_CSS = """
    ArgumentDialog {
      display: none;
      height: auto;
      margin: 1 2;
      padding: 1 2;
      background: $surface;
      border: tall $warning;
    }

    ArgumentDialog.visible {
      display: block;
    }

    .arg-title {
      height: 1;
      color: $text;
      text-style: bold;
      margin-bottom: 1;
    }

    .arg-field {
      height: auto;
      margin-bottom: 0;
    }

    .arg-label {
      height: 1;
      width: 16;
      color: $accent;
      text-style: bold;
      content-align: left middle;
    }

    .arg-input {
      height: 3;
      margin: 0;
    }

    .arg-hint {
      height: 1;
      color: $text-muted;
      text-style: dim;
      margin-top: 1;
    }
    """

    class ArgsSubmitted(Message):
      """Posted when user fills all arguments and confirms."""
      def __init__(self, command_id: str, args: dict[str, str]) -> None:
        self.command_id = command_id
        self.args = args
        super().__init__()

    class Cancelled(Message):
      """Posted when user cancels the argument dialog."""
      pass

    def __init__(self, command_id: str, arg_names: list[str], **kwargs) -> None:
      super().__init__(**kwargs)
      self._command_id = command_id
      self._arg_names = arg_names
      self._current_idx: int = 0

    def compose(self) -> ComposeResult:
      yield Static(f"  Command: /{self._command_id}", classes="arg-title")
      for name in self._arg_names:
        with Horizontal(classes="arg-field"):
          yield Static(f"  ${name}:", classes="arg-label")
          yield Input(placeholder=f"Enter ${name}...", id=f"arg-{name}", classes="arg-input")
      yield Static("  Tab: next field  Enter: submit  Escape: cancel", classes="arg-hint")

    def on_mount(self) -> None:
      """Focus the first input field."""
      if self._arg_names:
        first = self.query_one(f"#arg-{self._arg_names[0]}", Input)
        first.focus()

    def on_key(self, event) -> None:
      if event.key == "escape":
        event.prevent_default()
        self.post_message(self.Cancelled())
        return
      if event.key == "enter":
        event.prevent_default()
        self._submit()
        return
      if event.key == "tab":
        event.prevent_default()
        self._cycle_field(1)
        return

    def _cycle_field(self, direction: int) -> None:
      """Move focus to the next/previous input field."""
      self._current_idx = (self._current_idx + direction) % len(self._arg_names)
      name = self._arg_names[self._current_idx]
      try:
        inp = self.query_one(f"#arg-{name}", Input)
        inp.focus()
      except Exception:
        pass

    def _submit(self) -> None:
      """Collect all input values and post ArgsSubmitted."""
      args: dict[str, str] = {}
      for name in self._arg_names:
        try:
          inp = self.query_one(f"#arg-{name}", Input)
          args[name] = inp.value
        except Exception:
          args[name] = ""
      self.post_message(self.ArgsSubmitted(self._command_id, args))

    @staticmethod
    def extract_placeholders(content: str) -> list[str]:
      """Extract $NAME placeholders from command content.

      Returns a deduplicated list of argument names (without the $).
      """
      import re
      matches = re.findall(r"\$([A-Z][A-Z0-9_]*)", content)
      seen: set[str] = set()
      result: list[str] = []
      for m in matches:
        if m not in seen:
          seen.add(m)
          result.append(m)
      return result

    @staticmethod
    def apply_arguments(content: str, args: dict[str, str]) -> str:
      """Replace $NAME placeholders with user-provided values."""
      result = content
      for name, value in args.items():
        result = result.replace(f"${name}", value)
      return result