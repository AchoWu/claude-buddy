"""
TerminalCaptureTool — CC-aligned terminal output capture.
CC: feature-gated behind TERMINAL_PANEL.
Captures terminal/tmux output for the model to analyze.
"""

import platform
import subprocess
from tools.base import BaseTool


class TerminalCaptureTool(BaseTool):
    name = "TerminalCapture"
    description = (
        "Capture recent terminal output. Tries tmux capture-pane first, "
        "then falls back to platform-specific methods. "
        "Returns the last ~100 lines of terminal content."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "lines": {
                "type": "integer",
                "description": "Number of lines to capture (default: 100)",
            },
            "target": {
                "type": "string",
                "description": "tmux target pane (e.g., '0:0.0'). Default: auto-detect.",
            },
        },
        "required": [],
    }
    is_read_only = True
    concurrency_safe = True

    def execute(self, input_data: dict) -> str:
        lines = input_data.get("lines", 100)
        target = input_data.get("target", "")

        # Try tmux first (works on all platforms where tmux is available)
        try:
            cmd = ["tmux", "capture-pane", "-p", f"-S-{lines}"]
            if target:
                cmd.extend(["-t", target])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                return f"Terminal output (tmux, {len(output.splitlines())} lines):\n```\n{output}\n```"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Platform-specific fallbacks
        system = platform.system()
        if system == "Darwin":
            try:
                script = 'tell application "Terminal" to get contents of front window'
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    output = "\n".join(result.stdout.strip().splitlines()[-lines:])
                    return f"Terminal output (macOS Terminal, {len(output.splitlines())} lines):\n```\n{output}\n```"
            except Exception:
                pass

        elif system == "Windows":
            # On Windows, try reading recent command output from history
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-History | Select-Object -Last 20 | Format-Table -AutoSize"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    return f"Recent commands (PowerShell):\n```\n{result.stdout.strip()}\n```"
            except Exception:
                pass

        return (
            "Could not capture terminal output. "
            "Ensure tmux is running (recommended), or use Bash tool to run commands directly."
        )
