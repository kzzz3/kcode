"""Unit tests for MCP bridge (register_mcp_tools)."""
from __future__ import annotations

from unittest.mock import AsyncMock


from packages.core.src.config.mcp import McpServerConfig
from packages.core.src.tools.contracts import ToolOutput, ToolRegistry
from packages.core.src.tools.mcp.bridge import register_mcp_tools, _descriptor_to_meta
from packages.core.src.tools.mcp.contracts import (
    McpServerInfo,
    McpServerStatus,
    McpToolDescriptor,
    McpToolInvocation,
    McpToolProvider,
    McpToolResult,
)


class MockMcpProvider(McpToolProvider):
    """Mock MCP provider for testing."""

    def __init__(self) -> None:
        self._status = McpServerStatus.DISCONNECTED
        self._call_tool_mock = AsyncMock()

    async def connect(self) -> McpServerInfo:
        self._status = McpServerStatus.READY
        return McpServerInfo(name="mock", version="1.0.0")

    async def disconnect(self) -> None:
        self._status = McpServerStatus.DISCONNECTED

    async def discover_tools(self) -> list[McpToolDescriptor]:
        return []

    async def call_tool(self, invocation: McpToolInvocation) -> McpToolResult:
        return await self._call_tool_mock(invocation)

    def status(self) -> McpServerStatus:
        return self._status


class TestDescriptorToMeta:
    """Tests for _descriptor_to_meta()."""

    def test_naming_convention(self) -> None:
        """MCP tools use mcp__{server}__{tool} naming."""
        desc = McpToolDescriptor(name="read_file", description="Read a file")
        config = McpServerConfig(name="filesystem")
        meta = _descriptor_to_meta(desc, config)
        assert meta.name == "mcp__filesystem__read_file"

    def test_description_prefix(self) -> None:
        """Description includes server name prefix."""
        desc = McpToolDescriptor(name="tool", description="Does something")
        config = McpServerConfig(name="mysrv")
        meta = _descriptor_to_meta(desc, config)
        assert meta.description == "[MCP:mysrv] Does something"

    def test_safety_override(self) -> None:
        """Server config safety overrides take precedence."""
        desc = McpToolDescriptor(name="write_file")
        config = McpServerConfig(
            name="test",
            safety_overrides={"write_file": "system"},
        )
        meta = _descriptor_to_meta(desc, config)
        assert meta.safety_class == "system"


class TestRegisterMcpTools:
    """Tests for register_mcp_tools()."""

    def test_registers_all_tools(self) -> None:
        """All non-filtered tools are registered."""
        registry = ToolRegistry()
        provider = MockMcpProvider()
        config = McpServerConfig(name="test")
        descriptors = [
            McpToolDescriptor(name="tool_a"),
            McpToolDescriptor(name="tool_b"),
        ]
        count = register_mcp_tools(registry, provider, config, descriptors)
        assert count == 2
        assert registry.get("mcp__test__tool_a") is not None
        assert registry.get("mcp__test__tool_b") is not None

    def test_filters_excluded_tools(self) -> None:
        """Excluded tools are not registered."""
        registry = ToolRegistry()
        provider = MockMcpProvider()
        config = McpServerConfig(name="test", exclude_tools=["tool_b"])
        descriptors = [
            McpToolDescriptor(name="tool_a"),
            McpToolDescriptor(name="tool_b"),
        ]
        count = register_mcp_tools(registry, provider, config, descriptors)
        assert count == 1
        assert registry.get("mcp__test__tool_a") is not None
        assert registry.get("mcp__test__tool_b") is None

    def test_executor_returns_tool_output(self) -> None:
        """Registered executor returns ToolOutput on success."""
        registry = ToolRegistry()
        provider = MockMcpProvider()
        provider._call_tool_mock.return_value = McpToolResult(
            ok=True,
            content=[{"type": "text", "text": "result"}],
        )
        config = McpServerConfig(name="test")
        descriptors = [McpToolDescriptor(name="my_tool")]
        register_mcp_tools(registry, provider, config, descriptors)

        tool = registry.get("mcp__test__my_tool")
        assert tool is not None
        output = tool.run({"arg": "value"})
        assert isinstance(output, ToolOutput)
        assert output.ok is True
        assert output.message == "result"

    def test_executor_handles_error(self) -> None:
        """Registered executor returns ToolOutput(ok=False) on MCP error."""
        registry = ToolRegistry()
        provider = MockMcpProvider()
        provider._call_tool_mock.return_value = McpToolResult(
            ok=False,
            isError=True,
            error_message="tool failed",
        )
        config = McpServerConfig(name="test")
        descriptors = [McpToolDescriptor(name="my_tool")]
        register_mcp_tools(registry, provider, config, descriptors)

        tool = registry.get("mcp__test__my_tool")
        assert tool is not None
        output = tool.run({})
        assert output.ok is False
        assert "tool failed" in output.message
