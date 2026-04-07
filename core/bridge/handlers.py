"""
Bridge Handlers — process incoming JSON-RPC method calls.
"""

from __future__ import annotations
from typing import Any


class BridgeHandlers:
    """
    Handles all incoming RPC methods from Bridge clients.
    Each method returns a result dict (or raises on error).
    """

    def __init__(self, engine=None, command_registry=None):
        self._engine = engine
        self._command_registry = command_registry

    def send_message(self, params: dict) -> dict:
        """Send a user message to the engine."""
        text = params.get("text", "").strip()
        if not text:
            raise ValueError("text is required")

        if not self._engine:
            raise RuntimeError("Engine not available")

        if self._engine._is_running:
            raise RuntimeError("Engine is busy processing another message")

        # Check if it's a slash command
        if self._command_registry and text.startswith("/"):
            result = self._command_registry.execute(text, self._build_cmd_context())
            if result:
                return {"type": "command_result", "text": result}

        self._engine.send_message(text)
        return {"type": "message_sent", "text": text}

    def abort(self, params: dict) -> dict:
        """Abort the current operation."""
        if self._engine:
            self._engine.abort()
            return {"aborted": True}
        raise RuntimeError("Engine not available")

    def get_status(self, params: dict) -> dict:
        """Get current engine status."""
        if not self._engine:
            return {"status": "unavailable"}
        c = self._engine.conversation
        return {
            "running": self._engine._is_running,
            "messages": c.message_count,
            "tokens": c.estimated_tokens,
            "context_window": self._engine._context_window,
            "compactions": c._compaction_count,
            "files_read": len(c.file_read_state.read_files),
            "model": self._engine._provider_model or "(not set)",
        }

    def get_history(self, params: dict) -> dict:
        """Get conversation history."""
        if not self._engine:
            return {"messages": []}
        limit = params.get("limit", 50)
        msgs = self._engine.conversation.messages[-limit:]
        # Simplify messages for transport
        simple = []
        for msg in msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str):
                simple.append({"role": role, "content": content[:2000]})
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            text_parts.append(f"[Tool: {block.get('name', '')}]")
                        elif block.get("type") == "tool_result":
                            text_parts.append(f"[Result: {str(block.get('content', ''))[:200]}]")
                simple.append({"role": role, "content": "\n".join(text_parts)[:2000]})
            else:
                simple.append({"role": role, "content": str(content)[:2000]})
        return {"messages": simple}

    def list_tools(self, params: dict) -> dict:
        """List all available tools."""
        if not self._engine:
            return {"tools": []}
        tools = []
        for name in sorted(self._engine._tool_executors.keys()):
            ro = self._engine._tool_read_only.get(name, False)
            tools.append({"name": name, "read_only": ro})
        return {"tools": tools}

    def run_command(self, params: dict) -> dict:
        """Execute a slash command."""
        command = params.get("command", "").strip()
        if not command:
            raise ValueError("command is required")
        if not command.startswith("/"):
            command = "/" + command
        if self._command_registry:
            result = self._command_registry.execute(command, self._build_cmd_context())
            return {"result": result or "(no output)"}
        raise RuntimeError("Command registry not available")

    def clear_history(self, params: dict) -> dict:
        """Clear conversation history."""
        if self._engine:
            self._engine.clear_conversation()
            self._engine.save_conversation()
            return {"cleared": True}
        raise RuntimeError("Engine not available")

    def get_cost(self, params: dict) -> dict:
        """Get session cost summary."""
        if self._engine:
            return {"summary": self._engine.get_cost_summary()}
        return {"summary": "Engine not available"}

    def permission_response(self, params: dict) -> dict:
        """Handle permission response from remote client."""
        request_id = params.get("request_id", "")
        approved = params.get("approved", False)
        # Store for the permission callback to pick up
        if hasattr(self, '_pending_permissions'):
            self._pending_permissions[request_id] = approved
        return {"received": True}

    def _build_cmd_context(self) -> dict:
        """Build context dict for slash command execution."""
        return {
            "engine": self._engine,
            "command_registry": self._command_registry,
        }

    def get_all_handlers(self) -> dict:
        """Return method name → handler mapping for the RPC router."""
        return {
            "sendMessage": self.send_message,
            "abort": self.abort,
            "getStatus": self.get_status,
            "getHistory": self.get_history,
            "listTools": self.list_tools,
            "runCommand": self.run_command,
            "clearHistory": self.clear_history,
            "getCost": self.get_cost,
            "permissionResponse": self.permission_response,
        }
