from __future__ import annotations

from pathlib import Path

from apps.cli.src.tools.builtin_readonly import _list_files, _read_file


def test_read_file_returns_content(tmp_path: Path) -> None:
  p = tmp_path / "hello.txt"
  p.write_text("hello", encoding="utf-8")
  out = _read_file({"workspace_root": str(tmp_path), "path": "hello.txt"})
  assert out.ok is True
  assert "hello" in out.message


def test_read_file_missing_returns_error(tmp_path: Path) -> None:
  out = _read_file({"workspace_root": str(tmp_path), "path": "missing.txt"})
  assert out.ok is False


def test_list_files_returns_relative_paths(tmp_path: Path) -> None:
  (tmp_path / "d").mkdir()
  (tmp_path / "d" / "x.py").write_text("x", encoding="utf-8")
  (tmp_path / "y.txt").write_text("y", encoding="utf-8")
  out = _list_files({"workspace_root": str(tmp_path), "path": "."})
  assert out.ok is True
  assert "d/x.py" in out.message.replace("\\", "/") or "d\\x.py" in out.message
  assert out.artifacts["count"] == 2


def test_list_files_missing_dir_error(tmp_path: Path) -> None:
  out = _list_files({"workspace_root": str(tmp_path), "path": "missing"})
  assert out.ok is False
