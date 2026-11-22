"""Small local stdio MCP client for ahujasid/mcp-for-blender.

It launches one MCP subprocess on demand and never opens Blender's socket directly.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import AsyncExitStack
from typing import Any


class BlenderMCPError(RuntimeError):
    pass


class BlenderMCPClient:
    def __init__(self) -> None:
        self.command = os.getenv("BLENDER_MCP_COMMAND") or shutil.which("uvx") or "uvx"
        raw_args = os.getenv("BLENDER_MCP_ARGS", '["mcp-for-blender"]')
        try:
            self.args = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            raise BlenderMCPError("BLENDER_MCP_ARGS must be a JSON array, for example [\"mcp-for-blender\"].") from exc
        if not isinstance(self.args, list) or not all(isinstance(item, str) for item in self.args):
            raise BlenderMCPError("BLENDER_MCP_ARGS must be a JSON array of strings.")
        self.host = os.getenv("BLENDER_HOST", "localhost")
        self.port = os.getenv("BLENDER_PORT", "9876")
        self.timeout = float(os.getenv("BLENDER_MCP_TIMEOUT", "180"))
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> Any:
        if self._session is not None:
            return self._session
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise BlenderMCPError("MCP SDK is missing. Run the PoC setup script to install its requirements.") from exc

        # Pass only the ordinary Windows runtime variables required by uvx. Do not
        # leak unrelated environment variables or credentials into the MCP child.
        allowed_env = ("PATH", "SystemRoot", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "HOME")
        child_env = {key: os.environ[key] for key in allowed_env if key in os.environ}
        child_env.update({"BLENDER_HOST": self.host, "BLENDER_PORT": self.port})
        params = StdioServerParameters(command=self.command, args=self.args, env=child_env)
        stack = AsyncExitStack()
        try:
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await asyncio.wait_for(session.initialize(), timeout=30)
        except asyncio.CancelledError:
            # Cancellation (for example, Ctrl+C during MCP startup) must still
            # unwind the AnyIO context in this same task, then propagate.
            await stack.aclose()
            raise
        except Exception as exc:
            await stack.aclose()
            raise BlenderMCPError(
                f"Could not start/initialize the Blender MCP stdio server ({self.command}). "
                "Check that Blender's MCP add-on is enabled, its panel server is started, and the configured uvx path/package are valid. "
                f"Details: {exc}"
            ) from exc
        self._stack, self._session = stack, session
        return session

    @staticmethod
    def _text(result: Any) -> str:
        return "\n".join(str(getattr(item, "text", "")) for item in getattr(result, "content", []) if getattr(item, "text", None))

    async def _call(self, name: str, arguments: dict[str, Any]) -> str:
        session = await self._connect()
        try:
            result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=self.timeout)
        except Exception as exc:
            # Discard a potentially desynchronized MCP child; the next attempt starts fresh.
            await self.close()
            raise BlenderMCPError(f"MCP tool {name!r} failed: {exc}") from exc
        text = self._text(result)
        if getattr(result, "isError", False):
            raise BlenderMCPError(text or f"MCP tool {name!r} returned an error.")
        return text

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            try:
                await self._connect()
                return await self.status_unlocked()
            finally:
                # MCP stdio uses AnyIO task groups. Enter and exit them in the
                # same request task; never carry the stack across HTTP requests.
                await self.close()

    async def execute(self, code: str, user_prompt: str) -> str:
        async with self._lock:
            try:
                # Keep handshake and build within one request-scoped MCP session.
                await self._connect()
                await self.status_unlocked()
                result = await self._call("execute_blender_code", {"code": code, "user_prompt": user_prompt})
                if "Error executing code:" in result or result.startswith("Rejected by safe mode"):
                    raise BlenderMCPError(result)
                return result
            finally:
                await self.close()

    async def status_unlocked(self) -> dict[str, Any]:
        session = await self._connect()
        try:
            listed = await asyncio.wait_for(session.list_tools(), timeout=20)
        except Exception as exc:
            raise BlenderMCPError(f"Could not list tools from MCP for Blender: {exc}") from exc
        names = {tool.name for tool in listed.tools}
        if not {"get_addon_status", "execute_blender_code"}.issubset(names):
            raise BlenderMCPError("MCP tools are incomplete; expected get_addon_status and execute_blender_code.")
        text = await self._call("get_addon_status", {})
        if not text.strip():
            raise BlenderMCPError("MCP tool get_addon_status returned no status text; connection is not confirmed.")
        if "not connected to blender" in text.lower():
            raise BlenderMCPError("MCP for Blender started, but its add-on socket is not connected. Start the add-on server in Blender's sidebar.")
        return {"connected": True, "server": "mcp-for-blender", "tools": sorted(names), "addon_status": text}

    async def close(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:
                pass
