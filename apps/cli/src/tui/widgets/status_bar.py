"""Status bar showing agent state, tokens, cost, context utilization, and model."""
from __future__ import annotations

from textual.widgets import Static
from textual.reactive import reactive


class StatusBar(Static):
  """Bottom status bar with reactive state display."""

  DEFAULT_CSS = """
  StatusBar {
    height: 1;
    dock: bottom;
    padding: 0 1;
    background: $accent;
    color: $text;
  }
  """

  state: reactive[str] = reactive("IDLE")
  tokens: reactive[int] = reactive(0)
  cost: reactive[float] = reactive(0.0)
  context_utilization: reactive[float] = reactive(0.0)
  model_name: reactive[str] = reactive("")

  def render(self) -> str:
    parts: list[str] = []
    parts.append(f"State: {self.state}")
    if self.tokens > 0:
      parts.append(f"Tokens: {self.tokens:,}")
    if self.cost > 0:
      parts.append(f"Cost: ${self.cost:.4f}")
    if self.context_utilization > 0:
      parts.append(f"Ctx: {self.context_utilization:.0%}")
    if self.model_name:
      parts.append(f"Model: {self.model_name}")
    return " | ".join(parts)

  def update_status(
    self,
    *,
    state: str | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    context_utilization: float | None = None,
    model_name: str | None = None,
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
