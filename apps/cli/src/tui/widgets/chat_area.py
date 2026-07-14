"""Transcript display with role-aligned rows and tool timeline.

Design (OpenCode/Crush-inspired):
  - Messages use a fixed 10-col role gutter + content area, no Panel cards.
  - Tool calls rendered as a timeline: status icon + name + args summary + duration.
  - Collapsible long tool output (Enter toggles).
  - Smart auto-scroll: follow when at bottom, pause when scrolled up.
  - Welcome state is compact (<=8 lines).
"""

from __future__ import annotations

import time
from enum import Enum

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


# ── Welcome banner (compact, <=8 lines) ─────────────────────────────────

_WELCOME_LINES = [
    "[bold cyan]KCode[/bold cyan]  [dim]AI Coding Agent[/dim]",
    "[dim]─────────────────────────────────────[/dim]",
    "  Workspace  [cyan]{workspace}[/cyan]",
    "  Model      [cyan]{model}[/cyan]",
    "  Approval   [cyan]{approval}[/cyan]",
    "[dim]─────────────────────────────────────[/dim]",
    "  Type a message and press [bold]Enter[/bold]",
    "  [cyan]/[/cyan] for commands  ·  [cyan]Ctrl+H[/cyan] help  ·  [cyan]Escape[/cyan] cancel",
]


# ── Role label helper ──────────────────────────────────────────────────

class Role(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


_ROLE_LABELS: dict[Role, str] = {
    Role.USER:      "[bold cyan]  You    [/bold cyan]",
    Role.ASSISTANT: "[bold green]  KCode  [/bold green]",
    Role.SYSTEM:    "[dim italic]  System [/dim italic]",
}

_ROLE_BORDERS: dict[Role, str] = {
    Role.USER:      "cyan",
    Role.ASSISTANT: "green",
    Role.SYSTEM:    "dim",
}


# ── Tool status icons ─────────────────────────────────────────────────

class ToolStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


_TOOL_ICONS: dict[ToolStatus, str] = {
    ToolStatus.RUNNING: "[yellow]⏳[/yellow]",
    ToolStatus.SUCCESS: "[green] ✓[/green]",
    ToolStatus.DENIED:  "[red] ⊘[/red]",
    ToolStatus.FAILED:  "[red] ✗[/red]",
}


# ── Transcript message row ─────────────────────────────────────────────

class MessageRow(Widget):
    """A single role-aligned message row: 10-col gutter + content."""

    DEFAULT_CSS = """
    MessageRow {
      height: auto;
      min-height: 1;
      layout: horizontal;
      margin: 0 0 0 0;
      padding: 0;
    }
    MessageRow .gutter {
      width: 10;
      min-width: 10;
      height: 100%;
    }
    MessageRow .content {
      width: 1fr;
      height: auto;
      padding: 0 1 0 0;
    }
    MessageRow.user .gutter {
      border-right: tall cyan 20%;
    }
    MessageRow.assistant .gutter {
      border-right: tall green 20%;
    }
    MessageRow.system .gutter {
      border-right: tall $text-muted 20%;
    }
    """

    def __init__(self, content: str, role: Role) -> None:
        super().__init__(classes=role.value)
        self._content = content
        self._role = role

    def compose(self) -> ComposeResult:
        label = _ROLE_LABELS.get(self._role, "[dim]  ?      [/dim]")
        yield Static(label, classes="gutter")

        if self._role == Role.ASSISTANT:
            try:
                rendered = Markdown(self._content)
            except Exception:
                rendered = Text(self._content)
        else:
            rendered = Text(self._content)

        yield Static(rendered, classes="content")

    def update_content(self, new_content: str) -> None:
        """Update the content area (used during streaming finalization)."""
        self._content = new_content
        try:
            content_widget = self.query_one(".content", Static)
            if self._role == Role.ASSISTANT:
                try:
                    rendered = Markdown(new_content)
                except Exception:
                    rendered = Text(new_content)
            else:
                rendered = Text(new_content)
            content_widget.update(rendered)
        except Exception:
            pass


# ── Tool timeline entry ────────────────────────────────────────────────

class ToolEntry(Widget):
    """A single tool call in the timeline: icon + name + args + duration.

    Collapsible: click or Enter toggles result visibility.
    """

    DEFAULT_CSS = """
    ToolEntry {
      height: auto;
      min-height: 1;
      layout: horizontal;
      padding: 0;
      margin: 0;
    }
    ToolEntry .tc-gutter {
      width: 10;
      min-width: 10;
      height: 100%;
      color: $text-muted;
    }
    ToolEntry .tc-body {
      width: 1fr;
      height: auto;
      padding: 0 1 0 0;
    }
    ToolEntry .tc-header {
      height: 1;
      color: $text-muted;
    }
    ToolEntry .tc-detail {
      height: auto;
      display: none;
      padding: 0 0 0 2;
      color: $text-muted;
    }
    ToolEntry.expanded .tc-detail {
      display: block;
    }
    """

    expanded: reactive[bool] = reactive(False)

    def __init__(
        self,
        tool_name: str,
        tool_call_id: str = "",
        args_summary: str = "",
    ) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._tool_call_id = tool_call_id
        self._args_summary = args_summary
        self._status = ToolStatus.RUNNING
        self._result: str = ""
        self._duration_ms: int = 0
        self._start_time: float = time.monotonic()

    def compose(self) -> ComposeResult:
        yield Static("  tools", classes="tc-gutter")
        yield Static(self._render_header(), classes="tc-header")
        yield Static(self._render_detail(), classes="tc-detail")

    def _render_header(self) -> str:
        icon = _TOOL_ICONS[self._status]
        name = f"[bold]{self._tool_name}[/bold]"
        args = f" [dim]{self._args_summary[:60]}[/dim]" if self._args_summary else ""
        dur = ""
        if self._status != ToolStatus.RUNNING and self._duration_ms > 0:
            if self._duration_ms >= 1000:
                dur = f" [dim]({self._duration_ms / 1000:.1f}s)[/dim]"
            else:
                dur = f" [dim]({self._duration_ms}ms)[/dim]"
        return f"  {icon} {name}{args}{dur}"

    def _render_detail(self) -> str:
        parts: list[str] = []
        if self._args_summary and len(self._args_summary) > 60:
            parts.append(f"[dim]Args:[/dim] {self._args_summary[:500]}")
        if self._result:
            preview = self._result[:600]
            if len(self._result) > 600:
                preview += "..."
            parts.append(f"[dim]Result:[/dim] {preview}")
        return "\n".join(parts) if parts else "  (no details)"

    def update_status(
        self,
        status: ToolStatus,
        result: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Update tool status after completion/denial/failure."""
        self._status = status
        self._result = result
        self._duration_ms = duration_ms
        try:
            header = self.query_one(".tc-header", Static)
            header.update(self._render_header())
            detail = self.query_one(".tc-detail", Static)
            detail.update(self._render_detail())
        except Exception:
            pass

    def append_args(self, delta: str) -> None:
        """Accumulate incremental tool-call args."""
        self._args_summary += delta
        try:
            header = self.query_one(".tc-header", Static)
            header.update(self._render_header())
        except Exception:
            pass

    def on_click(self) -> None:
        self.expanded = not self.expanded

    def watch_expanded(self, old: bool, new: bool) -> None:
        self.toggle_class("expanded", new)

    def action_toggle(self) -> None:
        self.expanded = not self.expanded


# ── Stream row (live-updating assistant message) ───────────────────────

class StreamRow(Widget):
    """A streaming assistant message with buffered rendering and cursor."""

    DEFAULT_CSS = """
    StreamRow {
      height: auto;
      min-height: 1;
      layout: horizontal;
      margin: 0;
      padding: 0;
    }
    StreamRow .gutter {
      width: 10;
      min-width: 10;
      height: 100%;
      border-right: tall green 20%;
    }
    StreamRow .content {
      width: 1fr;
      height: auto;
      padding: 0 1 0 0;
    }
    StreamRow.thinking .gutter {
      border-right: tall $warning 40%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffer: list[str] = []
        self._text: str = ""
        self._dirty_len: int = 0
        self._render_threshold: int = 80
        self._streaming: bool = True
        self._start_time: float = time.monotonic()

    def compose(self) -> ComposeResult:
        yield Static("[bold green]  KCode  [/bold green]", classes="gutter")
        yield Static("[dim]thinking...[/dim]", classes="content")

    def append_delta(self, delta: str) -> None:
        self._buffer.append(delta)
        self._text += delta
        if len(self._text) - self._dirty_len >= self._render_threshold:
            self._flush()

    def _flush(self) -> None:
        if not self._text:
            return
        self._dirty_len = len(self._text)
        try:
            display = self._text + (" ▌" if self._streaming else "")
            try:
                rendered = Markdown(display)
            except Exception:
                rendered = Text(display)
            content = self.query_one(".content", Static)
            content.update(rendered)
        except Exception:
            pass

    def finalize(self) -> str:
        """Finalize the stream. Returns the full text."""
        self._streaming = False
        self._flush()
        return self._text

    def get_text(self) -> str:
        return self._text


# ── "New output" indicator ─────────────────────────────────────────────

class NewOutputBanner(Widget):
    """Shown when user scrolled up and new content arrived."""

    DEFAULT_CSS = """
    NewOutputBanner {
      height: 1;
      dock: bottom;
      background: $accent;
      color: white;
      text-align: center;
      display: none;
    }
    NewOutputBanner.visible {
      display: block;
    }
    """

    def show(self) -> None:
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")


# ── Main ChatArea (Transcript) ─────────────────────────────────────────

class ChatArea(VerticalScroll):
    """Scrollable transcript with role-aligned rows and tool timeline.

    Layout: each message is a MessageRow with a 10-col role gutter.
    Tool calls are ToolEntry widgets with status icons.
    Streaming uses StreamRow with buffered rendering.
    """

    DEFAULT_CSS = """
    ChatArea {
      height: 1fr;
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

    # Welcome banner (compact, per-workspace)
    _WELCOME_TPL = "\n".join(_WELCOME_LINES)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stream_widget: StreamRow | None = None
        self._active_tools: dict[str, ToolEntry] = {}
        self._welcome_shown: bool = False
        self._auto_scroll: bool = True
        self._new_output_banner: NewOutputBanner | None = None

    def compose(self) -> ComposeResult:
        yield NewOutputBanner(id="new-output-banner")

    def on_mount(self) -> None:
        try:
            self._new_output_banner = self.query_one("#new-output-banner", NewOutputBanner)
        except Exception:
            pass

    # ── Welcome ───────────────────────────────────────────────────────

    def show_welcome(
        self,
        workspace: str = "",
        model: str = "",
        approval: str = "manual",
    ) -> None:
        """Display compact welcome state."""
        if self._welcome_shown:
            return
        self._welcome_shown = True
        text = self._WELCOME_TPL.format(
            workspace=workspace or ".",
            model=model or "(not configured)",
            approval=approval,
        )
        row = Static(Text.from_markup(text), classes="welcome-banner")
        self.mount(row)
        self._scroll_end()

    def hide_welcome(self) -> None:
        if not self._welcome_shown:
            return
        self._welcome_shown = False
        try:
            self.query_one(".welcome-banner").remove()
        except Exception:
            pass

    # ── Messages ──────────────────────────────────────────────────────

    def add_message(self, content: str, role: str = "user") -> None:
        """Add a completed message to the transcript."""
        self.hide_welcome()
        try:
            r = Role(role)
        except ValueError:
            r = Role.SYSTEM
        row = MessageRow(content, r)
        self.mount(row)
        self._scroll_end()
        self.post_message(self.Submitted(content, role))

    # ── Streaming ─────────────────────────────────────────────────────

    def start_stream(self, role: str = "assistant") -> None:
        """Begin a new streaming assistant message."""
        self.hide_welcome()
        self._stream_widget = StreamRow()
        self.mount(self._stream_widget)
        self._scroll_end()

    def add_stream_chunk(self, delta: str, turn_id: str = "") -> None:
        """Append text delta. turn_id is accepted for API compat but unused."""
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

    # ── Tool timeline ─────────────────────────────────────────────────

    def add_tool_call_start(
        self,
        tool_name: str,
        tool_call_id: str = "",
        turn_id: str = "",
    ) -> None:
        """Show a new tool call entry (running state)."""
        self.hide_welcome()
        entry = ToolEntry(tool_name, tool_call_id=tool_call_id)
        self.mount(entry)
        key = tool_call_id or tool_name
        self._active_tools[key] = entry
        self._scroll_end()

    def add_tool_call_args(
        self,
        tool_call_id: str,
        delta: str,
        tool_name: str = "",
    ) -> None:
        """Incremental tool args accumulation."""
        entry = self._active_tools.get(tool_call_id)
        if entry is not None:
            entry.append_args(delta)

    def add_tool_call_result(
        self,
        tool_call_id: str,
        result: str = "",
        duration_ms: int = 0,
        is_error: bool = False,
    ) -> None:
        """Update tool call entry with result."""
        entry = self._active_tools.pop(tool_call_id, None)
        if entry is not None:
            status = ToolStatus.FAILED if is_error else ToolStatus.SUCCESS
            entry.update_status(status, result=result, duration_ms=duration_ms)
        self._scroll_end()

    def add_tool_call_denied(
        self,
        tool_call_id: str,
        reason: str = "denied by user",
    ) -> None:
        """Mark a tool call as denied."""
        entry = self._active_tools.pop(tool_call_id, None)
        if entry is not None:
            entry.update_status(ToolStatus.DENIED, result=reason)
        self._scroll_end()

    # ── Clear ─────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all messages and reset state."""
        self._welcome_shown = False
        self._stream_widget = None
        self._active_tools.clear()
        for child in list(self.children):
            if not child.id or child.id != "new-output-banner":
                child.remove()

    # ── Auto-scroll logic ─────────────────────────────────────────────

    def on_scroll(self) -> None:
        """Track whether user is at the bottom."""
        self._auto_scroll = self.is_scrollable and self.scroll_y >= self.max_scroll_y - 2
        if self._auto_scroll and self._new_output_banner is not None:
            self._new_output_banner.hide()

    def _scroll_end(self) -> None:
        """Scroll to bottom if auto-scroll is enabled."""
        def _do() -> None:
            if self._auto_scroll:
                self.scroll_end(animate=False)
            elif self._new_output_banner is not None:
                self._new_output_banner.show()
        self.call_after_refresh(_do)

    def action_scroll_end(self) -> None:
        """Manual scroll-to-bottom and re-enable auto-scroll."""
        self._auto_scroll = True
        if self._new_output_banner is not None:
            self._new_output_banner.hide()
        self.scroll_end(animate=False)
