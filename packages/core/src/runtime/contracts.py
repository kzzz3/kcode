"""Agent runtime contracts and state machine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from packages.core.src.runtime.events import EventBus


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    AWAITING_APPROVAL = "awaiting_approval"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass
class AgentSnapshot:
    state: AgentState
    step_index: int
    messages: list[dict[str, Any]]
    tool_runs: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRuntime(ABC):
    """Abstract runtime contract shared by CLI and future desktop shell."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or EventBus()

    @abstractmethod
    def step(self, user_input: str) -> AgentSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_snapshot(self) -> AgentSnapshot:
        raise NotImplementedError

