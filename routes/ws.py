"""
Horizon Video Downloader v3 — WebSocket Route
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Single WebSocket endpoint at /ws for real-time
progress streaming to connected browser clients.
"""

from __future__ import annotations

import logging

from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger("hvd.ws")


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Main WebSocket connection handler.

    On connect:
      1. Register with WebSocketManager
      2. Send initial snapshot of all current tasks

    While connected:
      - Server → Client: Receives progress broadcasts pushed by
        DownloadManager worker threads via the asyncio bridge.
      - Client → Server: Listens for incoming text messages
        (reserved for future client-side commands like URL submission).

    On disconnect:
      - Unregister from WebSocketManager (auto-cleans dead sockets).
    """
    ws_manager = websocket.app.state.ws_manager
    download_manager = websocket.app.state.download_manager

    await ws_manager.connect(websocket)

    try:
        # ── Send initial state snapshot ───────────────────────
        # When a browser connects (or reconnects after a drop),
        # it immediately receives the current state of all tasks
        # so the UI can render in-progress downloads.
        tasks = download_manager.get_all_tasks()
        sm = getattr(websocket.app.state, "sniffer_manager", None)
        sniffer_data = sm.get_status() if sm else {"running": False, "streams": []}
        await ws_manager.send_personal(websocket, {
            "type": "init",
            "tasks": tasks,
            "sniffer": sniffer_data,
        })

        # ── Listen loop ──────────────────────────────────────
        # Keep the connection alive and receive any client messages.
        # Currently a no-op receiver — the real data flows server→client
        # via broadcast(). This loop ensures the connection stays open
        # and we detect disconnects promptly.
        while True:
            message = await websocket.receive_text()
            # Future: handle client commands here (e.g., URL submission,
            # settings changes, batch operations)
            logger.debug(f"WS received: {message[:100]}")

    except WebSocketDisconnect:
        pass  # Normal browser tab close / navigation
    except Exception as exc:
        logger.debug(f"WebSocket error: {exc}")
    finally:
        await ws_manager.disconnect(websocket)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Route Table (imported by server.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

routes = [
    WebSocketRoute("/ws", websocket_endpoint),
]
