"""Core configuration models and loader."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional, List, Dict

from pydantic import BaseModel, Field

from packages.core.src.config.mcp import McpConfig


class ApprovalMode(str, Enum):
  """How sensitive tool calls are approved.

  - ``manual``: prompt the user for every sensitive tool call.
  - ``auto``: auto-approve all tool calls without prompting.
  """
  manual = "manual"
  auto = "auto"


class ModelProviderConfig(BaseModel):
    """Configuration for a single model provider."""
    name: str = "default"
    provider_type: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolsConfig(BaseModel):
    """Configuration for built-in tools."""
    allowlisted_commands: List[str] = Field(default_factory=lambda: ["python", "pytest", "git", "ls"])
    blocked_commands: List[str] = Field(default_factory=lambda: ["rm", "shutdown", "format"])
    max_command_timeout_seconds: float = 120.0
    max_file_read_bytes: int = 2_000_000
    approval_mode: ApprovalMode = ApprovalMode.auto


class AppConfig(BaseModel):
    """Top-level application configuration schema."""
    version: int = 1
    workspace_root: Path = Path(".")
    debug: bool = False
    model: ModelProviderConfig = Field(default_factory=ModelProviderConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)


def merge_config_sources(sources: List[Dict[str, Any]]) -> dict[str, Any]:
    """Shallow-merge config sources with later sources winning."""
    merged: Dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    return merged


def load_config_from_dict(data: Dict[str, Any]) -> AppConfig:
    """Load AppConfig from a dictionary with validation."""
    return AppConfig.model_validate(data)
