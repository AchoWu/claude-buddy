"""
MCP Manager — Model Context Protocol server connection manager.
Aligned with Claude Code's services/mcp/ patterns.

Provides:
  - MCP server connection management (stdio and SSE transports)
  - Tool discovery from MCP servers
  - Proxy tool execution (forward tool calls to MCP servers)
  - Resource listing
  - Prompt template listing

This is an extensible scaffold. The MCP protocol is JSON-RPC 2.0 based,
and full implementation requires the mcp SDK or a custom client.
"""

import json
import subprocess
import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict
    server_name: str  # which server provides this tool


@dataclass
class MCPResource:
    """A resource exposed by an MCP server."""
    uri: str
    name: str
    description: str = ""
    mime_type: str = ""
    server_name: str = ""


@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    command: list[str] | None = None       # stdio transport
    url: str | None = None                 # SSE transport
    env: dict[str, str] = field(default_factory=dict)
    status: str = "disconnected"           # disconnected, connecting, connected, error
    tools: list[MCPTool] = field(default_factory=list)
    resources: list[MCPResource] = field(default_factory=list)
    error: str = ""


class MCPManager:
    """
    Manages MCP server connections and proxies tool calls.
    """

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}

    def add_server(self, name: str, command: list[str] | None = None,
                   url: str | None = None, env: dict[str, str] | None = None):
        """Register an MCP server configuration."""
        self._servers[name] = MCPServer(
            name=name, command=command, url=url, env=env or {},
        )

    def load_config(self, config_path: str | Path):
        """
        Load MCP server configs from a JSON file.
        Expected format (same as Claude Code):
        {
          "mcpServers": {
            "server-name": {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-filesystem"],
              "env": {"KEY": "value"}
            }
          }
        }
        """
        try:
            path = Path(config_path)
            if not path.exists():
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcpServers", {})
            for name, config in servers.items():
                cmd = config.get("command")
                args = config.get("args", [])
                command = [cmd] + args if cmd else None
                self.add_server(
                    name=name,
                    command=command,
                    url=config.get("url"),
                    env=config.get("env", {}),
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def get_all_tools(self) -> list[MCPTool]:
        """Get all tools from all connected servers."""
        tools = []
        for server in self._servers.values():
            if server.status == "connected":
                tools.extend(server.tools)
        return tools

    def get_all_resources(self) -> list[MCPResource]:
        """Get all resources from all connected servers."""
        resources = []
        for server in self._servers.values():
            if server.status == "connected":
                resources.extend(server.resources)
        return resources

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Execute a tool call by proxying to the appropriate MCP server.
        Returns the tool result as a string.
        """
        # Find which server provides this tool
        for server in self._servers.values():
            for tool in server.tools:
                if tool.name == tool_name:
                    return self._execute_tool(server, tool_name, arguments)
        return f"Error: MCP tool '{tool_name}' not found in any connected server."

    def _execute_tool(self, server: MCPServer, tool_name: str, arguments: dict) -> str:
        """Execute a tool on a specific MCP server."""
        # Stub: in full implementation, this sends a JSON-RPC call
        # For now, return a descriptive message
        return (
            f"MCP tool '{tool_name}' on server '{server.name}' "
            f"called with arguments: {json.dumps(arguments, ensure_ascii=False)[:200]}\n"
            f"(MCP server execution not yet implemented — "
            f"install mcp SDK and connect servers to enable)"
        )

    def list_servers(self) -> list[dict]:
        """Get status of all configured servers."""
        return [
            {
                "name": s.name,
                "status": s.status,
                "tools": len(s.tools),
                "resources": len(s.resources),
                "transport": "stdio" if s.command else "sse" if s.url else "unknown",
                "error": s.error,
            }
            for s in self._servers.values()
        ]

    def shutdown(self):
        """Disconnect all servers."""
        for server in self._servers.values():
            server.status = "disconnected"
        self._servers.clear()
