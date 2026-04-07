"""
Bridge Manager — central controller for the Bridge system.
Integrates: WebSocket server, RPC router, auth, handlers, state sync.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from core.bridge.server import BridgeServer
from core.bridge.protocol import RPCRouter
from core.bridge.auth import BridgeAuth
from core.bridge.handlers import BridgeHandlers
from core.bridge.state_sync import StateSync
from core.bridge.session_pointer import format_session_pointer


class BridgeManager:
    """
    Top-level Bridge API. Create one of these and call start().

    Usage:
        bridge = BridgeManager(engine=engine, port=3456)
        bridge.start()
        # ... BUDDY runs ...
        bridge.stop()
    """

    def __init__(self, engine=None, command_registry=None, port: int = 3456):
        self._engine = engine
        self._port = port

        # Auth
        self._auth = BridgeAuth()
        self._token = self._auth.generate_token("buddy-session")

        # RPC router + handlers
        self._router = RPCRouter()
        self._handlers = BridgeHandlers(
            engine=engine,
            command_registry=command_registry,
        )
        for method, handler in self._handlers.get_all_handlers().items():
            self._router.register(method, handler)

        # WebSocket server
        self._server = BridgeServer(
            host="0.0.0.0",
            port=port,
            auth=self._auth,
            router=self._router,
        )

        # State sync (broadcasts engine events to clients)
        self._state_sync = StateSync(broadcast_fn=self._server.broadcast)

        # Built-in web client path
        self._web_client_path = Path(__file__).parent / "web_client.html"

    def start(self):
        """Start the Bridge server and wire engine signals."""
        self._server.start()
        self._connect_engine_signals()
        # Print session pointer
        print(format_session_pointer(self._port, self._token))

    def stop(self):
        """Stop the Bridge server."""
        self._server.stop()

    @property
    def is_running(self) -> bool:
        return self._server.is_running

    @property
    def client_count(self) -> int:
        return self._server.client_count

    @property
    def port(self) -> int:
        return self._port

    @property
    def web_client_html(self) -> str:
        """Read the built-in web client HTML."""
        try:
            return self._web_client_path.read_text(encoding="utf-8")
        except Exception:
            return "<html><body>Web client not found.</body></html>"

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "port": self._port,
            "clients": self.client_count,
        }

    def _connect_engine_signals(self):
        """Wire Qt signals from the engine to the state sync broadcaster."""
        if not self._engine:
            return

        try:
            self._engine.response_chunk.connect(self._state_sync.on_response_chunk)
            self._engine.response_text.connect(self._state_sync.on_response_text)
            self._engine.tool_start.connect(self._state_sync.on_tool_start)
            self._engine.tool_result.connect(self._state_sync.on_tool_result)
            self._engine.state_changed.connect(self._state_sync.on_state_changed)
            self._engine.error.connect(self._state_sync.on_error)
        except Exception:
            pass  # signals may not be available in test context
