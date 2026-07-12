"""User input area with Enter-to-submit, Shift+Enter for newline."""
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

  class Submitted(Message):
    """Emitted when the user presses Enter (without Shift)."""
    def __init__(self, value: str) -> None:
      self.value = value
      super().__init__()

  def on_key(self, event) -> None:
    """Enter submits; Shift+Enter inserts newline."""
    if event.key == "enter" and not event.shift:
      event.prevent_default()
      text = self.text.strip()
      if text:
        self.post_message(self.Submitted(text))
        self.clear()
