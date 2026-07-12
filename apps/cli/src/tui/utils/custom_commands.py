"""Custom command loader -- loads user and project level slash commands.

Inspired by OpenCode's custom commands system:
  - User commands: ~/.config/kcode/commands/*.md (including nested dirs)
  - Project commands: .kcode/commands/*.md (including nested dirs)
  - Nested directories use "dir:filename" as command ID
  - Commands support $ARGUMENTS placeholder for parameterization
  - Robust error handling with detailed diagnostics
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class CustomCommand:
  """A custom command loaded from markdown file."""
  id: str
  title: str
  description: str
  content: str
  source: str  # "user" or "project"
  has_arguments: bool = False
  argument_names: list[str] = field(default_factory=list)
  file_path: Path | None = None


# Pattern to find named arguments like $NAME
_NAMED_ARG_PATTERN = re.compile(r'\$([A-Z][A-Z0-9_]*)')

# Max file size for a command file (128 KB)
_MAX_CMD_FILE_SIZE = 128 * 1024


def load_user_commands() -> list[CustomCommand]:
  """Load commands from ~/.config/kcode/commands/ (including nested dirs)."""
  config_home = os.environ.get("XDG_CONFIG_HOME")
  if not config_home:
    config_home = str(Path.home() / ".config")
  commands_dir = Path(config_home) / "kcode" / "commands"
  return _load_commands_from_dir(commands_dir, "user")


def load_project_commands(workspace_root: Path) -> list[CustomCommand]:
  """Load commands from .kcode/commands/ in workspace (including nested dirs)."""
  commands_dir = workspace_root / ".kcode" / "commands"
  return _load_commands_from_dir(commands_dir, "project")


def _load_commands_from_dir(
  commands_dir: Path, source: str, _root_dir: Path | None = None,
) -> list[CustomCommand]:
  """Recursively load all .md command files from a directory tree.

  Nested directories produce IDs with ":" separator, e.g.:
    commands/git/review.md -> "user:git:review" (from user dir)
    commands/review.md     -> "user:review"

  Args:
    commands_dir: The directory to scan.
    source: "user" or "project".
    _root_dir: Internal — the top-level commands dir (for computing relative paths).

  Returns:
    List of parsed CustomCommand objects.
  """
  commands: list[CustomCommand] = []
  if _root_dir is None:
    _root_dir = commands_dir

  # Create directory if it doesn't exist (only at top level)
  if _root_dir == commands_dir:
    commands_dir.mkdir(parents=True, exist_ok=True)

  if not commands_dir.is_dir():
    return commands

  for entry in sorted(commands_dir.iterdir()):
    if entry.is_file() and entry.suffix.lower() == ".md":
      try:
        command = _parse_command_file(entry, source, _root_dir)
        if command:
          commands.append(command)
      except Exception as e:
        # Log warning but continue loading other commands
        print(f"Warning: Failed to load command from {entry}: {e}")
    elif entry.is_dir() and not entry.name.startswith("."):
      # Recurse into subdirectories (skip hidden dirs)
      commands.extend(
        _load_commands_from_dir(entry, source, _root_dir)
      )

  return commands


def _parse_command_file(
  file_path: Path, source: str, root_dir: Path,
) -> CustomCommand | None:
  """Parse a single .md command file.

  Args:
    file_path: Absolute path to the .md file.
    source: "user" or "project".
    root_dir: The top-level commands directory (for computing relative ID).

  Returns:
    Parsed CustomCommand or None if the file is empty/invalid.
  """
  # Safety: skip files that are too large
  try:
    stat = file_path.stat()
    if stat.st_size > _MAX_CMD_FILE_SIZE:
      print(f"Warning: Skipping oversized command file ({stat.st_size} bytes): {file_path}")
      return None
    if stat.st_size == 0:
      return None
  except OSError:
    return None

  try:
    content = file_path.read_text(encoding="utf-8").lstrip("\ufeff").strip()
  except UnicodeDecodeError:
    try:
      content = file_path.read_text(encoding="utf-8-sig").strip()
    except Exception:
      print(f"Warning: Cannot decode command file: {file_path}")
      return None

  if not content:
    return None

  # Build command ID from relative path
  # e.g. root_dir/user_commands/git/review.md -> "git:review"
  try:
    rel = file_path.relative_to(root_dir)
    # Replace path separators with ":", drop .md extension
    parts = list(rel.parts)
    parts[-1] = Path(parts[-1]).stem  # Remove .md
    command_id = ":".join(parts)
  except ValueError:
    command_id = file_path.stem

  # Check for named arguments
  matches = _NAMED_ARG_PATTERN.findall(content)
  has_arguments = len(matches) > 0
  argument_names: list[str] = []
  if has_arguments:
    seen: set[str] = set()
    for m in matches:
      if m not in seen:
        seen.add(m)
        argument_names.append(m)

  # Extract title from first line if it starts with #
  lines = content.split("\n")
  title = command_id
  description = f"Custom {source} command"

  if lines and lines[0].startswith("# "):
    title = lines[0][2:].strip()
    # Use second non-empty line as description
    for line in lines[1:]:
      stripped = line.strip()
      if stripped and not stripped.startswith("#"):
        description = stripped
        break

  return CustomCommand(
    id=f"{source}:{command_id}",
    title=title,
    description=description,
    content=content,
    source=source,
    has_arguments=has_arguments,
    argument_names=argument_names,
    file_path=file_path,
  )


def load_all_custom_commands(
  workspace_root: Path | None = None,
) -> list[CustomCommand]:
  """Load both user and project level commands."""
  commands = load_user_commands()
  if workspace_root:
    commands.extend(load_project_commands(workspace_root))
  return commands