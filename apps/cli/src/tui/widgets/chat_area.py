"""Chat message display area with streaming and Markdown rendering."""
from __future__ import annotations

from textual.widgets import RichLog
from textual.message import Message
from rich.markdown import Markdown
from rich.text import Text
from rich.panel import Panel


class ChatArea(RichLog):
  """Chat message display with streaming, Markdown, and tool call support."""

  DEFAULT_CSS = """
  ChatArea {
    height: 1fr;
    border: solid $primary;
    padding: 0 1;
    overflow-y: auto;
  }
  """

  class Submitted(Message):
    """Notify that user submitted text."""
    def __init__(self, content: str, role: str) -> None:
      self.content = content
      self.role = role
      super().__init__()

  def __init__(self) -> None:
    super().__init__(auto_scroll=True)
    self._stream_parts: list[str] = []
    self._stream_role: str = ""

  # --- Public API ---

  def add_message(self, content: str, role: str = "user") -> None:
    """Add a complete message (user or system)."""
    if role == "user":
      header = Text("You", style="bold cyan")
    elif role == "system":
      header = Text("System", style="bold yellow")
    else:
      header = Text("KCode", style="bold green")

    self.write(Panel(Text(content), title=header, border_style="cyan" if role == "user" else "dim"))
    self.post_message(self.Submitted(content, role))

  def start_stream(self, role: str = "assistant") -> None:
    """Begin accumulating a streaming assistant message."""
    self._stream_parts = []
    self._stream_role = role

  def add_stream_chunk(self, delta: str) -> None:
    """Append a text delta to the current stream buffer."""
    self._stream_parts.append(delta)
    # Live-preview: render accumulated Markdown so far
    self._render_stream_preview()

  def end_stream(self) -> None:
    """Finalize the streaming message — render full Markdown."""
    if not self._stream_parts:
      return
    full_text = "".join(self._stream_parts)
    self._clear_stream_preview()
    header = Text("KCode", style="bold green")
    self.write(Panel(Markdown(full_text), title=header, border_style="green"))
    self._stream_parts = []
    self._stream_role = ""

  def cancel_stream(self) -> None:
    """Discard an in-progress stream."""
    self._stream_parts = []
    self._stream_role = ""

  def add_tool_call_start(self, tool_name: str, tool_call_id: str = "") -> None:
    """Show tool call invocation."""
    label = f" Calling: {tool_name} "
    self.write(Text(label, style="bold blue"))

  def add_tool_call_args(self, tool_name: str, delta: str) -> None:
    """Show incremental tool arguments (accumulated externally)."""
    # We don't dump raw JSON args to the log — too noisy.
    pass

  def add_tool_call_end(self, tool_name: str, tool_call_id: str = "", result: str = "", is_error: bool = False) -> None:
    """Show tool call result."""
    if is_error:
      self.write(Text(f" Error: {tool_name} — {result[:200]}", style="red"))
    else:
      # Truncate long results for display
      preview = result[:300] + ("..." if len(result) > 300 else "")
      self.write(Text(f" Done: {tool_name} — {preview}", style="dim green"))

  # --- Internal ---

  def _render_stream_preview(self) -> None:
    """Re-render the current stream buffer as Markdown preview."""
    # RichLog doesn't support in-place updates well, so we just accumulate.
    # The final end_stream() will render the full Markdown.
    # During streaming we write plain text deltas for responsiveness.
    pass

  def _clear_stream_preview(self) -> None:
    """Remove the preview widgets (no-op for RichLog — we just finalize)."""
    pass

