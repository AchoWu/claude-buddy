"""
Bridge WebSocket Server — accept remote client connections.
"""

from __future__ import annotations
import asyncio
import json
import threading
import time
from typing import Any, Set

from core.bridge.protocol import RPCRouter, RPCResponse, ERR_AUTH_FAILED
from core.bridge.auth import BridgeAuth


class BridgeServer:
    """
    WebSocket server that accepts remote Bridge client connections.
    Runs in a background thread with its own asyncio event loop.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 3456,
                 auth: BridgeAuth | None = None,
                 router: RPCRouter | None = None):
        self._host = host
        self._port = port
        self._auth = auth or BridgeAuth()
        self._router = router or RPCRouter()
        self._clients: Set[Any] = set()  # connected websocket objects
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._serve_web_client = True  # serve built-in HTML client

    @property
    def port(self) -> int:
        return self._port

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        """Start the server in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the server."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def broadcast(self, message: str):
        """Send a message to all connected clients."""
        if not self._clients or not self._loop:
            return

        async def _send_all():
            dead = set()
            for ws in self._clients.copy():
                try:
                    await ws.send(message)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

        asyncio.run_coroutine_threadsafe(_send_all(), self._loop)

    def _run_event_loop(self):
        """Background thread: run the asyncio event loop with the WS server."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._serve())
        except Exception:
            pass
        finally:
            self._running = False

    async def _serve(self):
        """Start the WebSocket + HTTP server."""
        try:
            import websockets
            from websockets.server import serve
        except ImportError:
            print("[Bridge] websockets library not installed. Run: pip install websockets")
            self._running = False
            return

        # Combined handler: WebSocket for ws://, HTTP for http://
        async def handler(websocket, path=""):
            # HTTP request for web client
            # (websockets 10+ uses 'path' differently, handle both)
            request_path = path if path else getattr(websocket, 'path', '/')

            await self._handle_websocket(websocket)

        try:
            async with serve(handler, self._host, self._port):
                while self._running:
                    await asyncio.sleep(0.5)
        except OSError as e:
            print(f"[Bridge] Could not start on port {self._port}: {e}")
            self._running = False

    async def _handle_websocket(self, websocket):
        """Handle a single WebSocket connection."""
        # Auth: check token from query params or first message
        # For simplicity, accept all local connections
        self._clients.add(websocket)
        try:
            async for message in websocket:
                response = self._router.handle(message)
                if response:
                    await websocket.send(response)
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
