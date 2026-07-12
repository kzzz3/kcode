"""Custom command loader -- loads user and project level slash commands.

Inspired by OpenCode's custom commands system:
  - User commands: ~/.config/kcode/commands/*.md
  - Project commands: .kcode/commands/*.md
  - Commands support $ARGUMENTS placeholder for parameterization
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CustomCommand:
  """A custom command loaded from markdown file."""
  id: str
  title: str
  description: str
  content: str
  source: str  # "user" or "project"
  has_arguments: bool = False
  argument_names: list[str] | None = None


# Pattern to find named arguments like $NAME
_NAMED_ARG_PATTERN = re.compile(r'\$([A-Z][A-Z0-9_]*)')


def load_user_commands() -> list[CustomCommand]:
  """Load commands from ~/.config/kcode/commands/"""
  
  # XDG_CONFIG_HOME or ~/.config
  config_home = os.environ.get("XDG_CONFIG_HOME")
  if not config_home:
    config_home = str(Path.home() / ".config")
  
  commands_dir = Path(config_home) / "kcode" / "commands"
  return _load_commands_from_dir(commands_dir, "user")


def load_project_commands(workspace_root: Path) -> list[CustomCommand]:
  """Load commands from .kcode/commands/ in workspace"""
  commands_dir = workspace_root / ".kcode" / "commands"
  return _load_commands_from_dir(commands_dir, "project")


def _load_commands_from_dir(commands_dir: Path, source: str) -> list[CustomCommand]:
  """Load all .md command files from a directory."""
  commands: list[CustomCommand] = []
  
  # Create directory if it doesn't exist
  commands_dir.mkdir(parents=True, exist_ok=True)
  
  # Load all .md files
  for md_file in sorted(commands_dir.glob("*.md")):
    try:
      command = _parse_command_file(md_file, source)
      if command:
        commands.append(command)
    except Exception as e:
      # Log error but continue loading other commands
      print(f"Warning: Failed to load command from {md_file}: {e}")
  
  return commands


def _parse_command_file(file_path: Path, source: str) -> CustomCommand | None:
  """Parse a single .md command file."""
  content = file_path.read_text(encoding="utf-8").strip()
  if not content:
    return None
  
  # Extract command ID from filename
  command_id = file_path.stem
  
  # Check for named arguments
  matches = _NAMED_ARG_PATTERN.findall(content)
  has_arguments = len(matches) > 0
  argument_names = list(set(matches)) if has_arguments else None
  
  # Extract title from first line if it starts with #
  lines = content.split("\n")
  title = command_id
  description = f"Custom {source} command"
  
  if lines and lines[0].startswith("# "):
    title = lines[0][2:].strip()
    # Use second line as description if available
    if len(lines) > 1 and lines[1].strip():
      description = lines[1].strip()
  
  return CustomCommand(
    id=f"{source}:{command_id}",
    title=title,
    description=description,
    content=content,
    source=source,
    has_arguments=has_arguments,
    argument_names=argument_names,
  )


def load_all_custom_commands(workspace_root: Path | None = None) -> list[CustomCommand]:
  """Load both user and project level commands."""
  commands = load_user_commands()
  
  if workspace_root:
    commands.extend(load_project_commands(workspace_root))
  
  return commands