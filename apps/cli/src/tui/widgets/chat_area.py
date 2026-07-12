"""Chat message display with live streaming Markdown and tool-call support.

Design notes (inspired by OpenCode):
  - Messages rendered as Rich Panels in a vertical scrollable container.
  - Streaming text uses buffered updates (not every-token re-render).
  - Tool calls tracked by ID for parallel/concurrent MCP calls.
  - Tool calls shown as collapsible dimmed lines with expand on click/key.
  - Auto-scroll to bottom on new content.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static
from rich.markdown import Markdown
from rich.text import Text
from rich.panel import Panel

# Welcome banner shown on first mount
_WELCOME_BANNER = """\
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


class ToolCallEntry(Widget):
  """A single tool-call display -- collapsed by default, expandable."""

  DEFAULT_CSS = """
  ToolCallEntry {
    height: auto;
    padding: 0 1;
    background: $surface;
    margin: 0 0 0 2;
  }
  ToolCallEntry .tc-header {
    height: 1;
    color: $text-muted;
  }
  ToolCallEntry .tc-body {
    height: auto;
    display: none;
    color: $text-muted;
    padding: 0 0 0 2;
  }
  ToolCallEntry.expanded .tc-body {
    display: block;
  }
  """

  expanded: reactive[bool] = reactive(False)

  def __init__(self, tool_name: str, tool_args: str = "", tool_result: str = "",
               is_error: bool = False) -> None:
    super().__init__()
    self._tool_name = tool_name
    self._tool_args = tool_args
    self._tool_result = tool_result
    self._is_error = is_error

  def compose(self) -> ComposeResult:
    icon = "[red]✗[/red]" if self._is_error else "[green]✓[/green]"
    yield Static(f"  {icon} {self._tool_name}", classes="tc-header")
    body_parts: list[str] = []
    if self._tool_args:
      body_parts.append(f"[dim]Args:[/dim] {self._tool_args[:300]}")
    if self._tool_result:
      preview = self._tool_result[:400] + ("..." if len(self._tool_result) > 400 else "")
      body_parts.append(f"[dim]Result:[/dim] {preview}")
    yield Static("\n".join(body_parts) if body_parts else "  (no details)", classes="tc-body")

  def on_click(self) -> None:
    self.expanded = not self.expanded

  def watch_expanded(self, old: bool, new: bool) -> None:
    if new:
      self.add_class("expanded")
    else:
      self.remove_class("expanded")

  def append_args(self, delta: str) -> None:
    """Accumulate incremental tool-call args."""
    self._tool_args += delta

  def update_result(self, result: str, is_error: bool = False) -> None:
    """Update the result after the tool call completes."""
    self._tool_result = result
    self._is_error = is_error
    icon = "[red]✗[/red]" if is_error else "[green]✓[/green]"
    header = self.query_one(".tc-header", Static)
    header.update(f"  {icon} {self._tool_name}")
    body = self.query_one(".tc-body", Static)
    preview = result[:400] + ("..." if len(result) > 400 else "")
    body.update(f"[dim]Result:[/dim] {preview}")


class StreamMessage(Widget):
  """A live-updating message bubble for streaming assistant content.

  Uses buffered rendering: only re-renders Markdown every N characters
  or on finalization, to avoid per-token re-parsing overhead.
  """

  DEFAULT_CSS = """
  StreamMessage {
    height: auto;
    min-height: 1;
    padding: 0 1;
    margin: 0 1;
    background: $surface;
    border: tall $success 30%;
  }
  StreamMessage Static {
    height: auto;
  }
  """

  # Re-render Markdown at most every 200 chars or on finalize
  _RENDER_THRESHOLD = 200

  def __init__(self) -> None:
    super().__init__()
    self._parts: list[str] = []
    self._dirty_len: int = 0

  def compose(self) -> ComposeResult:
    yield Static("▌", id="stream-text")

  def append_delta(self, delta: str) -> None:
    """Append text delta. Re-renders Markdown only when threshold is exceeded."""
    self._parts.append(delta)
    total_len = sum(len(p) for p in self._parts)
    if total_len - self._dirty_len >= self._RENDER_THRESHOLD:
      self._render_incremental()

  def _render_incremental(self) -> None:
    """Re-render the Markdown preview."""
    full = "".join(self._parts)
    self._dirty_len = len(full)
    text_widget = self.query_one("#stream-text", Static)
    try:
      text_widget.update(Markdown(full))
    except Exception:
      text_widget.update(full + "▌")

  def finalize(self) -> str:
    """Finalize the stream, return the full text."""
    full = "".join(self._parts)
    text_widget = self.query_one("#stream-text", Static)
    try:
      text_widget.update(Markdown(full))
    except Exception:
      text_widget.update(full)
    return full


class ChatArea(VerticalScroll):
  """Scrollable chat display with streaming, Markdown, and tool call support.

  OpenCode-inspired design:
    - User messages: cyan panel with "You" header.
    - Assistant messages: green-bordered panel with rendered Markdown.
    - Streaming: buffered Markdown preview.
    - Tool calls: tracked by tool_call_id for parallel support.
    - Auto-scrolls to bottom on new content.
  """

  DEFAULT_CSS = """
  ChatArea {
    height: 1fr;
    border: solid $primary;
    padding: 0;
    overflow-y: auto;
    scrollbar-size-vertical: 1;
  }
  """

  class Submitted(Message):
    """Notify that user submitted text."""
    def __init__(self, content: str, role: str) -> None:
      self.content = content
      self.role = role
      super().__init__()

  def __init__(self) -> None:
    super().__init__()
    self._stream_widget: StreamMessage | None = None
    self._active_tools: dict[str, ToolCallEntry] = {}
    self._welcome_shown: bool = False

  # ── Public API ────────────────────────────────────────────────────────

  def add_message(self, content: str, role: str = "user") -> None:
    """Add a completed message."""
    if role == "user":
      panel = Static(
        Panel(Text(content), title=Text(" You ", style="bold cyan"),
              border_style="cyan", padding=(0, 1)),
      )
    else:
      try:
        rendered = Markdown(content)
      except Exception:
        rendered = Text(content)
      panel = Static(
        Panel(rendered, title=Text(" KCode ", style="bold green"),
              border_style="green", padding=(0, 1)),
      )
    self.mount(panel)
    self._scroll_end()
    self.post_message(self.Submitted(content, role))

  def start_stream(self, role: str = "assistant") -> None:
    """Begin a new streaming assistant message."""
    self._stream_widget = StreamMessage()
    self.mount(self._stream_widget)
    self._scroll_end()

  def add_stream_chunk(self, delta: str) -> None:
    """Append a text delta to the live stream widget."""
    if self._stream_widget is not None:
      self._stream_widget.append_delta(delta)
      self._scroll_end()

  def end_stream(self) -> None:
    """Finalize the streaming message."""
    if self._stream_widget is not None:
      self._stream_widget.finalize()
      self._stream_widget = None
      self._scroll_end()

  def cancel_stream(self) -> None:
    """Discard in-progress stream."""
    if self._stream_widget is not None:
      self._stream_widget.remove()
      self._stream_widget = None

  def add_tool_call_start(self, tool_name: str, tool_call_id: str = "") -> None:
    """Show a new tool call entry (collapsible)."""
    entry = ToolCallEntry(tool_name)
    self.mount(entry)
    key = tool_call_id or tool_name
    self._active_tools[key] = entry
    self._scroll_end()

  def add_tool_call_args(self, tool_name: str, delta: str, tool_call_id: str = "") -> None:
    """Incremental tool args -- accumulated and shown on expand."""
    key = tool_call_id or tool_name
    entry = self._active_tools.get(key)
    if entry is not None:
      entry.append_args(delta)

  def add_tool_call_end(self, tool_name: str, tool_call_id: str = "",
                        result: str = "", is_error: bool = False) -> None:
    """Update tool call entry with result."""
    key = tool_call_id or tool_name
    entry = self._active_tools.pop(key, None)
    if entry is not None:
      entry.update_result(result, is_error)
    self._scroll_end()

  # ── Internal ──────────────────────────────────────────────────────────

  def _scroll_end(self) -> None:
    """Scroll to bottom after a short delay to allow layout to settle."""
    def _do_scroll() -> None:
      self.scroll_end(animate=False)
    self.call_after_refresh(_do_scroll)