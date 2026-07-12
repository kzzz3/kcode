"""MCP server configuration models."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class McpTransportType(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server.

    Examples in YAML::

        mcp:
          servers:
            - name: filesystem
              transport: stdio
              command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
              env:
                FOO: bar
            - name: github
              transport: sse
              url: https://mcp.example.com/sse
              api_key: sk-...
    """

    name: str
    transport: McpTransportType = McpTransportType.STDIO
    enabled: bool = True
    timeout_seconds: float = 120.0

    # stdio transport
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    # SSE / HTTP transport
    url: str | None = None
    api_key: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    # Tool filtering
    include_tools: list[str] = Field(default_factory=list)
    exclude_tools: list[str] = Field(default_factory=list)

    # Safety overrides: tool_name -> safety_class
    safety_overrides: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    def should_include_tool(self, tool_name: str) -> bool:
        """Return True if the tool should be exposed given include/exclude lists."""
        if self.include_tools and tool_name not in self.include_tools:
            return False
        if tool_name in self.exclude_tools:
            return False
        return True


class McpConfig(BaseModel):
    """Top-level MCP configuration section."""

    servers: list[McpServerConfig] = Field(default_factory=list)
    auto_connect: bool = True
    discovery_timeout_seconds: float = 30.0
