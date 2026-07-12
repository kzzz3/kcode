"""Unit tests for core configuration loader."""

import pytest
from pydantic import ValidationError

from packages.core.src.config.loader import AppConfig, load_config_from_dict


def test_default_config_valid():
    config = load_config_from_dict({"workspace_root": "."})
    assert isinstance(config, AppConfig)
    assert config.version == 1


def test_model_config_merge():
    config = load_config_from_dict({
        "workspace_root": ".",
        "model": {"name": "default", "base_url": "https://example.com/v1"},
    })
    assert config.model.base_url == "https://example.com/v1"


def test_empty_dict_uses_defaults():
    config = load_config_from_dict({})
    assert config.version == 1
    assert config.debug is False
    assert config.model.name == "default"


def test_unknown_top_level_keys_are_ignored():
    config = load_config_from_dict({"workspace_root": ".", "future_flag": True})
    assert config.version == 1


def test_invalid_model_type_raises_validation_error():
    with pytest.raises(ValidationError):
        load_config_from_dict({"workspace_root": ".", "model": "invalid"})
