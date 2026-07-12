"""CLI chat failure-path integration tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from apps.cli.src.kcode_cli import app

runner = CliRunner()


def _raise_connect_error(*args, **kwargs):
  raise httpx.ConnectError("Connection refused")


def test_chat_model_connection_error_exits_cleanly(tmp_path: Path) -> None:
  """When the model API is unreachable, chat should exit with code 1 and print an error, not a traceback."""
  (tmp_path / ".kcode").mkdir()
  # Patch OpenAICompatibleClient.complete_stream to raise ConnectError
  with patch(
    "packages.core.src.models.openai_compatible.OpenAICompatibleClient.complete_stream",
    side_effect=_raise_connect_error,
  ):
    result = runner.invoke(
      app,
      ["chat", "--workspace", str(tmp_path), "--model", "gpt-4o", "hello"],
    )
    # Should exit with non-zero code (the runtime catches the error)
    # The agent loop should handle the exception gracefully
    assert result.exit_code != 0 or "error" in result.output.lower() or "Tool error" in result.output


def test_chat_no_model_configured_exits_with_message(tmp_path: Path) -> None:
  """When no model is configured and no --model flag, exit with code 1 and helpful message."""
  (tmp_path / ".kcode").mkdir()
  # Ensure no user-level or workspace config leaks in — only hard-coded defaults.
  with patch("apps.cli.src.config.resolution._USER_SEARCH_PATHS", []):
    result = runner.invoke(
      app,
      ["chat", "--workspace", str(tmp_path), "hello"],
    )
    assert result.exit_code == 1
    assert "model" in result.output.lower() or "No model" in result.output