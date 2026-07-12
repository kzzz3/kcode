"""Modal approval dialog for sensitive tool calls."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Static, Label
from textual.screen import ModalScreen


class ApprovalDialog(ModalScreen[bool]):
  """Modal that asks the user to approve or reject a tool call."""

  DEFAULT_CSS = """
  ApprovalDialog {
    align: center middle;
    background: $boost 60%;
  }

  #dialog {
    width: 70;
    max-width: 90;
    height: auto;
    max-height: 80%;
    border: thick $warning;
    background: $surface;
    padding: 1 2;
  }

  #tool-info {
    height: auto;
    max-height: 20;
    overflow-y: auto;
    margin: 1 0;
  }

  #buttons {
    width: 100%;
    height: auto;
    align: center middle;
    margin: 1 0 0 0;
  }

  Button {
    margin: 0 1;
    min-width: 12;
  }
  """

  def __init__(self, tool_name: str, tool_args: dict, safety_class: str = "unknown") -> None:
    super().__init__()
    self.tool_name = tool_name
    self.tool_args = tool_args
    self.safety_class = safety_class

  def compose(self) -> ComposeResult:
    import json
    args_display = json.dumps(self.tool_args, indent=2, ensure_ascii=False)
    if len(args_display) > 500:
      args_display = args_display[:500] + "\n..."

    with Vertical(id="dialog"):
      yield Label("Tool Approval Required", id="title")
      yield Static(f"[bold]{self.tool_name}[/bold] ({self.safety_class})", id="tool-name")
      yield Static(args_display, id="tool-info")
      with Horizontal(id="buttons"):
        yield Button("Approve (y)", variant="primary", id="btn-approve")
        yield Button("Reject (n)", variant="error", id="btn-reject")

  def on_key(self, event) -> None:
    """y approves, n rejects."""
    if event.key == "y":
      self.dismiss(True)
    elif event.key == "n":
      self.dismiss(False)

  def on_button_pressed(self, event: Button.Pressed) -> None:
    if event.button.id == "btn-approve":
      self.dismiss(True)
    elif event.button.id == "btn-reject":
      self.dismiss(False)