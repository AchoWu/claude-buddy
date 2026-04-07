"""
State Sync — broadcast engine state changes to all connected clients.
"""

from __future__ import annotations
from typing import Callable, Any

from core.bridge.protocol import build_notification


class StateSync:
    """
    Listens to engine signals and broadcasts state changes
    to all connected Bridge clients.
    """

    def __init__(self, broadcast_fn: Callable[[str], None]):
        """
        Args:
            broadcast_fn: Callable that sends a JSON string to all clients.
        """
        self._broadcast = broadcast_fn

    def on_response_chunk(self, text: str):
        """Streaming text fragment."""
        self._broadcast(build_notification("response_chunk", {"text": text}))

    def on_response_text(self, text: str):
        """Final complete response."""
        self._broadcast(build_notification("response_text", {"text": text}))

    def on_tool_start(self, name: str, input_data: dict):
        """Tool execution started."""
        # Truncate input for safety
        safe_input = {}
        for k, v in input_data.items():
            safe_input[k] = str(v)[:200] if isinstance(v, str) else v
        self._broadcast(build_notification("tool_start", {
            "name": name, "input": safe_input,
        }))

    def on_tool_result(self, name: str, output: str):
        """Tool execution completed."""
        self._broadcast(build_notification("tool_result", {
            "name": name, "output": output[:500],
        }))

    def on_state_changed(self, state: str):
        """Engine state changed (idle/work)."""
        self._broadcast(build_notification("state_changed", {"state": state}))

    def on_error(self, error: str):
        """Engine error."""
        self._broadcast(build_notification("error", {"message": error[:500]}))

    def on_permission_request(self, tool_name: str, input_data: dict, request_id: str):
        """Permission confirmation needed from remote client."""
        self._broadcast(build_notification("permission_request", {
            "request_id": request_id,
            "tool_name": tool_name,
            "input": {k: str(v)[:200] for k, v in input_data.items()},
        }))
