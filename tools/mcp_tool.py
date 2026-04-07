"""
MCP Tool — proxy tool calls to MCP (Model Context Protocol) servers.
Aligned with Claude Code's MCPTool.
"""

from tools.base import BaseTool


class MCPTool(BaseTool):
    name = "MCPCall"
    description = (
        "Execute a tool provided by an MCP (Model Context Protocol) server.\n\n"
        "MCP servers expose additional tools beyond the built-in set.\n"
        "Use this to call tools discovered from connected MCP servers.\n\n"
        "Parameters:\n"
        "- server_name: Name of the MCP server to call\n"
        "- tool_name: Name of the tool on that server\n"
        "- arguments: Arguments to pass to the tool (JSON object)\n\n"
        "Use CronList or /plugins to see available MCP servers and their tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Name of the MCP server",
            },
            "tool_name": {
                "type": "string",
                "description": "Name of the tool on the server",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments to pass to the tool",
                "default": {},
            },
        },
        "required": ["server_name", "tool_name"],
    }
    is_read_only = False

    def __init__(self):
        self._mcp_manager = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        server_name = input_data.get("server_name", "").strip()
        tool_name = input_data.get("tool_name", "").strip()
        arguments = input_data.get("arguments", {})

        if not server_name:
            return "Error: server_name is required."
        if not tool_name:
            return "Error: tool_name is required."

        if not self._mcp_manager:
            return (
                "Error: MCP manager not available. "
                "No MCP servers are configured. "
                "Add servers to ~/.claude-buddy/mcp.json to enable."
            )

        # Check if server exists
        servers = self._mcp_manager.list_servers()
        server_names = [s["name"] for s in servers]
        if server_name not in server_names:
            return (
                f"Error: MCP server '{server_name}' not found. "
                f"Available servers: {', '.join(server_names) or '(none)'}"
            )

        return self._mcp_manager.call_tool(tool_name, arguments)
