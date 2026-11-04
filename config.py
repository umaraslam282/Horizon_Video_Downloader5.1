"""
Horizon Video Downloader v3 — Configuration & Path Resolution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Handles PyInstaller frozen-state detection, bundled binary PATH
injection (yt-dlp + deno), port resolution, and global constants.

Imported first by main.py — the PATH mutation at module level
ensures every subprocess inherits the bundled binaries.
"""

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

# ── Application Metadata ──────────────────────────────────────────────
APP_NAME = "Horizon Video Downloader"
APP_VERSION = "5.2.0"
APP_ID = "hvd"

# ── Runtime Path Resolution ───────────────────────────────────────────
# PyInstaller sets sys.frozen = True and unpacks to sys._MEIPASS.
# In dev mode we resolve relative to this file's directory.
IS_FROZEN: bool = getattr(sys, "frozen", False)

BUNDLE_DIR: Path = (
    Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if IS_FROZEN
    else Path(__file__).resolve().parent
)

RUNTIME_DIR: Path = (
    Path(sys.executable).resolve().parent
    if IS_FROZEN
    else Path(__file__).resolve().parent
)

# ── Settings File (persisted on disk) ────────────────────────────────
SETTINGS_FILE: Path = RUNTIME_DIR / "settings.json"


def load_settings() -> dict[str, Any]:
    """Load persisted user settings from JSON file if available."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data: dict[str, Any]) -> bool:
    """Save or update user settings to JSON file."""
    try:
        current = load_settings()
        current.update(data)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception:
        return False


def resolve_and_convert_cookie(cookie_input: str | None = None) -> str | None:
    """
    Resolves cookie file path and automatically converts JSON cookies
    (e.g. from Chrome extensions) to Netscape format on the fly.
    """
    if not cookie_input:
        cookie_input = load_settings().get("cookie_file")
    if not cookie_input:
        for def_cand in [
            RUNTIME_DIR / "cookies.txt",
            BUNDLE_DIR / "cookies.txt",
            BUNDLE_DIR / "_internal" / "cookies.txt",
            RUNTIME_DIR / "_internal" / "cookies.txt",
            Path.cwd() / "cookies.txt",
        ]:
            if def_cand.exists() and def_cand.stat().st_size > 0:
                cookie_input = str(def_cand)
                break
    if not cookie_input:
        return None

    cpath = Path(cookie_input)
    if not cpath.is_absolute():
        for candidate in [
            RUNTIME_DIR / cookie_input,
            BUNDLE_DIR / cookie_input,
            BUNDLE_DIR / "_internal" / cookie_input,
            RUNTIME_DIR / "_internal" / cookie_input,
            Path(DEFAULT_DOWNLOAD_DIR) / cookie_input,
            Path.cwd() / cookie_input,
        ]:
            if candidate.exists():
                cpath = candidate
                break

    if not cpath.exists():
        return None

    # Check if file is JSON format
    try:
        with open(cpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()

        if content.startswith("[") or content.startswith("{"):
            data = json.loads(content)
            cookies_list = data if isinstance(data, list) else data.get("cookies", [])
            if isinstance(cookies_list, list) and len(cookies_list) > 0:
                netscape_file = cpath.with_name(f"{cpath.stem}.netscape.txt")
                with open(netscape_file, "w", encoding="utf-8") as out:
                    out.write("# Netscape HTTP Cookie File\n")
                    out.write("# Converted by Horizon Video Downloader\n\n")
                    for c in cookies_list:
                        if not isinstance(c, dict):
                            continue
                        domain = c.get("domain", "")
                        flag = "TRUE" if domain.startswith(".") else "FALSE"
                        path = c.get("path", "/")
                        secure = "TRUE" if c.get("secure") else "FALSE"
                        expiry = c.get("expirationDate") or c.get("expires") or c.get("expiry") or 0
                        expiry = int(float(expiry)) if expiry else 2147483647
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and domain:
                            out.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
                return str(netscape_file)
    except Exception:
        pass

    return str(cpath)


# ── PATH Injection (runs on import) ──────────────────────────────────
# Prepend the bundle directory to PATH so yt-dlp can auto-discover
# deno.exe (YouTube JS interpreter) and any other bundled tools.
os.environ["PATH"] = str(BUNDLE_DIR) + os.pathsep + os.environ.get("PATH", "")

# ── Binary Paths ─────────────────────────────────────────────────────
_ytdlp_local = BUNDLE_DIR / "yt-dlp.exe"
YTDLP_PATH: str = str(_ytdlp_local) if (_ytdlp_local.exists() or IS_FROZEN) else "yt-dlp"

# In dev mode, prefer a local ffmpeg.exe if it exists; otherwise fall back to
# the system PATH so developers without the bundled binary can still run.
_ffmpeg_local = BUNDLE_DIR / "ffmpeg.exe"
FFMPEG_PATH: str = str(_ffmpeg_local) if (_ffmpeg_local.exists() or IS_FROZEN) else "ffmpeg"

# ── Static Assets ────────────────────────────────────────────────────
STATIC_DIR: str = str(BUNDLE_DIR / "static")

# ── Download Defaults ────────────────────────────────────────────────
DEFAULT_DOWNLOAD_DIR: str = str(Path.home() / "Downloads")
MAX_CONCURRENT_DOWNLOADS: int = 10
OUTPUT_TEMPLATE: str = "%(title).200s.%(ext)s"

# ── Network ──────────────────────────────────────────────────────────
PREFERRED_PORTS: list[int] = [80, 8080, 8090, 9000]
BIND_HOST: str = "0.0.0.0"  # Listen on all interfaces so mobile/LAN can connect
LOCAL_HOST: str = "127.0.0.1"  # Loopback interface for browser & readiness check
HOST: str = BIND_HOST  # Kept for backward compatibility

# ── yt-dlp Resilience & Performance Flags ────────────────────────────
# Injected into every yt-dlp subprocess for fault tolerance & maximum throughput.
YTDLP_RESILIENCE_FLAGS: list[str] = [
    "--continue",
    "--retries", "infinite",
    "--fragment-retries", "infinite",
    "--retry-sleep", "2",
    "--ignore-errors",
    "--no-update",
    "--concurrent-fragments", "8",
]

# ── Windows Subprocess Flags ─────────────────────────────────────────
# Prevents console windows from flashing when spawning yt-dlp.
SUBPROCESS_FLAGS: int = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def find_available_port() -> int:
    """
    Probe preferred ports in order and return the first available one.
    Checks user-specified port in settings.json first if defined.
    Falls back to an OS-assigned ephemeral port if none are free.
    """
    settings = load_settings()
    custom_port = settings.get("preferred_port")
    ports_to_check = []
    if custom_port:
        try:
            cp = int(custom_port)
            if 1 <= cp <= 65535:
                ports_to_check.append(cp)
        except Exception:
            pass
    for p in PREFERRED_PORTS:
        if p not in ports_to_check:
            ports_to_check.append(p)

    for port in ports_to_check:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((BIND_HOST, port))
                return port
        except OSError:
            continue

    # Fallback: let the OS pick an ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((BIND_HOST, 0))
        return sock.getsockname()[1]
