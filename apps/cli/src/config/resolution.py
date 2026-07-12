"""CLI configuration resolution with multi-source precedence."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from packages.core.src.config.loader import AppConfig, load_config_from_dict, merge_config_sources

# Accept both old and new config filenames for backward compatibility.
_CONFIG_FILENAMES = ("config.yaml", "config.yml", "kcode.config.yaml")

_USER_SEARCH_PATHS: list[Path] = []
for _name in _CONFIG_FILENAMES:
    _USER_SEARCH_PATHS.append(Path.home() / ".config" / "kcode" / _name)
    _USER_SEARCH_PATHS.append(Path.home() / ".kcode" / _name)

# Standard environment variables recognised as provider config.
# These are lower-priority than YAML/CLI overrides but higher than hard-coded defaults.
_ENV_VAR_MAP: dict[str, tuple[str, str]] = {
    # env var name -> (model section key, field name)
    "OPENAI_API_KEY":      ("model", "api_key"),
    "OPENAI_BASE_URL":     ("model", "base_url"),
    "OPENAI_MODEL":        ("model", "default_model"),
    # OPENAI_ORG_ID goes into model.extra.org_id (handled separately below)
    # KCode-specific env vars (override OpenAI ones if both set)
    "KCODE_API_KEY":       ("model", "api_key"),
    "KCODE_BASE_URL":      ("model", "base_url"),
    "KCODE_MODEL":         ("model", "default_model"),
    "KCODE_PROVIDER_TYPE": ("model", "provider_type"),
}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _read_workspace_config(workspace_root: Path) -> dict[str, Any]:
    candidates = [
        workspace_root / name
        for name in _CONFIG_FILENAMES
    ] + [
        workspace_root / ".kcode" / name
        for name in _CONFIG_FILENAMES
    ] + [
        workspace_root / "kcode.config.json",
    ]
    for path in candidates:
        if path.exists():
            if path.suffix == ".json":
                return json.loads(path.read_text(encoding="utf-8"))
            return _read_yaml(path)
    return {}


def _env_overrides() -> dict[str, Any]:
    """Build a partial config dict from recognised environment variables.

    KCODE_* vars take priority over OPENAI_* vars for the same field.
    """
    result: dict[str, Any] = {}
    for env_name, (section, field) in _ENV_VAR_MAP.items():
        value = os.environ.get(env_name)
        if value is not None:
            result.setdefault(section, {})
            result[section][field] = value
    # org_id goes into extra since ModelProviderConfig has no dedicated field
    org_id = os.environ.get("OPENAI_ORG_ID")
    if org_id is not None:
        result.setdefault("model", {})
        result["model"].setdefault("extra", {})
        result["model"]["extra"]["org_id"] = org_id
    return result


def resolve_config(
    workspace_root: Path,
    overrides: dict[str, Any] | None = None,
    *,
    skip_env: bool = False,
) -> AppConfig:
    """Resolve configuration from env/file/CLI sources.

    Precedence (lowest -> highest):
        1. Hard-coded defaults (Pydantic model defaults)
        2. Environment variables (OPENAI_*, KCODE_*)
        3. User config file (~/.config/kcode/config.yaml)
        4. Workspace config (.kcode/config.yaml)
        5. CLI overrides (passed programmatically)
    """
    sources: list[dict[str, Any]] = []

    # Layer 2: env vars (skip for deterministic unit tests)
    if not skip_env:
        sources.append(_env_overrides())

    # Layer 3: user config files (first match wins within each search root)
    seen_roots: set[Path] = set()
    for candidate in _USER_SEARCH_PATHS:
        root = candidate.parent
        if root in seen_roots:
            continue
        data = _read_yaml(candidate)
        if data:
            sources.append(data)
            seen_roots.add(root)
        # Even if this candidate is empty, check next filename in same root

    # Layer 4: workspace config
    sources.append(_read_workspace_config(workspace_root))

    # Layer 5: CLI overrides
    if overrides:
        sources.append(overrides)

    merged = merge_config_sources(sources)
    merged.setdefault("workspace_root", workspace_root)
    return load_config_from_dict(merged)
