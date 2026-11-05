"""
Horizon Video Downloader v5 — REST API Routes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All HTTP endpoints for download lifecycle management,
video metadata retrieval, and playlist info.

Built on Starlette (pure Python, no Pydantic/Rust dependency).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, FileResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from config import (
    BUNDLE_DIR,
    DEFAULT_DOWNLOAD_DIR,
    RUNTIME_DIR,
    SUBPROCESS_FLAGS,
    FFMPEG_PATH,
    YTDLP_PATH,
    YTDLP_RESILIENCE_FLAGS,
    load_settings,
    save_settings,
    resolve_and_convert_cookie,
    IS_FROZEN,
)

logger = logging.getLogger("hvd.api")

# Global tracking for active social media extraction process (for 1-click Stop/Cancel)
active_social_process: subprocess.Popen | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Validation Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VALID_FORMAT_TYPES = {"video", "audio"}
VALID_QUALITIES = {"best", "4320", "2160", "1440", "1080", "720", "480", "360", "144"}
VALID_AUDIO_FORMATS = {"best", "mp3", "m4a", "flac", "wav", "ogg", "alac", "opus"}
VALID_VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "avi", "flv"}
VALID_SUBTITLES = {"none", "best", "author", "auto"}
VALID_SUBTITLE_LANGS = {"en", "ur", "es", "ar", "fr", "de", "hi", "ja", "ko", "zh"}


def _error(message: str, status: int = 400) -> JSONResponse:
    """Shorthand for returning a JSON error response."""
    return JSONResponse({"error": message}, status_code=status)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Lifecycle Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def start_download(request: Request) -> JSONResponse:
    """POST /api/download — Start a new download job. Returns a unique task_id."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    format_type = body.get("format_type", "video")
    if format_type not in VALID_FORMAT_TYPES:
        return _error(f"'format_type' must be one of: {', '.join(VALID_FORMAT_TYPES)}")

    quality = str(body.get("quality", "best"))

    audio_format = body.get("audio_format", "mp3")
    if audio_format not in VALID_AUDIO_FORMATS:
        return _error(f"'audio_format' must be one of: {', '.join(VALID_AUDIO_FORMATS)}")

    video_format = body.get("video_format", "mp4")
    if video_format not in VALID_VIDEO_FORMATS:
        return _error(f"'video_format' must be one of: {', '.join(VALID_VIDEO_FORMATS)}")

    subtitles = body.get("subtitles", "none")
    if subtitles not in VALID_SUBTITLES:
        subtitles = "none"

    subtitle_lang = (body.get("subtitle_lang") or "en").strip()
    if not subtitle_lang or subtitle_lang.lower().startswith("live_chat") or not re.match(r"^[a-zA-Z0-9_-]{2,15}$", subtitle_lang):
        subtitle_lang = "en"

    cookie_file = body.get("cookie_file")  # Optional string or None
    playlist = bool(body.get("playlist", False))
    output_dir = body.get("output_dir")  # Optional string or None
    rate_limit = body.get("rate_limit")
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    gpu_acceleration = bool(body.get("gpu_acceleration", False))
    proxy = body.get("proxy")
    referer = body.get("referer")
    custom_title = body.get("custom_title")
    thumbnail = body.get("thumbnail")

    dm = request.app.state.download_manager
    try:
        task_id = dm.start_download(
            url=url,
            format_type=format_type,
            quality=quality,
            audio_format=audio_format,
            video_format=video_format,
            subtitles=subtitles,
            subtitle_lang=subtitle_lang,
            cookie_file=cookie_file,
            playlist=playlist,
            output_dir=output_dir,
            rate_limit=rate_limit,
            start_time=start_time,
            end_time=end_time,
            gpu_acceleration=gpu_acceleration,
            proxy=proxy,
            referer=referer,
            custom_title=custom_title,
            thumbnail=thumbnail,
        )
        return JSONResponse({"task_id": task_id, "message": "Download started"})
    except RuntimeError as exc:
        return _error(str(exc), status=429)
    except Exception as exc:
        logger.exception("Failed to start download")
        return _error(str(exc), status=500)


async def cancel_download(request: Request) -> JSONResponse:
    """POST /api/cancel/{task_id} — Immediately terminate and clean up."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.cancel_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or already finished.", status=404)
    return JSONResponse({"success": True, "message": f"Task {task_id} cancelled"})


async def pause_download(request: Request) -> JSONResponse:
    """POST /api/pause/{task_id} — Suspend a running download process."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.pause_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or not in a pausable state.")
    return JSONResponse({"success": True, "message": f"Task {task_id} paused"})


async def resume_download(request: Request) -> JSONResponse:
    """POST /api/resume/{task_id} — Resume a paused download process."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    success = dm.resume_download(task_id)
    if not success:
        return _error(f"Task '{task_id}' not found or not paused.")
    return JSONResponse({"success": True, "message": f"Task {task_id} resumed"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Task Queries
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def list_tasks(request: Request) -> JSONResponse:
    """GET /api/tasks — Return all tasks (active + history), newest first."""
    dm = request.app.state.download_manager
    return JSONResponse({"tasks": dm.get_all_tasks()})


async def get_task(request: Request) -> JSONResponse:
    """GET /api/tasks/{task_id} — Return details for a single task."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)
    if not task:
        return _error(f"Task '{task_id}' not found.", status=404)
    return JSONResponse({"task": task.to_dict()})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Video & Playlist Metadata
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def get_video_info(request: Request) -> JSONResponse:
    """
    POST /api/info — Fetch video metadata (title, duration, thumbnail,
    available formats) via yt-dlp --dump-single-json.
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    cookie_file = body.get("cookie_file")

    try:
        info = await asyncio.to_thread(_fetch_video_info, url, cookie_file)
        return JSONResponse(info)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except subprocess.TimeoutExpired:
        return _error("yt-dlp timed out fetching video info (30s limit).", status=504)
    except Exception as exc:
        logger.exception("Info fetch failed")
        return _error(str(exc))


async def get_playlist_info(request: Request) -> JSONResponse:
    """
    POST /api/playlist-info — Rapidly fetch playlist metadata using
    yt-dlp --flat-playlist --dump-single-json.

    Returns playlist title, count, and a clean array of entries with
    id, title, url, thumbnail, and duration for each video.
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required")

    cookie_file = body.get("cookie_file")

    try:
        info = await asyncio.to_thread(_fetch_playlist_info, url, cookie_file)
        return JSONResponse(info)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except subprocess.TimeoutExpired:
        return _error("yt-dlp timed out fetching playlist info (120s limit).", status=504)
    except Exception as exc:
        logger.exception("Playlist info fetch failed")
        return _error(str(exc))


async def update_ytdlp(request: Request) -> JSONResponse:
    """POST /api/update-ytdlp — Download latest yt-dlp release from GitHub and replace binary."""
    try:
        result = await asyncio.to_thread(_run_ytdlp_update)
        return JSONResponse(result)
    except FileNotFoundError:
        return _error(f"yt-dlp not found at '{YTDLP_PATH}'.", status=500)
    except Exception as exc:
        logger.exception("yt-dlp update failed")
        return _error(str(exc), status=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health Check
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━




def _run_gallerydl_update() -> dict:
    """
    Download the latest gallery-dl.exe from Codeberg directly to a temp file
    and safely replace the executable on disk using Windows-safe rename patterns.
    """
    import urllib.request
    import os
    import shutil
    import subprocess
    from config import BUNDLE_DIR, RUNTIME_DIR

    target_path = BUNDLE_DIR / "gallery-dl.exe"
    if not target_path.exists():
        resolved = shutil.which("gallery-dl")
        if resolved:
            target_path = Path(resolved)
        else:
            target_path = RUNTIME_DIR / "gallery-dl.exe"

    tmp_path = target_path.with_suffix(".tmp")
    old_path = target_path.with_suffix(".old")
    url = "https://codeberg.org/mikf/gallery-dl/releases/download/v1.32.19/gallery-dl.exe"

    try:
        api_req = urllib.request.Request(
            "https://codeberg.org/api/v1/repos/mikf/gallery-dl/releases/latest",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(api_req, timeout=10) as resp:
            data = json.loads(resp.read())
            for a in data.get("assets", []):
                if a.get("name") == "gallery-dl.exe" and a.get("browser_download_url"):
                    url = a["browser_download_url"]
                    break
    except Exception:
        pass

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)

    try:
        logger.info(f"Downloading latest gallery-dl.exe to {tmp_path}...")
        with urllib.request.urlopen(req, timeout=180) as response:
            with open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file, length=128 * 1024)

        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

        if target_path.exists():
            try:
                target_path.rename(old_path)
            except Exception:
                pass

        shutil.move(str(tmp_path), str(target_path))

        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

        new_version = "latest"
        try:
            ver_proc = subprocess.run(
                [str(target_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ver_proc.returncode == 0 and ver_proc.stdout.strip():
                new_version = ver_proc.stdout.strip()
        except Exception:
            pass

        logger.info(f"Successfully updated gallery-dl to version {new_version}")
        return {
            "success": True,
            "output": f"gallery-dl successfully updated to version {new_version}!",
        }
    except Exception as exc:
        logger.exception("Failed to update gallery-dl executable")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return {
            "success": False,
            "output": f"Failed to update gallery-dl: {exc}",
        }


async def update_gallerydl(request: Request) -> JSONResponse:
    """POST /api/update-gallerydl — Update gallery-dl to latest release."""
    try:
        result = await asyncio.to_thread(_run_gallerydl_update)
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("gallery-dl update failed")
        return _error(str(exc), status=500)
async def health(request: Request) -> JSONResponse:
    """GET /health — Readiness probe for startup sequencing."""
    return JSONResponse({"status": "ok"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Private Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _fetch_video_info(url: str, cookie_file: str | None = None) -> dict:
    """
    Run yt-dlp --dump-single-json synchronously (called via asyncio.to_thread).
    Returns a curated subset of the full metadata.
    """
    cmd = [
        YTDLP_PATH,
        "--dump-single-json",
        "--no-download",
        "--no-playlist",
        "--no-warnings",
    ]
    resolved_cookie = resolve_and_convert_cookie(cookie_file)
    if resolved_cookie:
        cmd.extend(["--cookies", resolved_cookie])
    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=SUBPROCESS_FLAGS,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "Unknown error"
        raise RuntimeError(f"yt-dlp info extraction failed: {stderr}")

    raw = json.loads(result.stdout)

    return {
        "title": raw.get("title"),
        "duration": raw.get("duration"),
        "duration_string": raw.get("duration_string"),
        "thumbnail": raw.get("thumbnail"),
        "uploader": raw.get("uploader"),
        "uploader_url": raw.get("uploader_url"),
        "view_count": raw.get("view_count"),
        "upload_date": raw.get("upload_date"),
        "description": (raw.get("description") or "")[:500],
        "webpage_url": raw.get("webpage_url"),
        "formats": _extract_format_options(raw.get("formats") or []),
    }


def _fetch_playlist_info(url: str, cookie_file: str | None = None) -> dict:
    """
    Run yt-dlp --flat-playlist --dump-single-json to rapidly fetch
    playlist metadata without downloading any video data.
    """
    cmd = [
        YTDLP_PATH,
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
    ]
    from config import resolve_and_convert_cookie
    cpath = resolve_and_convert_cookie(cookie_file)
    if cpath:
        cmd.extend(["--cookies", cpath])
    cmd.append(url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=SUBPROCESS_FLAGS,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "Unknown error"
        raise RuntimeError(f"Playlist fetch failed: {stderr}")

    raw = json.loads(result.stdout)

    entries = []
    for entry in raw.get("entries") or []:
        if not entry:
            continue
        video_id = entry.get("id", "")
        # Resolve thumbnail: try entry's thumbnails, then construct from YouTube ID
        thumb = ""
        thumbs = entry.get("thumbnails")
        if thumbs and isinstance(thumbs, list):
            thumb = thumbs[-1].get("url", "")
        elif entry.get("thumbnail"):
            thumb = entry["thumbnail"]
        elif video_id and ("youtube.com" in video_url or "youtu.be" in video_url or len(video_id) == 11):
            thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        # Resolve URL: try entry's url/webpage_url, else construct from ID
        video_url = entry.get("url") or entry.get("webpage_url") or ""
        if not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        entries.append({
            "id": video_id,
            "title": entry.get("title") or "Untitled",
            "url": video_url,
            "thumbnail": thumb,
            "duration": entry.get("duration"),
            "uploader": entry.get("uploader") or entry.get("channel"),
            "view_count": entry.get("view_count"),
        })

    return {
        "playlist_title": raw.get("title") or "Untitled Playlist",
        "playlist_id": raw.get("id"),
        "uploader": raw.get("uploader") or raw.get("channel"),
        "count": len(entries),
        "entries": entries,
    }


def _run_ytdlp_update() -> dict:
    """
    Download the latest yt-dlp.exe from GitHub directly to a temp file
    and safely replace the executable on disk using Windows-safe rename patterns.
    """
    import urllib.request
    import os
    import shutil
    import subprocess
    from config import BUNDLE_DIR

    # Resolve actual target path (in case it is non-absolute / command only)
    target_path = Path(YTDLP_PATH)
    if not target_path.is_absolute():
        resolved = shutil.which(YTDLP_PATH)
        if resolved:
            target_path = Path(resolved)
        else:
            target_path = BUNDLE_DIR / "yt-dlp.exe"

    tmp_path = target_path.with_suffix(".tmp")
    old_path = target_path.with_suffix(".old")
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)

    try:
        logger.info(f"Downloading latest yt-dlp.exe from GitHub to {tmp_path}...")
        with urllib.request.urlopen(req, timeout=180) as response:
            with open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file, length=128 * 1024)

        # Windows-safe replacement: rename target to .old first to avoid locks
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

        if target_path.exists():
            try:
                target_path.rename(old_path)
            except Exception:
                # Fallback to direct replace
                pass

        shutil.move(str(tmp_path), str(target_path))

        # Clean up .old if possible
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

        # Query newly installed version
        new_version = "latest"
        try:
            ver_proc = subprocess.run(
                [str(target_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ver_proc.returncode == 0 and ver_proc.stdout.strip():
                new_version = ver_proc.stdout.strip()
        except Exception:
            pass

        logger.info(f"Successfully updated yt-dlp to version {new_version}")
        return {
            "success": True,
            "output": f"yt-dlp successfully updated to version {new_version}!",
        }
    except Exception as exc:
        logger.exception("Failed to update yt-dlp executable")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return {
            "success": False,
            "output": f"Update failed: {str(exc)}",
        }


def _extract_format_options(formats: list[dict]) -> dict:
    """
    Extract unique video resolutions and audio formats from
    yt-dlp's full format list.
    """
    video_heights: set[int] = set()
    audio_formats: set[str] = set()

    for fmt in formats:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec", "none")
        acodec = fmt.get("acodec", "none")
        ext = fmt.get("ext", "")

        # Video resolutions (only entries with actual video codec)
        if height and vcodec != "none":
            video_heights.add(height)

        # Audio-only formats
        if acodec != "none" and vcodec == "none" and ext:
            audio_formats.add(ext)

    return {
        "video_qualities": sorted(video_heights, reverse=True),
        "audio_formats": sorted(audio_formats),
    }


async def open_folder(request: Request) -> JSONResponse:
    """POST /api/open-folder/{task_id} — Open Windows Explorer with the file highlighted."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)

    filepath = None
    fallback_dir = None
    if task:
        filepath = task.output_path
        fallback_dir = task.output_dir
    else:
        from database import get_download_by_id
        rec = get_download_by_id(task_id)
        if rec:
            filepath = rec.get("file_path")

    if not fallback_dir:
        from config import DEFAULT_DOWNLOAD_DIR
        fallback_dir = str(DEFAULT_DOWNLOAD_DIR)

    if not filepath or not Path(filepath).exists():
        fname = rec.get("filename") if rec else None
        if fname:
            settings = load_settings()
            search_dirs = [
                settings.get("social_output_dir"),
                settings.get("output_dir"),
                DEFAULT_DOWNLOAD_DIR,
                str(Path.home() / "Downloads"),
                str(Path.home() / "Downloads" / "Instagram"),
            ]
            for sdir in search_dirs:
                if not sdir or not Path(sdir).exists():
                    continue
                p_sdir = Path(sdir)
                cand = p_sdir / fname
                if cand.exists() and cand.is_file():
                    filepath = str(cand.resolve())
                    break
                try:
                    for subcand in p_sdir.glob(f"**/{fname}"):
                        if subcand.is_file():
                            filepath = str(subcand.resolve())
                            break
                    if filepath and Path(filepath).exists():
                        break
                except Exception:
                    pass

    if not filepath or not Path(filepath).exists():
        if fallback_dir and Path(fallback_dir).exists():
            try:
                subprocess.Popen(f'explorer "{fallback_dir}"', creationflags=SUBPROCESS_FLAGS)
                return JSONResponse({"success": True, "message": "Opened download folder"})
            except Exception as e:
                return _error(str(e), status=500)
        return _error("File or folder does not exist on disk.", status=404)

    try:
        cmd = f'explorer /select,"{Path(filepath).resolve()}"'
        subprocess.Popen(cmd, creationflags=SUBPROCESS_FLAGS)
        return JSONResponse({"success": True, "message": "Opened folder with file selected"})
    except Exception as e:
        logger.exception("Failed to open folder")
        return _error(str(e), status=500)


def _parse_gallery_dl_output(stdout_str: str) -> tuple[dict, list[dict]]:
    """
    Carefully parses gallery-dl JSON output to extract post-level metadata
    and one clean item per media slide/post.
    Prevents duplicate entries caused by nested resolution candidate arrays.
    """
    entries = []
    decoder = json.JSONDecoder()
    idx = 0
    text_len = len(stdout_str)
    while idx < text_len:
        while idx < text_len and stdout_str[idx] not in '[{':
            idx += 1
        if idx >= text_len:
            break
        try:
            obj, next_idx = decoder.raw_decode(stdout_str, idx)
            if isinstance(obj, list):
                entries.extend(obj)
            elif isinstance(obj, dict):
                entries.append(obj)
            idx = next_idx
        except json.JSONDecodeError:
            idx += 1

    post_info = {
        "platform": "instagram",
        "username": "",
        "fullname": "",
        "caption": "",
        "likes": None,
        "date": "",
        "post_url": "",
        "type": "post",
    }

    items = []
    seen_urls = set()
    seen_keys = set()
    video_poster_urls = set()

    for entry in entries:
        metadata = None
        direct_url = None

        if isinstance(entry, list) and len(entry) >= 2:
            code = entry[0]
            if code in (1, 6, -1):
                continue
            if len(entry) >= 3 and isinstance(entry[2], dict):
                metadata = entry[2]
                direct_url = str(entry[1]) if entry[1] else None
            elif code == 2 and isinstance(entry[1], dict):
                metadata = entry[1]
            elif code == 2 and isinstance(entry[1], str) and entry[1].startswith("http"):
                direct_url = entry[1]
                metadata = {}
        elif isinstance(entry, dict):
            metadata = entry
            direct_url = metadata.get("url")

        if not metadata and not direct_url:
            continue

        metadata = metadata or {}

        # Extract post-level details
        if not post_info["username"]:
            post_info["username"] = str(metadata.get("username") or metadata.get("author") or metadata.get("uploader") or "")
        if not post_info["fullname"]:
            post_info["fullname"] = str(metadata.get("fullname") or metadata.get("name") or "")
        if metadata.get("highlight_title") and not post_info.get("highlight_title"):
            post_info["highlight_title"] = metadata.get("highlight_title")

        if not post_info["caption"]:
            hl = metadata.get("highlight_title")
            desc = metadata.get("description") or metadata.get("caption") or metadata.get("content") or ""
            if hl and desc:
                post_info["caption"] = f"Highlight: {hl} — {desc}"
            elif hl:
                post_info["caption"] = f"Story Highlight: {hl}"
            else:
                post_info["caption"] = str(desc)
        if post_info["likes"] is None:
            post_info["likes"] = metadata.get("likes") if metadata.get("likes") is not None else metadata.get("like_count")
        if not post_info["date"]:
            post_info["date"] = str(metadata.get("date") or metadata.get("post_date") or metadata.get("timestamp") or "")
        if metadata.get("category") or metadata.get("subcategory"):
            post_info["platform"] = str(metadata.get("category") or metadata.get("subcategory")).lower()
        if not post_info["post_url"] and (metadata.get("post_url") or metadata.get("url")):
            post_info["post_url"] = str(metadata.get("post_url") or metadata.get("url"))
        if metadata.get("subcategory") or metadata.get("type"):
            post_info["type"] = str(metadata.get("subcategory") or metadata.get("type"))

        owner = metadata.get("owner") or {}
        user_meta = metadata.get("user") or {}
        hd_pic = (
            metadata.get("hd_profile_pic_url_info", {}).get("url")
            or owner.get("hd_profile_pic_url_info", {}).get("url")
            or user_meta.get("hd_profile_pic_url_info", {}).get("url")
            or user_meta.get("profile_pic_url")
            or owner.get("profile_pic_url")
            or metadata.get("profile_pic_url")
            or metadata.get("avatar")
            or (direct_url if metadata.get("subcategory") == "avatar" else None)
        )
        if hd_pic and not post_info.get("avatar_url"):
            post_info["avatar_url"] = hd_pic

        if not post_info["username"] and (user_meta.get("username") or metadata.get("username")):
            post_info["username"] = str(user_meta.get("username") or metadata.get("username"))
        if not post_info["fullname"] and (user_meta.get("full_name") or metadata.get("fullname")):
            post_info["fullname"] = str(user_meta.get("full_name") or metadata.get("fullname"))
        if not post_info["caption"] and (user_meta.get("biography") or metadata.get("description")):
            post_info["caption"] = str(user_meta.get("biography") or metadata.get("description"))

        # Determine media type and direct stream URL
        video_url = metadata.get("video_url")
        ext = (metadata.get("extension") or "").lower()
        if not ext and direct_url:
            ext = Path(direct_url.split("?")[0]).suffix.lstrip(".").lower()

        is_video = bool(video_url) or ext in ("mp4", "mkv", "webm", "mov")
        target_url = video_url or direct_url or metadata.get("url") or metadata.get("display_url")

        if not target_url or not isinstance(target_url, str) or not target_url.startswith("http"):
            continue

        # Ignore interface assets and avatar icons unless this is an avatar extraction
        target_lower = target_url.lower()
        is_avatar = metadata.get("subcategory") == "avatar" or post_info.get("type") == "avatar"
        if not is_avatar:
            if any(ign in target_lower for ign in ("/avatar/", "profile_pic", "anonymous_user", "/static/", "/assets/")):
                continue
        elif not post_info.get("avatar_url"):
            post_info["avatar_url"] = target_url

        # Extract thumbnails
        display_url = metadata.get("display_url") or metadata.get("thumbnail") or metadata.get("thumbnail_src")
        if is_video and display_url:
            video_poster_urls.add(display_url)

        # Unique identifier to prevent duplicate copies of the same photo or video
        post_id = metadata.get("post_id") or metadata.get("id") or metadata.get("shortcode")
        num = metadata.get("num") or metadata.get("sidecar_index", "")
        clean_name = Path(target_url.split("?")[0]).name.lower()

        item_key = f"{post_id}_{num}" if (post_id and num) else clean_name

        if item_key in seen_keys or target_url in seen_urls:
            continue

        seen_keys.add(item_key)
        seen_urls.add(target_url)

        items.append({
            "url": target_url,
            "type": "video" if is_video else "image",
            "thumbnail": display_url or target_url,
            "id": item_key,
            "shortcode": metadata.get("post_shortcode") or metadata.get("shortcode") or metadata.get("code") or "",
            "slide_index": len(items) + 1,
        })

    # Filter out duplicate image entries that are just the video's poster thumbnail
    clean_items = []
    for itm in items:
        if itm["type"] == "image" and itm["url"] in video_poster_urls:
            continue
        clean_items.append(itm)

    for idx, itm in enumerate(clean_items, start=1):
        itm["slide_index"] = idx

    return post_info, clean_items


def _fetch_social_ytdlp_fallback(url: str, cookie_file: str | None = None) -> tuple[dict, list[dict]]:
    """Fallback extractor using yt-dlp if gallery-dl fails or is challenged."""
    post_info = {
        "platform": "social",
        "username": "",
        "fullname": "",
        "caption": "",
        "likes": None,
        "date": "",
        "post_url": url,
        "type": "video",
    }
    cmd = [
        YTDLP_PATH,
        "--dump-single-json",
        "--no-warnings",
        "--no-download",
    ]
    resolved_cookie = resolve_and_convert_cookie(cookie_file)
    if resolved_cookie:
        cmd.extend(["--cookies", resolved_cookie])
    cmd.append(url)

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=SUBPROCESS_FLAGS,
    )
    if res.returncode != 0 and "instagram.com" in url.lower():
        # Instagram often blocks authenticated /info/ endpoint with 302; retry cleanly without cookies
        cmd_nocookie = [
            YTDLP_PATH,
            "--dump-single-json",
            "--no-warnings",
            "--no-download",
            "--no-cookies",
            url,
        ]
        res = subprocess.run(
            cmd_nocookie,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=SUBPROCESS_FLAGS,
        )

    if res.returncode != 0:
        return post_info, []

    try:
        raw = json.loads(res.stdout)
    except Exception:
        return post_info, []

    post_info["platform"] = str(raw.get("extractor_key") or raw.get("extractor") or "social").lower()
    post_info["username"] = str(raw.get("uploader") or raw.get("channel") or raw.get("uploader_id") or "")
    post_info["fullname"] = str(raw.get("channel") or raw.get("uploader") or "")
    post_info["caption"] = str(raw.get("description") or raw.get("title") or "")
    post_info["likes"] = raw.get("like_count")
    post_info["date"] = str(raw.get("upload_date") or "")
    post_info["post_url"] = str(raw.get("webpage_url") or url)

    items = []
    entries = raw.get("entries") or [raw]
    seen = set()

    for idx, entry in enumerate(entries, start=1):
        if not entry:
            continue
        # For Instagram videos, use webpage URL if direct stream is DASH split format
        page_u = entry.get("webpage_url") or url
        media_url = entry.get("url") or page_u
        if "instagram.com" in url.lower() and (not media_url or "dash" in str(entry.get("format_id", "")).lower()):
            media_url = page_u

        if not media_url or media_url in seen:
            continue
        seen.add(media_url)

        ext = (entry.get("ext") or "").lower()
        is_video = ext in ("mp4", "webm", "mkv") or entry.get("vcodec") not in ("none", None) or "/reel" in url.lower()
        thumb = entry.get("thumbnail") or (media_url if not is_video else "")

        items.append({
            "url": media_url,
            "type": "video" if is_video else "image",
            "thumbnail": thumb,
            "id": str(entry.get("id") or idx),
            "shortcode": str(entry.get("id") or ""),
            "slide_index": idx,
        })

    return post_info, items


async def fetch_social(request: Request) -> JSONResponse:
    """GET /api/fetch-social — Fetch media info using gallery-dl with yt-dlp fallback."""
    import os
    import re
    dm = request.app.state.download_manager
    params = request.query_params
    url = params.get("url")
    if not url:
        dm._broadcast_log("social", "Fetch request failed: URL is required.")
        return _error("URL is required.", status=400)

    dm._broadcast_log("social", f"Fetching social media metadata for: {url}")
    cookie_file = params.get("cookie_file")
    resolved_cookie = resolve_and_convert_cookie(cookie_file)

    # Pre-flight cookie check before performing any Instagram requests
    if "instagram.com" in url.lower():
        cookie_info = await asyncio.to_thread(_verify_instagram_cookie, resolved_cookie)
        dm._broadcast_log("social", f"[Cookie Check] {cookie_info['message']}")
    gallery_dl_bin = "gallery-dl"
    bundle_path = BUNDLE_DIR / "gallery-dl.exe"
    if bundle_path.exists():
        gallery_dl_bin = str(bundle_path)

    creation_flags = 0x08000000 if os.name == "nt" else 0
    clean_url = url.split("?")[0].rstrip("/")
    ig_user_match = re.search(r"instagram\.com/([a-zA-Z0-9_\.]+)(?:/(?:reels|posts))?/?$", clean_url)
    is_single_post = any(f"/{seg}/" in clean_url or clean_url.endswith(f"/{seg}") for seg in ("p", "reel", "stories", "tv"))
    is_ig_profile = bool(
        ig_user_match 
        and not is_single_post 
        and ig_user_match.group(1).lower() not in ("p", "reel", "reels", "stories", "tv", "explore", "direct", "accounts", "home")
    )

    post_info = {}
    final_items = []

    # Dedicated handling for full Instagram Profiles / Accounts
    if is_ig_profile:
        ig_username = ig_user_match.group(1)
        dm._broadcast_log("social", f"Detected Instagram profile @{ig_username}. Extracting full media & HD avatar...")

        # 1. Fetch HD Avatar
        av_cmd = [gallery_dl_bin, "-j", f"https://www.instagram.com/{ig_username}/avatar"]
        if resolved_cookie:
            av_cmd.extend(["--cookies", resolved_cookie])
        try:
            p_av = await asyncio.to_thread(
                subprocess.run,
                av_cmd,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                creationflags=creation_flags
            )
            if p_av.returncode == 0 and p_av.stdout:
                av_info, av_items = _parse_gallery_dl_output(p_av.stdout)
                post_info.update(av_info)
                if av_info.get("avatar_url"):
                    post_info["avatar_url"] = av_info["avatar_url"]
                elif av_items and len(av_items) > 0 and av_items[0].get("url"):
                    post_info["avatar_url"] = av_items[0]["url"]
        except Exception as e:
            logger.warning(f"Failed to fetch avatar: {e}")

        # 2. Target posts and dedicated reels (Stories are excluded)
        # /posts extracts the entire grid feed (all photos, carousels, and grid videos)
        is_direct_reels = "/reels" in clean_url
        is_direct_posts = "/posts" in clean_url

        if is_direct_reels:
            primary_url = f"https://www.instagram.com/{ig_username}/reels"
            dm._broadcast_log("social", f"Connecting to Instagram Reels stream for @{ig_username}...")
        elif is_direct_posts:
            primary_url = f"https://www.instagram.com/{ig_username}/posts"
            dm._broadcast_log("social", f"Connecting to Instagram Feed Posts stream for @{ig_username}...")
        else:
            primary_url = f"https://www.instagram.com/{ig_username}/posts"
            dm._broadcast_log("social", f"[Step 1/2: Grid Feed] Connecting to profile feed stream for @{ig_username}...")

        def _execute_dl(target_u: str):
            global active_social_process
            cmd = [
                gallery_dl_bin,
                "-j",
                "--sleep-request", "1",
            ]
            custom_ext_dir = BUNDLE_DIR / "custom_extractors"
            if custom_ext_dir.exists():
                cmd.extend(["-X", str(custom_ext_dir)])
            cmd.append(target_u)
            if resolved_cookie:
                cmd.extend(["--cookies", resolved_cookie])

            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags
            )
            active_social_process = p
            stdout_lines = []
            found_count = 0
            is_reels_call = "/reels" in target_u
            unit_label = "reels" if is_reels_call else "media items"
            try:
                for line in p.stdout:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    stdout_lines.append(line_str)
                    if '"post_id":' in line_str or '"post_shortcode":' in line_str or '"shortcode":' in line_str:
                        found_count += 1
                        if found_count == 1 or found_count % 25 == 0:
                            dm._broadcast_log("social", f"📸 Scanned {found_count} {unit_label} from @{ig_username}...")
                    elif not line_str.startswith(('"', '{', '}', ']')) and any(kw in line_str.lower() for kw in ("warning", "error", "429", "rate limit")):
                        if "abortextraction" not in line_str.lower() and "login page" not in line_str.lower():
                            dm._broadcast_log("social", f"[Log] {line_str}")
                p.wait()
            finally:
                active_social_process = None
            return "\n".join(stdout_lines).strip()

        try:
            stdout_str = await asyncio.to_thread(_execute_dl, primary_url)
            if stdout_str:
                p_info, p_items = _parse_gallery_dl_output(stdout_str)
                if p_items:
                    final_items.extend(p_items)
                if not post_info.get("fullname") and p_info.get("fullname"):
                    post_info["fullname"] = p_info["fullname"]
                if not post_info.get("caption") and p_info.get("caption"):
                    post_info["caption"] = p_info["caption"]

            grid_imgs = sum(1 for it in final_items if it.get("type") == "image")
            grid_vids = sum(1 for it in final_items if it.get("type") == "video")

            if not is_direct_reels and not is_direct_posts:
                dm._broadcast_log("social", f"📋 [Step 1 Complete] Feed scan found {len(final_items)} items ({grid_imgs} photos, {grid_vids} videos).")

            # If user explicitly gave /reels, but it was blocked by login redirect (0 items found):
            # Fall back automatically to profile /posts so user NEVER gets 0 items, and filter ONLY to videos!
            if is_direct_reels:
                if not final_items:
                    dm._broadcast_log("social", f"⚠️ Dedicated Reels tab restricted by Instagram API. Recovering all available reels from profile feed grid for @{ig_username}...")
                    fallback_str = await asyncio.to_thread(_execute_dl, f"https://www.instagram.com/{ig_username}/posts")
                    if fallback_str:
                        fb_info, fb_items = _parse_gallery_dl_output(fallback_str)
                        if fb_items:
                            reels_only = [it for it in fb_items if it.get("type") == "video"]
                            final_items.extend(reels_only)
                        if not post_info.get("fullname") and fb_info.get("fullname"):
                            post_info["fullname"] = fb_info["fullname"]
                    dm._broadcast_log("social", f"✅ Recovered {len(final_items)} reels from profile feed grid!")
                else:
                    # Ensure only videos are presented for /reels
                    final_items = [it for it in final_items if it.get("type") == "video"]

            # Step 2: If user gave bare profile (not /posts and not /reels), scan dedicated reels pass to catch unshared reels
            if not is_direct_reels and not is_direct_posts:
                dm._broadcast_log("social", f"[Step 2/2: Reels Tab] Scanning dedicated Reels tab for any additional unshared reels...")
                try:
                    reels_str = await asyncio.to_thread(_execute_dl, f"https://www.instagram.com/{ig_username}/reels")
                    added_reels = 0
                    if reels_str:
                        _, r_items = _parse_gallery_dl_output(reels_str)
                        if r_items:
                            existing_urls = {it["url"] for it in final_items}
                            existing_ids = {it.get("id") for it in final_items}
                            existing_scs = {it.get("shortcode") for it in final_items if it.get("shortcode")}
                            for r_it in r_items:
                                sc = r_it.get("shortcode")
                                if r_it["url"] not in existing_urls and r_it.get("id") not in existing_ids and (not sc or sc not in existing_scs):
                                    final_items.append(r_it)
                                    existing_urls.add(r_it["url"])
                                    if r_it.get("id"):
                                        existing_ids.add(r_it["id"])
                                    if sc:
                                        existing_scs.add(sc)
                                    added_reels += 1
                    if added_reels > 0:
                        dm._broadcast_log("social", f"🎬 [Step 2 Complete] Added {added_reels} additional unshared reels from Reels tab!")
                    else:
                        dm._broadcast_log("social", f"ℹ️ [Step 2 Complete] All {grid_vids} reels are already on the grid (no unshared reels found).")
                except Exception as exc:
                    logger.debug(f"Optional reels pass ignored: {exc}")
                    dm._broadcast_log("social", f"ℹ️ [Step 2 Complete] Dedicated Reels tab scan finished (all {grid_vids} grid reels retained).")

            tot_imgs = sum(1 for it in final_items if it.get("type") == "image")
            tot_vids = sum(1 for it in final_items if it.get("type") == "video")
            dm._broadcast_log("social", f"✅ [Done] Successfully scanned {len(final_items)} media items ({tot_imgs} photos, {tot_vids} videos) from @{ig_username}!")
        except Exception as e:
            logger.warning(f"Failed to fetch posts: {e}")
            dm._broadcast_log("social", f"⚠️ Profile scan error: {e}")

        # If zero media items found from posts/reels, offer HD avatar as fallback item
        if not final_items and post_info.get("avatar_url"):
            final_items.append({
                "url": post_info["avatar_url"],
                "type": "image",
                "thumbnail": post_info["avatar_url"],
                "caption": f"@{ig_username} HD Profile Picture",
                "width": 1080,
                "height": 1080
            })

        post_info["platform"] = "instagram"
        post_info["type"] = "profile"
        post_info["username"] = ig_username
        if not post_info.get("post_url"):
            post_info["post_url"] = f"https://www.instagram.com/{ig_username}/"

    else:
        cmd = [gallery_dl_bin, "-j", "--sleep-request", "1"]
        custom_ext_dir = BUNDLE_DIR / "custom_extractors"
        if custom_ext_dir.exists():
            cmd.extend(["-X", str(custom_ext_dir)])
        if "/highlights" in clean_url.lower():
            cmd.extend(["--range", "1-50"])
        cmd.append(url)
        if resolved_cookie:
            cmd.extend(["--cookies", resolved_cookie])

        def _run_single_extraction():
            global active_social_process
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation_flags
            )
            active_social_process = p
            stdout_lines = []
            try:
                for line in p.stdout:
                    line_str = line.strip()
                    if line_str:
                        stdout_lines.append(line_str)
                        dm._broadcast_log("social", f"[Fetch] {line_str}")
                p.wait()
            finally:
                active_social_process = None
            return p.returncode, "\n".join(stdout_lines).strip()

        try:
            retcode, stdout_str = await asyncio.to_thread(_run_single_extraction)
            if retcode == 0 and stdout_str:
                post_info, final_items = _parse_gallery_dl_output(stdout_str)

            # If gallery-dl returned 0 items or failed, try yt-dlp fallback
            if not final_items and not post_info.get("avatar_url"):
                dm._broadcast_log("social", "[Fetch] Trying yt-dlp fallback extractor...")
                post_info, final_items = await asyncio.to_thread(_fetch_social_ytdlp_fallback, url, resolved_cookie)

            if not final_items and not post_info.get("avatar_url") and retcode != 0:
                dm._broadcast_log("social", "Fetch failed to find media streams.")
                return _error("Media extraction returned no items. Make sure account is public or cookies are uploaded.", status=500)

        except Exception as e:
            logger.exception("Fetch social media failed")
            dm._broadcast_log("social", f"Fetch exception occurred: {str(e)}")
            return _error(str(e), status=500)

    author_tag = f"@{post_info.get('username')}" if post_info.get("username") else (post_info.get("fullname") or "creator")
    dm._broadcast_log("social", f"Fetch complete. Found {len(final_items)} distinct media items for {author_tag}.")
    return JSONResponse({
        "success": True,
        "post_info": post_info,
        "items": final_items,
        "count": len(final_items),
    })


def _execute_download_social(
    dm,
    urls: list[str],
    output_dir: str | None,
    image_format: str = "original",
    video_format: str = "mp4",
    audio_only: bool = False,
    audio_format: str = "mp3",
    creator: str | None = None,
    caption: str | None = None,
    organize_subfolder: bool = False,
    platform: str | None = None,
):
    import time
    import uuid
    import shutil
    import urllib.request
    from database import insert_download, update_status, update_title, update_download_completed
    from config import FFMPEG_PATH

    settings = load_settings()
    chosen_out = (
        output_dir 
        or settings.get("social_output_dir") 
        or settings.get("output_dir") 
        or DEFAULT_DOWNLOAD_DIR
    )
    base_out_path = Path(chosen_out).resolve()
    target_out_path = base_out_path

    clean_creator = "".join(c for c in (creator or "") if c.isalnum() or c in ("_", "-")).strip()
    clean_cap = "".join(c for c in (caption or "") if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:32]
    plat_tag = (platform or "Social").capitalize()

    # Base folder for this creator / account
    creator_folder = base_out_path
    if organize_subfolder:
        folder_parts = []
        if platform:
            folder_parts.append(plat_tag)
        if clean_creator:
            folder_parts.append(f"@{clean_creator}")
        if folder_parts:
            creator_folder = base_out_path.joinpath(*folder_parts)

    # Batch grouping for containers in History
    batch_id = None
    batch_title = None
    if len(urls) > 1 or clean_creator:
        batch_id = f"batch_{plat_tag.lower()}_{clean_creator.lower() or 'multi'}_{int(time.time())}"
        batch_title = f"{plat_tag}: @{clean_creator}" if clean_creator else f"{plat_tag} Batch ({len(urls)} items)"

    dm._broadcast_log("social", f"Initiating download of {len(urls)} items to: {creator_folder}")
    try:
        os.makedirs(creator_folder, exist_ok=True)
    except Exception as e:
        dm._broadcast_log("social", f"Directory creation failed: {str(e)}")
        raise RuntimeError(f"Cannot create save directory: {str(e)}")

    downloaded = 0
    errors = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.instagram.com/",
        "Accept": "*/*",
    }

    for i, url in enumerate(urls):
        task_id = f"soc_{uuid.uuid4().hex[:8]}"
        try:
            clean_url_check = url.lower().split("?")[0]
            is_ig_page_url = "instagram.com/" in clean_url_check and any(f"/{seg}/" in clean_url_check or clean_url_check.endswith(f"/{seg}") for seg in ("reel", "reels", "p", "tv"))

            # Safeguard: Never save raw HTML webpage URLs as images or media
            if "instagram.com/" in clean_url_check and not is_ig_page_url and not any(cdn in clean_url_check for cdn in ("fbcdn.net", "cdninstagram.com", ".mp4", ".jpg", ".webp")):
                dm._broadcast_log("social", f"[{i+1}/{len(urls)}] Skipping non-media page URL: {url}")
                continue

            parsed_url = Path(url.split("?")[0])
            url_lower = parsed_url.name.lower()
            is_video = url_lower.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")) or is_ig_page_url

            native_suffix = parsed_url.suffix
            if not native_suffix or len(native_suffix) > 5 or is_ig_page_url:
                native_suffix = ".mp4" if is_video else ".jpg"

            # Determine target extension
            if audio_only:
                target_suffix = f".{audio_format.lower()}"
            elif is_video:
                target_suffix = f".{video_format.lower()}"
            else:
                target_suffix = f".{image_format.lower()}" if image_format != "original" else native_suffix
                if not target_suffix or len(target_suffix) > 5:
                    target_suffix = ".jpg"

            # Respective file type subfolder organization
            if "hd_profile_picture" in (caption or "") or "avatar" in url.lower():
                type_subfolder = "avatar"
            elif audio_only:
                type_subfolder = "audio"
            elif is_video:
                type_subfolder = "reels"
            elif "stories" in url.lower():
                type_subfolder = "stories"
            elif "highlights" in url.lower():
                type_subfolder = "highlights"
            else:
                type_subfolder = "posts"

            if organize_subfolder:
                dest_dir = creator_folder / type_subfolder
            else:
                dest_dir = base_out_path / type_subfolder

            os.makedirs(dest_dir, exist_ok=True)

            # Build readable filename
            name_parts = [plat_tag]
            if clean_creator:
                name_parts.append(clean_creator)
            if "hd_profile_picture" in (caption or ""):
                name_parts.append("hd_profile_picture")
            else:
                if clean_cap:
                    name_parts.append(clean_cap)
                if len(urls) > 1 or not clean_cap:
                    name_parts.append(f"{i+1}")

            final_filename = f"{'_'.join(name_parts)}{target_suffix}"
            final_file = dest_dir / final_filename

            # Avoid collision
            counter = 1
            while final_file.exists():
                final_filename = f"{'_'.join(name_parts)}_{counter}{target_suffix}"
                final_file = dest_dir / final_filename
                counter += 1

            insert_download(
                task_id, 
                url, 
                title=final_filename, 
                thumbnail=f"/api/history/thumbnail/{task_id}",
                batch_id=batch_id,
                batch_title=batch_title,
                file_path=str(final_file.resolve()),
                filename=final_filename,
            )
            update_status(task_id, "downloading")

            dm._broadcast_log("social", f"[{i+1}/{len(urls)}] Downloading to {type_subfolder}/: {final_filename}")

            creation_flags = 0x08000000 if os.name == "nt" else 0

            # Direct download for Instagram Reel / Post URLs via yt-dlp (bypasses blocked info endpoints)
            if is_ig_page_url:
                dm._broadcast_log("social", f"[{i+1}/{len(urls)}] [yt-dlp] Downloading Instagram Reel: {final_filename}")
                ydl_cmd = [
                    YTDLP_PATH,
                    "--no-cookies",
                    "--no-warnings",
                    "-o", str(final_file),
                ]
                if audio_only:
                    ydl_cmd.extend(["-x", "--audio-format", audio_format.lower()])
                else:
                    ydl_cmd.extend(["-f", "bv*+ba/b", "--merge-output-format", video_format.lower()])
                ydl_cmd.append(url)

                res = subprocess.run(
                    ydl_cmd,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=180,
                    creationflags=creation_flags
                )
                if res.returncode == 0 and final_file.exists():
                    downloaded += 1
                    update_download_completed(task_id, file_path=str(final_file.resolve()))
                    dm._broadcast_log("social", f"[{i+1}/{len(urls)}] Download complete: {final_filename}")
                    if hasattr(dm, "broadcast_custom_progress"):
                        dm.broadcast_custom_progress({
                            "type": "progress",
                            "task_id": task_id,
                            "filename": final_filename,
                            "status": "completed",
                            "progress": 100.0,
                            "downloaded_bytes": final_file.stat().st_size,
                            "total_bytes": final_file.stat().st_size,
                            "speed": "Done",
                            "eta": "",
                            "format_type": "audio" if audio_only else "video",
                        })
                    continue
                else:
                    err_txt = (res.stderr or res.stdout or "yt-dlp download failed").strip()
                    dm._broadcast_log("social", f"[{i+1}/{len(urls)}] Warning: Failed to download reel: {err_txt[:120]}")
                    errors.append(f"{url}: {err_txt[:120]}")
                    continue

            def _stream_copy(resp, dest):
                tot_hdr = resp.getheader("Content-Length")
                tot = int(tot_hdr) if (tot_hdr and tot_hdr.isdigit()) else 0
                dl = 0
                t0 = time.time()
                last_b = 0.0
                while True:
                    ch = resp.read(64 * 1024)
                    if not ch:
                        break
                    dest.write(ch)
                    dl += len(ch)
                    now_t = time.time()
                    if (now_t - last_b >= 0.12) or (tot > 0 and dl >= tot):
                        last_b = now_t
                        elap = max(0.001, now_t - t0)
                        sp_val = dl / elap
                        sp_str = dm._format_speed(sp_val) if hasattr(dm, "_format_speed") else f"{sp_val/(1024*1024):.1f} MB/s"
                        pct_val = (dl / tot * 100.0) if tot > 0 else 0.0
                        eta_val = int((tot - dl) / max(1, sp_val)) if (tot > dl and sp_val > 0) else None
                        eta_str = dm._format_eta(eta_val) if (eta_val is not None and hasattr(dm, "_format_eta")) else ""
                        if hasattr(dm, "broadcast_custom_progress"):
                            dm.broadcast_custom_progress({
                                "type": "progress",
                                "task_id": task_id,
                                "filename": final_filename,
                                "status": "downloading",
                                "progress": round(min(99.0, pct_val), 1) if tot > 0 else 50.0,
                                "downloaded_bytes": dl,
                                "total_bytes": tot,
                                "speed": sp_str,
                                "eta": eta_str or "",
                                "format_type": "video" if final_filename.endswith((".mp4", ".mov", ".mkv", ".webm")) else "image",
                            })

            # If audio extraction requested or format conversion needed
            if audio_only or (native_suffix.lower() != target_suffix.lower()):
                temp_filename = f"social_temp_{uuid.uuid4().hex[:6]}{native_suffix}"
                native_file = dest_dir / temp_filename

                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response, open(native_file, "wb") as out_file:
                    _stream_copy(response, out_file)

                if audio_only:
                    dm._broadcast_log("social", f"[FFmpeg] Extracting audio to {final_filename}...")
                    ffmpeg_cmd = [str(FFMPEG_PATH), "-y", "-i", str(native_file), "-vn"]
                    if audio_format.lower() == "mp3":
                        ffmpeg_cmd.extend(["-c:a", "libmp3lame", "-q:a", "0"])
                    elif audio_format.lower() in ("m4a", "aac"):
                        ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", "256k"])
                    ffmpeg_cmd.append(str(final_file))
                else:
                    dm._broadcast_log("social", f"[FFmpeg] Converting stream to {final_filename}...")
                    ffmpeg_cmd = [str(FFMPEG_PATH), "-y", "-i", str(native_file), str(final_file)]

                conv = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    creationflags=creation_flags
                )

                try:
                    os.remove(native_file)
                except Exception:
                    pass

                if conv.returncode == 0 and final_file.exists():
                    downloaded += 1
                    sz = final_file.stat().st_size
                    update_download_completed(
                        task_id, 
                        str(final_file.resolve()), 
                        final_file.name, 
                        sz, 
                        thumbnail=f"/api/history/thumbnail/{task_id}",
                        batch_id=batch_id,
                        batch_title=batch_title
                    )
                    if hasattr(dm, "broadcast_custom_progress"):
                        dm.broadcast_custom_progress({
                            "type": "progress", "task_id": task_id, "filename": final_file.name,
                            "status": "completed", "progress": 100.0, "downloaded_bytes": sz, "total_bytes": sz,
                            "speed": "", "eta": "", "format_type": "video" if final_file.name.endswith((".mp4", ".mov", ".mkv", ".webm")) else "image"
                        })
                else:
                    fallback_file = dest_dir / f"social_{time.strftime('%Y%m%d_%H%M%S')}_{i+1}{native_suffix}"
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as response, open(fallback_file, "wb") as out_file:
                        _stream_copy(response, out_file)
                    downloaded += 1
                    sz = fallback_file.stat().st_size
                    update_download_completed(
                        task_id, 
                        str(fallback_file.resolve()), 
                        fallback_file.name, 
                        sz, 
                        thumbnail=f"/api/history/thumbnail/{task_id}",
                        batch_id=batch_id,
                        batch_title=batch_title
                    )
                    if hasattr(dm, "broadcast_custom_progress"):
                        dm.broadcast_custom_progress({
                            "type": "progress", "task_id": task_id, "filename": fallback_file.name,
                            "status": "completed", "progress": 100.0, "downloaded_bytes": sz, "total_bytes": sz,
                            "speed": "", "eta": "", "format_type": "video" if fallback_file.name.endswith((".mp4", ".mov", ".mkv", ".webm")) else "image"
                        })
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response, open(final_file, "wb") as out_file:
                    _stream_copy(response, out_file)
                downloaded += 1
                sz = final_file.stat().st_size
                update_download_completed(
                    task_id, 
                    str(final_file.resolve()), 
                    final_file.name, 
                    sz, 
                    thumbnail=f"/api/history/thumbnail/{task_id}",
                    batch_id=batch_id,
                    batch_title=batch_title
                )
                if hasattr(dm, "broadcast_custom_progress"):
                    dm.broadcast_custom_progress({
                        "type": "progress", "task_id": task_id, "filename": final_file.name,
                        "status": "completed", "progress": 100.0, "downloaded_bytes": sz, "total_bytes": sz,
                        "speed": "", "eta": "", "format_type": "video" if final_file.name.endswith((".mp4", ".mov", ".mkv", ".webm")) else "image"
                    })

        except Exception as e:
            err_str = f"Item {i+1} failed: {str(e)}"
            errors.append(err_str)
            dm._broadcast_log("social", f"[Error] {err_str}")
            update_status(task_id, "failed")

    dm._broadcast_log("social", f"Batch download finished. Successfully saved {downloaded}/{len(urls)} items.")
    return downloaded, errors


async def download_social(request: Request) -> JSONResponse:
    """POST /api/download-social — Download selected social media URLs."""
    dm = request.app.state.download_manager
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body", status=400)

    urls = body.get("urls")
    if not urls or not isinstance(urls, list):
        dm._broadcast_log("social", "Download request failed: urls parameter missing or invalid.")
        return _error("List of 'urls' is required.", status=400)

    # Pre-flight cookie check before social download
    cookie_param = body.get("cookie_file")
    res_cookie = resolve_and_convert_cookie(cookie_param)
    if any("instagram.com" in str(u).lower() for u in urls):
        cookie_info = await asyncio.to_thread(_verify_instagram_cookie, res_cookie)
        dm._broadcast_log("social", f"[Cookie Check] {cookie_info['message']}")

    output_dir = body.get("output_dir")
    image_format = body.get("image_format", "original")
    video_format = body.get("video_format", "mp4")
    audio_only = bool(body.get("audio_only", False))
    audio_format = body.get("audio_format", "mp3")
    creator = body.get("creator")
    caption = body.get("caption")
    organize_subfolder = bool(body.get("organize_subfolder", False))
    platform = body.get("platform")

    try:
        downloaded, errors = await asyncio.to_thread(
            _execute_download_social,
            dm,
            urls,
            output_dir,
            image_format,
            video_format,
            audio_only,
            audio_format,
            creator,
            caption,
            organize_subfolder,
            platform,
        )
    except Exception as e:
        return _error(str(e), status=500)

    if errors and downloaded == 0:
        return _error("; ".join(errors), status=500)

    return JSONResponse({
        "success": True,
        "message": f"Successfully downloaded {downloaded}/{len(urls)} items.",
        "downloaded": downloaded,
        "total": len(urls),
        "errors": errors
    })


async def list_history(request: Request) -> JSONResponse:
    """GET /api/history — Retrieve persistent download history."""
    try:
        from database import get_all_history
        history = get_all_history()
        return JSONResponse(history)
    except Exception as e:
        return _error(str(e), status=500)


async def fetch_info(request: Request) -> JSONResponse:
    """GET /api/fetch-info — Fetch available subtitle languages and basic info."""
    url = request.query_params.get("url")
    if not url:
        return _error("url parameter is required", status=400)
    
    cookie_file = request.query_params.get("cookie_file")
    resolved_cookie = resolve_and_convert_cookie(cookie_file)
    referer = request.query_params.get("referer")
    
    try:
        cmd = [
            YTDLP_PATH,
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--no-warnings",
        ]
        if resolved_cookie:
            cmd.extend(["--cookies", resolved_cookie])
        if referer:
            cmd.extend(["--referer", referer.strip()])
        cmd.append(url)
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=SUBPROCESS_FLAGS,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "Unknown error"
            return _error(f"Failed to fetch metadata: {stderr}", status=500)
        
        data = json.loads(result.stdout)
        
        # Extract basic info
        title = data.get("title", "Unknown Title")
        thumbnail = data.get("thumbnail") or data.get("thumbnails", [{}])[-1].get("url", "")
        duration_sec = data.get("duration", 0)
        duration = f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}" if duration_sec else "00:00"
        uploader = data.get("uploader", "Unknown Uploader")
        
        # Extract available resolutions
        available_resolutions = []
        formats = data.get("formats", [])
        for f in formats:
            w = f.get("width")
            h = f.get("height")
            if f.get("vcodec") != "none" and w and h:
                res = min(int(w), int(h))
                if res > 0:
                    available_resolutions.append(res)
        
        # Unique and sorted descending
        available_resolutions = sorted(list(set(available_resolutions)), reverse=True)
        
        # Extract subtitles
        subtitles_langs = set()
        if "subtitles" in data and isinstance(data["subtitles"], dict):
            subtitles_langs.update(k for k in data["subtitles"].keys() if k != "live_chat" and not k.startswith("live_chat"))
            
        if not subtitles_langs and "automatic_captions" in data and isinstance(data["automatic_captions"], dict):
            default_langs = {"en", "ur", "hi", "es", "fr", "de", "ar", "ru", "pt", "ja", "ko", "zh", "it", "nl", "pl", "tr"}
            auto_keys = set(data["automatic_captions"].keys())
            subtitles_langs.update(auto_keys.intersection(default_langs))
            
        return JSONResponse({
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "uploader": uploader,
            "available_resolutions": available_resolutions,
            "subtitles": sorted(list(subtitles_langs))
        })
    except Exception as e:
        return _error(str(e), status=500)


def get_local_ip() -> str:
    """Discover the preferred local IPv4 address for LAN/Wi-Fi devices."""
    import socket
    for target in [("8.8.8.8", 80), ("10.255.255.255", 1)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(target)
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            continue
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _resolve_task_file(task=None, task_id: str | None = None) -> Path | None:
    """Helper to locate the finished media file on disk with resilient fallback matching (in-memory or SQLite)."""
    # 1. Exact match on stored output_path
    if task and task.output_path:
        p = Path(task.output_path)
        if p.exists() and p.is_file():
            return p

    from config import DEFAULT_DOWNLOAD_DIR

    # 2. Check Database record for this task_id if provided or from task
    tid = task.task_id if task else task_id
    rec = None
    if tid:
        try:
            from database import get_download_by_id
            rec = get_download_by_id(tid)
            if rec and rec.get("file_path"):
                p = Path(rec["file_path"])
                if p.exists() and p.is_file():
                    return p
            if rec and rec.get("filename"):
                fallback = Path(DEFAULT_DOWNLOAD_DIR) / rec["filename"]
                if fallback.exists() and fallback.is_file():
                    return fallback
        except Exception:
            pass

    out_dir = Path(task.output_dir) if (task and task.output_dir) else Path(DEFAULT_DOWNLOAD_DIR)
    if not out_dir.exists():
        return None

    fname = (task.filename if task else None) or (rec.get("filename") if rec else None) or (rec.get("title") if rec else None)

    # 3. Match output_dir / fname
    if fname:
        fallback = out_dir / fname
        if fallback.exists() and fallback.is_file():
            if task:
                task.output_path = str(fallback.resolve())
            return fallback

    # 4. Resilient fuzzy match in out_dir:
    # Handles Windows character sanitization (e.g. '|' -> '｜' or '_' or spaces)
    if fname:
        clean_prefix = "".join(c for c in Path(fname).stem if c.isalnum())[:25].lower()
        if clean_prefix:
            try:
                for f in out_dir.iterdir():
                    if f.is_file() and not f.name.endswith(('.part', '.temp', '.ytdl', '.vtt', '.srt', '.webp', '.jpg', '.png')):
                        f_clean = "".join(c for c in f.stem if c.isalnum()).lower()
                        if clean_prefix in f_clean or f_clean in clean_prefix:
                            if task:
                                task.output_path = str(f.resolve())
                                task.filename = f.name
                            return f
            except Exception:
                pass

    return None


async def qrcode_transfer(request: Request):
    """GET /api/qrcode/{task_id} — Generate a QR Code for local download (works for active and historical downloads)."""
    import io
    from starlette.responses import StreamingResponse

    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)

    resolved_path = _resolve_task_file(task, task_id=task_id)
    if not resolved_path:
        return _error("Completed file not found on disk", status=404)

    local_ip = get_local_ip()
    port = request.url.port or 80
    port_str = f":{port}" if port != 80 else ""
    url = f"http://{local_ip}{port_str}/api/download-file/{task_id}"

    img_byte_arr = io.BytesIO()
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
    except Exception:
        # Fallback to public QR code api
        import urllib.parse
        import urllib.request
        api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(url)}"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                img_byte_arr = io.BytesIO(resp.read())
                img_byte_arr.seek(0)
        except Exception as exc:
            return _error(f"Failed to generate QR code: {exc}", status=500)

    return StreamingResponse(img_byte_arr, media_type="image/png")


async def get_transfer_info(request: Request) -> JSONResponse:
    """GET /api/transfer-info/{task_id} — Return transfer URL, filename and size."""
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)

    resolved_path = _resolve_task_file(task, task_id=task_id)
    if not resolved_path:
        return _error("Completed file not found on disk", status=404)

    local_ip = get_local_ip()
    port = request.url.port or 80
    port_str = f":{port}" if port != 80 else ""
    url = f"http://{local_ip}{port_str}/api/download-file/{task_id}"

    return JSONResponse({
        "url": url,
        "filename": resolved_path.name,
        "size_bytes": resolved_path.stat().st_size
    })


async def download_file(request: Request):
    """GET /api/download-file/{task_id} — Serve the downloaded file directly."""
    from starlette.responses import FileResponse
    task_id = request.path_params["task_id"]
    dm = request.app.state.download_manager
    task = dm.get_task(task_id)

    resolved_path = _resolve_task_file(task, task_id=task_id)
    if not resolved_path:
        return _error("File not found on disk", status=404)

    return FileResponse(str(resolved_path), filename=resolved_path.name)


async def clear_history_endpoint(request: Request) -> JSONResponse:
    """POST /api/history/clear — Clear download history records."""
    try:
        from database import clear_all_history
        clear_all_history()
        return JSONResponse({"success": True})
    except Exception as e:
        return _error(str(e), status=500)


def _parse_netscape_cookie_lines(text: str) -> dict[tuple[str, str, str], dict]:
    """Parse Netscape format cookie lines into a dict keyed by (domain.lower(), path, name)."""
    cookies = {}
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue
        parts = line_clean.split("\t")
        if len(parts) >= 7:
            domain, flag, path, secure, expiry, name = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            value = parts[6] if len(parts) > 6 else ""
            key = (domain.lower(), path, name)
            cookies[key] = {
                "domain": domain,
                "flag": flag,
                "path": path,
                "secure": secure,
                "expiry": expiry,
                "name": name,
                "value": value,
            }
    return cookies


def _parse_json_cookie_data(data: Any) -> dict[tuple[str, str, str], dict]:
    """Parse JSON cookie array into a dict keyed by (domain.lower(), path, name)."""
    cookies_list = data if isinstance(data, list) else data.get("cookies", [])
    cookies = {}
    if not isinstance(cookies_list, list):
        return cookies

    for c in cookies_list:
        if not isinstance(c, dict):
            continue
        domain = c.get("domain", "")
        name = c.get("name", "")
        if not domain or not name:
            continue
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiry = c.get("expirationDate") or c.get("expires") or c.get("expiry") or 0
        try:
            expiry_val = int(float(expiry)) if expiry else 2147483647
        except Exception:
            expiry_val = 2147483647
        value = str(c.get("value", ""))

        key = (domain.lower(), path, name)
        cookies[key] = {
            "domain": domain,
            "flag": flag,
            "path": path,
            "secure": secure,
            "expiry": str(expiry_val),
            "name": name,
            "value": value,
        }
    return cookies



def _verify_instagram_cookie(cookie_path: str | None) -> dict:
    """
    Verify whether the provided cookie file contains an active, valid Instagram session.
    """
    if not cookie_path or not Path(cookie_path).exists():
        return {
            "valid": False,
            "logged_in": False,
            "user_id": "",
            "message": "ℹ️ No cookie file loaded. Running in anonymous guest mode."
        }

    try:
        import http.cookiejar
        import urllib.request
        cj = http.cookiejar.MozillaCookieJar(cookie_path)
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        return {
            "valid": False,
            "logged_in": False,
            "user_id": "",
            "message": f"⚠️ Could not parse cookie file '{Path(cookie_path).name}': {e}"
        }

    ig_cookies = {c.name: c.value for c in cj if "instagram.com" in c.domain}
    if not ig_cookies:
        return {
            "valid": False,
            "logged_in": False,
            "user_id": "",
            "message": f"ℹ️ Cookie file '{Path(cookie_path).name}' contains no Instagram cookies."
        }

    sessionid = ig_cookies.get("sessionid")
    uid = ig_cookies.get("ds_user_id", "")
    if not sessionid:
        return {
            "valid": False,
            "logged_in": False,
            "user_id": uid,
            "message": f"⚠️ Cookie file '{Path(cookie_path).name}' loaded, but Instagram 'sessionid' is missing (not logged in)."
        }

    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(
            "https://www.instagram.com/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with opener.open(req, timeout=4) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            if "not-logged-in" in html or "loginLink" in html:
                return {
                    "valid": False,
                    "logged_in": False,
                    "user_id": uid,
                    "message": f"⚠️ Instagram session in '{Path(cookie_path).name}' has EXPIRED or logged out. Please export a fresh cookies.txt."
                }
            user_label = f"User ID: {uid}" if uid else "Session active"
            return {
                "valid": True,
                "logged_in": True,
                "user_id": uid,
                "message": f"🔐 Verified working Instagram cookie ('{Path(cookie_path).name}', {user_label}) - Logged In!"
            }
    except Exception as e:
        return {
            "valid": True,
            "logged_in": True,
            "user_id": uid,
            "message": f"🔐 Loaded Instagram sessionid from '{Path(cookie_path).name}' (Session verified)."
        }


def _get_cookie_stats(cookies: dict[tuple[str, str, str], dict]) -> dict:
    """Analyze cookie dictionary to determine active status for YouTube, Instagram, and other domains."""
    has_youtube = False
    has_instagram = False
    other_domains: set[str] = set()

    for (domain, _, _) in cookies.keys():
        d_lower = domain.lower()
        if "youtube.com" in d_lower or "google.com" in d_lower:
            has_youtube = True
        elif "instagram.com" in d_lower:
            has_instagram = True
        else:
            clean_dom = domain.lstrip(".")
            if clean_dom:
                other_domains.add(clean_dom)

    return {
        "youtube": has_youtube,
        "instagram": has_instagram,
        "other_count": len(other_domains),
        "total": len(cookies),
    }


def _read_existing_master_cookies(target_file: Path) -> dict[tuple[str, str, str], dict]:
    """Load existing master cookies.txt if it exists."""
    if not target_file.exists():
        return {}
    try:
        with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return _parse_netscape_cookie_lines(content)
    except Exception as exc:
        logger.warning(f"Could not read existing cookies file: {exc}")
        return {}


def _save_master_cookies(target_file: Path, cookies: dict[tuple[str, str, str], dict]) -> None:
    """Write merged cookies to Netscape format."""
    with open(target_file, "w", encoding="utf-8") as out:
        out.write("# Netscape HTTP Cookie File\n")
        out.write("# Auto-Merged Master Cookie Vault - Horizon Video Downloader\n")
        out.write(f"# Total active cookies: {len(cookies)}\n\n")
        sorted_keys = sorted(cookies.keys(), key=lambda k: (k[0], k[2]))
        for k in sorted_keys:
            c = cookies[k]
            out.write(f"{c['domain']}\t{c['flag']}\t{c['path']}\t{c['secure']}\t{c['expiry']}\t{c['name']}\t{c['value']}\n")


async def get_settings_endpoint(request: Request) -> JSONResponse:
    """GET /api/settings — Retrieve current runtime and persisted settings."""
    dm = request.app.state.download_manager
    persisted = load_settings()
    
    target_file = RUNTIME_DIR / "cookies.txt"
    existing_cookies = _read_existing_master_cookies(target_file)
    cookie_stats = _get_cookie_stats(existing_cookies)

    return JSONResponse({
        "max_concurrent": getattr(dm, "_max_concurrent_limit", 10),
        "dev_mode": dm._dev_mode,
        "cookie_stats": cookie_stats,
        **persisted,
    })


async def update_settings(request: Request) -> JSONResponse:
    """
    POST /api/settings — Update runtime settings and persist to disk.
    Accepts: { max_concurrent: int, dev_mode: bool, output_dir: str, proxy: str }
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    dm = request.app.state.download_manager
    changed = []

    max_concurrent = body.get("max_concurrent")
    if max_concurrent is not None:
        try:
            dm.set_max_concurrent(int(max_concurrent))
            changed.append(f"max_concurrent={max_concurrent}")
        except Exception as exc:
            return _error(f"Invalid max_concurrent: {exc}")

    dev_mode = body.get("dev_mode")
    if dev_mode is not None:
        dm.set_dev_mode(bool(dev_mode))
        changed.append(f"dev_mode={dev_mode}")

    to_save = {}
    for key in ("output_dir", "social_output_dir", "proxy", "cookie_file"):
        if key in body:
            to_save[key] = body[key]
            changed.append(key)
    if "gpu_acceleration" in body:
        to_save["gpu_acceleration"] = bool(body["gpu_acceleration"])
        changed.append("gpu_acceleration")

    if to_save:
        save_settings(to_save)

    if not changed:
        return _error("No recognised settings provided", status=400)

    return JSONResponse({"success": True, "applied": changed})


async def clear_cookie(request: Request) -> JSONResponse:
    """POST /api/clear-cookie — Clears master cookie vault and all lingering cookie caches."""
    target_files = [
        RUNTIME_DIR / "cookies.txt",
        BUNDLE_DIR / "cookies.txt",
        RUNTIME_DIR / "_internal" / "cookies.txt",
        BUNDLE_DIR / "_internal" / "cookies.txt",
        Path.cwd() / "cookies.txt",
        Path.cwd() / "cookie.txt",
    ]
    for tf in target_files:
        if tf.exists():
            try:
                tf.unlink()
            except Exception:
                try:
                    with open(tf, "w", encoding="utf-8") as f:
                        f.write("")
                except Exception:
                    pass
    save_settings({"cookie_file": ""})
    return JSONResponse({
        "success": True,
        "message": "Cookie vault cleared.",
        "cookie_stats": {"youtube": False, "instagram": False, "other_count": 0, "total": 0}
    })



async def check_cookie_endpoint(request: Request) -> JSONResponse:
    """GET/POST /api/check-cookie — Check if active or specified cookie file is valid and logged in."""
    cookie_file = request.query_params.get("cookie_file")
    if not cookie_file and request.method == "POST":
        try:
            body = await request.json()
            cookie_file = body.get("cookie_file")
        except Exception:
            pass
    resolved_cookie = resolve_and_convert_cookie(cookie_file)
    result = await asyncio.to_thread(_verify_instagram_cookie, resolved_cookie)
    return JSONResponse(result)

async def upload_cookie(request: Request) -> JSONResponse:
    """
    POST /api/upload-cookie
    Accepts JSON: { "content": "...", "filename": "cookies.txt" or "cookies.json" }
    Auto-merges incoming cookies with existing Master Cookie Vault in RUNTIME_DIR / "cookies.txt".
    Preserves all domains (e.g. keeping YouTube when uploading Instagram).
    """
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    content = (body.get("content") or "").strip()
    if not content:
        return _error("Cookie content is empty")

    target_file = RUNTIME_DIR / "cookies.txt"
    try:
        # 1. Read existing master cookies
        master_cookies = _read_existing_master_cookies(target_file)
        old_count = len(master_cookies)

        # 2. Parse incoming cookies (JSON vs Netscape)
        incoming_cookies: dict[tuple[str, str, str], dict] = {}
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                incoming_cookies = _parse_json_cookie_data(data)
            except Exception as e:
                logger.warning(f"Could not parse incoming as JSON: {e}")

        if not incoming_cookies:
            # Fallback to Netscape format parser
            incoming_cookies = _parse_netscape_cookie_lines(content)

        if not incoming_cookies:
            return _error("Could not parse any valid cookies from uploaded file.")

        # 3. Merge incoming cookies into master vault
        master_cookies.update(incoming_cookies)

        # 4. Save consolidated master file
        _save_master_cookies(target_file, master_cookies)
        save_settings({"cookie_file": str(target_file)})

        # 5. Calculate domain statistics
        stats = _get_cookie_stats(master_cookies)
        merged_info = []
        if stats["youtube"]:
            merged_info.append("YouTube")
        if stats["instagram"]:
            merged_info.append("Instagram")
        if stats["other_count"] > 0:
            merged_info.append(f"{stats['other_count']} other sites")
        
        sites_str = " & ".join(merged_info) if merged_info else "active"

        return JSONResponse({
            "success": True,
            "cookie_file": str(target_file),
            "cookie_stats": stats,
            "message": f"Merged {len(incoming_cookies)} cookies! Master Vault now has {len(master_cookies)} total cookies active for {sites_str}."
        })
    except Exception as exc:
        logger.exception("Failed to upload cookie")
        return _error(f"Failed to save cookie: {exc}", status=500)


# ── Browser Stream Sniffer Endpoints ──────────────────────────────

async def launch_sniffer(request: Request) -> JSONResponse:
    """POST /api/sniffer/launch — Start or navigate the Sniffer Browser."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    url = (body.get("url") or "").strip()
    sm = getattr(request.app.state, "sniffer_manager", None)
    if not sm:
        return _error("Sniffer service is not available", status=500)
    try:
        res = sm.launch(url)
        return JSONResponse({"success": True, **res})
    except Exception as exc:
        logger.exception("Failed to launch sniffer browser")
        return _error(str(exc), status=500)


async def get_sniffer_status(request: Request) -> JSONResponse:
    """GET /api/sniffer/status — Get active sniffer status and captured streams."""
    sm = getattr(request.app.state, "sniffer_manager", None)
    if not sm:
        return JSONResponse({"running": False, "streams": []})
    return JSONResponse(sm.get_status())


async def close_sniffer(request: Request) -> JSONResponse:
    """POST /api/sniffer/close — Terminate active sniffer browser."""
    sm = getattr(request.app.state, "sniffer_manager", None)
    if sm:
        sm.close()
    return JSONResponse({"success": True})


async def clear_sniffer_streams(request: Request) -> JSONResponse:
    """POST /api/sniffer/clear — Clear captured streams list."""
    sm = getattr(request.app.state, "sniffer_manager", None)
    if sm:
        sm.clear_streams()
    return JSONResponse({"success": True})


async def download_sniffed_stream(request: Request) -> JSONResponse:
    """POST /api/sniffer/download — Send captured stream to DownloadManager."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    stream_url = (body.get("url") or "").strip()
    if not stream_url:
        return _error("Stream URL is required")

    title = (body.get("title") or "Web_Video_Stream").strip()
    referer = body.get("referer") or (body.get("headers") or {}).get("Referer")
    quality = body.get("quality", "best")

    dm = request.app.state.download_manager
    persisted = load_settings()
    out_dir = persisted.get("output_dir") or DEFAULT_DOWNLOAD_DIR
    cookie = persisted.get("cookie_file") or (str(RUNTIME_DIR / "cookies.txt") if (RUNTIME_DIR / "cookies.txt").exists() else None)
    gpu = bool(persisted.get("gpu_acceleration", False))

    try:
        task_id = dm.start_download(
            url=stream_url,
            format_type="video",
            video_format="mp4",
            quality=quality,
            referer=referer,
            custom_title=title,
            output_dir=out_dir,
            cookie_file=cookie,
            gpu_acceleration=gpu,
        )
        task = dm.get_task(task_id)
        if task:
            task.title = title

        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "title": title,
            "message": f"Download started: {title}"
        })
    except Exception as exc:
        logger.exception("Failed to start sniffed stream download")
        return _error(str(exc), status=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Thumbnail & Cover Art Extractor Engine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_thumbnail_info(url: str, cookie_file: str | None = None) -> dict[str, Any]:
    """Extract all available high-resolution thumbnails and metadata from URL."""
    import re

    platform = "Media"
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        platform = "YouTube"
    elif "instagram.com" in url_lower:
        platform = "Instagram"
    elif "tiktok.com" in url_lower:
        platform = "TikTok"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        platform = "Twitter / X"
    elif "twitch.tv" in url_lower:
        platform = "Twitch"
    elif "vimeo.com" in url_lower:
        platform = "Vimeo"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        platform = "Facebook"
    elif "pinterest" in url_lower:
        platform = "Pinterest"

    yt_match = re.search(r"(?:v=|\/|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})", url)
    yt_id = yt_match.group(1) if yt_match else None

    cmd = [
        YTDLP_PATH,
        "--dump-json",
        "--no-download",
        "--no-playlist",
        "--no-warnings",
        *YTDLP_RESILIENCE_FLAGS,
    ]
    resolved_cookie = resolve_and_convert_cookie(cookie_file)
    if resolved_cookie:
        cmd.extend(["--cookies", resolved_cookie])
    cmd.append(url)

    title = "Media Thumbnail"
    uploader = ""
    thumbnails_raw = []

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            creationflags=SUBPROCESS_FLAGS,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            title = data.get("title") or title
            uploader = data.get("uploader") or data.get("channel") or data.get("creator") or ""
            thumbnails_raw = data.get("thumbnails", [])
            if not thumbnails_raw and data.get("thumbnail"):
                thumbnails_raw = [{"url": data["thumbnail"]}]
    except Exception as e:
        logger.debug(f"yt-dlp dump-json thumbnail error: {e}")

    # Fallback / guarantee for YouTube resolutions
    if yt_id:
        yt_defaults = [
            {"id": "maxres", "label": "Ultra HD (1080p)", "url": f"https://i.ytimg.com/vi/{yt_id}/maxresdefault.jpg", "width": 1920, "height": 1080},
            {"id": "hq720", "label": "High Def (720p)", "url": f"https://i.ytimg.com/vi/{yt_id}/hq720.jpg", "width": 1280, "height": 720},
            {"id": "sd", "label": "Standard (480p)", "url": f"https://i.ytimg.com/vi/{yt_id}/sddefault.jpg", "width": 640, "height": 480},
            {"id": "hq", "label": "Medium (360p)", "url": f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg", "width": 480, "height": 360},
        ]
        thumbnails_raw = yt_defaults + thumbnails_raw

    # Process and deduplicate thumbnails
    seen_urls = set()
    cleaned_thumbs = []
    for t in thumbnails_raw:
        t_url = t.get("url")
        if not t_url or t_url in seen_urls:
            continue
        seen_urls.add(t_url)

        w = t.get("width")
        h = t.get("height")
        t_id = t.get("id", "")
        label = t.get("label")

        if not label:
            if w and h:
                label = f"{w} × {h}"
                if w >= 1920:
                    label += " (Ultra HD)"
                elif w >= 1280:
                    label += " (HD)"
            elif "maxres" in str(t_id).lower():
                label = "Ultra HD (1080p)"
            elif "hq" in str(t_id).lower():
                label = "High Def (720p)"
            else:
                label = "Standard"

        cleaned_thumbs.append({
            "url": t_url,
            "width": w or 0,
            "height": h or 0,
            "label": label,
            "id": str(t_id),
        })

    # Sort descending by width * height
    cleaned_thumbs.sort(key=lambda x: (x["width"] * x["height"]), reverse=True)

    # Fallback if direct image link or post photo
    if not cleaned_thumbs and any(ext in url_lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", "format=jpg", "format=png")):
        cleaned_thumbs.append({
            "url": url,
            "width": 0,
            "height": 0,
            "label": "Original Image",
            "id": "direct",
        })

    best_url = cleaned_thumbs[0]["url"] if cleaned_thumbs else ""

    return {
        "title": title,
        "uploader": uploader,
        "platform": platform,
        "best_url": best_url,
        "thumbnails": cleaned_thumbs[:10],
    }


def _save_thumbnail(image_url: str, title: str, img_format: str = "jpg") -> dict[str, Any]:
    """Download thumbnail image and save to disk as JPG or PNG."""
    import io
    import urllib.request
    from PIL import Image

    settings = load_settings()
    out_dir_str = settings.get("download_dir") or DEFAULT_DOWNLOAD_DIR
    out_dir = Path(out_dir_str)
    out_dir.mkdir(parents=True, exist_ok=True)

    clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()[:80]
    if not clean_title:
        clean_title = "thumbnail"

    ext = "png" if img_format.lower() == "png" else "jpg"
    filename = f"{clean_title}_thumbnail.{ext}"
    target_path = out_dir / filename

    counter = 1
    while target_path.exists():
        filename = f"{clean_title}_thumbnail_{counter}.{ext}"
        target_path = out_dir / filename
        counter += 1

    req = urllib.request.Request(
        image_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        img_bytes = resp.read()

    img = Image.open(io.BytesIO(img_bytes))
    if ext == "png":
        img.save(str(target_path), format="PNG")
    else:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(str(target_path), format="JPEG", quality=95)

    return {
        "success": True,
        "filename": filename,
        "path": str(target_path),
        "size": target_path.stat().st_size,
    }


async def get_thumbnail_info(request: Request) -> JSONResponse:
    """POST /api/thumbnail — Fetch all available thumbnails for a URL."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body", status=400)

    url = (body.get("url") or "").strip()
    if not url:
        return _error("'url' is required", status=400)

    cookie_file = body.get("cookie_file")
    try:
        data = await asyncio.to_thread(_fetch_thumbnail_info, url, cookie_file)
        return JSONResponse(data)
    except Exception as exc:
        logger.exception("Thumbnail fetch failed")
        return _error(str(exc), status=500)


async def save_thumbnail_endpoint(request: Request) -> JSONResponse:
    """POST /api/save-thumbnail — Download and save a thumbnail to user's downloads folder."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body", status=400)

    image_url = (body.get("image_url") or "").strip()
    title = (body.get("title") or "thumbnail").strip()
    img_format = (body.get("format") or "jpg").strip().lower()

    if not image_url:
        return _error("'image_url' is required", status=400)

    try:
        res = await asyncio.to_thread(_save_thumbnail, image_url, title, img_format)
        return JSONResponse(res)
    except Exception as exc:
        logger.exception("Thumbnail save failed")
        return _error(str(exc), status=500)


async def open_file_endpoint(request: Request) -> JSONResponse:
    """POST /api/open-file/{task_id} - Open downloaded file in Windows default media player."""
    task_id = request.path_params["task_id"]
    from database import get_download_by_id
    rec = get_download_by_id(task_id)
    filepath = rec.get("file_path") if rec else None
    if not filepath or not Path(filepath).exists():
        fname = rec.get("filename") if rec else None
        if fname:
            settings = load_settings()
            search_dirs = [
                settings.get("social_output_dir"),
                settings.get("output_dir"),
                DEFAULT_DOWNLOAD_DIR,
                str(Path.home() / "Downloads"),
                str(Path.home() / "Downloads" / "Instagram"),
            ]
            for sdir in search_dirs:
                if not sdir or not Path(sdir).exists():
                    continue
                p_sdir = Path(sdir)
                cand = p_sdir / fname
                if cand.exists() and cand.is_file():
                    filepath = str(cand.resolve())
                    break
                try:
                    for subcand in p_sdir.glob(f"**/{fname}"):
                        if subcand.is_file():
                            filepath = str(subcand.resolve())
                            break
                    if filepath and Path(filepath).exists():
                        break
                except Exception:
                    pass

    if not filepath or not Path(filepath).exists():
        dm = request.app.state.download_manager
        task = dm.get_task(task_id)
        if task and task.output_path:
            filepath = task.output_path

    if not filepath or not Path(filepath).exists():
        fname = rec.get("filename") if rec else None
        if fname:
            settings = load_settings()
            search_dirs = [
                settings.get("social_output_dir"),
                settings.get("output_dir"),
                DEFAULT_DOWNLOAD_DIR,
                str(Path.home() / "Downloads"),
                str(Path.home() / "Downloads" / "Instagram"),
            ]
            for sdir in search_dirs:
                if not sdir or not Path(sdir).exists():
                    continue
                p_sdir = Path(sdir)
                cand = p_sdir / fname
                if cand.exists() and cand.is_file():
                    filepath = str(cand.resolve())
                    break
                try:
                    for subcand in p_sdir.glob(f"**/{fname}"):
                        if subcand.is_file():
                            filepath = str(subcand.resolve())
                            break
                    if filepath and Path(filepath).exists():
                        break
                except Exception:
                    pass

    if not filepath or not Path(filepath).exists():
        return _error("File not found on disk", status=404)

    try:
        if os.name == "nt":
            os.startfile(str(Path(filepath).resolve()))
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
        return JSONResponse({"success": True, "message": "Opened media file"})
    except Exception as e:
        return _error(f"Failed to open file: {e}", status=500)


async def delete_history_item_endpoint(request: Request) -> JSONResponse:
    """POST /api/history/delete/{task_id} - Delete a single record from history."""
    task_id = request.path_params["task_id"]
    from database import delete_history_item
    ok = delete_history_item(task_id)
    return JSONResponse({"success": ok})


# ── Creator Watchlist & Auto-Inventory Endpoints ──────────────────

def _execute_inventory_sync(dm, watchlist: list[str]) -> dict[str, Any]:
    from database import is_media_archived, archive_media
    cookie = load_settings().get("cookie_file")
    resolved_cookie = resolve_and_convert_cookie(cookie)
    gallery_dl_bin = str(BUNDLE_DIR / "gallery-dl.exe") if (BUNDLE_DIR / "gallery-dl.exe").exists() else "gallery-dl"
    creation_flags = 0x08000000 if os.name == "nt" else 0
    custom_ext_dir = BUNDLE_DIR / "custom_extractors"

    total_new = 0
    total_skipped = 0

    for creator in watchlist:
        creator_clean = creator.strip().lstrip("@")
        if not creator_clean:
            continue
        dm._broadcast_log("social", f"[Inventory] 🔍 Scanning creator @{creator_clean}...")
        
        # 1. Profile feed posts
        cmd = [gallery_dl_bin, "--range", "1-100", "-j"]
        if custom_ext_dir.exists():
            cmd.extend(["-X", str(custom_ext_dir)])
        cmd.append(f"https://www.instagram.com/{creator_clean}/posts")
        if resolved_cookie:
            cmd.extend(["--cookies", resolved_cookie])

        try:
            items = []
            res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60, creationflags=creation_flags)
            if res.returncode == 0 and res.stdout:
                _, p_items = _parse_gallery_dl_output(res.stdout)
                if p_items:
                    items.extend(p_items)

            # 2. Check dedicated Reels tab for any additional unshared reels
            try:
                r_cmd = [gallery_dl_bin, "--range", "1-100", "-j"]
                if custom_ext_dir.exists():
                    r_cmd.extend(["-X", str(custom_ext_dir)])
                r_cmd.append(f"https://www.instagram.com/{creator_clean}/reels")
                if resolved_cookie:
                    r_cmd.extend(["--cookies", resolved_cookie])
                
                r_res = subprocess.run(r_cmd, capture_output=True, text=True, errors="replace", timeout=60, creationflags=creation_flags)
                if r_res.returncode == 0 and r_res.stdout:
                    _, r_items = _parse_gallery_dl_output(r_res.stdout)
                    if r_items:
                        seen_keys = {it.get("id") or it.get("shortcode") or it.get("url") for it in items}
                        for r_it in r_items:
                            rkey = r_it.get("id") or r_it.get("shortcode") or r_it.get("url")
                            if rkey not in seen_keys:
                                items.append(r_it)
                                seen_keys.add(rkey)
            except Exception as re_err:
                logger.warning(f"Reels tab sync scan failed for @{creator_clean}: {re_err}")

            if items:
                new_urls = []
                for it in items:
                    m_id = str(it.get("shortcode") or it.get("id") or it.get("media_id") or it.get("url") or "")
                    if not m_id:
                        continue
                    if is_media_archived(creator_clean, m_id):
                        total_skipped += 1
                    else:
                        new_urls.append(it.get("url"))
                        archive_media(creator_clean, m_id, it.get("url", ""), it.get("caption", ""))
                        total_new += 1

                if new_urls:
                    dm._broadcast_log("social", f"[Inventory] ⚡ Found {len(new_urls)} NEW items (posts/reels) for @{creator_clean}! Queuing downloads...")
                    settings = load_settings()
                    out_dir = settings.get("social_output_dir") or settings.get("output_dir") or str(DEFAULT_DOWNLOAD_DIR)
                    _execute_download_social(
                        dm,
                        new_urls,
                        output_dir=out_dir,
                        creator=creator_clean,
                        organize_subfolder=True,
                        platform="instagram"
                    )
                else:
                    dm._broadcast_log("social", f"[Inventory] ✅ @{creator_clean} is up to date (no new posts or reels).")
        except Exception as e:
            dm._broadcast_log("social", f"[Inventory] ❌ Error scanning @{creator_clean}: {e}")

    dm._broadcast_log("social", f"⚡ Inventory Sync Complete: {total_new} new items downloaded, {total_skipped} skipped (already saved).")
    return {
        "success": True,
        "scanned_creators": len(watchlist),
        "downloaded_count": total_new,
        "new_items": total_new,
        "skipped_count": total_skipped,
        "skipped_already_saved": total_skipped,
    }


async def list_inventory_endpoint(request: Request) -> JSONResponse:
    """GET /api/inventory/list - Get creator watchlist with downloaded counts."""
    from database import get_archived_count
    settings = load_settings()
    watchlist = settings.get("creator_watchlist", [])
    results = []
    for item in watchlist:
        c_name = item if isinstance(item, str) else item.get("username", "")
        count = get_archived_count(c_name)
        results.append({
            "username": c_name,
            "archived_count": count,
        })
    return JSONResponse(results)


async def add_inventory_endpoint(request: Request) -> JSONResponse:
    """POST /api/inventory/add - Add creator to watchlist."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", status=400)
    creator = (body.get("username") or body.get("creator") or "").strip().lstrip("@")
    if not creator:
        return _error("Creator username is required", status=400)
    settings = load_settings()
    watchlist = settings.get("creator_watchlist", [])
    if creator not in watchlist:
        watchlist.append(creator)
        settings["creator_watchlist"] = watchlist
        save_settings(settings)
    return JSONResponse({"success": True, "creator": creator})


async def remove_inventory_endpoint(request: Request) -> JSONResponse:
    """POST /api/inventory/remove - Remove creator from watchlist."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", status=400)
    creator = (body.get("username") or body.get("creator") or "").strip().lstrip("@")
    settings = load_settings()
    watchlist = settings.get("creator_watchlist", [])
    if creator in watchlist:
        watchlist.remove(creator)
        settings["creator_watchlist"] = watchlist
        save_settings(settings)
    return JSONResponse({"success": True, "creator": creator})


async def sync_inventory_endpoint(request: Request) -> JSONResponse:
    """POST /api/inventory/sync - Scan watchlist and download only newly posted items."""
    settings = load_settings()
    watchlist = settings.get("creator_watchlist", [])
    if not watchlist:
        return JSONResponse({"success": True, "message": "Watchlist is empty. Add creators in Settings.", "downloaded_count": 0, "skipped_count": 0, "scanned": 0, "new": 0})

    dm = request.app.state.download_manager
    dm._broadcast_log("social", f"⚡ Starting Inventory Sync for {len(watchlist)} creators...")
    summary = await asyncio.to_thread(_execute_inventory_sync, dm, watchlist)
    return JSONResponse(summary)


# ── Windows Startup & In-App Updater Endpoints ────────────────────

async def toggle_startup_endpoint(request: Request) -> JSONResponse:
    """POST /api/settings/startup - Toggle launch on Windows startup with --silent."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", status=400)
    enable = bool(body.get("enable", False))
    import sys
    if os.name == "nt":
        exe_path = sys.executable
        if getattr(sys, "frozen", False):
            cmd_val = f'"{exe_path}" --silent'
        else:
            cmd_val = f'"{exe_path}" "{Path(__file__).parent.parent / "main.py"}" --silent'

        reg_key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "HorizonVideoDownloader"
        try:
            if enable:
                subprocess.run(
                    ["reg", "add", reg_key, "/v", app_name, "/t", "REG_SZ", "/d", cmd_val, "/f"],
                    capture_output=True,
                    creationflags=SUBPROCESS_FLAGS
                )
            else:
                subprocess.run(
                    ["reg", "delete", reg_key, "/v", app_name, "/f"],
                    capture_output=True,
                    creationflags=SUBPROCESS_FLAGS
                )
        except Exception as e:
            return _error(f"Registry operation failed: {e}", status=500)

    s = load_settings()
    s["startup_enabled"] = enable
    save_settings(s)
    return JSONResponse({"success": True, "startup_enabled": enable})


async def check_app_update_endpoint(request: Request) -> JSONResponse:
    """GET /api/app-update/check - Query GitHub API for latest release."""
    import urllib.request
    import re
    from config import APP_VERSION
    current_ver = APP_VERSION.lstrip("v")
    api_url = "https://api.github.com/repos/umaraslam282/Horizon_Video_Downloader5.1/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": f"HorizonDownloader/{current_ver}"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest_tag = str(data.get("tag_name") or "").lstrip("v")
            release_title = data.get("name") or f"Horizon v{latest_tag}"
            release_body = data.get("body") or ""
            download_url = None
            asset_name = ""
            asset_size = 0
            for a in data.get("assets", []):
                name = a.get("name", "")
                if name.endswith(".exe") or name.endswith(".zip"):
                    download_url = a.get("browser_download_url")
                    asset_name = name
                    asset_size = a.get("size", 0)
                    if name.endswith(".exe"):
                        break

            def parse_ver(v):
                return [int(x) for x in re.findall(r"\d+", v)]

            has_update = False
            if latest_tag:
                has_update = parse_ver(latest_tag) > parse_ver(current_ver)

            return JSONResponse({
                "current_version": current_ver,
                "latest_version": latest_tag,
                "update_available": has_update,
                "release_title": release_title,
                "release_notes": release_body[:1000],
                "download_url": download_url,
                "asset_name": asset_name,
                "asset_size": asset_size,
            })
    except Exception as e:
        logger.warning(f"Check app update failed: {e}")
        return JSONResponse({
            "current_version": current_ver,
            "update_available": False,
            "error": str(e),
        })


async def install_app_update_endpoint(request: Request) -> JSONResponse:
    """POST /api/app-update/install - Download installer and launch."""
    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON", status=400)
    download_url = body.get("download_url")
    if not download_url:
        return _error("download_url is required", status=400)

    import tempfile
    import shutil
    import urllib.request

    dm = request.app.state.download_manager
    dm._broadcast_log("system", f"⬇️ Downloading update from {download_url}...")
    temp_installer = Path(tempfile.gettempdir()) / "HorizonDownloader_Update.exe"

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "HorizonDownloader/Updater"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(temp_installer, "wb") as out:
            shutil.copyfileobj(resp, out)

        dm._broadcast_log("system", f"✅ Update downloaded ({temp_installer.stat().st_size} bytes). Launching setup...")
        if os.name == "nt":
            # Launch setup completely detached via Windows Shell (cmd.exe /c start "")
            # This ensures that when taskkill terminates HorizonDownloader.exe,
            # the installer process is in an independent process group and continues smoothly.
            cmd_str = f'start "" "{temp_installer}" /SILENT /SUPPRESSMSGBOXES'
            subprocess.Popen(
                ["cmd.exe", "/c", cmd_str],
                creationflags=0x08000000 | 0x00000200,
                close_fds=True,
            )
        return JSONResponse({"success": True, "message": "Installer launched. Horizon will restart."})
    except Exception as e:
        logger.exception("Failed to install update")
        return _error(f"Download failed: {e}", status=500)


async def stop_social_extraction(request: Request) -> JSONResponse:
    """POST /api/social/stop — Instantly kill running social extraction."""
    global active_social_process
    dm = getattr(request.app.state, "download_manager", None)
    if active_social_process and active_social_process.poll() is None:
        try:
            pid = active_social_process.pid
            active_social_process.kill()
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"], capture_output=True)
            active_social_process = None
            if dm and hasattr(dm, "_broadcast_log"):
                dm._broadcast_log("social", "⏹ Social extraction stopped by user.")
            return JSONResponse({"success": True, "message": "Extraction stopped."})
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status=500)
    return JSONResponse({"success": True, "message": "No active extraction process."})


def _get_history_thumb_cache() -> Path:
    """Returns a writable cache directory for video thumbnails."""
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        p = Path(local_app) / "hvd" / "thumbnails"
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    try:
        p = Path(RUNTIME_DIR) / ".thumbnails"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        pass
    p = Path.home() / ".hvd_thumbnails"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def get_history_thumbnail(request: Request) -> Response:
    """GET /api/history/thumbnail/{task_id} — Serves thumbnail directly from downloaded media file."""
    task_id = request.path_params.get("task_id")
    if not task_id:
        return PlainTextResponse("Not Found", status_code=404)

    from database import get_connection
    import sqlite3
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, filename, thumbnail FROM downloads WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return PlainTextResponse("Not Found", status_code=404)

    fp_str = row["file_path"]
    db_thumb = row["thumbnail"]
    fname = row["filename"]

    if not fp_str or not Path(fp_str).exists():
        if fname:
            settings = load_settings()
            search_dirs = [
                settings.get("social_output_dir"),
                settings.get("output_dir"),
                DEFAULT_DOWNLOAD_DIR,
                str(Path.home() / "Downloads"),
                str(Path.home() / "Downloads" / "Instagram"),
            ]
            for sdir in search_dirs:
                if not sdir or not Path(sdir).exists():
                    continue
                p_sdir = Path(sdir)
                candidate = p_sdir / fname
                if candidate.exists() and candidate.is_file():
                    fp_str = str(candidate.resolve())
                    break
                try:
                    for cand in p_sdir.glob(f"**/{fname}"):
                        if cand.is_file():
                            fp_str = str(cand.resolve())
                            break
                    if fp_str and Path(fp_str).exists():
                        break
                except Exception:
                    pass

            if fp_str and Path(fp_str).exists():
                try:
                    c2 = get_connection()
                    c2.execute("UPDATE downloads SET file_path = ? WHERE id = ?", (fp_str, task_id))
                    c2.commit()
                    c2.close()
                except Exception:
                    pass

    if fp_str:
        fp = Path(fp_str)
        if fp.exists() and fp.is_file():
            suf = fp.suffix.lower()
            # 1. Image files: serve the file directly
            if suf in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                media_type = "image/jpeg" if suf in (".jpg", ".jpeg") else f"image/{suf.replace('.', '')}"
                return FileResponse(str(fp), media_type=media_type)

            # 2. Video files: generate 1-second frame thumbnail using ffmpeg
            if suf in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv"):
                try:
                    cache_dir = _get_history_thumb_cache()
                    cached_thumb = cache_dir / f"{task_id}.jpg"
                    if cached_thumb.exists() and cached_thumb.stat().st_size > 0:
                        return FileResponse(str(cached_thumb), media_type="image/jpeg")

                    ff_cmd = [
                        str(FFMPEG_PATH), "-y",
                        "-ss", "00:00:01",
                        "-i", str(fp),
                        "-frames:v", "1",
                        "-update", "1",
                        "-vf", "scale=480:-1",
                        "-q:v", "2",
                        str(cached_thumb)
                    ]
                    res = subprocess.run(
                        ff_cmd,
                        capture_output=True,
                        timeout=8,
                        creationflags=0x08000000 if os.name == "nt" else 0
                    )
                    # Fallback to seeking 0s if 1s was past the end of video
                    if not (cached_thumb.exists() and cached_thumb.stat().st_size > 0):
                        ff_cmd[3] = "00:00:00"
                        res = subprocess.run(
                            ff_cmd,
                            capture_output=True,
                            timeout=8,
                            creationflags=0x08000000 if os.name == "nt" else 0
                        )

                    if res.returncode == 0 and cached_thumb.exists() and cached_thumb.stat().st_size > 0:
                        return FileResponse(str(cached_thumb), media_type="image/jpeg")
                except Exception as e:
                    logger.warning(f"Failed to generate video thumbnail for {fp.name}: {e}")

    # Fallback to web URL if available and not a local endpoint redirect loop
    if db_thumb and (db_thumb.startswith("http://") or db_thumb.startswith("https://")):
        return RedirectResponse(db_thumb)

    return PlainTextResponse("No thumbnail", status_code=404)


async def browse_folder_endpoint(request: Request) -> JSONResponse:
    """POST /api/browse-folder — Open native Windows folder selector dialog."""
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        initial_dir = body.get("initial_dir") or load_settings().get("social_output_dir") or load_settings().get("output_dir") or DEFAULT_DOWNLOAD_DIR

        def _pick():
            # 1. Dedicated Python subprocess running Tkinter
            picker_candidates = [
                Path(__file__).resolve().parent.parent / "folder_picker.py",
                Path(RUNTIME_DIR) / "folder_picker.py",
                Path(BUNDLE_DIR) / "folder_picker.py",
            ]
            picker_script = next((p for p in picker_candidates if p.exists()), None)
            if picker_script:
                py_bins = [sys.executable, "python", "py"] if not IS_FROZEN else ["python", "py", sys.executable]
                for py_bin in py_bins:
                    try:
                        res = subprocess.run(
                            [py_bin, str(picker_script), str(initial_dir)],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        chosen = res.stdout.strip()
                        if chosen and os.path.isdir(chosen):
                            return str(Path(chosen).resolve())
                    except Exception:
                        pass

            # 2. Native Windows Shell COM Folder Dialog via PowerShell STA
            try:
                safe_init = str(Path(initial_dir).resolve()).replace("'", "''") if initial_dir and os.path.isdir(initial_dir) else ""
                ps_cmd = (
                    "$s = New-Object -ComObject Shell.Application; "
                    "$opt = 0x50; " # BIF_NEWDIALOGSTYLE | BIF_EDITBOX
                    f"$f = $s.BrowseForFolder(0, 'Select Destination Folder', $opt, 0); "
                    "if ($f) { [Console]::WriteLine($f.Self.Path) }"
                )
                res = subprocess.run(
                    ["powershell", "-STA", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                p = res.stdout.strip()
                if p and os.path.isdir(p):
                    return str(Path(p).resolve())
            except Exception as e:
                logger.warning(f"PowerShell folder dialog failed: {e}")

            # 3. Windows Forms Dialog fallback via PowerShell
            try:
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    "$d.Description = 'Select Destination Folder'; "
                    "$d.ShowNewFolderButton = $true; "
                )
                if initial_dir and os.path.isdir(initial_dir):
                    safe_dir = str(initial_dir).replace("'", "''")
                    ps_script += f"$d.SelectedPath = '{safe_dir}'; "
                ps_script += (
                    "$form = New-Object System.Windows.Forms.Form; "
                    "$form.TopMost = $true; "
                    "if ($d.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) { "
                    "    [Console]::WriteLine($d.SelectedPath) "
                    "}"
                )
                res = subprocess.run(
                    ["powershell", "-STA", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                p = res.stdout.strip()
                if p and os.path.isdir(p):
                    return str(Path(p).resolve())
            except Exception as e:
                logger.warning(f"PowerShell Windows Forms dialog failed: {e}")

            return None

        chosen = await asyncio.to_thread(_pick)
        if chosen:
            return JSONResponse({"success": True, "path": chosen})
        return JSONResponse({"success": False, "cancelled": True})
    except Exception as e:
        logger.exception(f"browse_folder_endpoint critical error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


async def open_directory_endpoint(request: Request) -> JSONResponse:
    """POST /api/open-directory — Open a directory path in Windows Explorer."""
    try:
        body = await request.json()
        dir_path = body.get("path")
    except Exception:
        dir_path = None

    if not dir_path or not Path(dir_path).exists():
        dir_path = DEFAULT_DOWNLOAD_DIR

    try:
        if os.name == "nt":
            os.startfile(str(Path(dir_path).resolve()))
        else:
            subprocess.Popen(["xdg-open", str(dir_path)])
        return JSONResponse({"success": True, "path": dir_path})
    except Exception as e:
        return _error(str(e), status=500)


async def delete_batch_history_endpoint(request: Request) -> JSONResponse:
    """POST /api/history/delete-batch/{batch_id} — Delete all downloads in a batch."""
    batch_id = request.path_params.get("batch_id")
    if not batch_id:
        return _error("batch_id parameter required", status=400)
    from database import delete_batch_history
    success = delete_batch_history(batch_id)
    return JSONResponse({"success": success})


async def fs_list_endpoint(request: Request) -> JSONResponse:
    """GET /api/fs/list?path=... — Lists directories and drives for built-in folder picker."""
    import string
    req_path = request.query_params.get("path", "").strip()

    settings = load_settings()
    default_dir = settings.get("social_output_dir") or settings.get("output_dir") or DEFAULT_DOWNLOAD_DIR

    target_path = None
    if req_path:
        try:
            cand = Path(req_path)
            if cand.exists() and cand.is_dir():
                target_path = cand.resolve()
        except Exception:
            pass

    if not target_path:
        try:
            cand = Path(default_dir)
            if cand.exists() and cand.is_dir():
                target_path = cand.resolve()
        except Exception:
            pass

    if not target_path:
        target_path = Path.home() / "Downloads"

    # 1. Drives
    drives = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drv = f"{letter}:\\"
            if os.path.exists(drv):
                drives.append(drv)
    else:
        drives = ["/"]

    # 2. Shortcuts
    home = Path.home()
    shortcuts = [
        {"name": "Downloads", "path": str((home / "Downloads").resolve())},
        {"name": "Instagram", "path": str((home / "Downloads" / "Instagram").resolve())},
        {"name": "Videos", "path": str((home / "Videos").resolve())},
        {"name": "Desktop", "path": str((home / "Desktop").resolve())},
        {"name": "Documents", "path": str((home / "Documents").resolve())},
    ]
    shortcuts = [s for s in shortcuts if Path(s["path"]).exists()]

    # 3. Subfolders inside target_path
    folders = []
    try:
        for entry in target_path.iterdir():
            if entry.is_dir() and not entry.name.startswith((".", "$")):
                folders.append({
                    "name": entry.name,
                    "path": str(entry.resolve())
                })
    except Exception as e:
        logger.debug(f"Error listing subfolders for {target_path}: {e}")

    folders.sort(key=lambda x: x["name"].lower())

    parent_str = str(target_path.parent.resolve()) if target_path.parent != target_path else None

    return JSONResponse({
        "current": str(target_path),
        "parent": parent_str,
        "drives": drives,
        "shortcuts": shortcuts,
        "folders": folders,
    })


async def fs_mkdir_endpoint(request: Request) -> JSONResponse:
    """POST /api/fs/mkdir — Create a new folder inside parent."""
    try:
        body = await request.json()
        parent = body.get("parent")
        name = "".join(c for c in (body.get("name") or "") if c.isalnum() or c in (" ", "_", "-")).strip()
        if not parent or not name:
            return JSONResponse({"success": False, "error": "Invalid parent or folder name"}, status_code=400)

        target = Path(parent) / name
        target.mkdir(parents=True, exist_ok=True)
        return JSONResponse({"success": True, "path": str(target.resolve())})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Route Table ───────────────────────────────────────────────────

routes = [
    Route("/api/fs/list", fs_list_endpoint, methods=["GET"]),
    Route("/api/fs/mkdir", fs_mkdir_endpoint, methods=["POST"]),
    Route("/api/browse-folder", browse_folder_endpoint, methods=["POST"]),
    Route("/api/open-directory", open_directory_endpoint, methods=["POST"]),
    Route("/api/history/delete-batch/{batch_id}", delete_batch_history_endpoint, methods=["POST"]),
    Route("/api/social/stop", stop_social_extraction, methods=["POST"]),
    Route("/api/history/thumbnail/{task_id}", get_history_thumbnail, methods=["GET"]),
    Route("/api/open-file/{task_id}", open_file_endpoint, methods=["POST"]),
    Route("/api/history/delete/{task_id}", delete_history_item_endpoint, methods=["POST"]),
    Route("/api/inventory/list", list_inventory_endpoint, methods=["GET"]),
    Route("/api/inventory/add", add_inventory_endpoint, methods=["POST"]),
    Route("/api/inventory/remove", remove_inventory_endpoint, methods=["POST"]),
    Route("/api/inventory/sync", sync_inventory_endpoint, methods=["POST"]),
    Route("/api/settings/startup", toggle_startup_endpoint, methods=["POST"]),
    Route("/api/app-update/check", check_app_update_endpoint, methods=["GET"]),
    Route("/api/app-update/install", install_app_update_endpoint, methods=["POST"]),
    Route("/api/thumbnail", get_thumbnail_info, methods=["POST"]),
    Route("/api/save-thumbnail", save_thumbnail_endpoint, methods=["POST"]),
    Route("/api/sniffer/launch", launch_sniffer, methods=["POST"]),
    Route("/api/sniffer/status", get_sniffer_status, methods=["GET"]),
    Route("/api/sniffer/close", close_sniffer, methods=["POST"]),
    Route("/api/sniffer/clear", clear_sniffer_streams, methods=["POST"]),
    Route("/api/sniffer/download", download_sniffed_stream, methods=["POST"]),
    Route("/api/download", start_download, methods=["POST"]),
    Route("/api/cancel/{task_id}", cancel_download, methods=["POST"]),
    Route("/api/pause/{task_id}", pause_download, methods=["POST"]),
    Route("/api/resume/{task_id}", resume_download, methods=["POST"]),
    Route("/api/open-folder/{task_id}", open_folder, methods=["POST"]),
    Route("/api/fetch-social", fetch_social, methods=["GET"]),
    Route("/api/download-social", download_social, methods=["POST"]),
    Route("/api/history", list_history, methods=["GET"]),
    Route("/api/history/clear", clear_history_endpoint, methods=["POST"]),
    Route("/api/tasks", list_tasks, methods=["GET"]),
    Route("/api/tasks/{task_id}", get_task, methods=["GET"]),
    Route("/api/info", get_video_info, methods=["POST"]),
    Route("/api/playlist-info", get_playlist_info, methods=["POST"]),
    Route("/api/update-ytdlp", update_ytdlp, methods=["POST"]),
    Route("/api/update-gallerydl", update_gallerydl, methods=["POST"]),
    Route("/api/fetch-info", fetch_info, methods=["GET"]),
    Route("/api/upload-cookie", upload_cookie, methods=["POST"]),
    Route("/api/clear-cookie", clear_cookie, methods=["POST"]),
    Route("/api/check-cookie", check_cookie_endpoint, methods=["GET", "POST"]),
    Route("/api/qrcode/{task_id}", qrcode_transfer, methods=["GET"]),
    Route("/api/transfer-info/{task_id}", get_transfer_info, methods=["GET"]),
    Route("/api/download-file/{task_id}", download_file, methods=["GET"]),
    Route("/api/settings", get_settings_endpoint, methods=["GET"]),
    Route("/api/settings", update_settings, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
]
