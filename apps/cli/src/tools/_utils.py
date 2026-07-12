"""Shared utility functions for CLI tools."""
from __future__ import annotations

import os
from pathlib import Path


def resolve_within_root(root: Path, target: Path) -> Path:
  """Resolve *target* relative to *root* and ensure it stays inside.

  Raises:
    ValueError: If the resolved path escapes the workspace root.
  """
  resolved = (root / target).resolve() if not target.is_absolute() else target.resolve()
  if not (resolved == root or str(resolved).startswith(str(root) + os.sep)):
    raise ValueError(f"Path escapes workspace root: {target}")
  return resolved