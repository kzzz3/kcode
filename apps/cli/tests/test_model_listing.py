"""Tests for model listing functionality."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from apps.cli.src.config.resolution import resolve_config
from packages.core.src.models.openai_compatible import OpenAICompatibleClient


# --- ModelClient.list_models() ABC default ---

def test_model_client_list_models_default_returns_empty() -> None:
    """Base ModelClient.list_models() returns empty list by default."""
    from packages.core.src.models.interfaces import ModelClient

    class Bare(ModelClient):
        def complete(self, **kw):  # pragma: no cover
            raise NotImplementedError

    assert Bare().list_models() == []


# --- OpenAICompatibleClient.list_models() ---

def _make_client(tmp_path: Path) -> OpenAICompatibleClient:
    config = resolve_config(tmp_path, skip_env=True)
    return OpenAICompatibleClient(config.model)


def test_list_models_parses_response(monkeypatch, tmp_path: Path) -> None:
    """list_models() parses a standard OpenAI /v1/models response."""
    client = _make_client(tmp_path)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"id": "gpt-4o", "owned_by": "openai", "created": 1700000000},
            {"id": "gpt-3.5-turbo", "owned_by": "openai", "created": 1690000000},
            {"id": "mimo-v2.5-pro", "owned_by": "xiaomi", "created": 1710000000},
        ]
    }
    monkeypatch.setattr(client._client, "get", lambda url, **kw: mock_resp)

    models = client.list_models()
    assert len(models) == 3
    # Should be sorted by id
    assert models[0].id == "gpt-3.5-turbo"
    assert models[1].id == "gpt-4o"
    assert models[2].id == "mimo-v2.5-pro"
    assert models[0].owned_by == "openai"
    assert models[2].owned_by == "xiaomi"
    assert models[2].created == 1710000000


def test_list_models_empty_data(monkeypatch, tmp_path: Path) -> None:
    """list_models() returns empty list when provider returns empty data array."""
    client = _make_client(tmp_path)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": []}
    monkeypatch.setattr(client._client, "get", lambda url, **kw: mock_resp)

    assert client.list_models() == []


def test_list_models_no_data_key(monkeypatch, tmp_path: Path) -> None:
    """list_models() returns empty list when response has no 'data' key."""
    client = _make_client(tmp_path)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {}
    monkeypatch.setattr(client._client, "get", lambda url, **kw: mock_resp)

    assert client.list_models() == []


def test_list_models_preserves_capabilities(monkeypatch, tmp_path: Path) -> None:
    """list_models() preserves extra fields in capabilities dict."""
    client = _make_client(tmp_path)

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"id": "test-model", "owned_by": "test", "created": 0, "context_window": 128000},
        ]
    }
    monkeypatch.setattr(client._client, "get", lambda url, **kw: mock_resp)

    models = client.list_models()
    assert models[0].capabilities == {"context_window": 128000}


def test_list_models_propagates_http_error(monkeypatch, tmp_path: Path) -> None:
    """list_models() raises on HTTP errors (caller decides error handling)."""
    import httpx

    client = _make_client(tmp_path)

    def fake_get(url: str, **kw: object) -> object:
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        raise httpx.HTTPStatusError("401", request=MagicMock(), response=resp)

    monkeypatch.setattr(client._client, "get", fake_get)

    try:
        client.list_models()
        assert False, "Should have raised"
    except httpx.HTTPStatusError:
        pass


# --- _try_fetch_models helper (init.py) ---

def test_try_fetch_models_success(monkeypatch) -> None:
    """_try_fetch_models returns sorted model IDs on success."""
    from apps.cli.src.commands.init import _try_fetch_models

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "c-model"}]
    }
    monkeypatch.setattr("httpx.get", lambda *a, **kw: mock_resp)

    result = _try_fetch_models("http://localhost:8000/v1", "sk-test")
    assert result == ["a-model", "b-model", "c-model"]


def test_try_fetch_models_failure_returns_empty(monkeypatch) -> None:
    """_try_fetch_models returns empty list on any error."""
    from apps.cli.src.commands.init import _try_fetch_models
    import httpx

    monkeypatch.setattr("httpx.get", MagicMock(side_effect=httpx.ConnectError("fail")))
    assert _try_fetch_models("http://bad-host/v1", "") == []


def test_try_fetch_models_empty_data(monkeypatch) -> None:
    """_try_fetch_models returns empty list when data is empty."""
    from apps.cli.src.commands.init import _try_fetch_models

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": []}
    monkeypatch.setattr("httpx.get", lambda *a, **kw: mock_resp)

    assert _try_fetch_models("http://localhost/v1", "") == []