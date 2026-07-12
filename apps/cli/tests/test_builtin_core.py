from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.cli.src.tools._utils import resolve_within_root

from apps.cli.src.tools.builtin_core import (
  _create_file,
  _edit_file,
  _is_allowed_command,
  _run_command,
  _search_code,
)


def test_resolve_within_root_allows_workspace_paths(tmp_path: Path) -> None:
  root = tmp_path.resolve()
  target = Path("sub") / "a.txt"
  assert resolve_within_root(root, target) == (root / target).resolve()


def test_resolve_within_root_rejects_escape(tmp_path: Path) -> None:
  root = tmp_path.resolve()
  with pytest.raises(ValueError):
    resolve_within_root(root, Path("..") / "escape.txt")


def test_create_file_writes_content_and_respects_overwrite(tmp_path: Path) -> None:
  out = _create_file({
    "workspace_root": str(tmp_path),
    "path": "a/b.txt",
    "content": "hello",
  })
  assert out.ok is True
  p = tmp_path / "a" / "b.txt"
  assert p.read_text(encoding="utf-8") == "hello"

  out2 = _create_file({
    "workspace_root": str(tmp_path),
    "path": "a/b.txt",
    "content": "world",
    "overwrite": False,
  })
  assert out2.ok is False

  out3 = _create_file({
    "workspace_root": str(tmp_path),
    "path": "a/b.txt",
    "content": "world",
    "overwrite": True,
  })
  assert out3.ok is True
  assert p.read_text(encoding="utf-8") == "world"


def test_edit_file_modes_behave_correctly(tmp_path: Path) -> None:
  p = tmp_path / "m.txt"
  p.write_text("aaa\nbbb\naaa\n", encoding="utf-8")

  out_replace = _edit_file({
    "workspace_root": str(tmp_path),
    "path": "m.txt",
    "mode": "replace",
    "pattern": "aaa",
    "replacement": "zzz",
  })
  assert out_replace.ok is True
  assert p.read_text(encoding="utf-8").count("zzz") == 2

  out_append = _edit_file({
    "workspace_root": str(tmp_path),
    "path": "m.txt",
    "mode": "append",
    "content": "END",
  })
  assert out_append.ok is True
  assert p.read_text(encoding="utf-8").endswith("END")

  out_overwrite = _edit_file({
    "workspace_root": str(tmp_path),
    "path": "m.txt",
    "mode": "overwrite",
    "content": "NEW",
  })
  assert out_overwrite.ok is True
  assert p.read_text(encoding="utf-8") == "NEW"


def test_edit_file_invalid_cases(tmp_path: Path) -> None:
  assert _edit_file({
    "workspace_root": str(tmp_path),
    "path": "missing.txt",
    "mode": "replace",
    "pattern": "x",
  }).ok is False

  p = tmp_path / "f.txt"
  p.write_text("abc", encoding="utf-8")
  assert _edit_file({
    "workspace_root": str(tmp_path),
    "path": "f.txt",
    "mode": "replace",
    "pattern": "NOPE",
  }).ok is False

  assert _edit_file({
    "workspace_root": str(tmp_path),
    "path": "f.txt",
    "mode": "unknown",
  }).ok is False


def test_search_code_returns_hits_with_limit(tmp_path: Path) -> None:
  (tmp_path / "a.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
  (tmp_path / "b.txt").write_text("Beta line\n", encoding="utf-8")

  out = _search_code({
    "workspace_root": str(tmp_path),
    "query": "beta",
    "max_results": 2,
  })
  assert out.ok is True
  assert out.artifacts["count"] <= 2


def test_is_allowed_command_policy() -> None:
  assert _is_allowed_command("git status", [], []) is True
  assert _is_allowed_command("git status", ["git"], []) is True
  assert _is_allowed_command("git status", ["python"], []) is False
  assert _is_allowed_command("git status", [], ["git"]) is False


def test_run_command_policy_block(tmp_path: Path) -> None:
  out = _run_command({
    "workspace_root": str(tmp_path),
    "command": "python -V",
    "allowlist": ["git"],
  })
  assert out.ok is False


def test_run_command_success(tmp_path: Path) -> None:
  if os.name == "nt":
    cmd = "cmd /c echo ok"
  else:
    cmd = "printf ok"
  out = _run_command({
    "workspace_root": str(tmp_path),
    "command": cmd,
  })
  assert out.ok is True
