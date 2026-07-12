"""Rich formatting utilities for TUI messages."""
from __future__ import annotations

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.panel import Panel


def format_user_message(content: str) -> Panel:
  """Format a user message as a panel."""
  return Panel(Text(content), title=Text("You", style="bold cyan"), border_style="cyan")


def format_assistant_message(content: str) -> Panel:
  """Format an assistant message with Markdown rendering."""
  return Panel(Markdown(content), title=Text("KCode", style="bold green"), border_style="green")


def format_tool_call(tool_name: str, tool_args: dict | None = None) -> Text:
  """Format a tool call invocation line."""
  text = Text()
  text.append(" Calling: ", style="dim")
  text.append(tool_name, style="bold blue")
  return text


def format_tool_result(tool_name: str, result: str, is_error: bool = False) -> Text:
  """Format a tool result line."""
  text = Text()
  if is_error:
    text.append(" Error: ", style="bold red")
    text.append(tool_name, style="red")
    text.append(f" — {result[:200]}", style="red")
  else:
    text.append(" Done: ", style="dim green")
    text.append(tool_name, style="green")
    preview = result[:200] + ("..." if len(result) > 200 else "")
    text.append(f" — {preview}", style="dim")
  return text


def format_code_block(code: str, language: str = "python") -> Syntax:
  """Format a code block with syntax highlighting."""
  return Syntax(code, language, theme="monokai", line_numbers=True)
