"""
MCP Resource Tools — CC-aligned MCP resource discovery and reading.
CC: ListMcpResourcesTool + ReadMcpResourceTool
"""

from tools.base import BaseTool


class ListMcpResourcesTool(BaseTool):
    name = "ListMcpResources"
    description = (
        "List resources available from a connected MCP server. "
        "Returns resource URIs, names, and descriptions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Name of the MCP server to query",
            },
        },
        "required": ["server_name"],
    }
    is_read_only = True
    concurrency_safe = True

    _mcp_manager = None  # injected by tool_registry

    def execute(self, input_data: dict) -> str:
        server_name = input_data.get("server_name", "")
        if not self._mcp_manager:
            return "MCP manager not available."
        try:
            resources = self._mcp_manager.list_resources(server_name)
            if not resources:
                return f"No resources found on MCP server '{server_name}'."
            lines = [f"Resources on '{server_name}':"]
            for r in resources:
                uri = r.get("uri", "?")
                name = r.get("name", "")
                desc = r.get("description", "")
                lines.append(f"  {uri}")
                if name:
                    lines.append(f"    Name: {name}")
                if desc:
                    lines.append(f"    Desc: {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing resources: {e}"


class ReadMcpResourceTool(BaseTool):
    name = "ReadMcpResource"
    description = (
        "Read a specific resource from a connected MCP server by URI. "
        "Returns the resource content."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Name of the MCP server",
            },
            "uri": {
                "type": "string",
                "description": "Resource URI to read",
            },
        },
        "required": ["server_name", "uri"],
    }
    is_read_only = True
    concurrency_safe = True

    _mcp_manager = None  # injected by tool_registry

    def execute(self, input_data: dict) -> str:
        server_name = input_data.get("server_name", "")
        uri = input_data.get("uri", "")
        if not self._mcp_manager:
            return "MCP manager not available."
        if not uri:
            return "Error: uri is required."
        try:
            content = self._mcp_manager.read_resource(server_name, uri)
            if content is None:
                return f"Resource not found: {uri}"
            return str(content)
        except Exception as e:
            return f"Error reading resource: {e}"
