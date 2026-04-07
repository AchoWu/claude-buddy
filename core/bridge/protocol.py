"""
JSON-RPC 2.0 Protocol — message format and routing.
"""

import json
import uuid
from typing import Any, Callable
from dataclasses import dataclass, field


# ── JSON-RPC Message Types ────────────────────────────────────────

@dataclass
class RPCRequest:
    method: str
    params: dict = field(default_factory=dict)
    id: str | int | None = None  # None = notification (no response expected)

    def to_json(self) -> str:
        msg = {"jsonrpc": "2.0", "method": self.method, "params": self.params}
        if self.id is not None:
            msg["id"] = self.id
        return json.dumps(msg, ensure_ascii=False)


@dataclass
class RPCResponse:
    id: str | int | None
    result: Any = None
    error: dict | None = None  # {"code": int, "message": str}

    def to_json(self) -> str:
        msg: dict = {"jsonrpc": "2.0", "id": self.id}
        if self.error:
            msg["error"] = self.error
        else:
            msg["result"] = self.result
        return json.dumps(msg, ensure_ascii=False)


# ── Standard Error Codes ──────────────────────────────────────────

ERR_PARSE = {"code": -32700, "message": "Parse error"}
ERR_INVALID_REQUEST = {"code": -32600, "message": "Invalid request"}
ERR_METHOD_NOT_FOUND = {"code": -32601, "message": "Method not found"}
ERR_INVALID_PARAMS = {"code": -32602, "message": "Invalid params"}
ERR_INTERNAL = {"code": -32603, "message": "Internal error"}
ERR_AUTH_FAILED = {"code": -32000, "message": "Authentication failed"}
ERR_BUSY = {"code": -32001, "message": "Engine is busy"}


def make_error(code: int, message: str) -> dict:
    return {"code": code, "message": message}


# ── Message Router ────────────────────────────────────────────────

class RPCRouter:
    """Routes JSON-RPC method calls to handler functions."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, method: str, handler: Callable):
        """Register a handler for a method name."""
        self._handlers[method] = handler

    def handle(self, raw_message: str) -> str | None:
        """
        Parse and route a JSON-RPC message.
        Returns response JSON string, or None for notifications.
        """
        # Parse
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            return RPCResponse(id=None, error=ERR_PARSE).to_json()

        # Validate
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            return RPCResponse(id=data.get("id"), error=ERR_INVALID_REQUEST).to_json()

        method = data.get("method", "")
        params = data.get("params", {})
        msg_id = data.get("id")  # None = notification

        if not method:
            return RPCResponse(id=msg_id, error=ERR_INVALID_REQUEST).to_json()

        # Find handler
        handler = self._handlers.get(method)
        if not handler:
            if msg_id is not None:
                return RPCResponse(id=msg_id, error=ERR_METHOD_NOT_FOUND).to_json()
            return None  # silent drop for unknown notifications

        # Execute
        try:
            result = handler(params)
            if msg_id is not None:
                return RPCResponse(id=msg_id, result=result).to_json()
            return None  # notification, no response
        except Exception as e:
            if msg_id is not None:
                return RPCResponse(
                    id=msg_id,
                    error=make_error(-32603, str(e)[:200])
                ).to_json()
            return None


def build_notification(method: str, params: dict | None = None) -> str:
    """Build a JSON-RPC notification (no id, no response expected)."""
    return RPCRequest(method=method, params=params or {}).to_json()
