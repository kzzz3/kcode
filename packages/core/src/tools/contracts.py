from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    pass


class ToolOutput(BaseModel):
    ok: bool = True
    message: str = ""
    artifacts: dict[str, Any] = {}
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ToolMeta:
    name: str
    description: str
    safety_class: str
    parameter_schema: dict[str, Any]
    version: str = "1.0.0"


ToolExecutor = Callable[[dict[str, Any]], ToolOutput]


class Tool:
    def __init__(self, meta: ToolMeta, executor: ToolExecutor) -> None:
        self.meta = meta
        self._executor = executor

    def run(self, payload: dict[str, Any]) -> ToolOutput:
        return self._executor(payload)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.meta.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> Sequence[ToolMeta]:
        return [t.meta for t in self._tools.values()]