"""CLI: kcode config."""
from __future__ import annotations

from pathlib import Path

from rich import print as rprint
from rich.pretty import pretty_repr
import typer

from apps.cli.src.config.resolution import resolve_config

app = typer.Typer(help="Configuration utilities.")


@app.command("show")
def show_config(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
) -> None:
    """Show resolved configuration."""
    config = resolve_config(workspace)
    rprint(pretty_repr(config.model_dump()))


@app.command("validate")
def validate_config(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
) -> None:
    """Validate configuration sources and exit."""
    config = resolve_config(workspace)
    rprint(f"[green]Configuration valid for workspace:[/green] {config.workspace_root.resolve()}")

