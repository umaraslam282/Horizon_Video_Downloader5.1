"""
Horizon Video Downloader v3 — Starlette Application Factory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Creates and configures the Starlette ASGI application.

Uses Starlette directly (not FastAPI) to avoid the Pydantic v2
/ pydantic-core Rust compilation requirement on Python 3.15.
Provides identical ASGI routing, WebSocket, and static file
serving with zero native dependencies.

Responsibilities:
  - Lifespan management (startup/shutdown hooks)
  - Mounts static file serving for the SPA frontend
  - Assembles API and WebSocket route tables
  - Configures CORS for localhost development
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from config import APP_NAME, APP_VERSION, STATIC_DIR
from download_manager import DownloadManager
from ws_manager import WebSocketManager
from sniffer_manager import BrowserSnifferManager
from routes.api import routes as api_routes
from routes.ws import routes as ws_routes

logger = logging.getLogger("hvd.server")


def create_app() -> Starlette:
    """
    Application factory — creates a fully configured Starlette instance.

    Called once by main.py before handing the app to Uvicorn.
    """

    # ── Instantiate core services ─────────────────────────────
    download_manager = DownloadManager()
    ws_manager = WebSocketManager()
    sniffer_manager = BrowserSnifferManager()

    # ── Lifespan (startup + shutdown) ─────────────────────────

    @asynccontextmanager
    async def lifespan(app: Starlette):
        """
        Startup:  Wire the DownloadManager to the async event loop and
                  the WebSocket broadcast callback.
        Shutdown: Gracefully kill all active downloads.
        """
        # ── Startup ───────────────────────────────────────────
        loop = asyncio.get_running_loop()
        download_manager.set_event_loop(loop)
        download_manager.set_broadcast_callback(ws_manager.broadcast)
        sniffer_manager.set_event_loop(loop)
        sniffer_manager.set_broadcast_callback(ws_manager.broadcast)

        # Attach services to app.state for route handler access
        app.state.download_manager = download_manager
        app.state.ws_manager = ws_manager
        app.state.sniffer_manager = sniffer_manager

        logger.info(f"{APP_NAME} v{APP_VERSION} — server started")
        yield
        # ── Shutdown ──────────────────────────────────────────
        download_manager.shutdown()
        sniffer_manager.shutdown()
        logger.info("Server shutdown complete")

    # ── Assemble route table ──────────────────────────────────
    # API and WS routes come first; static mount is last (catch-all).
    all_routes = [
        *api_routes,
        *ws_routes,
    ]

    # Static files (SPA frontend) — mounted as catch-all at "/"
    static_path = Path(STATIC_DIR)
    if static_path.is_dir():
        all_routes.append(
            Mount("/", app=StaticFiles(directory=str(static_path), html=True), name="static")
        )
        logger.info(f"Serving static files from: {static_path}")
    else:
        logger.warning(
            f"Static directory not found: {static_path}  "
            "(frontend will not be served)"
        )

    # ── CORS Middleware (permissive for localhost) ─────────────
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ]

    # ── Create Starlette app ──────────────────────────────────
    app = Starlette(
        routes=all_routes,
        middleware=middleware,
        lifespan=lifespan,
    )

    return app
