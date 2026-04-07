"""
Hook System — CC-aligned lifecycle event hooks.
Supports both Python callable hooks and bash command hooks.

CC hooks (src/hooks/): pre_tool_use, post_tool_use, session_start, session_end, etc.
BUDDY implements the same event model with JSON stdin/stdout for bash hooks.

Usage:
  1. Register hooks in ~/.claude-buddy/settings.json:
     {"hooks": {"pre_tool_use": ["echo pre-hook"], "post_tool_use": ["python my_hook.py"]}}
  2. Or register programmatically:
     hook_registry.register("pre_tool_use", my_handler_fn)
"""

import json
import subprocess
import platform
import time
import threading
from typing import Any, Callable
from pathlib import Path


# CC-aligned hook event types
HOOK_EVENTS = [
    "pre_tool_use",     # Before tool execution (can block)
    "post_tool_use",    # After tool execution
    "session_start",    # When engine starts a new session
    "session_end",      # When session is archived/cleared
    "on_error",         # When an error occurs
    "pre_compact",      # Before compaction
    "post_compact",     # After compaction
    "on_memory_extract",  # After memory extraction
]

# Default timeout for hook execution
HOOK_TIMEOUT_SEC = 10


class HookResult:
    """Result from a hook execution."""
    def __init__(self, success: bool = True, output: str = "",
                 block: bool = False, error: str = ""):
        self.success = success
        self.output = output
        self.block = block    # If True, the triggering action should be cancelled
        self.error = error


class HookRegistry:
    """
    CC-aligned hook registry and dispatcher.
    Supports Python callables and bash commands.
    """

    def __init__(self):
        self._hooks: dict[str, list[dict]] = {event: [] for event in HOOK_EVENTS}
        self._execution_log: list[dict] = []

    def register(self, event: str, handler: Callable | str,
                 name: str = "", timeout: int = HOOK_TIMEOUT_SEC):
        """
        Register a hook handler.

        Args:
            event: Hook event type (e.g., "pre_tool_use")
            handler: Python callable(context) → HookResult, or bash command string
            name: Optional name for identification
            timeout: Max seconds to wait for execution
        """
        if event not in HOOK_EVENTS:
            raise ValueError(f"Unknown hook event: {event}. Valid: {HOOK_EVENTS}")

        hook_type = "python" if callable(handler) else "bash"
        self._hooks[event].append({
            "handler": handler,
            "type": hook_type,
            "name": name or f"{hook_type}_{len(self._hooks[event])}",
            "timeout": timeout,
        })

    def unregister(self, event: str, name: str):
        """Remove a named hook."""
        if event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h["name"] != name]

    def fire(self, event: str, context: dict | None = None) -> list[HookResult]:
        """
        Fire all hooks for an event. Returns list of HookResults.
        For pre_* events, if any hook returns block=True, the action should be cancelled.
        """
        if event not in self._hooks:
            return []

        results = []
        for hook in self._hooks[event]:
            start = time.time()
            try:
                if hook["type"] == "python":
                    result = self._run_python_hook(hook, context or {})
                else:
                    result = self._run_bash_hook(hook, context or {})
            except Exception as e:
                result = HookResult(success=False, error=str(e))

            elapsed = time.time() - start
            self._execution_log.append({
                "event": event,
                "hook": hook["name"],
                "success": result.success,
                "elapsed": elapsed,
                "time": time.time(),
            })
            results.append(result)

        return results

    def fire_async(self, event: str, context: dict | None = None):
        """Fire hooks in a background thread (non-blocking)."""
        t = threading.Thread(target=self.fire, args=(event, context), daemon=True)
        t.start()

    def _run_python_hook(self, hook: dict, context: dict) -> HookResult:
        """Execute a Python callable hook."""
        handler = hook["handler"]
        result = handler(context)
        if isinstance(result, HookResult):
            return result
        if isinstance(result, dict):
            return HookResult(
                success=result.get("success", True),
                output=result.get("output", ""),
                block=result.get("block", False),
            )
        return HookResult(success=True, output=str(result) if result else "")

    def _run_bash_hook(self, hook: dict, context: dict) -> HookResult:
        """
        Execute a bash command hook.
        CC-aligned: JSON stdin/stdout communication.
        """
        command = hook["handler"]
        timeout = hook.get("timeout", HOOK_TIMEOUT_SEC)

        try:
            # Pass context as JSON on stdin
            stdin_data = json.dumps(context, default=str, ensure_ascii=False)

            is_windows = platform.system() == "Windows"
            if is_windows:
                result = subprocess.run(
                    command, shell=True,
                    input=stdin_data, capture_output=True, text=True,
                    timeout=timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                result = subprocess.run(
                    ["/bin/bash", "-c", command],
                    input=stdin_data, capture_output=True, text=True,
                    timeout=timeout,
                )

            # Try to parse JSON output from hook
            output = result.stdout.strip()
            try:
                parsed = json.loads(output) if output else {}
                return HookResult(
                    success=parsed.get("success", result.returncode == 0),
                    output=parsed.get("output", output),
                    block=parsed.get("block", False),
                )
            except json.JSONDecodeError:
                return HookResult(
                    success=result.returncode == 0,
                    output=output,
                )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                error=f"Hook timed out after {timeout}s",
            )
        except Exception as e:
            return HookResult(success=False, error=str(e))

    def load_from_config(self, settings_path: Path | None = None):
        """
        Load hooks from settings.json.
        CC-aligned: reads hooks from configuration file.

        Format: {"hooks": {"pre_tool_use": ["command1", "command2"], ...}}
        """
        if settings_path is None:
            from config import DATA_DIR
            settings_path = DATA_DIR / "settings.json"

        if not settings_path.exists():
            return

        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            hooks_config = data.get("hooks", {})

            for event, commands in hooks_config.items():
                if event not in HOOK_EVENTS:
                    continue
                if isinstance(commands, str):
                    commands = [commands]
                for i, cmd in enumerate(commands):
                    if isinstance(cmd, str):
                        self.register(event, cmd, name=f"config_{event}_{i}")
        except Exception:
            pass  # Config loading is best-effort

    def list_hooks(self) -> dict[str, list[str]]:
        """List all registered hooks by event."""
        result = {}
        for event, hooks in self._hooks.items():
            if hooks:
                result[event] = [h["name"] for h in hooks]
        return result

    def format_status(self) -> str:
        """Format hook registry status for display."""
        hooks = self.list_hooks()
        if not hooks:
            return "No hooks registered.\nConfigure in ~/.claude-buddy/settings.json under 'hooks' key."

        lines = ["Registered hooks:"]
        for event, names in hooks.items():
            lines.append(f"  {event}: {', '.join(names)}")

        if self._execution_log:
            recent = self._execution_log[-5:]
            lines.append(f"\nRecent executions ({len(self._execution_log)} total):")
            for log in recent:
                status = "OK" if log["success"] else "FAIL"
                lines.append(f"  [{status}] {log['event']}/{log['hook']} ({log['elapsed']:.2f}s)")

        return "\n".join(lines)
