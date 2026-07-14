"""TurnController -- manages agent streaming turns with cancellation support.

Encapsulates the sync-to-async bridge for consuming CliAgentRuntime.step_stream(),
generation-id based cancellation, and event dispatching to UI callbacks.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from packages.core.src.models.interfaces import StreamChunk, ChunkType
from packages.core.src.runtime.contracts import AgentSnapshot
from apps.cli.src.core.agent_runtime import CliAgentRuntime

_log = logging.getLogger(__name__)


# ── UI event types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnText:
  """A text delta from the model."""
  turn_id: int
  delta: str


@dataclass(frozen=True)
class TurnToolStart:
  """A tool call has started."""
  turn_id: int
  tool_name: str
  tool_call_id: str


@dataclass(frozen=True)
class TurnToolArgs:
  """Streaming tool call arguments."""
  turn_id: int
  tool_name: str
  tool_call_id: str
  delta: str


@dataclass(frozen=True)
class TurnToolEnd:
  """A tool call has finished."""
  turn_id: int
  tool_name: str
  tool_call_id: str
  result: str
  is_error: bool


@dataclass(frozen=True)
class TurnFinished:
  """The agent turn completed successfully."""
  turn_id: int
  snapshot: AgentSnapshot


@dataclass(frozen=True)
class TurnFailed:
  """The agent turn failed with an error."""
  turn_id: int
  message: str


TurnEvent = TurnText | TurnToolStart | TurnToolArgs | TurnToolEnd | TurnFinished | TurnFailed


# ── Callbacks ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnCallbacks:
  """UI callbacks invoked by the controller during a turn.

  All callbacks are called from the async consumer side (main event loop),
  NOT from the background thread.
  """
  on_text: Callable[[TurnText], None]
  on_tool_start: Callable[[TurnToolStart], None]
  on_tool_args: Callable[[TurnToolArgs], None]
  on_tool_end: Callable[[TurnToolEnd], None]
  on_finished: Callable[[TurnFinished], None]
  on_failed: Callable[[TurnFailed], None]


# ── Controller ──────────────────────────────────────────────────────


class TurnController:
  """Manages a single agent turn: start, consume, cancel.

  Usage::

    controller = TurnController(runtime, callbacks, loop)
    await controller.start(user_input)
    # ... later ...
    controller.cancel()
  """

  def __init__(
    self,
    runtime: CliAgentRuntime,
    callbacks: TurnCallbacks,
    loop: asyncio.AbstractEventLoop,
  ) -> None:
    self._runtime = runtime
    self._callbacks = callbacks
    self._loop = loop
    self._turn_id = 0
    self._cancel_event = threading.Event()
    self._active = False

  @property
  def is_active(self) -> bool:
    """Whether a turn is currently in progress."""
    return self._active

  @property
  def turn_id(self) -> int:
    """The current turn id."""
    return self._turn_id

  async def start(self, user_input: str) -> None:
    """Start a new agent turn. Consumes the sync generator in a daemon thread.

    Events are dispatched to callbacks on the main event loop.
    """
    if self._active:
      _log.warning("TurnController.start called while turn %d is active", self._turn_id)
      return

    self._turn_id += 1
    turn_id = self._turn_id
    self._cancel_event.clear()
    self._active = True

    queue: asyncio.Queue[StreamChunk | AgentSnapshot | Exception | None] = asyncio.Queue()
    cancel = self._cancel_event

    def _producer() -> None:
      """Run the sync generator in a daemon thread."""
      try:
        for item in self._runtime.step_stream(user_input):
          if cancel.is_set():
            break
          self._loop.call_soon_threadsafe(queue.put_nowait, item)
      except Exception as exc:
        if not cancel.is_set():
          self._loop.call_soon_threadsafe(queue.put_nowait, exc)
      finally:
        self._loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_producer, daemon=True).start()

    try:
      await self._consume(turn_id, queue)
    finally:
      self._active = False
      self._cancel_event.clear()

  async def _consume(
    self,
    turn_id: int,
    queue: asyncio.Queue[StreamChunk | AgentSnapshot | Exception | None],
  ) -> None:
    """Consume events from the queue and dispatch to callbacks."""
    cb = self._callbacks
    try:
      while True:
        item = await queue.get()
        if item is None:
          break

        if isinstance(item, Exception):
          cb.on_failed(TurnFailed(turn_id=turn_id, message=str(item)))
          break

        if isinstance(item, StreamChunk):
          if item.type == ChunkType.TEXT and item.delta:
            cb.on_text(TurnText(turn_id=turn_id, delta=item.delta))
          elif item.type == ChunkType.TOOL_CALL_START:
            cb.on_tool_start(TurnToolStart(
              turn_id=turn_id,
              tool_name=item.tool_name or "tool",
              tool_call_id=item.tool_call_id or "",
            ))
          elif item.type == ChunkType.TOOL_CALL_ARGS and item.delta:
            cb.on_tool_args(TurnToolArgs(
              turn_id=turn_id,
              tool_name=item.tool_name or "tool",
              tool_call_id=item.tool_call_id or "",
              delta=item.delta,
            ))
          elif item.type == ChunkType.TOOL_CALL_END:
            cb.on_tool_end(TurnToolEnd(
              turn_id=turn_id,
              tool_name=item.tool_name or "tool",
              tool_call_id=item.tool_call_id or "",
              result=item.delta or "",
              is_error=False,
            ))

        elif isinstance(item, AgentSnapshot):
          cb.on_finished(TurnFinished(turn_id=turn_id, snapshot=item))

    except Exception as exc:
      _log.error("Turn %d consume error: %s", turn_id, exc)
      cb.on_failed(TurnFailed(turn_id=turn_id, message=str(exc)))

  def cancel(self) -> None:
    """Cancel the current turn.

    Sets the cancel event so the producer thread stops iterating.
    The consumer will drain remaining items and finish.
    """
    if not self._active:
      return
    self._cancel_event.set()
