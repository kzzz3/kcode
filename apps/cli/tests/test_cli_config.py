from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from apps.cli.src.kcode_cli import app

runner = CliRunner()


def test_config_show_returns_dump(tmp_path: Path) -> None:
  result = runner.invoke(app, ["config", "show", "--workspace", str(tmp_path)])
  assert result.exit_code == 0
  assert "workspace_root" in result.output


def test_config_validate_prints_success(tmp_path: Path) -> None:
  result = runner.invoke(app, ["config", "validate", "--workspace", str(tmp_path)])
  assert result.exit_code == 0
  assert "Configuration valid for workspace" in result.output


def test_config_show_contains_model_section(tmp_path: Path) -> None:
  result = runner.invoke(app, ["config", "show", "--workspace", str(tmp_path)])
  assert result.exit_code == 0
  assert "model" in result.output
  assert "api_base" in result.output or "default_model" in result.output

def test_config_show_contains_mcp_section(tmp_path: Path) -> None:
  """config show output should include MCP section key."""
  result = runner.invoke(app, ["config", "show", "--workspace", str(tmp_path)])
  assert result.exit_code == 0
  assert "mcp" in result.output.lower()
