"""
Horizon Video Downloader - Browser Stream Sniffer Manager
──────────────────────────────────────────────────────────
High-precision media stream sniffer powered by Chrome DevTools Protocol (CDP).
Intercepts hidden HLS (.m3u8), DASH (.mpd), and direct video streams from
anime portals and web-player platforms (aniwaves, 9anime, MegaCloud, Vidplay,
Vidstreaming, StreamTape, etc.) across top-level pages and nested child iframes.
Broadcasts live, transparent terminal logs so the user can see real-time
browser navigation and stream capture status.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine
from urllib.parse import unquote, urlparse

logger = logging.getLogger("hvd.sniffer")

# Stream URL detection pattern
STREAM_PATTERN = re.compile(r"m3u8|\.mpd|\.mp4|\.webm", re.IGNORECASE)

# Ignored fragments and static assets
IGNORED_PATTERNS = re.compile(
    r"\.(?:ts|m4s|aac|jpg|jpeg|png|gif|svg|ico|css|woff2?|js)(?:\?|$)|"
    r"/(?:segment|fragment|chunks?|seg-\d+|frag-\d+)|"
    r"(?:doubleclick|google-analytics|googletagservices|adservice|facebook\.net|taboola|adnxs|popads)",
    re.IGNORECASE,
)


class BrowserSnifferManager:
    """
    Manages the companion browser process and multi-session CDP network
    interceptor to capture live streaming media URLs with 100% reliability.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._port: int = 9222
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_cb: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None
        self._monitor_task: asyncio.Task | None = None
        self._detected_streams: list[dict[str, Any]] = []
        self._seen_urls: set[str] = set()
        self._recent_logs: list[str] = []
        self._profile_dir: Path | None = None
        self._browser_name: str = "Browser"
        self._cdp_alive: bool = False
        self._active_connections: list[Any] = []
        self._active_page_url: str = ""
        self._active_page_title: str = ""

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store reference to running Starlette event loop."""
        self._loop = loop

    def set_broadcast_callback(
        self, cb: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Store WebSocket broadcast callback."""
        self._broadcast_cb = cb

    def _log(self, message: str) -> None:
        """Log message, save to rolling buffer, and broadcast to frontend."""
        logger.info(message)
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] [SNIFFER] {message}"
        self._recent_logs.append(entry)
        if len(self._recent_logs) > 200:
            self._recent_logs.pop(0)

        if self._broadcast_cb and self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_cb({
                        "type": "log",
                        "task_id": "SNIFFER",
                        "message": message,
                    }),
                    self._loop,
                )
            except Exception:
                pass

    async def _alog(self, message: str) -> None:
        """Async version of _log for use inside coroutines."""
        logger.info(message)
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] [SNIFFER] {message}"
        self._recent_logs.append(entry)
        if len(self._recent_logs) > 200:
            self._recent_logs.pop(0)

        if self._broadcast_cb:
            try:
                await self._broadcast_cb({
                    "type": "log",
                    "task_id": "SNIFFER",
                    "message": message,
                })
            except Exception:
                pass

    @staticmethod
    def find_browser_executable() -> tuple[str, str] | None:
        """
        Locate Google Chrome or Microsoft Edge executable on Windows.
        Returns tuple of (executable_path, friendly_name) or None.
        """
        candidates = [
            (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Google Chrome"),
            (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Google Chrome"),
            (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"), "Google Chrome"),
            (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
            (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
            (os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge"),
        ]
        for c, name in candidates:
            if os.path.isfile(c):
                return c, name

        for binary, name in (("chrome", "Google Chrome"), ("msedge", "Microsoft Edge"), ("google-chrome", "Google Chrome")):
            found = shutil.which(binary)
            if found:
                return found, name
        return None

    @staticmethod
    def get_free_port() -> int:
        """Find an available TCP port for CDP."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @property
    def is_running(self) -> bool:
        """
        Check if companion browser is running either via active process
        or responsive CDP debugging interface.
        """
        if self._proc is not None and self._proc.poll() is None:
            return True
        if self._cdp_alive:
            return True
        return False

    def launch(self, url: str | None = None) -> dict[str, Any]:
        """
        Launch companion browser or smoothly navigate it if already open.
        """
        target_url = (url or "").strip()
        if not target_url or not target_url.startswith(("http://", "https://")):
            target_url = "https://aniwaves.ru" if not target_url else f"https://{target_url}"

        # If already open and responsive, just navigate the existing tab in-place!
        if self.is_running:
            self._log(f"🌐 Companion browser is already open. Navigating to: {target_url}")
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.navigate_active_tab(target_url), self._loop)
            return {
                "success": True,
                "port": self._port,
                "url": target_url,
                "browser": self._browser_name,
                "action": "navigated",
            }

        browser_info = self.find_browser_executable()
        if not browser_info:
            err = "Neither Google Chrome nor Microsoft Edge could be located on this PC."
            self._log(f"❌ {err}")
            raise RuntimeError(err)

        browser_exe, browser_name = browser_info
        self._browser_name = browser_name

        # Clean old state
        self.close()
        self._port = self.get_free_port()
        self._profile_dir = Path(tempfile.gettempdir()) / f"hvd_profile_{self._port}_{int(time.time())}"
        self._profile_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            browser_exe,
            f"--remote-debugging-port={self._port}",
            f"--user-data-dir={str(self._profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-features=Translate",
            "--disable-blink-features=AutomationControlled",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            "--disable-infobars",
            "--window-size=1366,850",
            target_url,
        ]

        self._log(f"🚀 Launching companion browser: {browser_name}")
        self._log(f"🌐 Opening target: {target_url}")
        self._log(f"🔌 Initializing Chromium DevTools Protocol on port {self._port}...")

        self._proc = subprocess.Popen(cmd)
        self._cdp_alive = True

        if self._loop and self._loop.is_running():
            self._monitor_task = self._loop.create_task(self._cdp_orchestrator(self._port, browser_name))

        return {
            "success": True,
            "port": self._port,
            "url": target_url,
            "browser": browser_name,
            "action": "launched",
        }

    async def navigate_active_tab(self, url: str) -> bool:
        """Navigate the currently active companion browser tab without restarting."""
        import websockets
        try:
            def _fetch_targets():
                with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/json", timeout=1.5) as resp:
                    return json.loads(resp.read().decode())
            targets = await asyncio.to_thread(_fetch_targets)
            for t in targets:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    async with websockets.connect(t["webSocketDebuggerUrl"]) as ws:
                        await ws.send(json.dumps({
                            "id": 999,
                            "method": "Page.navigate",
                            "params": {"url": url}
                        }))
                    await self._alog(f"🧭 Navigated companion browser tab to: {url}")
                    return True
        except Exception as e:
            logger.debug(f"Navigate active tab failed: {e}")
        return False

    async def _cdp_orchestrator(self, port: int, browser_name: str) -> None:
        """
        Main monitor loop: monitors active browser pages, attaches to
        them via WebSocket, and continuously intercepts media streams.
        """
        attached_pages: set[str] = set()

        # Wait for browser to initialize debugging interface
        connected = False
        for attempt in range(25):
            if self._proc is not None and self._proc.poll() is not None:
                # Check if port is alive despite launcher process exit
                def _quick_check():
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=0.8) as resp:
                            return resp.status == 200
                    except Exception:
                        return False
                if not await asyncio.to_thread(_quick_check):
                    self._cdp_alive = False
                    await self._alog("🛑 Browser process stopped before connection could be established.")
                    return
            try:
                def _check_json():
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1.0) as resp:
                        return resp.status == 200
                res = await asyncio.to_thread(_check_json)
                if res:
                    connected = True
                    break
            except Exception:
                await asyncio.sleep(0.4)

        if not connected:
            self._cdp_alive = False
            await self._alog(f"⚠️ Failed to connect to {browser_name} debugging port {port}.")
            return

        self._cdp_alive = True
        await self._alog(f"✅ {browser_name} connected to Sniffer Engine! Monitoring web traffic...")

        failed_checks = 0
        while self.is_running:
            try:
                def _fetch_targets():
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1.5) as resp:
                        return json.loads(resp.read().decode())
                targets = await asyncio.to_thread(_fetch_targets)
                failed_checks = 0
                self._cdp_alive = True
            except Exception:
                failed_checks += 1
                if failed_checks >= 3:
                    self._cdp_alive = False
                    break
                await asyncio.sleep(1.0)
                continue

            for t in targets:
                t_type = t.get("type")
                t_id = t.get("id")
                ws_url = t.get("webSocketDebuggerUrl")

                if t_type == "page" and t_id and ws_url and t_id not in attached_pages:
                    attached_pages.add(t_id)
                    if self._loop and self._loop.is_running():
                        self._loop.create_task(self._page_listener(ws_url, t_id, attached_pages))

            await asyncio.sleep(1.5)

        self._cdp_alive = False
        self._proc = None
        await self._alog(f"🛑 Companion browser ({browser_name}) was closed.")
        # Broadcast status update to frontend
        if self._broadcast_cb:
            try:
                await self._broadcast_cb({
                    "type": "sniffer_status",
                    "running": False,
                })
            except Exception:
                pass

    async def _page_listener(
        self, page_ws_url: str, page_id: str, attached_pages: set[str]
    ) -> None:
        """
        Connects directly to an open page target, enables Page/Network/Runtime,
        recursively auto-attaches to all embedded iframes, and parses streams.
        """
        import websockets

        req_id_counter = 100
        pending_bodies: dict[int, tuple[str, str]] = {}
        pending_evals: dict[int, str] = {}

        try:
            async with websockets.connect(page_ws_url, max_size=32 * 1024 * 1024) as ws:
                self._active_connections.append(ws)

                # 1. Enable Page, Network, and Runtime monitoring
                req_id_counter += 1
                await ws.send(json.dumps({"id": req_id_counter, "method": "Page.enable"}))
                req_id_counter += 1
                await ws.send(json.dumps({"id": req_id_counter, "method": "Network.enable"}))
                req_id_counter += 1
                await ws.send(json.dumps({"id": req_id_counter, "method": "Runtime.enable"}))

                # 2. Inject media sniffer script into new document contexts
                hook_script = """
                (function() {
                    try {
                        const origSrc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
                        if (origSrc && origSrc.set) {
                            Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                                set: function(val) {
                                    if (val && typeof val === 'string' && (val.includes('m3u8') || val.includes('.mp4') || val.includes('.mpd'))) {
                                        console.log('__HVD_MEDIA__:' + val);
                                    }
                                    return origSrc.set.apply(this, arguments);
                                },
                                get: function() { return origSrc.get.apply(this, arguments); }
                            });
                        }
                    } catch(e) {}
                })();
                """
                req_id_counter += 1
                await ws.send(json.dumps({
                    "id": req_id_counter,
                    "method": "Page.addScriptToEvaluateOnNewDocument",
                    "params": {"source": hook_script}
                }))

                # 3. Auto-attach to all embedded child iframes (the video player)
                req_id_counter += 1
                await ws.send(json.dumps({
                    "id": req_id_counter,
                    "method": "Target.setAutoAttach",
                    "params": {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}
                }))

                while self.is_running:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        break

                    m = msg.get("method", "")
                    params = msg.get("params", {})
                    sid = msg.get("sessionId")
                    resp_id = msg.get("id")

                    # Handle getResponseBody callbacks (API sources)
                    if resp_id and resp_id in pending_bodies:
                        ref, api_url = pending_bodies.pop(resp_id)
                        result = msg.get("result", {})
                        body_text = result.get("body", "")
                        if result.get("base64Encoded", False):
                            try:
                                body_text = base64.b64decode(body_text).decode("utf-8", errors="ignore")
                            except Exception:
                                pass
                        await self._extract_streams_from_body(body_text, ref, api_url)

                    # Handle Runtime.evaluate callbacks (e.g. document.title)
                    elif resp_id and resp_id in pending_evals:
                        eval_type = pending_evals.pop(resp_id)
                        val = msg.get("result", {}).get("result", {}).get("value")
                        if eval_type == "title" and isinstance(val, str) and val.strip():
                            self._active_page_title = val.strip()

                    # Page navigation event (top-level or child)
                    if m == "Page.frameNavigated":
                        frame = params.get("frame", {})
                        f_url = frame.get("url", "")
                        f_title = frame.get("title", "")
                        if not frame.get("parentId") and f_url and not f_url.startswith("data:"):
                            self._active_page_url = f_url
                            if f_title:
                                self._active_page_title = f_title
                            clean_t = f" | {f_title}" if f_title else ""
                            await self._alog(f"🌐 Navigated to: {f_url}{clean_t}")

                    elif m == "Page.navigatedWithinDocument":
                        f_url = params.get("url", "")
                        if f_url and not f_url.startswith("data:"):
                            self._active_page_url = f_url

                    elif m == "Page.loadEventFired":
                        req_id_counter += 1
                        pending_evals[req_id_counter] = "title"
                        await ws.send(json.dumps({
                            "id": req_id_counter,
                            "method": "Runtime.evaluate",
                            "params": {"expression": "document.title"}
                        }))

                    # When a child iframe or worker attaches
                    elif m == "Target.attachedToTarget":
                        sub_sid = params.get("sessionId")
                        target_info = params.get("targetInfo", {})
                        t_type = target_info.get("type")
                        t_url = target_info.get("url", "")
                        if sub_sid:
                            req_id_counter += 1
                            await ws.send(json.dumps({
                                "id": req_id_counter,
                                "sessionId": sub_sid,
                                "method": "Network.enable"
                            }))
                            req_id_counter += 1
                            await ws.send(json.dumps({
                                "id": req_id_counter,
                                "sessionId": sub_sid,
                                "method": "Runtime.enable"
                            }))
                            if t_type in ("page", "iframe"):
                                req_id_counter += 1
                                await ws.send(json.dumps({
                                    "id": req_id_counter,
                                    "sessionId": sub_sid,
                                    "method": "Target.setAutoAttach",
                                    "params": {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}
                                }))
                                if t_url and not t_url.startswith("about:"):
                                    embed_domain = urlparse(t_url).netloc or t_url[:40]
                                    await self._alog(f"🔲 Video player iframe hooked: {embed_domain}")

                    # Hooked DOM media element console log
                    elif m == "Runtime.consoleAPICalled":
                        args = params.get("args", [])
                        for arg in args:
                            val = str(arg.get("value", ""))
                            if val.startswith("__HVD_MEDIA__:"):
                                media_url = val.replace("__HVD_MEDIA__:", "").strip()
                                if media_url.startswith("http"):
                                    await self._register_stream(media_url, src="media_element_hook")

                    # Direct Network Request
                    elif "Network.requestWillBeSent" in m:
                        req = params.get("request", {})
                        u = req.get("url", "")
                        headers = req.get("headers", {})
                        r_type = params.get("type", "")
                        if (STREAM_PATTERN.search(u) or r_type == "Media") and not IGNORED_PATTERNS.search(u):
                            ref = headers.get("Referer") or headers.get("referer") or ""
                            ua = headers.get("User-Agent") or headers.get("user-agent") or ""
                            await self._register_stream(u, ref, ua, src="request")

                    # Network Response
                    elif "Network.responseReceived" in m:
                        resp = params.get("response", {})
                        u = resp.get("url", "")
                        headers = resp.get("headers", {})
                        mime = (resp.get("mimeType") or "").lower()
                        req_id = params.get("requestId")

                        # If this is an AJAX sources response (e.g. getSources API), inspect body
                        u_lower = u.lower()
                        if any(k in u_lower for k in ("sources", "server", "get", "playlist", "stream", "ajax", "episode", "embed")):
                            if req_id:
                                req_id_counter += 1
                                ref = headers.get("referer") or headers.get("Referer") or u
                                pending_bodies[req_id_counter] = (ref, u)
                                cmd = {
                                    "id": req_id_counter,
                                    "method": "Network.getResponseBody",
                                    "params": {"requestId": req_id}
                                }
                                if sid:
                                    cmd["sessionId"] = sid
                                await ws.send(json.dumps(cmd))

                        if ("mpegurl" in mime or "dash" in mime or "video/" in mime) and not IGNORED_PATTERNS.search(u):
                            ref = headers.get("Referer") or headers.get("referer") or ""
                            ua = headers.get("User-Agent") or headers.get("user-agent") or ""
                            await self._register_stream(u, ref, ua, src=f"mime:{mime}")

        except Exception as e:
            logger.debug(f"Page listener {page_id} closed: {e}")
        finally:
            attached_pages.discard(page_id)

    async def _extract_streams_from_body(self, body_text: str, referer: str, api_url: str) -> None:
        """Parse JSON or text response body to extract stream URLs."""
        if not body_text:
            return

        # 1. Direct JSON parse
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                src = data.get("sources")
                if isinstance(src, str) and ("m3u8" in src or "mp4" in src):
                    await self._register_stream(src.replace("\\/", "/"), referer, src="api_body")
                elif isinstance(src, list):
                    for item in src:
                        if isinstance(item, dict):
                            f_url = item.get("file") or item.get("url")
                            if f_url:
                                await self._register_stream(f_url.replace("\\/", "/"), referer, src="api_body")
        except Exception:
            pass

        # 2. Regex fallback on raw body text
        matches = re.findall(r"https?://[^\s\"\'\\]+?\.(?:m3u8|mp4|mpd)[^\s\"\'\\]*", body_text)
        for m_url in matches:
            clean_url = m_url.replace("\\/", "/")
            await self._register_stream(clean_url, referer, src="api_body_regex")

    async def _register_stream(
        self, url: str, referer: str = "", user_agent: str = "", src: str = ""
    ) -> None:
        """Deduplicates, formats, and broadcasts captured video stream."""
        if not url or not url.startswith(("http://", "https://")):
            return

        # Skip fragments or tracking resources
        if IGNORED_PATTERNS.search(url):
            return

        # Clean key for deduplication
        clean_key = url.split("?")[0]
        if clean_key in self._seen_urls:
            return
        self._seen_urls.add(clean_key)

        is_hls = "m3u8" in url.lower() or "mpegurl" in src.lower()
        is_dash = ".mpd" in url.lower() or "dash" in src.lower()
        stream_type = "HLS Stream" if is_hls else ("DASH Stream" if is_dash else "Video Stream")

        domain = ""
        try:
            parsed = urlparse(referer if referer else url)
            domain = parsed.netloc
        except Exception:
            pass

        title = self._clean_stream_title(url, referer)
        stream_id = f"sniff_{uuid.uuid4().hex[:8]}"

        stream_entry = {
            "id": stream_id,
            "url": url,
            "title": title,
            "type": stream_type,
            "domain": domain,
            "referer": referer,
            "headers": {
                "Referer": referer,
                "User-Agent": user_agent,
            },
        }

        self._detected_streams.insert(0, stream_entry)
        if len(self._detected_streams) > 50:
            self._detected_streams.pop()

        # Log to terminal output
        await self._alog(f"🎬 CAPTURED {stream_type}: {title}")
        await self._alog(f"   ↳ URL: {url[:90]}...")
        if referer:
            await self._alog(f"   ↳ Referer: {referer[:80]}")

        # Broadcast instantly to connected frontend WebSocket clients
        if self._broadcast_cb:
            try:
                await self._broadcast_cb({
                    "type": "sniffer_stream",
                    "stream": stream_entry,
                })
            except Exception as e:
                logger.debug(f"Broadcast failed: {e}")

    @staticmethod
    def _polish_title(t: str) -> str:
        """Strip website branding, watch prefixes, and spam suffixes from page titles."""
        if not t:
            return ""
        t = re.sub(r"(?i)^watch\s+", "", t).strip()
        t = re.sub(r"(?i)\s*[-|–|:]\s*(?:aniwaves?|9anime|gogoanime|hianime|zoro|kickassanime|kisscartoon|fmovies|streamtape|megacloud|vidplay|vidstream).*$", "", t)
        t = re.sub(r"(?i)\s*(?:english sub(?:bed)?|english dub(?:bed)?|sub & dub|online free|free on \w+|free online|full hd|at \w+\.\w+).*$", "", t)
        return t.strip(" -:|–")

    def _clean_stream_title(self, url: str, referer: str) -> str:
        """Extract a readable anime / video title from the active page or URL."""
        # 1. Try polished active page title first
        if self._active_page_title:
            polished = self._polish_title(self._active_page_title)
            if len(polished) >= 4 and not re.match(r"^[a-f0-9]{20,}$", polished, re.I):
                return polished

        # 2. Try parsing active page URL or watch referer
        target = self._active_page_url or (referer if referer and "watch" in referer else url)
        try:
            path = unquote(urlparse(target).path).strip("/")
            parts = [p for p in path.split("/") if p]
            if parts:
                last = parts[-1].replace("_", "-")
                # If last segment is episode indicator e.g. ep-1, episode-12
                if any(k in last.lower() for k in ("ep", "episode", "chapter", "part")):
                    ep_match = re.search(r"(?:ep|episode)[-_]?(\d+)", last, re.I)
                    ep_str = f"Episode {ep_match.group(1)}" if ep_match else last.replace("-", " ").title()
                    if len(parts) >= 2:
                        series = parts[-2]
                        # Strip trailing internal IDs e.g. -78984
                        series = re.sub(r"-\d{4,}$", "", series)
                        series = series.replace("-", " ").title()
                        return f"{series} - {ep_str}"
                    return ep_str

                last_clean = last.replace("-", " ").title()
                if not re.match(r"^[a-f0-9]{20,}$", last, re.I):
                    return last_clean
        except Exception:
            pass

        return "Web Media Stream"

    def get_status(self) -> dict[str, Any]:
        """Return current status, captured streams, and recent log history."""
        return {
            "running": self.is_running,
            "port": self._port if self.is_running else None,
            "streams": self._detected_streams,
            "logs": self._recent_logs[-40:],
        }

    def clear_streams(self) -> None:
        """Clear detected streams list."""
        self._detected_streams.clear()
        self._seen_urls.clear()
        self._active_page_url = ""
        self._active_page_title = ""
        self._log("Stream list cleared.")

    def close(self) -> None:
        """Terminate the sniffer browser and monitor task cleanly."""
        self._cdp_alive = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None

        if self._proc:
            try:
                import psutil
                parent = psutil.Process(self._proc.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except Exception:
                        pass
                parent.kill()
            except Exception:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self._proc.pid)], capture_output=True)
                except Exception:
                    pass
            self._proc = None

        if self._profile_dir and self._profile_dir.exists():
            try:
                shutil.rmtree(self._profile_dir, ignore_errors=True)
            except Exception:
                pass
            self._profile_dir = None

    def shutdown(self) -> None:
        """Clean shutdown invoked when Horizon Downloader closes."""
        self.close()
