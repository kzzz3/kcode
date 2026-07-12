from __future__ import annotations

from pathlib import Path

from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.tools.builtin_core import register_core_tools


def test_create_and_edit_file(tmp_path: Path) -> None:
  registry = ToolRegistry()
  register_core_tools(registry)
  assert registry.get("create_file") is not None
  assert registry.get("edit_file") is not None
  assert registry.get("search_code") is not None
  assert registry.get("run_command") is not None
  assert registry.get("git_status") is not None

  create_tool = registry.get("create_file")
  assert create_tool is not None
  out = create_tool.run({"workspace_root": str(tmp_path), "path": "a.txt", "content": "hello"})
  assert out.ok is True
  assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"

  edit_tool = registry.get("edit_file")
  assert edit_tool is not None
  out = edit_tool.run({"workspace_root": str(tmp_path), "path": "a.txt", "mode": "append", "content": "\nworld"})
  assert out.ok is True
  assert "world" in (tmp_path / "a.txt").read_text(encoding="utf-8")

  search_tool = registry.get("search_code")
  assert search_tool is not None
  out = search_tool.run({"workspace_root": str(tmp_path), "query": "hello"})
  assert out.ok is True
  assert "a.txt" in out.message