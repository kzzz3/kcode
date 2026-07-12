"""Built-in read-only tools for CLI runtime."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.core.src.tools.contracts import Tool, ToolMeta, ToolOutput, ToolRegistry

from apps.cli.src.tools._utils import resolve_within_root


def _read_file(payload: dict[str, Any]) -> ToolOutput:
  workspace = Path(payload["workspace_root"]).resolve()
  path = resolve_within_root(workspace, Path(payload["path"]))
  if not path.exists():
    return ToolOutput(ok=False, message=f"File not found: {path}")
  text = path.read_text(encoding="utf-8", errors="replace")
  return ToolOutput(ok=True, message=text[:12000], artifacts={"path": str(path)})


def _list_files(payload: dict[str, Any]) -> ToolOutput:
  workspace = Path(payload["workspace_root"]).resolve()
  root = resolve_within_root(workspace, Path(payload.get("path", ".")))
  if not root.exists():
    return ToolOutput(ok=False, message=f"Directory not found: {root}")
  from apps.cli.src.tools.builtin_core import _is_ignored
  files = sorted(
    str(p.relative_to(root))
    for p in root.rglob("*")
    if p.is_file() and not _is_ignored(workspace, p)
  )[:200]
  return ToolOutput(ok=True, message="\n".join(files), artifacts={"count": len(files)})


def register_readonly_tools(registry: ToolRegistry) -> None:
  registry.register(Tool(
    meta=ToolMeta(
      name="read_file",
      description="Read a text file from the workspace.",
      safety_class="read",
      parameter_schema={
        "type": "object",
        "properties": {
          "workspace_root": {"type": "string"},
          "path": {"type": "string"},
        },
        "required": ["workspace_root", "path"],
      },
    ),
    executor=_read_file,
  ))
  registry.register(Tool(
    meta=ToolMeta(
      name="list_files",
      description="List files under a directory. Respects .kcode/ignore.",
      safety_class="read",
      parameter_schema={
        "type": "object",
        "properties": {
          "workspace_root": {"type": "string"},
          "path": {"type": "string"},
        },
        "required": ["workspace_root"],
      },
    ),
    executor=_list_files,
  ))