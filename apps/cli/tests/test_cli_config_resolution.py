"""Tests for CLI config resolution including env vars."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from apps.cli.src.config.resolution import resolve_config, _env_overrides


def _no_user_config():
    """Context manager that suppresses user-level config files in tests."""
    return patch("apps.cli.src.config.resolution._USER_SEARCH_PATHS", [])


def test_resolve_config_returns_defaults(tmp_path: Path) -> None:
    """Baseline: resolve_config with skip_env returns sane defaults."""
    with _no_user_config():
        config = resolve_config(tmp_path, skip_env=True)
        assert config.workspace_root == tmp_path
        assert config.model.default_model is None or isinstance(config.model.default_model, str)


def _set_env(env: dict[str, str | None]) -> dict[str, str | None]:
    """Set env vars, return old values for restoration."""
    old: dict[str, str | None] = {}
    for k, v in env.items():
        old[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def _restore_env(old: dict[str, str | None]) -> None:
    """Restore env vars from saved snapshot."""
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_env_overrides_openai_key(tmp_path: Path) -> None:
    """OPENAI_API_KEY is picked up."""
    old = _set_env({"OPENAI_API_KEY": "sk-test-123"})
    try:
        overrides = _env_overrides()
        assert overrides["model"]["api_key"] == "sk-test-123"
    finally:
        _restore_env(old)


def test_env_overrides_kcode_priority(tmp_path: Path) -> None:
    """KCODE_API_KEY overrides OPENAI_API_KEY."""
    old = _set_env({"OPENAI_API_KEY": "sk-openai", "KCODE_API_KEY": "sk-kcode"})
    try:
        overrides = _env_overrides()
        assert overrides["model"]["api_key"] == "sk-kcode"
    finally:
        _restore_env(old)


def test_env_overrides_no_vars(tmp_path: Path) -> None:
    """No env vars returns empty dict."""
    env_vars = [
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_ORG_ID",
        "KCODE_API_KEY", "KCODE_BASE_URL", "KCODE_MODEL", "KCODE_PROVIDER_TYPE",
    ]
    old = _set_env({k: None for k in env_vars})
    try:
        overrides = _env_overrides()
        assert overrides == {}
    finally:
        _restore_env(old)


def test_env_overrides_base_url_and_model(tmp_path: Path) -> None:
    """OPENAI_BASE_URL and OPENAI_MODEL are picked up."""
    old = _set_env({"OPENAI_BASE_URL": "http://localhost:8080/v1", "OPENAI_MODEL": "gpt-4o-mini"})
    try:
        overrides = _env_overrides()
        assert overrides["model"]["base_url"] == "http://localhost:8080/v1"
        assert overrides["model"]["default_model"] == "gpt-4o-mini"
    finally:
        _restore_env(old)


def test_resolve_config_env_api_key(tmp_path: Path) -> None:
    """resolve_config picks up OPENAI_API_KEY from environment."""
    old = _set_env({"OPENAI_API_KEY": "sk-env-test"})
    try:
        with _no_user_config():
            config = resolve_config(tmp_path)
            assert config.model.api_key == "sk-env-test"
    finally:
        _restore_env(old)


def test_resolve_config_cli_overrides_beat_env(tmp_path: Path) -> None:
    """CLI overrides take precedence over env vars."""
    old = _set_env({"OPENAI_API_KEY": "sk-env", "OPENAI_MODEL": "env-model"})
    try:
        with _no_user_config():
            config = resolve_config(
                tmp_path,
                overrides={"model": {"api_key": "sk-cli", "default_model": "cli-model"}},
            )
            assert config.model.api_key == "sk-cli"
            assert config.model.default_model == "cli-model"
    finally:
        _restore_env(old)


def test_resolve_config_skip_env(tmp_path: Path) -> None:
    """skip_env=True ignores environment variables."""
    old = _set_env({"OPENAI_API_KEY": "sk-should-not-appear"})
    try:
        with _no_user_config():
            config = resolve_config(tmp_path, skip_env=True)
            assert config.model.api_key != "sk-should-not-appear"
    finally:
        _restore_env(old)


def test_resolve_config_yaml_overrides_env(tmp_path: Path) -> None:
    """Workspace YAML config takes precedence over env vars."""
    old = _set_env({"OPENAI_API_KEY": "sk-env", "OPENAI_MODEL": "env-model"})
    kcode_dir = tmp_path / '.kcode'
    kcode_dir.mkdir()
    (kcode_dir / 'config.yaml').write_text(
        "model:\n  api_key: sk-yaml\n  default_model: yaml-model\n",
        encoding="utf-8",
    )
    try:
        with _no_user_config():
            config = resolve_config(tmp_path)
            assert config.model.api_key == "sk-yaml"
            assert config.model.default_model == "yaml-model"
    finally:
        _restore_env(old)