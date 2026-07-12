"""Additional tests for model listing robustness."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.cli.src.config.resolution import resolve_config
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


def _make_client(tmp_path: Path, base_url: str) -> OpenAICompatibleClient:
    config = resolve_config(
        tmp_path,
        overrides={"model": {"base_url": base_url}},
        skip_env=True,
    )
    return OpenAICompatibleClient(config.model)


def test_list_models_strips_trailing_slash(monkeypatch, tmp_path: Path) -> None:
    """Trailing slashes in base_url should not break model fetching."""
    client = _make_client(tmp_path, "https://example.com/v1/")

    called_with: list[str] = []
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": [{"id": "m1", "owned_by": "o"}]}

    def fake_get(url: str, **kw: object) -> object:
        called_with.append(url)
        return mock_resp

    monkeypatch.setattr(client._client, "get", fake_get)
    models = client.list_models()
    assert [m.id for m in models] == ["m1"]
    assert called_with == ["/models"]


def test_list_models_rejects_chat_completions_path(tmp_path: Path) -> None:
    """If base_url accidentally points to chat/completions, list_models() raises."""
    with pytest.raises(ValueError, match="must be the API root"):
        _make_client(tmp_path, "https://example.com/v1/chat/completions")
