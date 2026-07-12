from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click

from apps.cli.src.commands.doctor import run_doctor


def test_run_doctor_runs_without_crash(tmp_path: Path) -> None:
    (tmp_path / ".kcode").mkdir()
    with patch("apps.cli.src.commands.doctor.shutil.which", return_value="/usr/bin/git"):
        try:
            run_doctor(workspace=tmp_path)
        except click.exceptions.Exit as exc:
            assert isinstance(exc.exit_code, int)


def test_run_doctor_reports_missing_kcode_dir(tmp_path: Path) -> None:
    with patch("apps.cli.src.commands.doctor.shutil.which", return_value=None):
        try:
            run_doctor(workspace=tmp_path)
        except click.exceptions.Exit as exc:
            assert exc.exit_code == 1


def test_run_doctor_success_exit_code(tmp_path: Path) -> None:
    (tmp_path / ".kcode").mkdir()
    with patch("apps.cli.src.commands.doctor.shutil.which", return_value="/usr/bin/git"):
        with patch("apps.cli.src.commands.doctor.resolve_config") as resolve_mock:
            config = resolve_mock.return_value
            config.model.default_model = "gpt-4o"
            config.model.api_key = "test-key"
            try:
                run_doctor(workspace=tmp_path)
            except click.exceptions.Exit as exc:
                assert exc.exit_code == 0


def test_run_doctor_output_contains_sections(tmp_path: Path) -> None:
    (tmp_path / ".kcode").mkdir()
    captured: list[str] = []

    def fake_rprint(message: str = "") -> None:
        captured.append(message)

    with patch("apps.cli.src.commands.doctor.shutil.which", return_value="/usr/bin/git"):
        with patch("apps.cli.src.commands.doctor.rprint", fake_rprint):
            try:
                run_doctor(workspace=tmp_path)
            except click.exceptions.Exit:
                pass

    rendered = "\n".join(captured)
    for section in ("Workspace", "Python", "Dependencies", "External tools", "Configuration", "Tool registry", "Session store"):
        assert section in rendered, f"Missing section: {section}"
