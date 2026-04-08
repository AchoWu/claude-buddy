"""
Bash Tool v2 — execute shell commands with CWD tracking, safety, background support.
Aligned with Claude Code's BashTool: description field, background execution,
progress tracking, enhanced safety patterns.
"""

import subprocess
import os
import platform
import time
import threading
from typing import Any

from tools.base import BaseTool

# Commands considered dangerous
DANGEROUS_PATTERNS = frozenset([
    "rm -rf", "rm -r /", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777", "> /dev/sda", "shutdown", "reboot",
    "format c:", "del /s /q", "rd /s /q",
])

# Git destructive operations that need confirmation
GIT_DANGEROUS = frozenset([
    "push --force", "push -f", "reset --hard",
    "checkout .", "restore .", "clean -f", "branch -D",
    "branch -d", "--no-verify", "--no-gpg-sign",
])


class BashTool(BaseTool):
    name = "Bash"
    description = (
        "Execute a shell command and return stdout/stderr.\n\n"
        "CORRECT uses of Bash:\n"
        "- Run programs: python script.py, node app.js\n"
        "- Git commands: git status, git commit, git log\n"
        "- Package managers: pip install, npm install\n"
        "- Build tools: make, cargo, go build\n"
        "- System info: whoami, hostname\n\n"
        "NEVER use Bash for these — use dedicated tools instead:\n"
        "1. NEVER use cat/head/tail/type to read files -> use FileRead\n"
        "2. NEVER use find/ls/dir to search files -> use Glob\n"
        "3. NEVER use grep/rg/findstr to search content -> use Grep\n"
        "4. NEVER use sed/awk/echo to edit files -> use FileEdit or FileWrite\n\n"
        "Options:\n"
        "- description: short description of what the command does (for UI display)\n"
        "- timeout: max seconds (default 120, max 600)\n"
        "- run_in_background: if true, returns immediately with a task_id\n\n"
        "REMINDER: Bash is ONLY for running programs and commands. "
        "For ALL file operations, use FileRead/FileWrite/FileEdit/Glob/Grep."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "description": {
                "type": "string",
                "description": "Short description of what this command does (for display)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120, max 600)",
                "default": 120,
            },
            "run_in_background": {
                "type": "boolean",
                "description": "If true, run in background and return task_id immediately",
                "default": False,
            },
        },
        "required": ["command"],
    }
    is_read_only = False
    is_destructive = True

    def __init__(self):
        self._cwd = os.getcwd()
        self._background_tasks: dict[str, dict] = {}
        self._next_bg_id = 1

    @property
    def cwd(self) -> str:
        return self._cwd

    def execute(self, input_data: dict) -> str:
        command = input_data["command"]
        timeout = min(input_data.get("timeout", 120), 600)
        run_bg = input_data.get("run_in_background", False)

        # Safety check: dangerous patterns
        cmd_lower = command.lower().strip()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                return (
                    f"Potentially dangerous command detected: '{pattern}'. "
                    f"If you're sure, ask the user for explicit confirmation."
                )

        # Git safety check
        if "git " in cmd_lower:
            for git_pat in GIT_DANGEROUS:
                if git_pat in cmd_lower:
                    # Special case: push --force to main/master
                    if "push" in git_pat and ("main" in cmd_lower or "master" in cmd_lower):
                        return (
                            "BLOCKED: Force-push to main/master is extremely dangerous. "
                            "This can destroy the team's work. Use a feature branch instead."
                        )
                    return (
                        f"Git safety warning: '{git_pat}' detected. "
                        f"This is a destructive operation. Confirm with the user first."
                    )

        # Background execution
        if run_bg:
            return self._run_background(command, timeout)

        # Normal execution
        return self._run_foreground(command, timeout)

    def _run_foreground(self, command: str, timeout: int) -> str:
        """Execute command and wait for result."""
        start_time = time.time()
        try:
            is_windows = platform.system() == "Windows"
            if is_windows:
                result = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, encoding="utf-8", errors="replace",
                    timeout=timeout, cwd=self._cwd,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8",
                         "PYTHONUTF8": "1"},
                )
            else:
                result = subprocess.run(
                    ["/bin/bash", "-c", command], capture_output=True,
                    text=True, encoding="utf-8", errors="replace",
                    timeout=timeout, cwd=self._cwd,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )

            elapsed = time.time() - start_time
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"Exit code: {result.returncode}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            # Add timing for long commands (>2s)
            if elapsed > 2.0:
                output += f"\n(completed in {elapsed:.1f}s)"

            self._update_cwd(command)
            return output

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s. Try run_in_background=true for long-running commands."
        except FileNotFoundError:
            return "Error: Command not found. Check if the program is installed."
        except PermissionError:
            return "Error: Permission denied. Do NOT use sudo without asking the user."
        except Exception as e:
            return f"Error: {e}"

    def _run_background(self, command: str, timeout: int) -> str:
        """Start command in background thread and return task_id."""
        task_id = f"bg_{self._next_bg_id}"
        self._next_bg_id += 1

        record: dict[str, Any] = {
            "command": command,
            "status": "running",
            "output": None,
            "start_time": time.time(),
        }
        self._background_tasks[task_id] = record

        def _bg_run():
            try:
                is_windows = platform.system() == "Windows"
                if is_windows:
                    result = subprocess.run(
                        command, shell=True, capture_output=True,
                        text=True, encoding="utf-8", errors="replace",
                        timeout=timeout, cwd=self._cwd,
                        env={**os.environ, "PYTHONIOENCODING": "utf-8",
                             "PYTHONUTF8": "1"},
                    )
                else:
                    result = subprocess.run(
                        ["/bin/bash", "-c", command], capture_output=True,
                        text=True, encoding="utf-8", errors="replace",
                        timeout=timeout, cwd=self._cwd,
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    )
                parts = []
                if result.stdout:
                    parts.append(result.stdout)
                if result.stderr:
                    parts.append(f"STDERR:\n{result.stderr}")
                if result.returncode != 0:
                    parts.append(f"Exit code: {result.returncode}")
                record["output"] = "\n".join(parts) if parts else "(no output)"
                record["status"] = "completed"
            except subprocess.TimeoutExpired:
                record["output"] = f"Error: timed out after {timeout}s"
                record["status"] = "error"
            except Exception as e:
                record["output"] = f"Error: {e}"
                record["status"] = "error"
            record["end_time"] = time.time()

        t = threading.Thread(target=_bg_run, daemon=True)
        t.start()

        return (
            f"Background task started: {task_id}\n"
            f"Command: {command}\n"
            f"Use Bash with 'echo $({task_id})' or check later for results."
        )

    def get_background_task(self, task_id: str) -> dict | None:
        """Get status of a background task."""
        return self._background_tasks.get(task_id)

    def _update_cwd(self, command: str):
        """Track directory changes."""
        if "cd " not in command and "pushd" not in command and "popd" not in command:
            return
        try:
            is_windows = platform.system() == "Windows"
            pwd_cmd = "cd" if is_windows else "pwd"
            chained = f"{command} && {pwd_cmd}"
            if is_windows:
                result = subprocess.run(
                    chained, shell=True, capture_output=True,
                    text=True, timeout=5, cwd=self._cwd,
                )
            else:
                result = subprocess.run(
                    ["/bin/bash", "-c", chained], capture_output=True,
                    text=True, timeout=5, cwd=self._cwd,
                )
            if result.returncode == 0 and result.stdout.strip():
                new_cwd = result.stdout.strip().splitlines()[-1]
                if os.path.isdir(new_cwd):
                    self._cwd = new_cwd
        except Exception:
            pass
