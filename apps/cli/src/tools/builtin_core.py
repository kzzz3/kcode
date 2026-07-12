"""Core CLI tools for files, search, commands, and git."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from packages.core.src.tools.contracts import Tool, ToolMeta, ToolOutput, ToolRegistry

from apps.cli.src.tools._utils import resolve_within_root


def _create_file(payload: dict[str, Any]) -> ToolOutput:
  workspace = Path(payload["workspace_root"]).resolve()
  path = resolve_within_root(workspace, Path(payload["path"]))
  content = str(payload.get("content", ""))
  overwrite = bool(payload.get("overwrite", False))
  path.parent.mkdir(parents=True, exist_ok=True)
  if path.exists() and not overwrite:
    return ToolOutput(ok=False, message=f"File already exists: {path}")
  path.write_text(content, encoding="utf-8")
  return ToolOutput(ok=True, message=f"Created {path}", artifacts={"path": str(path)})


def _edit_file(payload: dict[str, Any]) -> ToolOutput:
  workspace = Path(payload["workspace_root"]).resolve()
  path = resolve_within_root(workspace, Path(payload["path"]))
  if not path.exists():
    return ToolOutput(ok=False, message=f"File not found: {path}")
  current = path.read_text(encoding="utf-8")
  mode = payload.get("mode", "replace")
  if mode == "replace":
    pattern = payload.get("pattern")
    replacement = payload.get("replacement")
    if not pattern:
      return ToolOutput(ok=False, message="pattern is required for replace mode.")
    new_text, count = re.subn(pattern, replacement or "", current, flags=re.DOTALL)
    if count == 0:
      return ToolOutput(ok=False, message="No matches found for replacement pattern.")
    path.write_text(new_text, encoding="utf-8")
    return ToolOutput(ok=True, message=f"Replaced {count} match(es) in {path}", artifacts={"count": count})
  if mode == "append":
    addition = payload.get("content", "")
    path.write_text(current + addition, encoding="utf-8")
    return ToolOutput(ok=True, message=f"Appended content to {path}")
  if mode == "overwrite":
    path.write_text(payload.get("content", ""), encoding="utf-8")
    return ToolOutput(ok=True, message=f"Overwrote {path}")
  return ToolOutput(ok=False, message=f"Unsupported edit mode: {mode}")


def _search_code(payload: dict[str, Any]) -> ToolOutput:
  workspace = Path(payload["workspace_root"]).resolve()
  query = str(payload["query"])
  pattern = payload.get("file_glob", "*")
  max_results = int(payload.get("max_results", 200))
  matcher = re.compile(query, re.IGNORECASE)
  hits: list[str] = []
  for path in workspace.rglob(pattern):
    if not path.is_file():
      continue
    if _is_ignored(workspace, path):
      continue
    try:
      text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
      continue
    for idx, line in enumerate(text.splitlines(), start=1):
      if matcher.search(line):
        hits.append(f"{path.relative_to(workspace)}:{idx}: {line[:300]}")
        if len(hits) >= max_results:
          return ToolOutput(ok=True, message="\n".join(hits), artifacts={"count": len(hits)})
  return ToolOutput(ok=True, message="\n".join(hits) or "No matches found.", artifacts={"count": len(hits)})


_DEFAULT_IGNORE_DIRS: set[str] = {
  ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
  ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist", "build",
  ".tox", ".nox", ".eggs", "*.egg-info",
}


def _is_ignored(workspace: Path, path: Path) -> bool:
  """Check if a file should be ignored based on .kcode/ignore or defaults."""
  try:
    rel = path.relative_to(workspace)
  except ValueError:
    return True
  for part in rel.parts:
    if part in _DEFAULT_IGNORE_DIRS:
      return True
    if part.endswith(".egg-info"):
      return True
  ignore_file = workspace / ".kcode" / "ignore"
  if ignore_file.exists():
    try:
      patterns = ignore_file.read_text(encoding="utf-8").splitlines()
      for pat in patterns:
        pat = pat.strip()
        if not pat or pat.startswith("#"):
          continue
        if path.match(pat):
          return True
        if any(p.startswith(pat.rstrip("/")) for p in rel.parts):
          return True
    except Exception:  # noqa: BLE001
      pass
  return False


def _is_allowed_command(command: str, allowlist: list[str], blocklist: list[str]) -> bool:
  first = command.split()[0].lower()
  if any(first == item.lower() for item in blocklist):
    return False
  if allowlist and not any(first == item.lower() for item in allowlist):
    return False
  return True


def _run_command(payload: dict[str, Any]) -> ToolOutput:
  command = str(payload["command"])
  allowlist = [str(x) for x in payload.get("allowlist", [])]
  blocklist = [str(x) for x in payload.get("blocklist", [])]
  timeout = float(payload.get("timeout_seconds", 120))
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  if not _is_allowed_command(command, allowlist, blocklist):
    return ToolOutput(ok=False, message=f"Command not permitted by policy: {command}")
  try:
    completed = subprocess.run(
      command,
      shell=True,
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=timeout,
      check=False,
    )
    artifacts = {
      "returncode": completed.returncode,
      "stdout_chars": len(completed.stdout),
      "stderr_chars": len(completed.stderr),
    }
    output = ((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")).strip()
    return ToolOutput(ok=completed.returncode == 0, message=output[:12000], artifacts=artifacts)
  except subprocess.TimeoutExpired:
    return ToolOutput(ok=False, message=f"Command timed out after {timeout}s", artifacts={"error": "timeout"})


def _git_status(payload: dict[str, Any]) -> ToolOutput:
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  completed = subprocess.run(["git", "status", "--short"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  return ToolOutput(ok=completed.returncode == 0, message=(completed.stdout + completed.stderr).strip())


def _git_diff(payload: dict[str, Any]) -> ToolOutput:
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  staged = bool(payload.get("staged", False))
  args = ["git", "diff", "--stat"] + (["--staged"] if staged else [])
  completed = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  return ToolOutput(ok=completed.returncode == 0, message=(completed.stdout + completed.stderr).strip()[:12000])


def _git_commit(payload: dict[str, Any]) -> ToolOutput:
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  message = str(payload["message"])
  add_all = bool(payload.get("add_all", False))
  if add_all:
    subprocess.run(["git", "add", "-A"], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  completed = subprocess.run(["git", "commit", "-m", message], cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  return ToolOutput(ok=completed.returncode == 0, message=(completed.stdout + completed.stderr).strip()[:12000])


def _git_log(payload: dict[str, Any]) -> ToolOutput:
  """Show recent commit history."""
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  count = int(payload.get("count", 20))
  oneline = bool(payload.get("oneline", True))
  since = payload.get("since")
  author = payload.get("author")
  args = ["git", "log"]
  if oneline:
    args.append("--oneline")
  else:
    args.append("--format=%h %ad %an: %s")
    args.append("--date=short")
  args.append(f"-{count}")
  if since:
    args.append(f"--since={since}")
  if author:
    args.append(f"--author={author}")
  completed = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  return ToolOutput(ok=completed.returncode == 0, message=(completed.stdout + completed.stderr).strip()[:12000])


def _git_checkout(payload: dict[str, Any]) -> ToolOutput:
  """Switch branches or create a new branch."""
  cwd = Path(payload.get("workspace_root", ".")).resolve()
  if "branch" not in payload:
    return ToolOutput(ok=False, message="branch parameter is required.")
  branch = str(payload["branch"])
  create = bool(payload.get("create", False))
  args = ["git", "checkout"]
  if create:
    args.append("-b")
  args.append(branch)
  completed = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=60)
  return ToolOutput(ok=completed.returncode == 0, message=(completed.stdout + completed.stderr).strip()[:12000])


def register_core_tools(registry: ToolRegistry) -> None:
  registry.register(Tool(meta=ToolMeta(name="create_file", description="Create a new file with UTF-8 content.", safety_class="write", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}, "overwrite": {"type": "boolean"}}, "required": ["workspace_root", "path", "content"]}), executor=_create_file))
  registry.register(Tool(meta=ToolMeta(name="edit_file", description="Edit an existing file using replace/append/overwrite modes.", safety_class="write", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "path": {"type": "string"}, "mode": {"type": "string", "enum": ["replace", "append", "overwrite"]}, "pattern": {"type": "string"}, "replacement": {"type": "string"}, "content": {"type": "string"}}, "required": ["workspace_root", "path"]}), executor=_edit_file))
  registry.register(Tool(meta=ToolMeta(name="search_code", description="Search file content using a regex and optional glob filter. Respects .kcode/ignore.", safety_class="read", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "query": {"type": "string"}, "file_glob": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["workspace_root", "query"]}), executor=_search_code))
  registry.register(Tool(meta=ToolMeta(name="run_command", description="Run a CLI command subject to allow/block policy.", safety_class="system", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "command": {"type": "string"}, "allowlist": {"type": "array", "items": {"type": "string"}}, "blocklist": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": "number"}}, "required": ["workspace_root", "command"]}), executor=_run_command))
  registry.register(Tool(meta=ToolMeta(name="git_status", description="Show repository status.", safety_class="read", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}}, "required": ["workspace_root"]}), executor=_git_status))
  registry.register(Tool(meta=ToolMeta(name="git_diff", description="Show repository diff summary.", safety_class="read", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "staged": {"type": "boolean"}}, "required": ["workspace_root"]}), executor=_git_diff))
  registry.register(Tool(meta=ToolMeta(name="git_commit", description="Commit changes with a message.", safety_class="write", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "message": {"type": "string"}, "add_all": {"type": "boolean"}}, "required": ["workspace_root", "message"]}), executor=_git_commit))
  registry.register(Tool(meta=ToolMeta(name="git_log", description="Show recent commit history with optional filters.", safety_class="read", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "count": {"type": "integer"}, "oneline": {"type": "boolean"}, "since": {"type": "string"}, "author": {"type": "string"}}, "required": ["workspace_root"]}), executor=_git_log))
  registry.register(Tool(meta=ToolMeta(name="git_checkout", description="Switch branches or create a new branch.", safety_class="write", parameter_schema={"type": "object", "properties": {"workspace_root": {"type": "string"}, "branch": {"type": "string"}, "create": {"type": "boolean"}}, "required": ["workspace_root", "branch"]}), executor=_git_checkout))
