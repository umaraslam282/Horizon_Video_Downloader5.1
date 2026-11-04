# -*- mode: python ; coding: utf-8 -*-
"""
Horizon Video Downloader v5.2 — PyInstaller Spec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build command:
    pyinstaller main.spec

Produces a one-folder distribution at dist/HorizonDownloader/
containing HorizonDownloader.exe plus all bundled tools and assets.
"""

import os
from pathlib import Path

block_cipher = None
project_root = os.path.abspath(".")

# ── Bundled binaries ──────────────────────────────────────────────
# All executables required at runtime:
# yt-dlp: Media extractor engine
# deno: JavaScript execution environment for yt-dlp YouTube visitor tokens
# ffmpeg, ffprobe, ffplay: Audio/video conversion, merging and stream probing
# gallery-dl: Image and video extractor for Instagram, Facebook, etc.
binaries_to_bundle = [
    "yt-dlp.exe",
    "deno.exe",
    "ffmpeg.exe",
    "ffprobe.exe",
    "ffplay.exe",
    "gallery-dl.exe",
]

bundled_binaries = []
for binary_name in binaries_to_bundle:
    binary_path = os.path.join(project_root, binary_name)
    if os.path.exists(binary_path):
        bundled_binaries.append((binary_path, "."))

# ── Static frontend assets & metadata ────────────────────────────
bundled_data = []
static_dir = os.path.join(project_root, "static")
if os.path.isdir(static_dir):
    bundled_data.append((static_dir, "static"))

icon_file = os.path.join(project_root, "icon.ico")
if os.path.exists(icon_file):
    bundled_data.append((icon_file, "."))

# Cookies excluded from installer

# ── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=bundled_binaries,
    datas=bundled_data,
    hiddenimports=[
        # App Routes & Modules
        "routes",
        "routes.api",
        "routes.ws",
        "download_manager",
        "sniffer_manager",
        "ws_manager",
        "database",
        "config",
        # Uvicorn
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # WebSockets
        "websockets",
        "websockets.legacy",
        "websockets.legacy.server",
        "websockets.legacy.protocol",
        "websockets.asyncio",
        "websockets.asyncio.server",
        # Starlette
        "starlette",
        "starlette.applications",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.requests",
        "starlette.responses",
        "starlette.routing",
        "starlette.staticfiles",
        "starlette.websockets",
        # Builtins & Utilities
        "sqlite3",
        "psutil",
        "qrcode",
        "qrcode.image.pil",
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
        "pydoc",
        "doctest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Build ─────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HorizonDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Console disabled (windowless execution)
    icon=icon_file if os.path.exists(icon_file) else None,
    uac_admin=True,  # Always request administrator privileges
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HorizonDownloader",
)
