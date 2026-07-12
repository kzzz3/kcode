"""User input area -- Enter submits, / triggers inline slash-command overlay."""
from __future__ import annotations

from textual.widgets import TextArea
from textual.message import Message


class InputArea(TextArea):
  """Multi-line text input with slash-command autocomplete integration.

  Behaviour:
    * Typing '/' at the start (or after only whitespace) opens the slash overlay.
    * While the overlay is open, arrow keys navigate, Tab / Enter confirms, Esc dismisses.
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

  # ── Key handling ───────────────────────────────────────────────────

  def on_key(self, event) -> None:
    key = event.key

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
      if key in ("tab", "enter"):
        event.prevent_default()
        self.post_message(self.ConfirmSlash())
        return
      if key == "escape":
        event.prevent_default()
        self._slash_active = False
        self.post_message(self.DismissSlash())
        return

    # --- Open overlay on '/' ---
    if key == "slash" and self._should_open_slash():
      event.prevent_default()
      self._slash_active = True
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

  def clear_slash_text(self) -> None:
    """Remove the slash + filter text from the input after a command is selected."""
    text = self.text
    if text.startswith("/"):
      # Find where the slash expression ends
      self.clear()

  # ── Internals ──────────────────────────────────────────────────────

  def _should_open_slash(self) -> bool:
    """Return True if cursor is at the start and input is empty or whitespace."""
    return not self.text.strip()
