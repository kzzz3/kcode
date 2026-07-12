from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from apps.cli.src.kcode_cli import app

runner = CliRunner()


def test_version_flag_prints_version() -> None:
  result = runner.invoke(app, ["--version"])
  assert result.exit_code == 0
  assert "kcode 0.1.0" in result.output


def test_init_creates_directory(tmp_path: Path) -> None:
  result = runner.invoke(app, ["init", "--path", str(tmp_path / "ws")])
  assert result.exit_code == 0
  assert (tmp_path / "ws" / ".kcode").exists()


def test_doctor_runs_without_crash(tmp_path: Path) -> None:
  (tmp_path / ".kcode").mkdir(parents=True, exist_ok=True)
  result = runner.invoke(app, ["doctor", "--workspace", str(tmp_path)])
  assert result.exit_code in {0, 1}

def test_doctor_nonexistent_workspace_exits_failure() -> None:
  """When --workspace points to a nonexistent path, doctor should report failure."""
  result = runner.invoke(
    app,
    ["doctor", "--workspace", "Z:\\nonexistent\\path\\that\\does\\not\\exist"],
  )
  assert result.exit_code == 1


def test_doctor_missing_kcode_dir_exits_failure(tmp_path: Path) -> None:
  """When .kcode/ is missing, doctor should exit with code 1."""
  # tmp_path exists but has no .kcode directory
  result = runner.invoke(app, ["doctor", "--workspace", str(tmp_path)])
  assert result.exit_code == 1
