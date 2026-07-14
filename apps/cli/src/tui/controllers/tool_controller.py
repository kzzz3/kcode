"""ToolController -- orchestrates slash commands, model switching, and tool-related actions.

Extracts tool dispatch, model listing, and utility actions from MainScreen
so the screen only does layout and event routing.
"""
from __future__ import annotations

import io
import contextlib
import logging
from typing import Callable

from apps.cli.src.core.agent_runtime import CliAgentRuntime
from apps.cli.src.tui.controllers.approval_controller import ApprovalController

_log = logging.getLogger(__name__)


class ToolController:
  """Orchestrates slash command dispatch, model listing, and utility actions.

  Usage::

    tc = ToolController(runtime, approval)
    result = tc.dispatch_slash("model_picker")
    models = tc.list_models()
  """

  def __init__(
    self,
    runtime: CliAgentRuntime,
    approval: ApprovalController,
    *,
    on_notify: Callable[[str, str], None] | None = None,
    on_model_changed: Callable[[str], None] | None = None,
    on_approval_toggled: Callable[[str], None] | None = None,
    on_doctor_output: Callable[[str], None] | None = None,
  ) -> None:
    self._runtime = runtime
    self._approval = approval
    self._on_notify = on_notify or (lambda msg, sev: None)
    self._on_model_changed = on_model_changed or (lambda m: None)
    self._on_approval_toggled = on_approval_toggled or (lambda m: None)
    self._on_doctor_output = on_doctor_output or (lambda t: None)

  # ── Slash command dispatch ────────────────────────────────────────

  def dispatch_slash(self, handler: str) -> str | None:
    """Dispatch a slash command by handler id.

    Returns an action id string for actions that need UI side-effects,
    or None if handled entirely within the controller.
    """
    actions = {
      "model_picker": "open_model_picker",
      "help": "show_help",
      "clear": "clear_chat",
      "sessions": "list_sessions",
      "theme": "cycle_theme",
      "sidebar": "toggle_sidebar",
    }
    if handler in ("compact",):
      self.compact_context()
      return None
    if handler in ("doctor",):
      self.run_doctor()
      return None
    if handler == "approval":
      self.toggle_approval()
      return None
    return actions.get(handler)

  # ── Model management ─────────────────────────────────────────────

  def list_models(self) -> list[str]:
    """Return available models from config, falling back to current model."""
    try:
      from apps.cli.src.config.resolution import resolve_config
      config = resolve_config(self._runtime._workspace_root)
      models = config.model.extra.get("models", [])
      if isinstance(models, list) and models:
        return [str(m) for m in models]
    except Exception:
      pass
    current = self._runtime._model_name
    return [current] if current else ["gpt-4o"]

  @property
  def current_model(self) -> str:
    return self._runtime._model_name or "gpt-4o"

  def set_model(self, model_name: str) -> None:
    """Switch the active model and notify UI."""
    self._runtime._model_name = model_name
    self._on_model_changed(model_name)

  # ── Approval toggle ──────────────────────────────────────────────

  def toggle_approval(self) -> None:
    """Toggle between manual and auto approval modes."""
    current = self._approval.mode
    new_mode = "manual" if current == "auto" else "auto"
    self._approval.mode = new_mode  # type: ignore[assignment]
    self._on_approval_toggled(new_mode)

  # ── Context compaction ───────────────────────────────────────────

  def compact_context(self) -> None:
    """Compact the conversation context window."""
    try:
      if self._runtime.compact():
        self._on_notify("Context compacted", "info")
      else:
        self._on_notify("Nothing to compact", "info")
    except Exception as exc:
      _log.error("Compact failed: %s", exc)
      self._on_notify(f"Compact failed: {exc}", "error")

  # ── Doctor check ─────────────────────────────────────────────────

  def run_doctor(self) -> None:
    """Run the doctor health check and report via callback."""
    try:
      from apps.cli.src.commands.doctor import run_doctor
      buf = io.StringIO()
      with contextlib.redirect_stdout(buf):
        run_doctor()
      output = buf.getvalue()
      lines = output.strip().split("\n")
      summary = "\n".join(lines[:20])
      self._on_doctor_output(summary)
    except Exception as exc:
      _log.error("Doctor check failed: %s", exc)
      self._on_doctor_output(f"Doctor check failed: {exc}")

  # ── Theme cycling ────────────────────────────────────────────────

  def cycle_theme(self, available_themes: list[str], current_theme: str) -> str | None:
    """Return the next theme name in the cycle, or None if no themes."""
    if not available_themes:
      return None
    try:
      idx = available_themes.index(current_theme)
      return available_themes[(idx + 1) % len(available_themes)]
    except ValueError:
      return available_themes[0]
