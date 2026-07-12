"""Tests for kcode init command."""
from __future__ import annotations

from pathlib import Path

from apps.cli.src.commands.init import run_init


def _init(path: Path, interactive: bool = False) -> None:
    """Helper: call run_init bypassing Typer Option markers."""
    run_init(path=path, interactive=interactive)


def test_run_init_creates_kcode_directory(tmp_path: Path) -> None:
    _init(tmp_path)
    assert (tmp_path / ".kcode").is_dir()


def test_run_init_creates_workspace_readme(tmp_path: Path) -> None:
    _init(tmp_path)
    readme = tmp_path / "kcode.workspace.md"
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "# KCode Workspace" in content
    assert "Initialized workspace" in content


def test_run_init_is_idempotent(tmp_path: Path) -> None:
    _init(tmp_path)
    readme_before = (tmp_path / "kcode.workspace.md").read_text(encoding="utf-8")
    _init(tmp_path)
    readme_after = (tmp_path / "kcode.workspace.md").read_text(encoding="utf-8")
    assert (tmp_path / ".kcode").is_dir()
    assert readme_before == readme_after


def test_run_init_no_interactive_does_not_write_config(tmp_path: Path) -> None:
    """Default init (non-interactive) should not create config file."""
    _init(tmp_path)
    config_path = tmp_path / ".kcode" / "config.yaml"
    assert not config_path.exists()
