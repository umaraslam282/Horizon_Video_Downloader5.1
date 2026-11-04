# Horizon Video Downloader v5 — Development Progress Log
> Last updated: 2026-11-03

---

## 🎯 Project Goal
A portable, high-performance media downloader built with Python, Starlette ASGI, and WebSockets.
Integrates `yt-dlp` (videos/audio/playlists), `gallery-dl` (Instagram/Facebook/social), `deno` (JS runtime), and `ffmpeg` (muxing/converting).
Packaged as a standalone executable via PyInstaller and distributable setup installer via Inno Setup.

---

## 📁 Project Architecture & File Roles
```
Horizon_Video_Downloader5/
├── main.py              ← Single entry point: port resolution, starts Uvicorn, health probe, opens browser
├── server.py            ← Starlette ASGI app factory: routes, lifespan, CORS, static file serving
├── config.py            ← Paths, constants, frozen vs dev environment detection, settings load/save
├── download_manager.py  ← Process management, worker threads, yt-dlp execution, pause/resume, cancel
├── ws_manager.py        ← WebSocketManager: broadcast updates to all connected browser tabs
├── database.py          ← SQLite persistent history with WAL mode
├── backup.py            ← Automated clean project backup utility
├── routes/
│   ├── api.py           ← REST API: /api/download, /api/pause, /api/resume, /api/qrcode, /api/settings, etc.
│   └── ws.py            ← WebSocket endpoint (/ws)
├── static/
│   ├── index.html       ← Modern dark/neon SPA shell with QR modal, tabs, download queue
│   ├── css/style.css    ← Glassmorphism UI, themes (violet-cyan, spotify, crimson, amber, aurora)
│   ├── js/app.js        ← Reactive state, WebSocket handler, dynamic progress cards, settings sync
│   └── img/             ← App assets and icons
├── progress/
│   └── PROGRESS.md      ← Detailed ongoing progress and technical documentation
├── requirements.txt     ← starlette, uvicorn, psutil, qrcode, pillow
├── main.spec            ← PyInstaller build specification (production windowless build)
├── build.spec           ← Alternate PyInstaller spec (console enabled for debugging)
├── installer.iss        ← Inno Setup script generating HorizonDownloader_Setup_v5.exe
├── yt-dlp.exe           ← Extraction engine binary
├── ffmpeg.exe           ← Video/audio processing binary
├── ffprobe.exe          ← Media analysis binary
├── ffplay.exe           ← Media playback binary
├── deno.exe             ← Embedded JS runtime for yt-dlp YouTube visitor tokens
├── gallery-dl.exe       ← Embedded social media scraper binary
├── icon.ico             ← Application icon
├── cookie.txt           ← Optional Netscape cookies for authenticated/private downloads (gitignored)
└── history.db           ← SQLite history database (gitignored)
```

---

## ✅ Session 1: Scan, Initial Cleanup & Core Bug Fixes
1. **Directory Cleanup**:
   - Removed ~390 MB of test downloads, release setup EXEs/ZIPs, debug dumps, and compile caches.
2. **Removed Schedule / Auto-Shutdown Dead Code**:
   - Completely purged `scheduled_time` and `auto_shutdown` from the backend and database.
3. **Semaphore Synchronization**:
   - Fixed semaphore limit to use `MAX_CONCURRENT_DOWNLOADS` from `config.py` rather than hardcoded 3.
4. **Frozen Database Path**:
   - Fixed `database.py` to use `RUNTIME_DIR` instead of temp extraction directory.
5. **Serialization Completeness**:
   - Added missing fields (`subtitles`, `subtitle_lang`, `playlist`) to `DownloadTask.to_dict()`.
6. **Speed Metric Formatting**:
   - Fixed precision to show 2 decimals for MB/s and 1 decimal for GB/s.

---

## ✅ Session 2: Deep Fixes — QR Code, Complete Resume System & Compilation Setup

### 1. Robust QR Code & Local Mobile Transfer Functionality ✅
- **LAN Access Fix (`0.0.0.0` Binding)**:
  - In `config.py` & `main.py`, configured Uvicorn to bind to `0.0.0.0` (`BIND_HOST`) so mobile phones on the same Wi-Fi can connect.
  - Browser auto-open and health check safely use `127.0.0.1` (`LOCAL_HOST`).
- **Dynamic Port & IP Detection**:
  - `routes/api.py` now resolves outbound LAN IP via socket probe (with hostname fallback) and uses `request.url.port` (omits redundant port 80).
- **Missing File Path Fallback**:
  - `qrcode_transfer()` and `download_file()` now automatically fallback to `task.output_dir / task.filename` if `task.output_path` was not populated during raw streams.
- **Frontend QR Modal Overhaul**:
  - Fixed `#qr-modal`: removed conflicting `.hidden` class that blocked modal rendering.
  - Added direct URL input box with a one-click **Copy Link** button and click-outside-to-close behavior.
  - Added new backend endpoint `GET /api/transfer-info/{task_id}` providing clean JSON metadata for the modal.

### 2. Complete Resume Support System ✅
- **Dual-Mode Resumption in `download_manager.py`**:
  - **Live Process**: If the download was paused and the process is still alive in memory, `psutil` safely un-suspends the process tree.
  - **Dead / Failed / Errored Process**: If the process exited, crashed, or errored out, `resume_download()` automatically re-queues the task and spawns a fresh worker thread.
  - `yt-dlp` runs with `--continue` and automatically detects the existing `.part` file in `task.output_dir`, seamlessly picking up from where it was interrupted.
- **Frontend Retry Action**:
  - In `static/js/app.js`, errored download cards now display a **Retry / Resume** action button (Play icon). Clicking it triggers `/api/resume/{task_id}` to recover from network drops.
- **Zombie Process Prevention**:
  - In `_kill_process_tree()`, suspended processes are un-suspended before issuing kill signals to prevent Windows process handle leaks.

### 3. Server Settings Persistence on Disk ✅
- **`settings.json` Storage**:
  - Created `load_settings()` and `save_settings()` in `config.py` pointing to `RUNTIME_DIR / "settings.json"`.
  - Stored settings: `max_concurrent`, `dev_mode`, `output_dir`, `proxy`, `cookie_file`, `gpu_acceleration`.
- **API Endpoints**:
  - `GET /api/settings`: Returns persisted and active settings.
  - `POST /api/settings`: Updates in-memory settings (semaphore limit and dev mode) and writes to disk.
- **Client Sync on Launch**:
  - `static/js/app.js` fetches `/api/settings` on startup and syncs with `localStorage`, ensuring the backend and frontend are always aligned.

### 4. Non-Blocking Social Media Extraction ✅
- In `routes/api.py`, converted synchronous downloading loop in `download_social()` to run inside `await asyncio.to_thread()`.
- Downloading multiple social media media files no longer blocks the Starlette asyncio event loop or freezes WebSocket telemetry.

### 5. Production PyInstaller & Installer Alignment ✅
- **`main.spec` and `build.spec`**:
  - Bundles ALL 6 essential binaries: `yt-dlp.exe`, `deno.exe`, `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`, `gallery-dl.exe`.
  - Sets output distribution folder to `dist/HorizonDownloader/` and executable to `HorizonDownloader.exe`.
  - Accurately references `icon.ico` in root directory.
  - Includes comprehensive `hiddenimports` for `starlette`, `uvicorn`, `psutil`, `sqlite3`, `qrcode`, and `PIL`.
- Matches `installer.iss` 1-to-1 for Inno Setup compilation.

---

## ✅ Session 3: Instagram / Social Media Improvements & Environment Setup
1. **Requirements & Build Tools Installed**:
   - `starlette`, `uvicorn`, `psutil`, `qrcode`, `pillow`, and `pyinstaller 6.22` installed into Python 3.13.
2. **Fixed Instagram Duplicate Cards & Random Downloads**:
   - **Root Cause Found**: The legacy `extract_items` function recursively inspected every dictionary key in Instagram metadata. Because Instagram includes multiple resolution candidate arrays (`image_versions2.candidates`, `video_versions`), it was extracting up to 6 different resolution/thumbnail variants of the exact same video or photo, causing duplicate cards in the grid and duplicate downloads.
   - **Clean Parser**: Replaced recursive traversal with direct per-slide extraction. Each photo or carousel slide is extracted once at max resolution, uniquely identified by `post_id_num`.
   - **Video Poster Filter**: Automatically filters out image preview posters that belong to extracted videos.
   - **Fallback Engine**: Added automatic `yt-dlp` fallback if `gallery-dl` fails on an Instagram link.
   - **Stream-Chunked Downloader**: Converted `urlopen().read()` in `_execute_download_social` to 64 KB chunk streaming via `shutil.copyfileobj()`, eliminating socket timeouts and RAM spikes on large media.
   - **UI Polish**: Added live selection counter to the social action button (`DOWNLOAD SELECTED (N)`).

---

## ✅ Session 4: Production Build & Setup Installer Compilation
1. **PyInstaller Compilation**:
   - Packaged entire application into standalone directory distribution `dist/HorizonDownloader/`.
   - Included Python 3.13 runtime, Starlette ASGI server, Uvicorn, and all 6 auxiliary binaries (`yt-dlp.exe`, `deno.exe`, `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`, `gallery-dl.exe`).
   - Cleanly bundled all frontend web assets (`index.html`, `style.css`, `app.js`, `instagram_icon.jpg`, `icon.ico`).
2. **Inno Setup 7 Compilation**:
   - Compiled `installer.iss` using `ISCC.exe`.
   - Compression: LZMA2 ultra compression.
   - Generated final single-file Windows setup executable: `HorizonDownloader_Setup_v5.exe` (165,061,314 bytes / ~157.4 MB).
   - Setup executable is located at: `J:\Python Projects\Horizon_Video_Downloader5\HorizonDownloader_Setup_v5.exe`.
   - Installer automatically creates Desktop and Start Menu shortcuts, registers Windows Add/Remove Programs uninstaller, and launches `HorizonDownloader.exe` on finish.

---

## ✅ Session 5: Diagnosis & Fix — Offline Status & Console Behavior
1. **Root Cause Analysis**:
   - **Why "Offline" in top right**: Starlette + Uvicorn require either `websockets` or `wsproto` to handle WebSocket requests. Neither package was installed in the environment or specified in `requirements.txt`. Without a WebSocket backend, Uvicorn rejected `/ws` requests with `404 Not Found`, causing `app.js` to immediately trigger `ws.onclose()` and display "Offline".
   - **Why "Console immediately closed"**: `main.spec` previously had `console=False` (windowless GUI subsystem). When launched by double-clicking or from a launcher, Windows creates no console window (or immediately detaches the runner), leaving no visible application window except the browser tab. Additionally, non-ASCII Unicode characters (`│`, `═`, `→`) in `main.py` logging could trigger `UnicodeEncodeError` under Windows default terminal code pages (`cp1252`/`cp437`).
2. **Fixes Applied**:
   - **Installed & Bundled `websockets`**: Installed `websockets 17.4` in the Python 3.13 runtime, updated `requirements.txt`, and added `websockets` and `uvicorn.protocols.websockets` to `hiddenimports` in `main.spec` and `build.spec`.
   - **Verified WebSocket Handshake**: Handshake tests returned `HTTP/1.1 101 Switching Protocols`, and logs confirmed `WebSocket connected — 1 active` with status turning green `Live`.
   - **Enabled Active Console Window**: Set `console=True` in `main.spec` so a titled console window (`Horizon Video Downloader v5.0`) remains open. It shows the active port, Uvicorn startup, and live logs, allowing the user to confirm the server is running and exit cleanly with `Ctrl+C` or by closing the window.
   - **Sanitized Logging & Unicode Protection**: Replaced box-drawing and Unicode arrow characters with clean ASCII in `main.py`, and added `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.
   - **Inno Setup Auto-Close**: Added `CloseApplications=yes` to `installer.iss` so the installer gracefully terminates any older running instance before copying new files.
3. **Re-Compilation**:
   - PyInstaller compiled cleanly into `dist/HorizonDownloader/` with all 6 binaries and `websockets`.
   - Inno Setup 7 compiled final setup executable: `HorizonDownloader_Setup_v5.exe` (165,420,326 bytes).

---

## ✅ Session 6: Diagnosis & Fix — HTTP 403 Forbidden & Retry Loop
1. **Root Cause Analysis from Terminal Output**:
   - **Invalid/Rotated Cookie File**: The user provided a cookie file (`C:\Users\Omar\Downloads\yt.txt`) in Settings. yt-dlp reported: `WARNING: [youtube] The provided YouTube account cookies are no longer valid. They have likely been rotated in the browser as a security measure.` When GoogleVideo received expired session cookies, it refused video chunk downloads with `HTTP Error 403: Forbidden`.
   - **Blind 10-Retry Loop**: `download_manager.py` had `"ERROR: unable to download video data"` in `network_keywords`. It treated `403 Forbidden` as a transient connection drop and retried 10 times in a row with 5-second pauses (`[Network Drop Guard] Connection timeout/drop detected. Retry 1/10...`), endlessly repeating a failing request.
   - **Outdated Engine & Player Client**: `yt-dlp` was running on `2026.07.04`, which triggered 90-day obsolescence warnings and used the blocked `ANDROID_VR` client fallback.
2. **Fixes Applied**:
   - **Updated `yt-dlp` to `2026.10.26`**: Upgraded the engine binary directly from GitHub release to latest stable release. Verified clean download with JS challenges solved via bundled `deno.exe`.
   - **Automatic Cookie Fallback**: If a cookie file is provided and YouTube reports invalid cookies or returns `HTTP 403 Forbidden`, `download_manager.py` now logs an auth warning, strips `--cookies`, and immediately retries the download without cookies.
   - **Fixed Retry Loop Guard**: Excluded permanent 403 Forbidden / 401 Unauthorized / Private Video errors from `Network Drop Guard` so the application never gets trapped in infinite retry loops.
   - **Optimized YouTube Player Client**: Injected `--extractor-args "youtube:player_client=web,mweb,android"` and `--no-update` into `download_manager.py` and `config.py`.
3. **Re-Compilation**:
   - Rebuilt PyInstaller distribution with new `yt-dlp` binary.
   - Compiled Inno Setup installer: `HorizonDownloader_Setup_v5.exe` (170,789,006 bytes).

---

## ✅ Session 7: Fix & Verification — "Update yt-dlp" in Settings
1. **Why It Failed Previously**:
   - The legacy implementation ran `yt-dlp -U` via subprocess. Inside PyInstaller-frozen packages, yt-dlp's built-in self-updater (`-U`) cannot write directly over files in Windows protected directories and throws `ERROR: unable to write to executable` or times out.
   - Socket timeouts on large executable downloads from GitHub (~23.5 MB) were hitting rigid 60s cutoffs.
   - Windows prevents replacing an active executable directly (`[WinError 5] Access is denied`).
2. **Fixes Applied & Verified**:
   - **Direct GitHub Release Downloader**: `_run_ytdlp_update()` now fetches the latest binary directly from `https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe` with a 180s socket timeout and 128KB chunked streaming.
   - **Windows Atomic Replacement**: Uses the `.old` rename pattern to bypass Windows file locks cleanly.
   - **Dynamic Version Reporting**: Queries `--version` on the newly downloaded binary and returns the exact version string (`yt-dlp successfully updated to version 2026.10.26!`) to the user interface.
   - **Verified**: Tested the endpoint live; successfully downloaded and replaced `yt-dlp.exe` in under 8 seconds.
3. **Re-Compilation**:
   - Packaged with PyInstaller and compiled with Inno Setup 7: `HorizonDownloader_Setup_v5.exe` (170,783,431 bytes).

---

## ✅ Session 8: Fixes for 4K/Best Quality Selection, MKV Container Remux, & QR Code Generation

### 1. Root Causes & Fixes

1. **Low Quality (360p / Format 18 Fallback Instead of 4K/Best)**:
   - **Root Cause**: Previously, `--extractor-args "youtube:player_client=web,mweb,android"` was passed to yt-dlp. In yt-dlp `2026.10.26`, the `mweb` client triggered YouTube's strict GVS PO Token enforcement (`WARNING: mweb client https formats require a GVS PO Token... They will be skipped`). Because PO tokens were unavailable, yt-dlp skipped all separate high-definition adaptive video streams (`bv*` - 4K, 1440p, 1080p), falling back to legacy pre-merged format 18 (360p).
   - **Fix**: Removed the forced player client flag in `download_manager.py`. yt-dlp's default player clients (`tv samsung` and `visionos`) solve JS challenges cleanly with `deno.exe` and unlock formats 701 (4K 2160p60 HDR), 315 (4K 2160p60), 623 (1440p), and 299 (1080p) without PO Token requirements. Verified live: downloaded 4K 2160p HDR (`701+251`) at full speed.

2. **Container Format (.mp4 instead of .mkv)**:
   - **Root Cause**: yt-dlp's `--merge-output-format` only executes when merging split video and audio streams. If a pre-merged stream or single stream is downloaded, merger post-processing is skipped and the file keeps its default extension (`.mp4`).
   - **Fix**: Added `--remux-video task.video_format` (e.g. `--remux-video mkv`) in `download_manager.py`. With `--remux-video`, ffmpeg remuxes into the target container (`.mkv`) regardless of whether separate streams were merged or not.

3. **QR Code Transfer Stuck on "Generating..."**:
   - **Root Cause**: The downloaded video title contained a pipe character `|` (`On The Floor - Jenefer Lopes (Dance Cover) | Orangie Choreography`). Windows does not allow `|` in filenames, so yt-dlp converted it on disk to the fullwidth character `｜` (`\uff5c`). However, because yt-dlp ran under the default Windows console code page (`cp1252`), which cannot encode fullwidth `\uff5c`, yt-dlp output two spaces in its `HVD_FILEPATH:` line. This caused `task.output_path` and `task.filename` in the database to differ from the real disk file. When `_resolve_task_file()` checked `Path(task.output_path).exists()`, it returned `False` (`404: Completed file not found on disk`), causing the modal frontend to wait indefinitely.
   - **Fixes Applied**:
     - **Resilient File Stem Matcher**: Updated `_resolve_task_file()` in `routes/api.py` with fuzzy alphanumeric stem matching. It strips non-alphanumeric/fullwidth characters and matches against files in `output_dir`. Tested and verified that disk files containing `｜` are immediately resolved.
     - **UTF-8 Subprocess Output**: Added `PYTHONIOENCODING="utf-8"` to `subprocess.Popen` in `download_manager.py` so yt-dlp writes correct UTF-8 filenames to stdout without lossy character replacement.
     - **Frontend Error Handling**: Updated `_qr()` in `static/js/app.js` with proper `r.ok` checks and alert notifications so that if any network or file error occurs, the user is immediately notified rather than leaving the modal hanging.

---

## ✅ Session 9: Real-Time Download Speed/Progress Reporting & Admin UAC Elevation

### 1. Root Causes & Fixes Applied

1. **Stuck on "Finalizing video...", Missing Speed, and Disabled Pause/Cancel Buttons**:
   - **Root Cause 1 (`[SubtitlesConvertor]`)**: When subtitles were requested (`--write-subs`), `yt-dlp` downloaded and converted subtitles right at the start. `download_manager.py` treated `[SubtitlesConvertor]` as a converting state, immediately setting `task.status = "converting"`. In `static/js/app.js`, `status === 'converting'` hid the Pause and Cancel buttons, wiped the speed to empty, and set the label to *"Finalizing video..."* before the 233 MB video stream even began downloading.
   - **Root Cause 2 (Missing `--progress-template`)**: `download_manager.py` had a full JSON parser expecting `--progress-template "download:%(progress)j"`, but `--progress-template` was omitted from `_build_command()`. In the fallback parser, `task.status` was never set back to `"downloading"`, keeping the task trapped in the "converting" state throughout the entire download.
   - **Fixes Applied**:
     - Added `"--progress-template", "download:%(progress)j"` to `_build_command()` in `download_manager.py`.
     - Removed `[SubtitlesConvertor]` from converting keywords; only actual post-processing merges/conversions (`[Merger]`, `[VideoConvertor]`, `[VideoRemuxer]`, `[EmbedSubtitle]`, `[EmbedThumbnail]`, `[Metadata]`) trigger `"converting"`.
     - Ensured `task.status = "downloading"` is set whenever download progress chunks or destination announcements are received.
     - Added real-time 1-second live terminal progress broadcasts: `Progress: XX.X% | Speed: XX.XX MB/s | ETA: MM:SS • XXX.X MB`.
     - In `static/js/app.js`, kept the Cancel button active (`display: flex`) even during conversion so users are never locked out of cancelling.

2. **Compiled Executable Run As Administrator (`uac_admin`)**:
   - **Requirement**: Make the executable generated by PyInstaller and the Inno Setup installer run with administrator elevation by default.
   - **Fixes Applied**:
     - Added `uac_admin=True` to `main.spec` and `build.spec` in `EXE(...)`. PyInstaller embeds the Windows UAC manifest requiring `requireAdministrator` so `HorizonDownloader.exe` prompts for administrator elevation on double-click.
     - Updated `installer.iss` with `PrivilegesRequired=admin` to ensure both the setup installer and the installed shortcuts run with administrator privileges.

---

## ✅ Session 10: Milestone Backup, Social Download Fix & Unified Flat-Line Tile UI

### 1. Milestone Backups Created
- Created two clean milestone backups preserving the fully working YouTube setup (Single, Audio, Playlist, and QR code transfer all verified):
  1. `J:\Python Projects\complete vid downloader project`
  2. `J:\Python Projects\Horizon_Video_Downloader5_YT_COMPLETED_BACKUP`
- Both backups contain the clean source tree, binaries, and configurations while excluding transient cache files.

### 2. Social Media Batch Download Bug Fix
- **Root Cause**: In `routes/api.py`, `os.makedirs(out_path, exist_ok=True)` was called during batch Instagram/Facebook media downloads, but `import os` was missing from the file's imports, resulting in `Directory creation failed: name 'os' is not defined`.
- **Fix**: Added `import os` to top-level imports in `routes/api.py`. Verified clean import and execution.

### 3. Redesigned UI: Unified "Flat Line Tile" Layout
1. **Single Tab**:
   - **Clean Initial State**: When first opening the tab, only the URL bar and action buttons (Paste, Fetch Info) are displayed.
   - **Integrated Media Flat Tile**: Upon pasting or fetching a URL, an all-in-one horizontal glass tile (`#single-media-tile`) appears.
   - **All Metadata & Controls Unified Inside the Tile**:
     - Top row: 16:9 thumbnail with duration badge overlay, video title, channel name, and media status badge.
     - Controls row: Dynamic Resolution selector (populated with video's actual stream resolutions), Container Format selector (MP4/MKV/WebM), and Subtitle options.
     - Action button: Big `DOWNLOAD VIDEO` button positioned right inside the same unified flat tile.
     - Expandable "More options" accordion for bandwidth limits and time-range clipping.
2. **Playlist Tab**:
   - Transformed the multi-column card grid into a sleek vertical list of horizontal "flat line tiles" (tracklist style).
   - Each playlist item displays a checkbox, `#Index` badge, 16:9 thumbnail with duration overlay, video title, and uploader.
   - Click anywhere on a playlist tile to toggle selection.

---

## ✅ Session 11: Generous Playlist Tiles, Rich Metadata Integration & Full Inno Setup Build

### 1. Playlist Tile Proportion & Fit Redesign
- **Thumbnail Enlargement**: Expanded `.pl-thumb-wrap` to true 16:9 widescreen dimensions (`176px × 99px`) with subtle dark background and card shadow, completely eliminating cramped or letterboxed video previews.
- **Tile Sizing**: Increased `.pl-card` padding to `18px 24px`, minimum height to `125px`, and gap to `20px` to give content generous breathing room matching the Single tab flat tile.
- **Two-Line Title Clamp**: Formatted `.pl-card-title` with `1.02rem` font size, `1.45` line height, and `-webkit-line-clamp: 2` with `word-break: break-word` so video titles are never abruptly cut off.

### 2. Rich Metadata Row Under Video Title
- **Backend Enrichment**: Added `"view_count"` to `_fetch_playlist_info` in `routes/api.py`.
- **Frontend Rendering**: Updated `_renderPlaylistGrid` and `fmtViews` in `static/js/app.js` to render the complete `.pl-meta-row` beneath each playlist title:
  - Channel / Uploader Name (`.pl-channel`)
  - Separator Dot (`•`)
  - Video Duration (`.pl-dur-text`, supporting hours/minutes/seconds)
  - Formatted Views (`.pl-views`, e.g. `7.4M views`)
  - Index Accent Badge (`.pl-badge`, e.g. `Video #1`)

### 3. Complete Standalone & Installer Compilation
- **PyInstaller**: Built clean standalone binary package to `dist/HorizonDownloader/` (exit code 0).
- **Inno Setup**: Compiled production setup package `HorizonDownloader_Setup_v5.exe` (exit code 0).

---

## ✅ Session 12: Complete Social Media Suite Redesign (Instagram, TikTok, Twitter/X, FB, Reddit)

### 1. Unified Post Metadata & Social Cards
- **Backend Post Info Extraction**:
  - Upgraded `_parse_gallery_dl_output` and `_fetch_social_ytdlp_fallback` in `routes/api.py` to capture rich post-level metadata: platform, author username (`@username`), full name, full caption/description, like counts, dates, and permalinks.
- **Frontend Post Header Card**:
  - Injected `#social-post-card`: displays gradient creator avatar, verified full name, `@username`, platform pill badge, post date, formatted likes counter (`❤️ 32.6K`), and direct "View Original" link.
  - Caption container with highlighted hashtags (`#hashtag` in glowing accent color).

### 2. Multi-Media Gallery & Interactive Lightbox
- **Network Chips**: Added quick visual chips for Instagram, TikTok, Twitter/X, Facebook, Reddit, and Pinterest.
- **Unified Action Input**: Added inline `[ Input ] [ Paste ] [ Fetch Media ]` with animated loader ring.
- **Type Filter Pills**: Added `All (N)`, `Videos (N)`, and `Photos (N)` tabs with dynamic item counts.
- **Interactive Gallery Cards**:
  - 4:5 widescreen cards with type badges (`🎬 VIDEO`, `🖼️ PHOTO`, `🎬 REEL`) and slide tags (`Slide 1 of 5`).
  - Hover Action Overlay:
    - 👁️ **Preview**: Opens interactive lightbox modal with full HTML5 video player and high-res image view.
    - ⬇️ **Quick Download**: 1-click download of individual media items.
    - 📋 **Copy Link**: Copies direct CDN stream URL to clipboard.

### 3. Audio Extraction & File Organization
- **Reel/Video Audio Extractor**:
  - Added Segmented Mode toggle (`Media` vs `Extract Audio`).
  - Integrated FFmpeg audio extraction (`MP3`, `M4A`, `WAV`, `FLAC`, `OPUS`) directly from social video streams.
- **Smart File Naming & Folder Organization**:
  - Checkbox to organize downloads into `@creator` subfolders (`/Downloads/Instagram/@username/`).
  - Descriptive filenames (`Platform_username_caption_index.ext`) rather than generic timestamps.
- **Live Batch Progress**:
  - Live progress bar showing real-time batch download progress and count.

### 4. Build & Distribution
- **PyInstaller**: Recompiled into `dist_build/HorizonDownloader` (exit code 0).
- **Inno Setup**: Packaged into `HorizonDownloader_Setup_v5.exe` (exit code 0).

---

## 🚀 How to Run & Build

### Development Mode
```bash
# 1. Install dependencies
py -3 -m pip install starlette uvicorn psutil qrcode pillow

# 2. Launch application
py -3 main.py
```

### Build Frozen Standalone Executable
```bash
# Compile with PyInstaller
py -3 -m PyInstaller main.spec
```
Output directory: `dist/HorizonDownloader/`

### Generate Windows Setup Installer
Open `installer.iss` in **Inno Setup Compiler** and click **Compile** (or run `ISCC.exe installer.iss`).
Produces: `HorizonDownloader_Setup_v5.exe`.
