from __future__ import annotations

from packages.core.src.tools.contracts import ToolRegistry
from apps.cli.src.tools.builtin_core import register_core_tools
from apps.cli.src.tools.builtin_readonly import register_readonly_tools


def test_registered_tool_schemas_are_valid_json_schema() -> None:
    registry = ToolRegistry()
    register_readonly_tools(registry)
    register_core_tools(registry)

    tools = registry.list_tools()
    assert len(tools) >= 7

    for meta in tools:
        schema = meta.parameter_schema
        assert isinstance(schema, dict), meta.name
        assert schema.get("type") == "object", meta.name
        assert isinstance(schema.get("properties"), dict), meta.name
        assert isinstance(schema.get("required"), list), meta.name
        for prop_name, prop_schema in schema["properties"].items():
            assert "type" in prop_schema, f"{meta.name}.{prop_name}"


def test_safety_classes_match_expectations() -> None:
    registry = ToolRegistry()
    register_readonly_tools(registry)
    register_core_tools(registry)

    by_name = {meta.name: meta for meta in registry.list_tools()}

    assert by_name["read_file"].safety_class == "read"
    assert by_name["list_files"].safety_class == "read"
    assert by_name["search_code"].safety_class == "read"
    assert by_name["git_status"].safety_class == "read"
    assert by_name["git_diff"].safety_class == "read"
    assert by_name["create_file"].safety_class == "write"
    assert by_name["edit_file"].safety_class == "write"
    assert by_name["git_commit"].safety_class == "write"
    assert by_name["run_command"].safety_class == "system"
