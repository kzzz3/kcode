"""MCP stdio transport adapter.

Connects to an MCP server running as a local subprocess, communicating
via JSON-RPC 2.0 over stdin/stdout.

This is the most common MCP transport — used by ``npx @modelcontextprotocol/server-*``
packages and similar local tool servers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from packages.core.src.config.mcp import McpServerConfig
from packages.core.src.tools.mcp.contracts import (
    McpServerInfo,
    McpServerStatus,
    McpToolDescriptor,
    McpToolInvocation,
    McpToolProvider,
    McpToolResult,
    McpToolParamSchema,
)

_LOGGER = logging.getLogger(__name__)

_JSONRPC_VERSION = "2.0"
_INIT_TIMEOUT = 30.0
_DEFAULT_TOOL_TIMEOUT = 120.0


class McpStdioProvider(McpToolProvider):
    """MCP provider that communicates with a local process over stdio.

    Lifecycle:
        provider = McpStdioProvider(config)
        info = await provider.connect()
        tools = await provider.discover_tools()
        result = await provider.call_tool(invocation)
        await provider.disconnect()
    """

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._status = McpServerStatus.DISCONNECTED
        self._server_info: McpServerInfo | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._tools_cache: list[McpToolDescriptor] | None = None

    def status(self) -> McpServerStatus:
        return self._status

    async def connect(self) -> McpServerInfo:
        """Spawn the subprocess and perform the MCP initialize handshake."""
        self._status = McpServerStatus.CONNECTING

        command = self._config.command
        if not command:
            raise ValueError("MCP stdio server requires a non-empty 'command'.")

        # Build environment: merge current env + config env overrides
        env = {**os.environ, **self._config.env}

        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.cwd,
                env=env,
            )
        except Exception as exc:
            self._status = McpServerStatus.ERROR
            raise RuntimeError(f"Failed to start MCP server process: {exc}") from exc

        # Start background reader
        self._reader_task = asyncio.create_task(self._read_loop())

        # MCP initialize handshake
        try:
            result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "kcode", "version": "0.1.0"},
                },
                timeout=_INIT_TIMEOUT,
            )
            self._server_info = McpServerInfo(
                name=result.get("serverInfo", {}).get("name", "unknown"),
                version=result.get("serverInfo", {}).get("version", ""),
                protocol_version=result.get("protocolVersion", ""),
                capabilities=result.get("capabilities", {}),
            )
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            self._status = McpServerStatus.READY
            _LOGGER.info("MCP server connected: %s %s", self._server_info.name, self._server_info.version)
            return self._server_info
        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Shut down the subprocess and cancel pending requests."""
        self._status = McpServerStatus.DISCONNECTED
        self._tools_cache = None

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Cancel pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        # Terminate process
        if self._process:
            try:
                self._process.stdin.close()  # type: ignore[union-attr]
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            self._process = None

    async def discover_tools(self) -> list[McpToolDescriptor]:
        """List tools exposed by the MCP server."""
        if self._status != McpServerStatus.READY:
            raise RuntimeError(f"Cannot discover tools: server status is {self._status.value}")

        result = await self._send_request("tools/list", {})
        raw_tools = result.get("tools", [])
        self._tools_cache = [
            McpToolDescriptor(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=McpToolParamSchema(**t.get("inputSchema", {"type": "object"})),
                annotations=t.get("annotations", {}),
            )
            for t in raw_tools
        ]
        return list(self._tools_cache)

    async def call_tool(self, invocation: McpToolInvocation) -> McpToolResult:
        """Invoke a tool on the MCP server."""
        if self._status != McpServerStatus.READY:
            return McpToolResult(ok=False, isError=True, error_message=f"Server not ready: {self._status.value}")

        try:
            result = await self._send_request(
                "tools/call",
                {"name": invocation.tool_name, "arguments": invocation.arguments},
                timeout=invocation.timeout_seconds,
            )
            return McpToolResult(
                ok=not result.get("isError", False),
                content=result.get("content", []),
                isError=result.get("isError", False),
            )
        except Exception as exc:
            return McpToolResult(ok=False, isError=True, error_message=str(exc))

    # -- Internal JSON-RPC methods ------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(
        self, method: str, params: dict[str, Any], timeout: float = _DEFAULT_TOOL_TIMEOUT,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response."""
        req_id = self._next_id()
        message = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        await self._write_message(message)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' (id={req_id}) timed out after {timeout}s")

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": _JSONRPC_VERSION,
            "method": method,
            "params": params,
        }
        await self._write_message(message)

    async def _write_message(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the server's stdin."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP server process not running.")

        payload = json.dumps(message) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Background task: read JSON-RPC messages from stdout."""
        assert self._process and self._process.stdout
        buffer = ""
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        _LOGGER.warning("Ignoring non-JSON line from MCP server: %s", line[:200])
                        continue
                    self._handle_message(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _LOGGER.error("MCP read loop error: %s", exc)
        finally:
            _LOGGER.debug("MCP read loop exited.")

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Route an incoming JSON-RPC message to the right handler."""
        # Response to a pending request
        if "id" in msg and "method" not in msg:
            req_id = msg["id"]
            future = self._pending.pop(req_id, None)
            if future and not future.done():
                if "error" in msg:
                    error = msg["error"]
                    future.set_exception(
                        RuntimeError(f"MCP error {error.get('code')}: {error.get('message')}")
                    )
                else:
                    future.set_result(msg.get("result", {}))
            return

        # Server-initiated notification
        if "method" in msg and "id" not in msg:
            _LOGGER.debug("MCP notification: %s", msg["method"])
            return

        _LOGGER.debug("Ignoring unhandled MCP message: %s", str(msg)[:200])
