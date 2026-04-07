"""
Brief, PowerShell, TodoWrite, ToolSearch — four remaining tools.
"""

import os
import json
import platform
import subprocess
from pathlib import Path
from tools.base import BaseTool


class BriefTool(BaseTool):
    """Toggle brief/concise output mode."""
    name = "Brief"
    description = (
        "Toggle brief mode — when active, keep all responses extremely concise.\n\n"
        "In brief mode:\n"
        "- Responses should be 1-3 sentences max\n"
        "- Skip explanations, just give the result\n"
        "- No preambles, no summaries, no sign-offs\n\n"
        "Parameters:\n"
        "- enabled: true to enable brief mode, false to disable"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "true = enable brief mode, false = disable",
                "default": True,
            },
        },
    }
    is_read_only = True

    def __init__(self):
        self._engine = None

    def execute(self, input_data: dict) -> str:
        enabled = input_data.get("enabled", True)
        if self._engine:
            self._engine._fast_mode = enabled
        state = "ON" if enabled else "OFF"
        return f"Brief mode: {state}. {'Keep responses extremely concise.' if enabled else 'Normal response length restored.'}"


class PowerShellTool(BaseTool):
    """Execute PowerShell commands on Windows."""
    name = "PowerShell"
    description = (
        "Execute a PowerShell command (Windows only).\n\n"
        "Use for Windows-specific operations that need PowerShell syntax:\n"
        "- Get-ChildItem, Get-Content, Set-Content\n"
        "- .NET method calls\n"
        "- Windows registry access\n"
        "- COM object automation\n\n"
        "For simple commands that work in cmd.exe, use Bash instead.\n"
        "PowerShell is only available on Windows."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "PowerShell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 60)",
                "default": 60,
            },
        },
        "required": ["command"],
    }
    is_read_only = False
    is_destructive = True

    def execute(self, input_data: dict) -> str:
        if platform.system() != "Windows":
            return "Error: PowerShell is only available on Windows."

        command = input_data["command"]
        timeout = min(input_data.get("timeout", 60), 300)

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            parts = []
            if result.stdout:
                parts.append(result.stdout)
            if result.stderr:
                parts.append(f"STDERR:\n{result.stderr}")
            if result.returncode != 0:
                parts.append(f"Exit code: {result.returncode}")
            return "\n".join(parts) if parts else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: PowerShell command timed out after {timeout}s."
        except FileNotFoundError:
            return "Error: PowerShell not found."
        except Exception as e:
            return f"Error: {e}"


class TodoWriteTool(BaseTool):
    """Write/update a todo list file."""
    name = "TodoWrite"
    description = (
        "Write or update a todo list file.\n\n"
        "Creates or overwrites a structured TODO file (markdown format).\n"
        "Useful for tracking project tasks, action items, and checklists.\n\n"
        "Parameters:\n"
        "- file_path: Path to the todo file (default: ./TODO.md)\n"
        "- items: List of todo items, each with 'text' and optional 'done' (bool)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the todo file (default: ./TODO.md)",
                "default": "TODO.md",
            },
            "items": {
                "type": "array",
                "description": "List of todo items",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Todo item text"},
                        "done": {"type": "boolean", "description": "Is it completed?", "default": False},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": ["items"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        file_path = Path(input_data.get("file_path", "TODO.md"))
        items = input_data.get("items", [])
        if not items:
            return "Error: items list is empty."

        lines = ["# TODO\n"]
        for item in items:
            text = item.get("text", "")
            done = item.get("done", False)
            check = "[x]" if done else "[ ]"
            lines.append(f"- {check} {text}")

        content = "\n".join(lines) + "\n"
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            done_count = sum(1 for i in items if i.get("done", False))
            return f"Wrote {len(items)} items to {file_path} ({done_count} completed)"
        except Exception as e:
            return f"Error writing todo file: {e}"


class ToolSearchTool(BaseTool):
    """Search available tools by keyword."""
    name = "ToolSearch"
    description = (
        "Search available tools by keyword.\n\n"
        "Use when you're not sure which tool to use for a task.\n"
        "Returns matching tools with their descriptions.\n\n"
        "Parameters:\n"
        "- query: Search keyword (matches tool name and description)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword",
            },
        },
        "required": ["query"],
    }
    is_read_only = True

    def __init__(self):
        self._tool_registry = None

    def execute(self, input_data: dict) -> str:
        query = input_data.get("query", "").strip().lower()
        if not query:
            return "Error: query is required."

        if not self._tool_registry:
            return "Error: Tool registry not available."

        matches = []
        for tool in self._tool_registry.all_tools():
            name_match = query in tool.name.lower()
            desc_match = query in tool.description.lower()
            if name_match or desc_match:
                ro = " (read-only)" if tool.is_read_only else ""
                matches.append(f"  {tool.name}{ro}: {tool.description[:100]}")

        if not matches:
            return f"No tools matching '{query}'. Use /tools to see all available tools."
        return f"Tools matching '{query}' ({len(matches)}):\n" + "\n".join(matches)
