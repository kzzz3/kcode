"""Tests for packages/core/src/tools/mcp/stdio_provider.py.

Mocks internal methods to test connect, discover_tools, call_tool,
disconnect, and _handle_message without subprocess timing issues.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.core.src.config.mcp import McpServerConfig
from packages.core.src.tools.mcp.contracts import (
    McpServerStatus,
    McpToolInvocation,
)
from packages.core.src.tools.mcp.stdio_provider import McpStdioProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides: Any) -> McpServerConfig:
    defaults: dict[str, Any] = dict(
        name="test-server",
        command=["echo", "server"],
        args=[],
        env={},
        cwd=None,
        include_tools=[],
        exclude_tools=[],
    )
    defaults.update(overrides)
    return McpServerConfig(**defaults)


def _mock_process() -> MagicMock:
    proc = MagicMock()
    proc.stdin = AsyncMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.stdin.close = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provider() -> McpStdioProvider:
    return McpStdioProvider(_make_config())


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def test_initial_status_disconnected(provider: McpStdioProvider) -> None:
    assert provider.status() == McpServerStatus.DISCONNECTED


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

def test_connect_sets_ready_status_and_returns_info() -> None:
    """connect() performs initialize handshake, sets READY, returns McpServerInfo."""
    init_result = {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "test-server", "version": "1.0"},
        "capabilities": {"tools": {}},
    }
    proc = _mock_process()

    async def _run():
        provider = McpStdioProvider(_make_config())
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):

            async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
                if method == "initialize":
                    return init_result
                raise AssertionError(f"Unexpected method: {method}")

            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                info = await provider.connect()
            await provider.disconnect()
            return info

    info = asyncio.run(_run())
    assert info.name == "test-server"
    assert info.version == "1.0"
    assert info.protocol_version == "2024-11-05"


def test_connect_empty_command_raises() -> None:
    provider = McpStdioProvider(_make_config(command=[]))
    with pytest.raises(ValueError, match="non-empty"):
        asyncio.run(provider.connect())


def test_connect_subprocess_failure_sets_error_status() -> None:
    async def _run():
        provider = McpStdioProvider(_make_config())
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=OSError("not found")):
            await provider.connect()

    with pytest.raises(RuntimeError, match="Failed to start"):
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# discover_tools
# ---------------------------------------------------------------------------

def test_discover_tools_returns_descriptors() -> None:
    tools_result = {
        "tools": [
            {
                "name": "search",
                "description": "Search files",
                "inputSchema": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            },
            {
                "name": "run_cmd",
                "description": "Run command",
                "inputSchema": {"type": "object"},
            },
        ]
    }

    async def _run():
        provider = McpStdioProvider(_make_config())
        proc = _mock_process()

        async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
            if method == "initialize":
                return {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "s", "version": "1"},
                    "capabilities": {},
                }
            if method == "tools/list":
                return tools_result
            raise AssertionError(f"Unexpected method: {method}")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                await provider.connect()
            descriptors = await provider.discover_tools()
            await provider.disconnect()
            return descriptors

    descriptors = asyncio.run(_run())
    assert len(descriptors) == 2
    assert descriptors[0].name == "search"
    assert descriptors[1].name == "run_cmd"


def test_discover_tools_empty_list() -> None:
    async def _run():
        provider = McpStdioProvider(_make_config())
        proc = _mock_process()

        async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
            if method == "initialize":
                return {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "s", "version": "1"},
                    "capabilities": {},
                }
            if method == "tools/list":
                return {"tools": []}
            raise AssertionError(f"Unexpected method: {method}")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                await provider.connect()
            descriptors = await provider.discover_tools()
            await provider.disconnect()
            return descriptors

    descriptors = asyncio.run(_run())
    assert len(descriptors) == 0


# ---------------------------------------------------------------------------
# call_tool
# ---------------------------------------------------------------------------

def test_call_tool_returns_result() -> None:
    async def _run():
        provider = McpStdioProvider(_make_config())
        proc = _mock_process()

        async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
            if method == "initialize":
                return {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "s", "version": "1"},
                    "capabilities": {},
                }
            if method == "tools/call":
                return {"content": [{"type": "text", "text": "result"}], "isError": False}
            raise AssertionError(f"Unexpected method: {method}")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                await provider.connect()
            result = await provider.call_tool(McpToolInvocation(tool_name="search", arguments={"q": "test"}))
            await provider.disconnect()
            return result

    result = asyncio.run(_run())
    assert result.ok is True
    assert result.isError is False
    assert result.text_content() == "result"


def test_call_tool_server_not_ready() -> None:
    """call_tool when DISCONNECTED returns error result."""
    provider = McpStdioProvider(_make_config())
    result = asyncio.run(provider.call_tool(McpToolInvocation(tool_name="x")))
    assert result.ok is False
    assert "not ready" in result.error_message.lower()


def test_call_tool_rpc_error_returns_error_result() -> None:
    async def _run():
        provider = McpStdioProvider(_make_config())
        proc = _mock_process()

        async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
            if method == "initialize":
                return {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "s", "version": "1"},
                    "capabilities": {},
                }
            if method == "tools/call":
                raise RuntimeError("MCP error -32600: Invalid request")
            raise AssertionError(f"Unexpected method: {method}")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                await provider.connect()
            result = await provider.call_tool(McpToolInvocation(tool_name="bad"))
            await provider.disconnect()
            return result

    result = asyncio.run(_run())
    assert result.ok is False
    assert result.isError is True
    assert "Invalid request" in result.error_message


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_disconnect_terminates_process() -> None:
    proc = _mock_process()

    async def _run():
        provider = McpStdioProvider(_make_config())

        async def fake_send_request(method: str, params: dict, timeout: float = 30) -> dict:
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "s", "version": "1"},
                "capabilities": {},
            }

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=proc):
            provider._send_request = fake_send_request  # type: ignore[assignment]
            provider._send_notification = AsyncMock()  # type: ignore[assignment]
            with patch.object(asyncio, "create_task"):
                await provider.connect()
            assert provider.status() == McpServerStatus.READY
            await provider.disconnect()
            return provider.status()

    status = asyncio.run(_run())
    assert status == McpServerStatus.DISCONNECTED
    proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_message edge cases
# ---------------------------------------------------------------------------

def test_handle_message_resolves_pending_future() -> None:
    """Response with matching id resolves the pending future."""
    provider = McpStdioProvider(_make_config())
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    provider._pending[42] = future

    provider._handle_message({"jsonrpc": "2.0", "id": 42, "result": {"key": "val"}})

    assert future.done()
    assert future.result() == {"key": "val"}
    loop.close()


def test_handle_message_sets_exception_on_error() -> None:
    """Error response sets RuntimeError on the pending future."""
    provider = McpStdioProvider(_make_config())
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    provider._pending[99] = future

    provider._handle_message({
        "jsonrpc": "2.0", "id": 99,
        "error": {"code": -32600, "message": "Bad request"},
    })

    assert future.done()
    with pytest.raises(RuntimeError, match="Bad request"):
        future.result()
    loop.close()


def test_handle_message_ignores_notification(provider: McpStdioProvider) -> None:
    """Server-initiated notification is logged but ignored."""
    provider._handle_message({"jsonrpc": "2.0", "method": "notifications/test", "params": {}})


def test_handle_message_ignores_unknown(provider: McpStdioProvider) -> None:
    """Message with neither id nor method is logged and ignored."""
    provider._handle_message({"jsonrpc": "2.0"})


def test_handle_message_ignores_response_without_pending(provider: McpStdioProvider) -> None:
    """Response with no matching pending future is silently ignored."""
    provider._handle_message({"jsonrpc": "2.0", "id": 999, "result": {}})