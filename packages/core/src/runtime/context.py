"""Core runtime context used by CLI and future desktop shell."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class RuntimeContext:
    """Runtime context that is intentionally desktop-agnostic."""

    cwd: Path
    workspace_root: Path
    config_paths: tuple[Path, ...]
    is_interactive: bool = False
    debug: bool = False
    extra: dict[str, Any] | None = None

    def with_overrides(self, **kwargs: Any) -> RuntimeContext:
        data: dict[str, Any] = {
            "cwd": self.cwd,
            "workspace_root": self.workspace_root,
            "config_paths": self.config_paths,
            "is_interactive": self.is_interactive,
            "debug": self.debug,
            "extra": dict(self.extra or {}),
        }
        data.update(kwargs)
        return cast(RuntimeContext, RuntimeContext(**data))