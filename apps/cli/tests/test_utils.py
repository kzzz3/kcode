"""Tests for apps.cli.src.tools._utils — shared path utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.cli.src.tools._utils import resolve_within_root


class TestResolveWithinRoot:
  """resolve_within_root rejects paths that escape workspace root."""

  def test_simple_relative_path(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = resolve_within_root(root, Path("src/main.py"))
    assert result == root / "src" / "main.py"

  def test_nested_relative_path(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = resolve_within_root(root, Path("a/b/c/d.txt"))
    assert result == root / "a" / "b" / "c" / "d.txt"

  def test_dot_dot_still_inside_root(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    (tmp_path / "sub").mkdir()
    result = resolve_within_root(root, Path("sub/../file.txt"))
    assert str(result).startswith(str(root))

  def test_escape_with_dot_dot_raises(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    with pytest.raises(ValueError, match="escapes"):
      resolve_within_root(root, Path("..") / "escape.txt")

  def test_deep_escape_raises(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    with pytest.raises(ValueError, match="escapes"):
      resolve_within_root(root, Path("a/../../etc/passwd"))

  def test_absolute_path_outside_root_raises(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    with pytest.raises(ValueError, match="escapes"):
      resolve_within_root(root, Path("/etc/passwd"))

  def test_file_name_only(self, tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = resolve_within_root(root, Path("file.txt"))
    assert result == root / "file.txt"