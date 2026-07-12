"""Tests for the ignore mechanism in builtin_core (_is_ignored)."""
from __future__ import annotations

from pathlib import Path

from apps.cli.src.tools.builtin_core import _is_ignored


class TestIsIgnoredDefaults:
  """Default ignore dirs are always skipped."""

  def test_git_dir_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / ".git" / "config"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_node_modules_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "node_modules" / "pkg" / "index.js"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_pycache_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "__pycache__" / "mod.cpython-313.pyc"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_dist_dir_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "dist" / "bundle.js"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_build_dir_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "build" / "output.bin"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_venv_dir_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / ".venv" / "lib" / "pkg.py"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_egg_info_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "mypackage.egg-info" / "PKG-INFO"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is True

  def test_normal_file_not_ignored(self, tmp_path: Path) -> None:
    p = tmp_path / "src" / "main.py"
    p.parent.mkdir(parents=True)
    p.touch()
    assert _is_ignored(tmp_path, p) is False


class TestIsIgnoredCustomPatterns:
  """Custom patterns from .kcode/ignore are respected."""

  def test_custom_glob_pattern(self, tmp_path: Path) -> None:
    kcode_dir = tmp_path / ".kcode"
    kcode_dir.mkdir()
    (kcode_dir / "ignore").write_text("*.log\ndist/\n", encoding="utf-8")

    log_file = tmp_path / "app.log"
    log_file.touch()
    assert _is_ignored(tmp_path, log_file) is True

  def test_custom_dir_pattern(self, tmp_path: Path) -> None:
    kcode_dir = tmp_path / ".kcode"
    kcode_dir.mkdir()
    (kcode_dir / "ignore").write_text("dist/\n", encoding="utf-8")

    dist_file = tmp_path / "dist" / "bundle.js"
    dist_file.parent.mkdir(parents=True)
    dist_file.touch()
    assert _is_ignored(tmp_path, dist_file) is True

  def test_no_ignore_file_allows_all(self, tmp_path: Path) -> None:
    p = tmp_path / "any_file.txt"
    p.touch()
    assert _is_ignored(tmp_path, p) is False