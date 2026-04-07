"""
Sleep Tool + REPL Tool — utility tools.
Aligned with Claude Code's SleepTool and REPLTool.
"""

import time
import subprocess
import platform
from tools.base import BaseTool


class SleepTool(BaseTool):
    name = "Sleep"
    description = (
        "Wait for a specified duration before continuing.\n\n"
        "Use sparingly — only when you need to wait for an external process\n"
        "(e.g., a deploy, a CI job, a server to start).\n\n"
        "Do NOT use sleep between tool calls that can run immediately.\n"
        "Do NOT use sleep in a polling loop — use TaskOutput with block=true instead.\n\n"
        "Parameters:\n"
        "- seconds: Duration to sleep (1-300, default: 5)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "integer",
                "description": "Duration to sleep in seconds (1-300)",
                "default": 5,
            },
        },
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        seconds = max(1, min(input_data.get("seconds", 5), 300))
        time.sleep(seconds)
        return f"Slept for {seconds} seconds."


class REPLTool(BaseTool):
    name = "REPL"
    description = (
        "Run code in an interactive REPL (Python or Node.js).\n\n"
        "Executes the given code snippet and returns the output.\n"
        "Useful for quick calculations, testing expressions, or\n"
        "running small scripts that don't need file persistence.\n\n"
        "Parameters:\n"
        "- code: The code to execute\n"
        "- language: 'python' (default) or 'node'"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Code to execute in the REPL",
            },
            "language": {
                "type": "string",
                "enum": ["python", "node"],
                "description": "Language: python (default) or node",
                "default": "python",
            },
        },
        "required": ["code"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        code = input_data.get("code", "").strip()
        language = input_data.get("language", "python")

        if not code:
            return "Error: code must not be empty."

        if language == "python":
            return self._run_python(code)
        elif language == "node":
            return self._run_node(code)
        return f"Error: unsupported language '{language}'."

    def _run_python(self, code: str) -> str:
        try:
            is_win = platform.system() == "Windows"
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
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
            return "Error: Python execution timed out (30s)."
        except Exception as e:
            return f"Error: {e}"

    def _run_node(self, code: str) -> str:
        try:
            is_win = platform.system() == "Windows"
            result = subprocess.run(
                ["node", "-e", code],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
            )
            parts = []
            if result.stdout:
                parts.append(result.stdout)
            if result.stderr:
                parts.append(f"STDERR:\n{result.stderr}")
            if result.returncode != 0:
                parts.append(f"Exit code: {result.returncode}")
            return "\n".join(parts) if parts else "(no output)"
        except FileNotFoundError:
            return "Error: Node.js not found. Install Node.js to use this language."
        except subprocess.TimeoutExpired:
            return "Error: Node execution timed out (30s)."
        except Exception as e:
            return f"Error: {e}"
