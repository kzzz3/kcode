"""Status bar showing agent state, tokens, cost, context utilization, and model.

Features:

  - Color-coded state display (IDLE=green, THINKING=yellow, TOOL_RUNNING=blue, ERROR=red)
  - Animated spinner during THINKING and TOOL_RUNNING states
  - Rich Text rendering for conditional styling
  - Responsive degradation: narrow shows state/approval/context; medium +model/step; wide +tokens/cost
"""

from __future__ import annotations

import itertools

from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

# Spinner frames (Braille dots style)
_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# State -> (color, label)
_STATE_STYLES: dict[str, tuple[str, str]] = {
  "IDLE":          ("green",  "IDLE"),
  "THINKING":      ("yellow", "THINKING"),
  "TOOL_RUNNING":  ("blue",   "TOOL RUNNING"),
  "ERROR":         ("red",    "ERROR"),
}


class StatusBar(Static):
  """Bottom status bar with rich color-coded state and spinner animation."""
  state: reactive[str] = reactive("IDLE")
  tokens: reactive[int] = reactive(0)
  cost: reactive[float] = reactive(0.0)
  context_utilization: reactive[float] = reactive(0.0)
  model_name: reactive[str] = reactive("")
  approval_mode: reactive[str] = reactive("auto")

  def __init__(self, **kwargs) -> None:
    super().__init__(**kwargs)
    self._spinner = itertools.cycle(_SPINNER_FRAMES)
    self._spinner_active = False
    self._streaming_active = False
    self._state_flash = False
    self._step_count = 0
    self._prompt_tokens = 0
    self._completion_tokens = 0

  def render(self) -> Text:
    text = Text()

    # State with color
    color, label = _STATE_STYLES.get(self.state, ("white", self.state))

    if self.state in ("THINKING", "TOOL_RUNNING"):
      frame = next(self._spinner)
      text.append(f" {frame} ", style=f"bold {color}")
      self._schedule_spinner_tick()

    text.append("State: ", style="dim")
    state_style = f"bold {color}"
    if self._state_flash:
      state_style = f"bold reverse {color}"
    text.append(label, style=state_style)

    # Context utilization (always visible when > 0)
    if self.context_utilization > 0:
      text.append(" │ ", style="dim")
      text.append("Ctx: ", style="dim")
      ctx_color = (
        "red" if self.context_utilization > 0.9
        else "darkorange" if self.context_utilization > 0.8
        else "yellow" if self.context_utilization > 0.5
        else "green"
      )
      text.append(f"{self.context_utilization:.0%}", style=ctx_color)

    # Approval
    text.append(" │ ", style="dim")
    text.append("Approval: ", style="dim")
    ap_color = "yellow" if self.approval_mode == "auto" else "green"
    text.append(self.approval_mode, style=ap_color)

    # Model (medium+)
    if self.model_name:
      text.append(" │ ", style="dim")
      text.append("Model: ", style="dim")
      text.append(self.model_name, style="cyan")

    # Step counter (medium+)
    if self._step_count > 0:
      text.append(" │ ", style="dim")
      text.append("Step: ", style="dim")
      text.append(str(self._step_count), style="white")

    # Tokens (wide)
    if self.tokens > 0:
      text.append(" │ ", style="dim")
      text.append("Tokens: ", style="dim")
      text.append(f"{self.tokens:,}", style="white")

    # Cost (wide)
    if self.cost > 0:
      text.append(" │ ", style="dim")
      text.append("Cost: ", style="dim")
      text.append(f"${self.cost:.4f}", style="yellow")

    return text

  def _schedule_spinner_tick(self) -> None:
    """Schedule the next spinner update via set_timer."""
    if not self._spinner_active:
      self._spinner_active = True
      self.set_timer(0.1, self._tick_spinner)

  def _tick_spinner(self) -> None:
    """Trigger a re-render for the spinner frame."""
    self._spinner_active = False
    if self.state in ("THINKING", "TOOL_RUNNING"):
      self.refresh()

  def watch_state(self, old_val: str, new_val: str) -> None:
    """Flash the state label briefly on state change."""
    if old_val != new_val:
      self._state_flash = True
      self.set_timer(0.6, self._clear_state_flash)

  def _clear_state_flash(self) -> None:
    """Clear the state flash effect."""
    self._state_flash = False
    self.refresh()

  def update_status(
    self,
    *,
    state: str | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    context_utilization: float | None = None,
    model_name: str | None = None,
    approval_mode: str | None = None,
  ) -> None:
    """Update one or more status fields."""
    if state is not None:
      self.state = state
    if tokens is not None:
      self.tokens = tokens
    if cost is not None:
      self.cost = cost
    if context_utilization is not None:
      self.context_utilization = context_utilization
    if model_name is not None:
      self.model_name = model_name
    if approval_mode is not None:
      self.approval_mode = approval_mode

  # ── Convenience setters (called by MainScreen controllers) ──

  def set_token_info(self, prompt_tokens: int, completion_tokens: int, cost: float = 0.0) -> None:
    """Update token counts and cost from a completed turn."""
    self._prompt_tokens = prompt_tokens
    self._completion_tokens = completion_tokens
    self.tokens = prompt_tokens + completion_tokens
    if cost > 0:
      self.cost = cost
    self.refresh()

  def set_context_usage(self, used: int, budget: int) -> None:
    """Update context window utilization as fraction of budget."""
    if budget > 0:
      self.context_utilization = used / budget
    self.refresh()

  def set_model(self, model: str) -> None:
    """Update the displayed model name."""
    self.model_name = model

  def set_approval_mode(self, mode: str) -> None:
    """Update the displayed approval mode."""
    self.approval_mode = mode

  def set_step_count(self, count: int) -> None:
    """Update the current agent step counter."""
    self._step_count = count
    self.refresh()

  def set_streaming_hint(self, active: bool) -> None:
    """Toggle streaming state flag (no longer renders keyboard hints)."""
    self._streaming_active = active
    self.refresh()
