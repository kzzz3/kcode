"""KCode CLI application entrypoint."""
from __future__ import annotations

from pathlib import Path

import typer

from apps.cli.src.commands import config as config_cmd
from apps.cli.src.commands import doctor as doctor_cmd
from apps.cli.src.commands.chat import run_chat
from apps.cli.src.commands.init import run_init
from apps.cli.src.commands.models import run_models

app = typer.Typer(add_completion=False, help="KCode CLI coding agent.")
app.add_typer(config_cmd.app, name="config", help="Inspect and validate configuration.")
app.command(name="init")(run_init)
app.command(name="doctor")(doctor_cmd.run_doctor)
app.command(name="chat")(run_chat)
app.command(name="models")(run_models)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo("kcode 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-v", is_eager=True, help="Show version and exit.", callback=_version_callback),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging."),
    workspace: Path | None = typer.Option(None, "--workspace", "-w", help="Workspace root override."),
) -> None:
    """Global CLI options."""
    return
@app.command()
def tui() -> None:
    """Launch the Terminal User Interface."""
    from .tui.app import KCodeTUI
    app = KCodeTUI()
    app.run()
