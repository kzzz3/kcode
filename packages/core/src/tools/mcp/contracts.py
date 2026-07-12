"""MCP adapter contracts.

Defines the abstract interface for MCP tool providers and the data models
used to describe, invoke, and return results from MCP-hosted tools.

These contracts are transport-agnostic — concrete adapters (stdio, SSE, HTTP)
implement McpToolProvider against these types.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class McpToolParamSchema(BaseModel):
    """JSON Schema fragment describing a tool's input parameters.

    Maps directly to the ``inputSchema`` field in the MCP ``tools/list``
    response.  We keep it as a free-form dict so adapters can round-trip
    arbitrary provider schemas without loss.
    """

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    additionalProperties: bool = False

    model_config = {"extra": "allow"}


class McpToolDescriptor(BaseModel):
    """A single tool exposed by an MCP server.

    Maps to the ``Tool`` object in the MCP spec.
    """

    name: str
    description: str = ""
    inputSchema: McpToolParamSchema = Field(default_factory=McpToolParamSchema)
    annotations: dict[str, Any] = Field(default_factory=dict)

    @property
    def safety_class(self) -> str:
        """Derive safety class from annotations or name heuristics.

        Defaults to ``read`` when the provider doesn't annotate.
        """
        cls = self.annotations.get("x-kcode-safety-class")
        if cls in ("read", "write", "system", "network"):
            return str(cls)
        # Heuristic fallbacks
        name_lower = self.name.lower()
        if any(kw in name_lower for kw in ("write", "create", "edit", "delete", "commit", "patch")):
            return "write"
        if any(kw in name_lower for kw in ("run", "exec", "command", "shell", "bash")):
            return "system"
        if any(kw in name_lower for kw in ("fetch", "http", "request", "download", "api")):
            return "network"
        return "read"


class McpToolInvocation(BaseModel):
    """A request to call a remote MCP tool."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timeout_seconds: float = 120.0


class McpToolResult(BaseModel):
    """The result of a remote MCP tool invocation.

    Maps to the ``CallToolResult`` object in the MCP spec.
    """

    ok: bool = True
    content: list[dict[str, Any]] = Field(default_factory=list)
    isError: bool = False
    error_message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def text_content(self) -> str:
        """Extract concatenated text from ``content`` blocks."""
        parts: list[str] = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)


class McpServerStatus(str, Enum):
    """Lifecycle state of an MCP server connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    ERROR = "error"


@dataclass
class McpServerInfo:
    """Metadata returned by an MCP server after initialization."""

    name: str
    version: str = ""
    protocol_version: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class McpToolProvider(ABC):
    """Abstract base class for MCP transport adapters.

    Concrete implementations (stdio, SSE, HTTP) must implement every method.
    The lifecycle is:

    1. ``connect()`` — establish transport and perform MCP handshake.
    2. ``discover_tools()`` — list available tools (may be called repeatedly).
    3. ``call_tool()`` — invoke a tool by name with arguments.
    4. ``disconnect()`` — tear down transport.
    """

    @abstractmethod
    async def connect(self) -> McpServerInfo:
        """Establish connection and perform MCP initialize handshake."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully shut down the connection."""
        ...

    @abstractmethod
    async def discover_tools(self) -> list[McpToolDescriptor]:
        """Return the list of tools exposed by the server."""
        ...

    @abstractmethod
    async def call_tool(self, invocation: McpToolInvocation) -> McpToolResult:
        """Invoke a single tool on the remote server."""
        ...

    @abstractmethod
    def status(self) -> McpServerStatus:
        """Current connection status."""
        ...
