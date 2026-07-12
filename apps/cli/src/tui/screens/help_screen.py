"""Help modal for TUI."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


HELP_TEXT = """\
[bold cyan]KCode TUI — Keyboard Shortcuts[/bold cyan]

  [bold]Ctrl+N[/bold]      New session
  [bold]Ctrl+L[/bold]      Clear chat display
  [bold]Ctrl+C[/bold]      Quit
  [bold]Escape[/bold]      Cancel streaming / close dialog

[bold cyan]Slash Commands[/bold cyan]  (type [bold]/[/bold] in empty input)

  [bold]/new_session[/bold]       Start a new chat session
  [bold]/refresh_sessions[/bold]  Reload sessions list
  [bold]/toggle_sidebar[/bold]    Show/hide sidebar panel
  [bold]/clear[/bold]             Clear chat display
  [bold]/model[/bold]             Switch active model
  [bold]/approval[/bold]          Toggle ask/auto approval mode
  [bold]/help[/bold]              Show this help screen
  [bold]/quit[/bold]              Exit KCode TUI

[bold cyan]Input[/bold cyan]

  [bold]Enter[/bold]           Send message
  [bold]Shift+Enter[/bold]    Insert newline

[dim]Press Escape to close.[/dim]
"""


class HelpScreen(ModalScreen[None]):
  """Modal help screen showing keyboard shortcuts and commands."""

  DEFAULT_CSS = """
  HelpScreen {
    align: center middle;
  }

  #help-box {
    width: 64;
    max-width: 80;
    height: auto;
    max-height: 80%;
    border: thick $accent;
    background: $surface;
    padding: 1 2;
    overflow-y: auto;
  }
  """

  def compose(self) -> ComposeResult:
    with Vertical(id="help-box"):
      yield Static(HELP_TEXT)

  def on_key(self, event) -> None:
    if event.key == "escape":
      self.dismiss(None)
