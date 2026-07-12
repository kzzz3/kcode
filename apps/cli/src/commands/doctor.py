"""CLI: kcode doctor."""
from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
from pathlib import Path

from rich import print as rprint
import typer

from apps.cli.src.config.resolution import resolve_config
from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.tools.builtin_core import register_core_tools
from apps.cli.src.tools.builtin_readonly import register_readonly_tools


def _check(name: str, ok: bool, detail: str = "") -> bool:
  status = "[green]ok[/green]" if ok else "[red]FAIL[/red]"
  suffix = f" — {detail}" if detail else ""
  rprint(f"  {name}: {status}{suffix}")
  return ok


def run_doctor(
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
) -> None:
    """Validate runtime prerequisites and configuration."""
    rprint("[bold]KCode Doctor[/bold]\n")
    all_ok = True

    # --- Workspace ---
    rprint("[cyan]Workspace[/cyan]")
    cwd = workspace.resolve()
    all_ok &= _check("cwd exists", cwd.exists(), str(cwd))
    kcode_dir = cwd / ".kcode"
    all_ok &= _check(".kcode directory", kcode_dir.exists(), str(kcode_dir))

    # --- Python environment ---
    rprint("\n[cyan]Python[/cyan]")
    import sys
    all_ok &= _check("Python >= 3.13", sys.version_info >= (3, 13), sys.version.split()[0])

    # --- Dependencies ---
    rprint("\n[cyan]Dependencies[/cyan]")
    for mod in ("pydantic", "typer", "httpx", "rich", "yaml"):
        try:
            importlib.import_module(mod)
            all_ok &= _check(f"import {mod}", True)
        except ImportError:
            all_ok &= _check(f"import {mod}", False, "missing")

    # --- git ---
    rprint("\n[cyan]External tools[/cyan]")
    has_git = shutil.which("git") is not None
    all_ok &= _check("git on PATH", has_git)

    # --- Config ---
    rprint("\n[cyan]Configuration[/cyan]")
    try:
      config = resolve_config(cwd)
      all_ok &= _check("config loads", True)
      model_name = config.model.default_model
      all_ok &= _check("model configured", model_name is not None, model_name or "set model.default_model")
      api_key = config.model.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
      all_ok &= _check("API key available", bool(api_key), "set model.api_key or OPENAI_API_KEY" if not api_key else "")
    except Exception as exc:  # noqa: BLE001
      all_ok &= _check("config loads", False, str(exc))

    # --- Tool registry ---
    rprint("\n[cyan]Tool registry[/cyan]")
    reg = ToolRegistry()
    register_readonly_tools(reg)
    register_core_tools(reg)
    expected = {"read_file", "list_files", "create_file", "edit_file", "search_code", "run_command", "git_status", "git_diff", "git_commit"}
    registered = {t.name for t in reg.list_tools()}
    missing = expected - registered
    all_ok &= _check(f"tools registered ({len(registered)}/{len(expected)})", not missing, f"missing: {missing}" if missing else "")

    # --- Session store ---
    rprint("\n[cyan]Session store[/cyan]")
    db_path = kcode_dir / "sessions.sqlite"
    try:
      conn = sqlite3.connect(str(db_path))
      conn.execute("SELECT 1")
      conn.close()
      all_ok &= _check("SQLite writable", True, str(db_path))
    except Exception as exc:  # noqa: BLE001
      all_ok &= _check("SQLite writable", False, str(exc))

    # --- Summary ---
    rprint()
    if all_ok:
      rprint("[green bold]All checks passed.[/green bold]")
    else:
      rprint("[red bold]Some checks failed. Fix the issues above before using KCode.[/red bold]")
    raise typer.Exit(code=0 if all_ok else 1)