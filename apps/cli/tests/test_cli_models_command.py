"""Tests for the kcode models CLI command."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from unittest.mock import MagicMock

from apps.cli.src.commands.models import run_models
from apps.cli.src.config.resolution import resolve_config
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


def _invoke(workspace: Path, monkeypatch, base_url: str = "https://example.com/v1", json_output: bool = False) -> str:
    config = resolve_config(
        workspace,
        overrides={"model": {"base_url": base_url}},
        skip_env=True,
    )
    client = OpenAICompatibleClient(config.model)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"id": "mimo-v2.5-pro", "owned_by": "xiaomi", "created": 1710000000},
            {"id": "gpt-4o", "owned_by": "openai", "created": 1700000000},
        ]
    }
    monkeypatch.setattr(client._client, "get", lambda url, **kw: mock_resp)
    monkeypatch.setattr("apps.cli.src.commands.models.OpenAICompatibleClient", lambda cfg: client)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            run_models(workspace=workspace, json_output=json_output)
        except SystemExit:
            pass
    return buf.getvalue()


def test_models_command_outputs_table(monkeypatch, tmp_path: Path) -> None:
    out = _invoke(tmp_path, monkeypatch)
    assert "gpt-4o" in out
    assert "mimo-v2.5-pro" in out
    assert "Models @" in out


def test_models_command_outputs_json(monkeypatch, tmp_path: Path) -> None:
    out = _invoke(tmp_path, monkeypatch, json_output=True)
    import json
    data = json.loads(out)
    ids = {entry["id"] for entry in data}
    assert {"gpt-4o", "mimo-v2.5-pro"} == ids
