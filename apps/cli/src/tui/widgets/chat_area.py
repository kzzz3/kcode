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

  Blinking cursor (\u25cc) during streaming, flash effect on finalize.

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

  StreamMessage.thinking {
    border: tall $warning 40%;
  }

  StreamMessage.flash {

    border: tall $success;

    background: $success 10%;

  }

  StreamMessage Static {

    height: auto;

  }

  """

  # Re-render Markdown at most every 200 chars or on finalize

  _RENDER_THRESHOLD = 140

  def __init__(self) -> None:

    super().__init__()

    self._parts: list[str] = []

    self._dirty_len: int = 0

    self._cursor_visible: bool = True

    self._streaming: bool = True
    self._thinking_phase: bool = True
    self._thinking_elapsed: int = 0
    self._thinking_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠏", "⠏"]
    self._thinking_idx: int = 0

  def compose(self) -> ComposeResult:

    yield Static("\u258e", id="stream-text")

  def on_mount(self) -> None:

    """Start cursor blink and thinking indicator timers."""

    self.set_interval(0.5, self._blink_cursor)
    self.set_interval(0.12, self._tick_thinking)

  def _blink_cursor(self) -> None:

    """Toggle cursor visibility during streaming."""

    if not self._streaming:

      return

    self._cursor_visible = not self._cursor_visible

    # Only re-render if we have content (avoid overwriting empty state)

    if self._parts:
      self._render_incremental()

  def _tick_thinking(self) -> None:
    """Animate thinking spinner when no text has been received yet."""
    if not self._streaming or not self._thinking_phase:
      return
    frame = self._thinking_frames[self._thinking_idx % len(self._thinking_frames)]
    self._thinking_idx += 1
    try:
      text_widget = self.query_one("#stream-text", Static)
      text_widget.update(f"[bold yellow]{frame}[/bold yellow] [dim]{self._thinking_elapsed}s thinking...[/dim]")
      if self._thinking_idx % 8 == 0:
        self._thinking_elapsed += 1
    except Exception:
      pass
    if not self.has_class("thinking"):
      self.call_after_refresh(lambda: self.add_class("thinking"))

  def append_delta(self, delta: str) -> None:

    """Append text delta. Re-renders Markdown only when threshold is exceeded."""

    if self._thinking_phase:
      self._thinking_phase = False
      self.remove_class("thinking")
    self._parts.append(delta)
    total_len = sum(len(p) for p in self._parts)
    if total_len - self._dirty_len >= self._RENDER_THRESHOLD or total_len == len(delta):
      self._render_incremental()

  def _render_incremental(self) -> None:
    """Re-render the Markdown preview with cursor."""
    try:
      text_widget = self.query_one("#stream-text", Static)
    except Exception:
      return
    full = "".join(self._parts)
    self._dirty_len = len(full)
    cursor = "▎" if self._cursor_visible else ""
    try:
      text_widget.update(Markdown(full + " " + cursor))
    except Exception:
      try:
        text_widget.update(full + " " + cursor)
      except Exception:
        pass

  def finalize(self) -> str:

    """Finalize the stream, return the full text."""

    self._streaming = False

    full = "".join(self._parts)

    text_widget = self.query_one("#stream-text", Static)

    try:

      text_widget.update(Markdown(full))

    except Exception:

      text_widget.update(full)

    # Brief highlight flash on finalization

    self.remove_class("thinking")
    self.add_class("flash")
    self.set_timer(0.5, lambda: self.remove_class("flash"))

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

  def __init__(self, **kwargs) -> None:

    super().__init__(**kwargs)

    self._stream_widget: StreamMessage | None = None

    self._active_tools: dict[str, ToolCallEntry] = {}

    self._welcome_shown: bool = False

  # ── Welcome banner ───────────────────────────────────────────────────

  _WELCOME_BANNER = r"""
[KCode Welcome Banner]

  ██╗  ██╗     ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██║     ██║   ██║██║  ██║█████╗
  ██╔═██╗     ██║     ██║   ██║██║  ██║██╔══╝
  ██║  ██╗    ╚██████╗╚██████╔╝██████╔╝███████╗
  ╚═╝  ╚═╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝

  [dim]v__version__  ·  AI-powered coding agent[/dim]

  [dim]Type [/dim][cyan]/help[cyan][dim] for commands  ·  [/dim][cyan]/slash[cyan][dim] for palette  ·  [dim]Ctrl+C[dim] to quit

"""

  def show_welcome(self) -> None:
    """Display the welcome banner if no messages yet."""
    if self._welcome_shown:
      return
    self._welcome_shown = True
    from rich.markdown import Markdown
    banner = self._WELCOME_BANNER.replace("__version__", self._get_version())
    md = Markdown(banner)
    self.mount(Static(md, classes="welcome-banner"))
    self._scroll_end()

  def hide_welcome(self) -> None:
    """Remove the welcome banner."""
    if not self._welcome_shown:
      return
    self._welcome_shown = False
    try:
      banner = self.query_one(".welcome-banner")
      banner.remove()
    except Exception:
      pass

  def _get_version(self) -> str:
    """Get the kcode version string."""
    try:
      from importlib.metadata import version
      return version("kcode")
    except Exception:
      return "dev"

  # ── Public API ────────────────────────────────────────────────────────

  def add_message(self, content: str, role: str = "user") -> None:
    """Add a completed message."""
    self.hide_welcome()

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
    self.hide_welcome()

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
      use_anim = self._stream_widget is not None
      self.scroll_end(animate=use_anim, duration=0.08 if use_anim else 0)
    self.call_after_refresh(_do_scroll)