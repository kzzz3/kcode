import pathlib

p = pathlib.Path(r"apps/cli/src/tui/widgets/chat_area.py")
text = p.read_text(encoding="utf-8").replace("\r\n", "\n")

# 1. Add welcome banner constant after Panel import
welcome_const = '''
# Welcome banner shown on first mount
_WELCOME_BANNER = """\\
[bold cyan]
  ██╗  ██╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝ ██║   ██║██║  ██║█████╗
  ██╔═██╗ ██║   ██║██║  ██║██╔══╝
  ██║  ██╗╚██████╔╝██████╔╝███████╗
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝
[/bold cyan]
[dim]  AI Coding Assistant[/dim]

[bold green]Quick Start[/bold green]
  [cyan]Type a message[/cyan] and press [bold]Enter[/bold] to chat
  [cyan]/[/cyan] at start of input for slash commands
  [cyan]Ctrl+K[/cyan] for command palette
  [cyan]Ctrl+H[/cyan] for help
  [cyan]Escape[/cyan] to cancel streaming

[dim]═══════════════════════════════════[/dim]
"""
'''

text = text.replace(
    "from rich.panel import Panel\n",
    "from rich.panel import Panel\n" + welcome_const
)

# 2. Add _welcome_shown to __init__
text = text.replace(
    "    self._active_tools: dict[str, ToolCallEntry] = {}",
    "    self._active_tools: dict[str, ToolCallEntry] = {}\n    self._welcome_shown: bool = False"
)

# 3. Add show_welcome method before the Public API section
old_pub_api = "  # \u2500\u2500 Public API \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
new_section = '''  def show_welcome(self) -> None:
    """Show the welcome banner if not already shown."""
    if self._welcome_shown:
      return
    self._welcome_shown = True
    try:
      banner = Static(Panel(
        Markdown(_WELCOME_BANNER),
        title=Text(" Welcome ", style="bold green"),
        border_style="green",
        padding=(0, 1),
      ))
      self.mount(banner)
      self._scroll_end()
    except Exception:
      pass

''' + old_pub_api

text = text.replace(old_pub_api, new_section, 1)

p.write_text(text.replace("\n", "\r\n"), encoding="utf-8")
print("chat_area.py updated successfully")