"""CLI: kcode models — list available models from the configured provider."""
from __future__ import annotations

from pathlib import Path

import httpx
from rich import print as rprint
from rich.table import Table
import typer

from apps.cli.src.config.resolution import resolve_config
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


def run_models(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON instead of a table."),
) -> None:
    """List available models from the configured provider (GET /v1/models)."""
    config = resolve_config(workspace.resolve(), overrides={"workspace_root": str(workspace.resolve())})
    client = OpenAICompatibleClient(config.model)

    try:
        models = client.list_models()
    except httpx.ConnectError:
        rprint(f"[red]Connection failed:[/red] cannot reach {config.model.base_url}")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as exc:
        rprint(f"[red]API error {exc.response.status_code}:[/red] {exc.response.text[:200]}")
        raise typer.Exit(code=1)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if not models:
        rprint("[yellow]No models returned by provider.[/yellow]")
        raise typer.Exit(code=0)

    if json_output:
        import json
        out = [{"id": m.id, "owned_by": m.owned_by} for m in models]
        rprint(json.dumps(out, indent=2))
        return

    table = Table(title=f"Models @ {config.model.base_url}")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model ID", style="bold cyan")
    table.add_column("Owned By", style="dim")

    default = config.model.default_model or ""
    for idx, m in enumerate(models, 1):
        marker = " *" if m.id == default else ""
        table.add_row(str(idx), f"{m.id}{marker}", m.owned_by)

    rprint(table)
    if default:
        rprint(f"[dim]* = current default ({default})[/dim]")
    rprint(f"[dim]{len(models)} model(s) available[/dim]")