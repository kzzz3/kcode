"""Modal approval dialog for sensitive tool calls."""

from __future__ import annotations



from textual.app import ComposeResult

from textual.containers import Vertical, Horizontal

from textual.widgets import Button, Static, Label

from textual.screen import ModalScreen

from rich.syntax import Syntax





# Safety-class -> (border_color, label_color)

_SAFETY_STYLES: dict[str, tuple[str, str]] = {

  "write":   ("$warning",  "yellow"),

  "system":  ("$error",    "red"),

  "network": ("$accent",   "blue"),

}





class ApprovalDialog(ModalScreen[bool]):

  """Modal that asks the user to approve or reject a tool call."""



  DEFAULT_CSS = """

  ApprovalDialog {

    align: center middle;

    background: $boost 60%;

  }



  #dialog {

    width: 75;

    max-width: 95;

    height: auto;

    max-height: 80%;

    border: thick $warning;

    background: $surface;

    padding: 1 2;

  }



  #tool-name {

    height: auto;

    margin: 0 0 1 0;

  }



  #tool-info {

    height: auto;

    max-height: 24;

    overflow-y: auto;

    margin: 1 0;

    background: $surface;

  }



  #buttons {

    width: 100%;

    height: auto;

    align: center middle;

    margin: 1 0 0 0;

  }



  Button {

    margin: 0 1;

    min-width: 14;

  }

  """



  def __init__(self, tool_name: str, tool_args: dict, safety_class: str = "unknown") -> None:

    super().__init__()

    self.tool_name = tool_name

    self.tool_args = tool_args

    self.safety_class = safety_class



  def compose(self) -> ComposeResult:

    import json

    border_color, label_color = _SAFETY_STYLES.get(

      self.safety_class, ("$warning", "white"),

    )



    # Format args as highlighted JSON

    args_json = json.dumps(self.tool_args, indent=2, ensure_ascii=False)

    if len(args_json) > 800:

      args_json = args_json[:800] + " ..."

    syntax = Syntax(args_json, "json", theme="monokai", word_wrap=True)



    safety_label = self.safety_class.upper()



    with Vertical(id="dialog", styles={"border": ("thick", border_color)}):

      yield Label("Tool Approval Required", id="title")

      yield Static(

        f"[bold {label_color}]\u26a0 {self.tool_name}[/]  "

        f"[dim]\u2014 {safety_label}[/]",

        id="tool-name",

      )

      yield Static(syntax, id="tool-info")

      with Horizontal(id="buttons"):

        yield Button("Approve  y", variant="primary", id="btn-approve")

        yield Button("Reject  n", variant="error", id="btn-reject")



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

