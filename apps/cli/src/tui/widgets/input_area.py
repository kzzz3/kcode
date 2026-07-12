"""User input area -- Enter submits, / triggers inline slash-command overlay.

Design notes:
  - Single-line / multi-line toggle (Shift+Enter for newlines)
  - '/' at start opens the slash overlay automatically
  - Placeholder text when empty
  - All slash interaction delegated to MainScreen via messages
  - Ctrl+K opens command palette (any time, not just empty input)
  - Real-time filter updates as user types after '/'
"""
from __future__ import annotations

from textual.widgets import TextArea
from textual.message import Message


class InputArea(TextArea):
  """Multi-line text input with slash-command autocomplete integration.

  Behaviour:
    * Empty input shows a dim placeholder hint.
    * Typing '/' at the start (or after only whitespace) opens the slash overlay.
    * Ctrl+K opens command palette regardless of input state.
    * While the overlay is open, continued typing updates the filter in real time.
    * Arrow keys navigate, Tab / Enter confirms, Esc dismisses.
    * Enter (with overlay closed) submits the message.
    * Shift+Enter inserts a newline.
    * Escape cancels streaming when overlay is not open.
  """

  DEFAULT_CSS = """
  InputArea {
    height: 5;
    min-height: 3;
    max-height: 10;
    border: solid $primary;
    padding: 0 1;
  }
  """

  PLACEHOLDER = "Type a message... (/ for commands, Ctrl+K palette)"

  # ── Messages ───────────────────────────────────────────────────────

  class OpenSlashOverlay(Message):
    """Request to show the inline slash-command overlay."""
    def __init__(self, query: str) -> None:
      self.query = query
      super().__init__()

  class UpdateSlashFilter(Message):
    """Update the overlay filter as the user types after '/'."""
    def __init__(self, query: str) -> None:
      self.query = query
      super().__init__()

  class NavigateSlash(Message):
    """Navigate the overlay up or down."""
    def __init__(self, direction: str) -> None:
      self.direction = direction  # "up" or "down"
      super().__init__()

  class ConfirmSlash(Message):
    """User confirmed a slash command (Tab or Enter while overlay open)."""
    pass

  class DismissSlash(Message):
    """User wants to dismiss the slash overlay."""
    pass

  class Submitted(Message):
    """User pressed Enter (overlay closed) to submit their message."""
    def __init__(self, value: str) -> None:
      self.value = value
      super().__init__()

  class CancelRequested(Message):
    """User pressed Escape to cancel active streaming."""
    pass

  # ── State ──────────────────────────────────────────────────────────

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    self._slash_active: bool = False
    self._palette_mode: bool = False  # True when opened via Ctrl+K

  # ── Change tracking for live filter ────────────────────────────────

  def on_changed(self, event: TextArea.Changed) -> None:
    """When text changes while slash overlay is open, update the filter."""
    if not self._slash_active:
      return
    text = self.text
    if self._palette_mode:
      # In palette mode, any text is the filter (no leading /)
      self.post_message(self.UpdateSlashFilter(text))
      return
    if not text.startswith("/"):
      # User deleted the slash -- dismiss
      self._slash_active = False
      self._palette_mode = False
      self.post_message(self.DismissSlash())
      return
    # Send the full slash text (e.g. "/mod") as the filter query
    self.post_message(self.UpdateSlashFilter(text))

  # ── Key handling ───────────────────────────────────────────────────

  def on_key(self, event) -> None:
    key = event.key

    # --- Ctrl+K: open command palette at any time ---
    if key == "ctrl+k":
      event.prevent_default()
      if self._slash_active:
        # Already open -- close it
        self._slash_active = False
        self._palette_mode = False
        self.post_message(self.DismissSlash())
      else:
        self._palette_mode = True
        self._slash_active = True
        self.post_message(self.OpenSlashOverlay(""))
      return

    # --- Slash overlay navigation ---
    if self._slash_active:
      if key == "up":
        event.prevent_default()
        self.post_message(self.NavigateSlash("up"))
        return
      if key == "down":
        event.prevent_default()
        self.post_message(self.NavigateSlash("down"))
        return
      if key == "tab":
        event.prevent_default()
        self.post_message(self.ConfirmSlash())
        return
      # Enter while overlay open: confirm and execute immediately
      if key == "enter":
        event.prevent_default()
        self.post_message(self.ConfirmSlash())
        return
      if key == "escape":
        event.prevent_default()
        self._slash_active = False
        self._palette_mode = False
        self.post_message(self.DismissSlash())
        return

    # --- Open overlay on '/' at start of input ---
    if key == "slash" and self._should_open_slash():
      event.prevent_default()
      self._slash_active = True
      self._palette_mode = False
      # Insert the slash so the user can see it
      self.insert("/")
      self.post_message(self.OpenSlashOverlay("/"))
      return

    # --- Submit ---
    if key == "enter" and not event.shift:
      event.prevent_default()
      text = self.text.strip()
      if text:
        self.post_message(self.Submitted(text))
        self.clear()
      return

    # --- Cancel streaming ---
    if key == "escape":
      event.prevent_default()
      self.post_message(self.CancelRequested())

  # ── Slash overlay lifecycle ────────────────────────────────────────

  def activate_slash_overlay(self) -> None:
    """Called by MainScreen when overlay is confirmed visible."""
    self._slash_active = True

  def deactivate_slash_overlay(self) -> None:
    """Called by MainScreen when overlay is dismissed or command selected."""
    self._slash_active = False
    self._palette_mode = False

  def clear_slash_text(self) -> None:
    """Remove the slash + filter text from the input after a command is selected."""
    if self._palette_mode:
      # Don't clear user text in palette mode -- they may have been typing
      return
    self.clear()

  @property
  def is_slash_active(self) -> bool:
    """Whether the slash overlay is currently active."""
    return self._slash_active

  @property
  def is_palette_mode(self) -> bool:
    """Whether we're in Ctrl+K palette mode (vs slash mode)."""
    return self._palette_mode

  # ── Internals ──────────────────────────────────────────────────────

  def _should_open_slash(self) -> bool:
    """Return True if input is empty or only whitespace.

    We allow '/' to trigger the overlay whenever the input contains no
    visible content. This is more robust than checking cursor position,
    which can drift in edge cases with multi-line input.
    """
    return not self.text.strip()