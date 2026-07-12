"""Extended tests for packages/core/src/runtime/events.py."""
from __future__ import annotations

from packages.core.src.runtime.events import Event, EventBus


def test_emit_calls_registered_handler() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.on("test", lambda e: received.append(e))

    bus.emit(Event(name="test", payload={"x": 1}))

    assert len(received) == 1
    assert received[0].payload == {"x": 1}


def test_emit_multiple_handlers_same_event() -> None:
    bus = EventBus()
    a: list[str] = []
    b: list[str] = []
    bus.on("ev", lambda e: a.append(e.name))
    bus.on("ev", lambda e: b.append(e.name))

    bus.emit(Event(name="ev"))

    assert a == ["ev"]
    assert b == ["ev"]


def test_emit_unregistered_event_is_noop() -> None:
    bus = EventBus()
    # Should not raise
    bus.emit(Event(name="unknown"))


def test_emit_different_events() -> None:
    bus = EventBus()
    log: list[str] = []
    bus.on("a", lambda e: log.append("a"))
    bus.on("b", lambda e: log.append("b"))

    bus.emit(Event(name="a"))
    bus.emit(Event(name="b"))
    bus.emit(Event(name="a"))

    assert log == ["a", "b", "a"]


def test_handler_receives_payload() -> None:
    bus = EventBus()
    captured: dict = {}
    bus.on("data", lambda e: captured.update(e.payload))

    bus.emit(Event(name="data", payload={"key": "val", "n": 42}))

    assert captured == {"key": "val", "n": 42}


def test_event_default_payload() -> None:
    e = Event(name="x")
    assert e.payload == {}
