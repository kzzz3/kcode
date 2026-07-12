"""Model picker modal for TUI.

Features:
  - Filterable model list with search
  - Enter submits highlighted item (not always first)
  - Dim background overlay for modal feel
  - Escape closes
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListView, ListItem, Label


class ModelPicker(ModalScreen[str | None]):
  """Modal that lets user pick a model from available models."""

  DEFAULT_CSS = """
  ModelPicker {
    align: center middle;
    background: $boost 60%;
  }

  #model-picker {
    width: 64;
    max-width: 80;
    height: auto;
    max-height: 70%;
    border: thick $accent;
    background: $surface;
    padding: 1 1;
  }

  #model-picker Input {
    margin: 0 0 1 0;
  }

  #model-picker ListView {
    height: 1fr;
  }
  """

  def __init__(self, models: list[str], current_model: str = "") -> None:
    super().__init__()
    self._models = models
    self._current_model = current_model

  def compose(self) -> ComposeResult:
    with Vertical(id="model-picker"):
      yield Input(placeholder="Search models...", id="model-input")
      yield ListView(id="model-list")

  def on_mount(self) -> None:
    self._rebuild_list("")
    self.query_one(Input).focus()

  def on_input_changed(self, event: Input.Changed) -> None:
    self._rebuild_list(event.value)

  def on_input_submitted(self, event: Input.Submitted) -> None:
    """Enter in the input field: select the highlighted item from the list."""
    list_view = self.query_one(ListView)
    idx = list_view.index
    filtered = self._filtered_models(event.value)
    if idx is not None and 0 <= idx < len(filtered):
      self.dismiss(filtered[idx])
    elif filtered:
      self.dismiss(filtered[0])
    else:
      self.dismiss(None)

  def on_list_view_selected(self, event: ListView.Selected) -> None:
    list_view = self.query_one(ListView)
    idx = list_view.index
    if idx is None:
      return
    filtered = self._filtered_models(self.query_one(Input).value)
    if 0 <= idx < len(filtered):
      self.dismiss(filtered[idx])
    else:
      self.dismiss(None)

  def on_key(self, event) -> None:
    if event.key == "escape":
      self.dismiss(None)

  def _rebuild_list(self, query: str) -> None:
    list_view = self.query_one(ListView)
    list_view.clear()
    for model in self._filtered_models(query):
      marker = " *current*" if model == self._current_model else ""
      list_view.append(ListItem(Label(f"{model}{marker}")))

  def _filtered_models(self, query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
      return list(self._models)
    return [m for m in self._models if q in m.lower()]