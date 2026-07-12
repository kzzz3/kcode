"""Unit tests for MCP tool contracts."""
from __future__ import annotations

from packages.core.src.tools.mcp.contracts import (
    McpToolDescriptor,
    McpToolResult,
)
from packages.core.src.config.mcp import McpServerConfig


class TestMcpToolDescriptor:
    """Tests for McpToolDescriptor.safety_class heuristic."""

    def test_safety_class_from_annotation(self) -> None:
        """Explicit annotation takes precedence."""
        desc = McpToolDescriptor(
            name="my_tool",
            annotations={"x-kcode-safety-class": "write"},
        )
        assert desc.safety_class == "write"

    def test_safety_class_heuristic_write(self) -> None:
        """Name containing 'write' → write."""
        desc = McpToolDescriptor(name="write_file")
        assert desc.safety_class == "write"

    def test_safety_class_heuristic_system(self) -> None:
        """Name containing 'exec' → system."""
        desc = McpToolDescriptor(name="exec_command")
        assert desc.safety_class == "system"

    def test_safety_class_heuristic_network(self) -> None:
        """Name containing 'fetch' → network."""
        desc = McpToolDescriptor(name="fetch_url")
        assert desc.safety_class == "network"

    def test_safety_class_default_read(self) -> None:
        """No signal → read."""
        desc = McpToolDescriptor(name="list_items")
        assert desc.safety_class == "read"

    def test_safety_class_invalid_annotation_ignored(self) -> None:
        """Invalid annotation value falls through to heuristic."""
        desc = McpToolDescriptor(
            name="write_data",
            annotations={"x-kcode-safety-class": "invalid"},
        )
        assert desc.safety_class == "write"


class TestMcpToolResult:
    """Tests for McpToolResult.text_content()."""

    def test_text_content_single_block(self) -> None:
        result = McpToolResult(
            content=[{"type": "text", "text": "hello"}],
        )
        assert result.text_content() == "hello"

    def test_text_content_multiple_blocks(self) -> None:
        result = McpToolResult(
            content=[
                {"type": "text", "text": "line1"},
                {"type": "text", "text": "line2"},
            ],
        )
        assert result.text_content() == "line1\nline2"

    def test_text_content_non_text_ignored(self) -> None:
        result = McpToolResult(
            content=[
                {"type": "image", "data": "base64..."},
                {"type": "text", "text": "only this"},
            ],
        )
        assert result.text_content() == "only this"

    def test_text_content_empty(self) -> None:
        result = McpToolResult(content=[])
        assert result.text_content() == ""


class TestMcpServerConfig:
    """Tests for McpServerConfig.should_include_tool()."""

    def test_include_all_by_default(self) -> None:
        config = McpServerConfig(name="test")
        assert config.should_include_tool("any_tool") is True

    def test_include_list_restricts(self) -> None:
        config = McpServerConfig(
            name="test",
            include_tools=["allowed_tool"],
        )
        assert config.should_include_tool("allowed_tool") is True
        assert config.should_include_tool("other_tool") is False

    def test_exclude_list_blocks(self) -> None:
        config = McpServerConfig(
            name="test",
            exclude_tools=["blocked_tool"],
        )
        assert config.should_include_tool("blocked_tool") is False
        assert config.should_include_tool("other_tool") is True

    def test_include_and_exclude_combined(self) -> None:
        config = McpServerConfig(
            name="test",
            include_tools=["tool_a", "tool_b"],
            exclude_tools=["tool_b"],
        )
        assert config.should_include_tool("tool_a") is True
        assert config.should_include_tool("tool_b") is False
        assert config.should_include_tool("tool_c") is False
