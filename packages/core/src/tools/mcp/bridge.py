"""Bridge between MCP tool providers and the core ToolRegistry.

This module is transport-agnostic: it takes any ``McpToolProvider`` and
registers its tools into a ``ToolRegistry`` so the agent runtime can call
them like any built-in tool.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from packages.core.src.config.mcp import McpServerConfig
from packages.core.src.tools.contracts import Tool, ToolMeta, ToolOutput, ToolRegistry
from packages.core.src.tools.mcp.contracts import (
    McpToolDescriptor,
    McpToolInvocation,
    McpToolProvider,
    McpToolResult,
)

_LOGGER = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from sync context, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside an already-running loop (e.g. Jupyter). Use a new thread.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _descriptor_to_meta(descriptor: McpToolDescriptor, server_config: McpServerConfig) -> ToolMeta:
    """Convert an MCP tool descriptor to a ToolMeta."""
    safety = server_config.safety_overrides.get(descriptor.name, descriptor.safety_class)
    schema = descriptor.inputSchema.model_dump() if hasattr(descriptor.inputSchema, "model_dump") else dict(descriptor.inputSchema)
    return ToolMeta(
        name=f"mcp__{server_config.name}__{descriptor.name}",
        description=f"[MCP:{server_config.name}] {descriptor.description}".strip(),
        safety_class=safety,
        parameter_schema=schema,
        version="mcp-1.0",
    )


def _make_executor(provider: McpToolProvider, original_name: str, timeout: float) -> Any:
    """Create a sync executor callable that delegates to the async MCP provider."""

    def executor(payload: dict[str, Any]) -> ToolOutput:
        invocation = McpToolInvocation(
            tool_name=original_name,
            arguments=payload,
            timeout_seconds=timeout,
        )
        try:
            result: McpToolResult = _run_async(provider.call_tool(invocation))
        except Exception as exc:
            _LOGGER.error("MCP tool %s failed: %s", original_name, exc)
            return ToolOutput(ok=False, message=f"MCP error: {exc}")

        if result.isError or not result.ok:
            error_msg = result.error_message or result.text_content() or "Unknown MCP error"
            return ToolOutput(ok=False, message=error_msg, metadata=result.metadata)

        text = result.text_content()
        return ToolOutput(
            ok=True,
            message=text or "(no text content)",
            metadata=result.metadata,
        )

    return executor


def register_mcp_tools(
    registry: ToolRegistry,
    provider: McpToolProvider,
    server_config: McpServerConfig,
    descriptors: list[McpToolDescriptor],
) -> int:
    """Register MCP tools from a provider into the core ToolRegistry.

    Args:
        registry: The target tool registry.
        provider: The MCP provider that owns these tools.
        server_config: Server configuration for filtering and naming.
        descriptors: Tool descriptors discovered from the server.

    Returns:
        Number of tools actually registered (after filtering).
    """
    count = 0
    for desc in descriptors:
        if not server_config.should_include_tool(desc.name):
            _LOGGER.debug("Skipping MCP tool %s (filtered out)", desc.name)
            continue

        meta = _descriptor_to_meta(desc, server_config)
        executor = _make_executor(provider, desc.name, server_config.timeout_seconds)
        registry.register(Tool(meta=meta, executor=executor))
        count += 1
        _LOGGER.debug("Registered MCP tool: %s", meta.name)

    return count
