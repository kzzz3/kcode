"""Inline slash-command autocomplete overlay -- dropdown below InputArea.

Inspired by OpenCode/Crush command palette: typed '/' opens a non-modal
overlay that filters in real time, grouped by category with icons, aliases,
keyboard shortcuts, and rich visual hints. Supports both built-in and
custom commands from user/project directories (including nested dirs).

Visual enhancements (OpenCode-inspired):
  - Two-line rendering: icon + title (bold) + shortcut badge right-aligned
    on line 1; description (muted) on line 2
  - Selected item with primary background highlight
  - No-results placeholder with hint
  - Category section headers with emoji icons and divider lines
  - Scroll-to-selected on arrow key navigation
  - Keyboard shortcut badges rendered as dim cyan pills
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widget import Widget
from textual.message import Message
from textual.widgets import Static, Input

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
  argument_names: list[str] | None = None  # For custom commands with $ARGUMENT placeholders

# -- Built-in command catalogue -----------------------------------------------

SLASH_COMMANDS: list[SlashCommand] = [
  # Session
  SlashCommand("new",      "New Session",   "Start a fresh chat session",            "session",  icon="➕", shortcut="Ctrl+N"),
  SlashCommand("compact",  "Compact",       "Compact conversation to save tokens",   "session",  icon="⚙️"),
  SlashCommand("clear",    "Clear Chat",    "Clear the current chat display",        "session",  icon="🗑️", shortcut="Ctrl+L"),
  SlashCommand("sessions", "Sessions",      "List and switch between sessions",      "session",  icon="📋"),
  SlashCommand("refresh",  "Refresh",       "Reload sessions list",                  "session",  icon="🔄"),
  # View
  SlashCommand("sidebar",  "Toggle Sidebar","Show / hide the sidebar panel",         "view",     alias="sb", icon="👁️", shortcut="Ctrl+B"),
  SlashCommand("theme",    "Cycle Theme",   "Switch between available themes",       "view",     alias="t",  icon="🎨"),
  # Model
  SlashCommand("model",    "Switch Model",  "Change the active LLM model",           "model",    alias="m",  icon="🤖"),
  # Config
  SlashCommand("approval", "Approval Mode", "Toggle ask / auto approval",            "config",   alias="ap", icon="🛡️"),
  # Help
  SlashCommand("help",     "Help",          "Show keyboard shortcuts and commands",  "help",     alias="h",  icon="❓", shortcut="Ctrl+H"),
  SlashCommand("doctor",   "Doctor",        "Check runtime health status",           "help",     alias="dr", icon="⚕️"),
  SlashCommand("init",     "Init Project",  "Create/Update kcode.workspace.md",      "project",  icon="📁"),
  # App
  SlashCommand("quit",     "Quit",          "Exit KCode TUI",                        "app",      alias="q",  icon="🔟", shortcut="Ctrl+Q"),
]

# Category display order, labels, and icons
CATEGORY_META: list[tuple[str, str, str]] = [
  ("session", "Session",  "💬"),  # speech balloon
  ("view",    "View",     "👁"),  # eye
  ("model",   "Model",    "🤖"),  # robot face
  ("config",  "Config",   "⚙️"),  # gear
  ("project", "Project",  "📁"),  # folder
  ("help",    "Help",     "❓"),      # red question mark
  ("app",     "App",      "🚪"),  # door
]

# -- Filtering -----------------------------------------------------------------

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

  # Catch any categories not in CATEGORY_META
  for cat_key, cmds in by_cat.items():
    if cat_key not in seen:
      result.append((cat_key, ">", cmds))

  return result

class SlashOverlay(Widget):
  """Inline overlay that appears above the input area.

  Renders grouped command items with icons, two-line layout,
  and keyboard navigation. Hides itself when not active.
  """

  # Total visible commands before scrolling
  _MAX_VISIBLE = 10

  DEFAULT_CSS = """
  SlashOverlay {
    display: none;
    height: auto;
    max-height: 60%;
    overflow: hidden;
    background: $surface;
    border: tall $primary 40%;
    margin: 0 2;
    padding: 0;
    layer: overlay;
  }

  SlashOverlay.visible {
    display: block;
  }

  .slash-scroll {
    height: auto;
    max-height: 28;
    overflow-y: auto;
    scrollbar-size-vertical: 1;
  }

  /* Category header */
  .slash-category {
    height: 1;
    padding: 0 1;
    margin: 1 0 0 0;
    color: $accent;
    text-style: bold dim;
  }

  .slash-category:first-child {
    margin-top: 0;
  }

  /* Command item - two-line layout */
  .slash-item {
    height: auto;
    min-height: 2;
    padding: 0 1;
    margin: 0;
  }

  .slash-item .slash-row1 {
    height: 1;
    width: 100%;
  }

  .slash-item .slash-row2 {
    height: 1;
    width: 100%;
  }

  /* Icon + title on row 1 */
  .slash-icon {
    width: 2;
    text-align: center;
    color: $accent;
  }

  .slash-title {
    width: 1fr;
    color: $text;
    text-style: bold;
  }

  /* Shortcut badge -- pill-like */
  .slash-shortcut {
    width: auto;
    min-width: 8;
    text-align: right;
    color: $accent;
    text-style: bold dim;
    padding: 0 1;
    background: $surface;
    border: round $primary 40%;
  }

  /* Alias hint */
  .slash-alias {
    width: auto;
    min-width: 3;
    text-align: right;
    color: $warning;
    text-style: dim;
    padding: 0 1 0 0;
  }

  /* Description on row 2 */
  .slash-desc {
    width: 1fr;
    padding-left: 4;
    color: $text-muted;
    text-style: dim;
  }

  /* Selected state -- accent left bar + background highlight */
  .slash-item.selected {
    background: $primary 20%;
    border-left: tall $primary;
  }
  .slash-item.selected .slash-title {
    color: $text;
    text-style: bold;
  }
  .slash-item.selected .slash-icon {
    color: $primary;
    text-style: bold;
  }
  .slash-item.selected .slash-desc {
    color: $text;
  }
  .slash-item.selected .slash-shortcut {
    color: $accent;
    background: $primary 30%;
  }

  /* Hover effect */
  .slash-item:hover {
    background: $primary 10%;
    border-left: tall $primary 50%;
  }
  .slash-item:hover .slash-title {
    text-style: bold;
  }

  /* No results placeholder */
  .slash-empty {
    height: 3;
    padding: 1 2;
    color: $text-muted;
    text-style: dim italic;
    text-align: center middle;
    background: $surface;
  }

  /* Scroll hint at bottom when content overflows */
  .slash-scroll-hint {
    height: 1;
    text-align: center;
    color: $text-muted;
    text-style: dim;
    background: $surface;
  }
  """

  class CommandSelected(Message):
    """Posted when user selects a command."""
    def __init__(self, command_id: str, content: str | None = None) -> None:
      self.command_id = command_id
      self.content = content
      super().__init__()

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    self._active: bool = False
    self._query: str = ""
    self._commands: list[SlashCommand] = list(SLASH_COMMANDS)
    self._custom_commands: list[SlashCommand] = []
    self._selected_idx: int = 0
    self._visible_ids: list[str] = []
    self.selected_id: str | None = None

  # -- Public API ------------------------------------------------------------

  def set_custom_commands(self, custom: list[SlashCommand]) -> None:
    """Inject custom commands (loaded from user/project dirs).

    Each item should be a SlashCommand with at least {id, label, description}.
    Optional fields: category, icon, shortcut, is_custom, content, argument_names.
    """
    self._custom_commands = custom
    self._commands = list(SLASH_COMMANDS) + custom

  def show_overlay(self, query: str) -> None:
    """Show overlay with optional initial filter."""
    self._active = True
    self._query = query
    self._selected_idx = 0
    self.add_class("visible")
    self._rebuild()

  def hide_overlay(self) -> None:
    """Hide and reset."""
    self._active = False
    self._query = ""
    self._selected_idx = 0
    self.remove_class("visible")
    self._rebuild()

  def update_filter(self, query: str) -> None:
    """Update the filter text (called as user types)."""
    self._query = query
    self._selected_idx = 0
    self._rebuild()

  def move_up(self) -> None:
    """Move selection up."""
    if self._visible_ids:
      self._selected_idx = max(0, self._selected_idx - 1)
      self._update_selection()
      self._scroll_to_selected()

  def move_down(self) -> None:
    """Move selection down."""
    if self._visible_ids:
      self._selected_idx = min(
        len(self._visible_ids) - 1, self._selected_idx + 1
      )
      self._update_selection()
      self._scroll_to_selected()

  def confirm_selection(self) -> tuple[str | None, str | None]:
    """Confirm selection -- returns (command_id, content) or (None, None)."""
    if not self._visible_ids:
      return None, None
    idx = min(self._selected_idx, len(self._visible_ids) - 1)
    selected_id = self._visible_ids[idx]
    # Find matching command to get content
    content = None
    for cmd in self._commands:
      if cmd.id == selected_id:
        content = cmd.content
        break
    return selected_id, content

  # -- Compose ---------------------------------------------------------------

  def compose(self) -> ComposeResult:
    # The content is built dynamically in _rebuild
    yield Vertical(classes="slash-scroll", id="slash-scroll-container")

  # -- Internal ---------------------------------------------------------------

  def _rebuild(self) -> None:
    """Rebuild the overlay content from scratch."""
    container = self.query_one("#slash-scroll-container")
    container.remove_children()

    if not self._active:
      self._visible_ids = []
      return

    filtered = filter_slash_commands(self._commands, self._query)

    if not filtered:
      container.mount(Static(
        "\n  \u2716  No matching commands\n  \u2514  Try a shorter or different query",
        classes="slash-empty",
      ))
      self._visible_ids = []
      return

    # Custom category first if any custom commands match
    groups = group_by_category(filtered)

    item_idx = 0
    for group_label, group_icon, group_cmds in groups:
      # Category header
      header_text = f"  {group_icon} {group_label}"
      container.mount(Static(header_text, classes="slash-category"))

      for cmd in group_cmds:
        selected = item_idx == self._selected_idx
        widget = self._build_item_widget(cmd, selected, item_idx)
        container.mount(widget)
        item_idx += 1

    self._visible_ids = [c.id for _, _, cmds in groups for c in cmds]

    # Ensure selected_idx is valid
    if self._selected_idx >= len(self._visible_ids):
      self._selected_idx = max(0, len(self._visible_ids) - 1)
      self._update_selection()

    # Show scroll hint when content overflows
    self._update_scroll_hint(container)

  @staticmethod
  def _highlight_match(text: str, query: str) -> str:
    """Sequential fuzzy highlight for *text* against *query*.

    Returns a Rich-markup string with matched characters wrapped in
    ``[bold cyan]...[/bold cyan]`` so the dropdown can render
    progressively better matches as the user types.
    """
    if not query:
      return text

    q = query.lower()
    qi = 0
    out: list[str] = []
    for ch in text:
      if qi < len(q) and ch.lower() == q[qi]:
        out.append(f"[bold cyan]{ch}[/bold cyan]")
        qi += 1
      else:
        out.append(ch)
    return "".join(out)

  def _build_item_widget(
    self, cmd: SlashCommand, selected: bool, idx: int,
  ) -> Widget:
    """Build a two-line widget for a single command."""
    classes = "slash-item" + (" selected" if selected else "")
    item = Vertical(classes=classes)
    item._cmd_id = cmd.id  # type: ignore[attr-defined]
    item._cmd_content = cmd.content  # type: ignore[attr-defined]
    item._item_idx = idx  # type: ignore[attr-defined]
    item.id = f"slash-item-{idx}"

    # Row 1: icon + title + shortcut/alias
    title_text = f"{cmd.icon}  {self._highlight_match(cmd.label, self._query)}"
    row1_children: list[Widget] = [
      Static(title_text, classes="slash-title"),
    ]
    if cmd.shortcut:
      row1_children.append(
        Static(f"  {cmd.shortcut}  ", classes="slash-shortcut")
      )
    elif cmd.alias:
      row1_children.append(
        Static(f"  /{cmd.alias}  ", classes="slash-alias")
      )
    row1 = Horizontal(*row1_children, classes="slash-row1")

    # Row 2: description
    row2 = Static(f"    {cmd.description}", classes="slash-row2 slash-desc")

    item.mount(row1)
    item.mount(row2)
    return item

  def _update_selection(self) -> None:
    """Update CSS classes to reflect current selection."""
    try:
      scroll = self.query_one("#slash-scroll-container")
      for child in scroll.query(".slash-item"):
        if child.has_class("selected"):
          child.remove_class("selected")
      # Add selected class to current
      selected = self.query_one(f"#slash-item-{self._selected_idx}")
      selected.add_class("selected")
    except Exception:
      pass

  def _scroll_to_selected(self) -> None:
    """Scroll the container so the selected item is visible."""
    try:
      selected_wid = f"slash-item-{self._selected_idx}"
      widget = self.query_one(f"#{selected_wid}")
      widget.scroll_visible()
    except Exception:
      pass

  def _update_scroll_hint(self, container: Widget) -> None:
    """Add or remove a scroll-overflow hint at the bottom of the overlay."""
    try:
      existing = container.query(".slash-scroll-hint")
      for e in existing:
        e.remove()
    except Exception:
      pass
    total = len(self._visible_ids)
    if total > self._MAX_VISIBLE:
      sel = self._selected_idx + 1
      hint = f"  \u25b2\u25bc  {sel}/{total}  (arrow keys to scroll)"
      container.mount(Static(hint, classes="slash-scroll-hint"))

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

  # -- Argument dialog support -----------------------------------------------

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