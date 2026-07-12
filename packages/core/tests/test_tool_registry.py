"""Unit tests for runtime tool registry."""
from packages.core.src.tools.contracts import Tool, ToolMeta, ToolOutput, ToolRegistry


def test_tool_registry_register_and_list():
    registry = ToolRegistry()
    registry.register(Tool(
        meta=ToolMeta(name="echo", description="echo tool", safety_class="read", parameter_schema={"type": "object"}),
        executor=lambda payload: ToolOutput(message=payload.get("text", "")),
    ))
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "echo"
