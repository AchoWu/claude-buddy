"""
Streaming Watchdog — CC-aligned tool execution timeout and loop detection.
CC: uses abort controllers + idle detection during streaming.

Features:
- Per-tool timeout (default 30s, Bash 120s, WebFetch 60s)
- Loop detection: same tool + same args 3 times → warning
"""

import time
import threading
from typing import Any


# CC: per-tool timeout overrides (seconds)
_TOOL_TIMEOUTS = {
    "Bash": 120,
    "WebFetch": 60,
    "WebSearch": 60,
    "Agent": 300,
}
DEFAULT_TOOL_TIMEOUT = 30

# Loop detection: max repeated identical calls
MAX_IDENTICAL_CALLS = 3


class ToolWatchdog:
    """Monitors tool execution for timeouts and loops."""

    def __init__(self):
        self._active: dict[str, float] = {}  # tool_use_id → start_time
        self._call_history: list[tuple[str, str]] = []  # (tool_name, args_hash)
        self._lock = threading.Lock()

    def start_tool(self, tool_use_id: str, tool_name: str) -> float:
        """Record tool execution start. Returns the timeout for this tool."""
        with self._lock:
            self._active[tool_use_id] = time.time()
        return _TOOL_TIMEOUTS.get(tool_name, DEFAULT_TOOL_TIMEOUT)

    def finish_tool(self, tool_use_id: str):
        """Record tool execution end."""
        with self._lock:
            self._active.pop(tool_use_id, None)

    def check_timeout(self, tool_use_id: str, tool_name: str) -> bool:
        """Check if a tool has exceeded its timeout. Returns True if timed out."""
        with self._lock:
            start = self._active.get(tool_use_id)
        if start is None:
            return False
        elapsed = time.time() - start
        timeout = _TOOL_TIMEOUTS.get(tool_name, DEFAULT_TOOL_TIMEOUT)
        return elapsed > timeout

    def check_loop(self, tool_name: str, args_hash: str) -> str | None:
        """
        CC-aligned: detect repeated identical tool calls.
        Returns warning string if loop detected, None otherwise.
        """
        with self._lock:
            self._call_history.append((tool_name, args_hash))
            # Check last N calls for identical pattern
            recent = self._call_history[-MAX_IDENTICAL_CALLS:]
            if len(recent) == MAX_IDENTICAL_CALLS:
                if all(r == recent[0] for r in recent):
                    return (
                        f"Warning: {tool_name} has been called {MAX_IDENTICAL_CALLS} times "
                        f"with identical arguments. This may indicate an infinite loop. "
                        f"Consider a different approach."
                    )
        return None

    def get_active_tools(self) -> dict[str, float]:
        """Return dict of active tool_use_id → elapsed seconds."""
        now = time.time()
        with self._lock:
            return {tid: now - start for tid, start in self._active.items()}

    def reset(self):
        with self._lock:
            self._active.clear()
            self._call_history.clear()
