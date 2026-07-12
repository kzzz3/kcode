"""User input area with Enter-to-submit, Shift+Enter for newline, / for palette."""
from __future__ import annotations

from textual.widgets import TextArea
from textual.message import Message


class InputArea(TextArea):
  """Multi-line text input with Enter-to-submit semantics."""

  DEFAULT_CSS = """
  InputArea {
    height: 5;
    min-height: 3;
    max-height: 10;
    border: solid $primary;
    padding: 0 1;
  }
  """

  class OpenCommandPalette(Message):
    """Emitted when the user explicitly requests the command palette."""
    pass

  class Submitted(Message):
    """Emitted when the user presses Enter (without Shift)."""
    def __init__(self, value: str) -> None:
      self.value = value
      super().__init__()

  class CancelRequested(Message):
    """Emitted when the user presses Escape to cancel streaming."""
    pass

  def on_key(self, event) -> None:
    """Slash opens palette; Enter submits; Shift+Enter inserts newline; Escape cancels."""
    if event.key == "slash" and not self.text:
      event.prevent_default()
      self.post_message(self.OpenCommandPalette())
      return

    if event.key == "enter" and not event.shift:
      event.prevent_default()
      text = self.text.strip()
      if text:
        self.post_message(self.Submitted(text))
        self.clear()
      return

    if event.key == "escape":
      event.prevent_default()
      self.post_message(self.CancelRequested())
