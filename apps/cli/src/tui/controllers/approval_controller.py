"""ApprovalController -- bridges sync approval callbacks to Textual modal dialogs."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal

_log = logging.getLogger(__name__)

ApprovalMode = Literal["manual", "auto"]
ApprovalCallback = Callable[[str, str, dict[str, Any]], bool]


@dataclass(frozen=True)
class ApprovalRequest:
  """An incoming approval request from the agent worker thread."""
  tool_name: str
  safety_class: str
  arguments: dict[str, Any]


@dataclass(frozen=True)
class ApprovalOutcome:
  """The result of an approval request."""
  approved: bool


class ApprovalController:
  """Routes approval requests to either auto-approve or to a modal UI.

  In manual mode the controller must be wired to an ``ask_approval`` callable
  that returns a ``bool`` **from the UI thread**.  The caller (agent worker
  thread) blocks until the outcome is available.

  In auto mode every request is approved immediately.

  Usage::

    controller = ApprovalController(mode="manual", ask_approval=show_modal)
    approved = controller.request(tool_name, safety_class, arguments)
  """

  def __init__(
    self,
    mode: ApprovalMode = "manual",
    ask_approval: Callable[[ApprovalRequest], bool] | None = None,
    timeout: float = 120.0,
  ) -> None:
    self._mode = mode
    self._ask_approval = ask_approval
    self._timeout = timeout

  @property
  def mode(self) -> ApprovalMode:
    return self._mode

  @mode.setter
  def mode(self, value: ApprovalMode) -> None:
    self._mode = value

  def request(
    self,
    tool_name: str,
    safety_class: str,
    arguments: dict[str, Any],
  ) -> bool:
    """Blocking call executed from the agent worker thread.

    Returns ``True`` if the tool call is approved.
    """
    if self._mode == "auto":
      return True

    if self._ask_approval is None:
      _log.warning("No ask_approval wired in manual mode -- denying tool=%s", tool_name)
      return False

    req = ApprovalRequest(
      tool_name=tool_name,
      safety_class=safety_class,
      arguments=arguments,
    )
    return self._ask_approval(req)
