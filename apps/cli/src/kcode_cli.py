"""KCode CLI application entrypoint."""
from __future__ import annotations

from pathlib import Path

import typer
from typing_extensions import Annotated

from apps.cli.src.commands import config as config_cmd
from apps.cli.src.commands import doctor as doctor_cmd
from apps.cli.src.commands.chat import run_chat
from apps.cli.src.commands.init import run_init
from apps.cli.src.commands.models import run_models

app = typer.Typer(
  add_completion=False,
  invoke_without_command=True,
  help="KCode — AI coding agent. Runs TUI by default.",
)
app.add_typer(config_cmd.app, name="config", help="Inspect and validate configuration.")
app.command(name="init")(run_init)
app.command(name="doctor")(doctor_cmd.run_doctor)
app.command(name="chat")(run_chat)
app.command(name="models")(run_models)


def _version_callback(value: bool) -> None:
  if value:
    typer.echo("kcode 0.1.0")
    raise typer.Exit()


# Global options set by the callback, consumed by subcommands / default TUI launch.
_global_workspace: Path | None = None
_global_debug: bool = False
_global_approval: str = "auto"
_global_model: str | None = None


@app.callback()
def main(
  version: Annotated[bool, typer.Option("--version", "-v", is_eager=True, help="Show version and exit.", callback=_version_callback)] = False,
  debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
  workspace: Annotated[Path | None, typer.Option("--workspace", "-w", help="Workspace root override.")] = None,
  approval: Annotated[str, typer.Option("--approval", "-a", help="Approval mode: manual or auto.")] = "auto",
  model: Annotated[str | None, typer.Option("--model", "-m", help="Model name override.")] = None,
  ctx: typer.Context = typer.Context,
) -> None:
  """KCode — AI coding agent. Launches TUI when no subcommand is given."""
  global _global_workspace, _global_debug, _global_approval, _global_model
  _global_workspace = workspace
  _global_debug = debug
  _global_approval = approval
  _global_model = model

  if ctx.invoked_subcommand is None:
    _launch_tui()


@app.command(name="tui", hidden=True)
def tui_cmd() -> None:
  """Launch the Terminal User Interface (default)."""
  _launch_tui()


def _launch_tui() -> None:
  """Start the Textual TUI."""
  if _global_debug:
    import logging
    logging.basicConfig(level=logging.DEBUG)

  from .tui.app import KCodeTUI
  application = KCodeTUI(
    workspace_root=_global_workspace,
    approval_mode=_global_approval,
    model=_global_model,
  )
  application.run()
