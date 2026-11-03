"""
Horizon Video Downloader v3 — Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Startup sequence:
  1. Import config (triggers PATH injection for deno.exe / yt-dlp.exe)
  2. Configure structured logging
  3. Resolve an available port (80 → 8080 → 8090 → 9000 → ephemeral)
  4. Start Uvicorn in a daemon thread
  5. Wait for server readiness via /health probe
  6. Auto-open the default web browser
  7. Block the main thread (Ctrl+C to exit)

This module is the single entry point for both development
(python main.py) and the PyInstaller-frozen executable.
"""

from __future__ import annotations

import logging
import sys
import io
import threading
import time
import webbrowser

import urllib.request
import urllib.error

# Null stream protection for PyInstaller --noconsole or detached launch
if sys.stdout is None:
    sys.stdout = io.StringIO()
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = io.StringIO()
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stdin is None:
    sys.stdin = io.StringIO()

# Set Windows console window title (if running with console attached)
if sys.platform == "win32":
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow():
            ctypes.windll.kernel32.SetConsoleTitleW("Horizon Video Downloader v5.1")
    except Exception:
        pass


import uvicorn

# config.py is imported first — its module-level code injects the
# bundled binary directory into os.environ["PATH"] so yt-dlp can
# auto-discover deno.exe without requiring Node.js.
from config import APP_NAME, APP_VERSION, BIND_HOST, LOCAL_HOST, find_available_port
from server import create_app


def configure_logging() -> None:
    """Set up structured logging with clean formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-14s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # Suppress noisy uvicorn access logs (each WS frame = a log line)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Keep uvicorn error logs visible
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.15) -> bool:
    """
    Poll the /health endpoint until the server is ready.
    Returns True if the server responded within the timeout.
    """
    health_url = f"{url}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(interval)
    return False


def main() -> None:
    """Application entry point."""
    configure_logging()
    logger = logging.getLogger("hvd.main")

    # ── Banner ────────────────────────────────────────────────
    logger.info(f"{'=' * 56}")
    logger.info(f"  {APP_NAME} v{APP_VERSION}")
    logger.info(f"{'=' * 56}")

    # ── Resolve port ──────────────────────────────────────────
    port = find_available_port()
    local_url = f"http://{LOCAL_HOST}:{port}"
    logger.info(f"Port resolved: {port}")

    # ── Create app ────────────────────────────────────────────
    app = create_app()

    # ── Start Uvicorn in daemon thread ────────────────────────
    # Binds to 0.0.0.0 so mobile phones on the same Wi-Fi network can download files via QR
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app,
            host=BIND_HOST,
            port=port,
            ws="auto",
            log_level="warning",
            # Single worker — all state is in-memory (no need for multi-worker)
            workers=1,
        ),
        name="hvd-uvicorn",
        daemon=True,
    )
    server_thread.start()
    logger.info("Uvicorn server thread started")

    # ── Wait for readiness ────────────────────────────────────
    if wait_for_server(local_url):
        logger.info(f"Server ready at {local_url}")
    else:
        logger.error(
            f"Server failed to respond within 15s at {local_url}. "
            "Check for port conflicts or firewall issues."
        )
        sys.exit(1)

    # ── Open browser ──────────────────────────────────────────
    logger.info(f"Opening browser -> {local_url}")
    try:
        webbrowser.open(local_url)
    except Exception as e:
        logger.warning(f"Could not open browser automatically: {e}")

    # ── Block main thread ─────────────────────────────────────
    # The daemon thread keeps Uvicorn running. We block here so
    # the process stays alive. Close the window or Ctrl+C to stop.
    logger.info("Server is running. Press Ctrl+C or close this window to stop.")
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
