"""
Horizon Video Downloader v3 — WebSocket Connection Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thread-safe broadcast hub for real-time progress updates.

Worker threads push updates via asyncio.run_coroutine_threadsafe()
into this manager, which fans them out to every connected browser.
"""

import asyncio
import json
import logging
from typing import Any

from starlette.websockets import WebSocket

logger = logging.getLogger("hvd.ws")


class WebSocketManager:
    """
    Manages active WebSocket connections and provides async broadcasting.

    Thread-safety: The broadcast() method is async and uses an asyncio.Lock.
    Worker threads call it via asyncio.run_coroutine_threadsafe(), which is
    safe to invoke from any thread as long as the event loop is running.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Connection Lifecycle ──────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(
            f"WebSocket connected  — {len(self._connections)} active"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(
            f"WebSocket disconnected — {len(self._connections)} active"
        )

    # ── Messaging ─────────────────────────────────────────────

    async def broadcast(self, data: dict[str, Any]) -> None:
        """
        Send a JSON payload to every connected client.
        Automatically removes dead/stale connections on send failure.
        """
        if not self._connections:
            return

        message = json.dumps(data)
        stale: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    stale.append(ws)

            for ws in stale:
                self._connections.discard(ws)
                logger.debug("Removed stale WebSocket connection")

    async def send_personal(
        self, websocket: WebSocket, data: dict[str, Any]
    ) -> None:
        """Send a JSON payload to a single specific client."""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            logger.debug("Failed to send personal message — connection dead")

    # ── Introspection ─────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        """Number of currently active WebSocket connections."""
        return len(self._connections)
