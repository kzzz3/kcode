"""Lightweight domain event bus."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    """Generic runtime event envelope."""
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[Event], None]


class EventBus:
    """Simple synchronous event bus for CLI runtime."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def on(self, name: str, handler: EventHandler) -> None:
        self._handlers.setdefault(name, []).append(handler)

    def emit(self, event: Event) -> None:
        for handler in self._handlers.get(event.name, []):
            handler(event)
