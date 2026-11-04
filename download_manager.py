"""
Horizon Video Downloader v3 — Download Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Centralized concurrent download engine with subprocess isolation.

Architecture
────────────
- Every download gets a unique task_id (UUID) and runs in its own
  daemon thread with an isolated yt-dlp subprocess.
- Progress is parsed from yt-dlp's structured JSON output
  (--progress-template "%(progress)j") — no regex on console text.
- Worker threads push updates to WebSocket clients via an
  asyncio.run_coroutine_threadsafe() bridge.
- Pause/Resume uses psutil to suspend/resume OS-level process threads.
- Cancel kills the entire subprocess tree and cleans up temp files.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import psutil

from config import (
    BUNDLE_DIR,
    DEFAULT_DOWNLOAD_DIR,
    FFMPEG_PATH,
    MAX_CONCURRENT_DOWNLOADS,
    OUTPUT_TEMPLATE,
    SUBPROCESS_FLAGS,
    YTDLP_PATH,
    YTDLP_RESILIENCE_FLAGS,
    load_settings,
    save_settings,
)
from database import insert_download, update_status, update_title

logger = logging.getLogger("hvd.download")

PROGRESS_RE = re.compile(r'\[download\]\s+([\d\.]+)%\s+of\s+~?(\S+)\s+at\s+(.*?)\s+ETA\s+(\S+)')

def _parse_size_bytes(s: str) -> int:
    s = s.strip().lstrip("~")
    units = {"b": 1, "kib": 1024, "kb": 1000, "mib": 1024**2, "mb": 1000**2, "gib": 1024**3, "gb": 1000**3}
    m = re.match(r"^([\d\.]+)\s*([A-Za-z]+)$", s)
    if not m:
        return 0
    val, unit = float(m.group(1)), m.group(2).lower()
    return int(val * units.get(unit, 1))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Task
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class DownloadTask:
    """
    Represents a single download job with full lifecycle state.

    Public fields are serialized to JSON for the REST API and WebSocket
    broadcasts.  Private fields (_process, _thread, _temp_files) are
    internal bookkeeping only.
    """

    task_id: str
    url: str
    format_type: str  # "video" | "audio"
    quality: str = "best"  # "best","2160","1440","1080","720","480","360"
    audio_format: str = "mp3"  # "mp3","m4a","flac","wav","ogg"
    video_format: str = "mp4"  # "mp4","mkv","webm"
    subtitles: str = "none"  # "none","best","author","auto"
    subtitle_lang: str = "en"  # "en","ur","es","ar","fr","de","hi","ja","ko","zh"
    cookie_file: str | None = None
    playlist: bool = False
    output_dir: str = DEFAULT_DOWNLOAD_DIR
    rate_limit: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    gpu_acceleration: bool = False
    proxy: str | None = None
    referer: str | None = None
    custom_title: str | None = None
    thumbnail: str | None = None
    status: str = "queued"
    # Possible statuses:
    #   queued → downloading → completed
    #                        → paused → downloading … → completed
    #                        → paused (game mode) → downloading … → completed
    #                        → cancelled
    #                        → error
    filename: str | None = None
    progress: float = 0.0  # 0.0 – 100.0
    speed: str | None = None
    eta: str | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    output_path: str | None = None

    # ── Internal (not serialized) ─────────────────────────────
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _temp_files: set[str] = field(default_factory=set, repr=False)
    _last_broadcast_time: float = field(default=0.0, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary for API / WS payloads."""
        return {
            "task_id": self.task_id,
            "url": self.url,
            "format_type": self.format_type,
            "quality": self.quality,
            "audio_format": self.audio_format,
            "video_format": self.video_format,
            "subtitles": self.subtitles,
            "subtitle_lang": self.subtitle_lang,
            "playlist": self.playlist,
            "output_dir": self.output_dir,
            "status": self.status,
            "filename": self.filename,
            "progress": round(self.progress, 1),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "output_path": self.output_path,
            "rate_limit": self.rate_limit,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "gpu_acceleration": self.gpu_acceleration,
            "proxy": self.proxy,
            "referer": self.referer,
            "thumbnail": self.thumbnail,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Download Manager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DownloadManager:
    """
    Centralized download engine.

    Usage (wired in server.py lifespan):
        dm = DownloadManager()
        dm.set_event_loop(asyncio.get_running_loop())
        dm.set_broadcast_callback(ws_manager.broadcast)

    Then from any REST route:
        task_id = dm.start_download(url, "video")
    """

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        
        # Load persisted settings (if any)
        initial_settings = load_settings()
        self._max_concurrent_limit = int(initial_settings.get("max_concurrent", MAX_CONCURRENT_DOWNLOADS))
        self._max_concurrent_limit = max(1, min(20, self._max_concurrent_limit))
        self._semaphore = threading.Semaphore(self._max_concurrent_limit)
        
        self._loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_fn: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._game_mode_paused_tasks: set[str] = set()
        self._dev_mode: bool = bool(initial_settings.get("dev_mode", False))
        self._start_game_mode_monitor()
        self._start_task_cleanup_monitor()

    def _start_game_mode_monitor(self):
        import psutil
        def monitor():
            games = {"cod.exe", "modernwarfare.exe", "csgo.exe", "valorant.exe", "r5apex.exe", "gta5.exe"}
            while True:
                game_running = False
                try:
                    for proc in psutil.process_iter(['name']):
                        if proc.info['name'] and proc.info['name'].lower() in games:
                            game_running = True
                            break
                except Exception:
                    pass

                with self._lock:
                    for task in self._tasks.values():
                        # Only suspend tasks that are actively downloading (not already paused by user)
                        if game_running and task.status == "downloading" and task._process:
                            try:
                                psutil.Process(task._process.pid).suspend()
                                task.status = "paused (game mode)"
                                self._broadcast_update(task)
                            except Exception:
                                pass
                        elif not game_running and task.status == "paused (game mode)" and task._process:
                            try:
                                psutil.Process(task._process.pid).resume()
                                task.status = "downloading"
                                self._broadcast_update(task)
                            except Exception:
                                pass
                time.sleep(10)

        thread = threading.Thread(target=monitor, daemon=True, name="hvd-game-monitor")
        thread.start()

    # ── Wiring (called once during server lifespan startup) ───

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main asyncio event loop for the thread→async bridge."""
        self._loop = loop

    def set_broadcast_callback(
        self, fn: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register the async broadcast function (WebSocketManager.broadcast)."""
        self._broadcast_fn = fn

    def set_max_concurrent(self, n: int) -> None:
        """Replace the concurrency semaphore with a new limit (min 1, max 20) and persist."""
        n = max(1, min(20, int(n)))
        self._max_concurrent_limit = n
        self._semaphore = threading.Semaphore(n)
        save_settings({"max_concurrent": n})
        logger.info(f"Max concurrent downloads set and saved to {n}")

    def set_dev_mode(self, enabled: bool) -> None:
        """Enable/disable verbose log broadcasting and persist."""
        self._dev_mode = bool(enabled)
        save_settings({"dev_mode": self._dev_mode})
        logger.info(f"Dev mode {'enabled' if self._dev_mode else 'disabled'} and saved")

    def _start_task_cleanup_monitor(self) -> None:
        """Runs a background thread to purge old completed/cancelled tasks."""
        def monitor():
            while True:
                time.sleep(3600)  # Check every hour
                now = time.time()
                with self._lock:
                    to_remove = []
                    for t_id, t in self._tasks.items():
                        if t.status in ("completed", "cancelled", "error"):
                            # Remove if older than 24 hours
                            if (now - t.created_at) > 86400:
                                to_remove.append(t_id)
                    
                    # Or if history limit exceeded (keep last 200)
                    if len(self._tasks) > 200:
                        # Sort by created_at ascending
                        sorted_tasks = sorted(self._tasks.values(), key=lambda x: x.created_at)
                        for t in sorted_tasks:
                            if len(self._tasks) - len(to_remove) <= 200:
                                break
                            if t.status in ("completed", "cancelled", "error") and t.task_id not in to_remove:
                                to_remove.append(t.task_id)

                    for t_id in to_remove:
                        self._tasks.pop(t_id, None)

        t = threading.Thread(target=monitor, daemon=True, name="hvd-task-cleanup")
        t.start()

    # ── Public API ────────────────────────────────────────────

    def start_download(
        self,
        url: str,
        format_type: str = "video",
        quality: str = "best",
        audio_format: str = "mp3",
        video_format: str = "mp4",
        subtitles: str = "none",
        subtitle_lang: str = "en",
        cookie_file: str | None = None,
        playlist: bool = False,
        output_dir: str | None = None,
        rate_limit: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        gpu_acceleration: bool = False,
        proxy: str | None = None,
        referer: str | None = None,
        custom_title: str | None = None,
        thumbnail: str | None = None,
    ) -> str:
        """
        Create and start a new download task.

        Returns the task_id (12-char hex UUID).
        """
        with self._lock:
            task_id = uuid.uuid4().hex[:12]
            task = DownloadTask(
                task_id=task_id,
                url=url,
                format_type=format_type,
                quality=quality,
                audio_format=audio_format,
                video_format=video_format,
                subtitles=subtitles,
                subtitle_lang=subtitle_lang,
                cookie_file=cookie_file,
                playlist=playlist,
                output_dir=output_dir or DEFAULT_DOWNLOAD_DIR,
                rate_limit=rate_limit,
                start_time=start_time,
                end_time=end_time,
                gpu_acceleration=gpu_acceleration,
                proxy=proxy,
                referer=referer,
                custom_title=custom_title,
                thumbnail=thumbnail,
                filename=custom_title if custom_title else None,
            )
            self._tasks[task_id] = task
            insert_download(task_id, url, title=custom_title or "Initializing...", thumbnail=thumbnail)

        # Spawn isolated worker thread
        thread = threading.Thread(
            target=self._run_download,
            args=(task,),
            name=f"hvd-worker-{task_id}",
            daemon=True,
        )
        task._thread = thread
        thread.start()

        logger.info(
            f"[{task_id}] Started: {url}  "
            f"format={format_type}  quality={quality}"
        )
        return task_id

    def cancel_download(self, task_id: str) -> bool:
        """
        Immediately terminate a download and clean up temp files.
        Returns True if the task was found and cancelled.
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task.status in ("completed", "cancelled"):
            return False

        self._kill_process_tree(task)
        task.status = "cancelled"
        task.progress = 0.0
        task.speed = None
        task.eta = None
        self._cleanup_temp_files(task)
        self._broadcast_update(task)
        logger.info(f"[{task_id}] Cancelled")
        return True

    def pause_download(self, task_id: str) -> bool:
        """
        Suspend a running download subprocess via psutil.
        Returns True on success.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in ("downloading",):
                return False

            try:
                if task._process and task._process.poll() is None:
                    proc = psutil.Process(task._process.pid)
                    # Suspend all threads in the process tree
                    for child in proc.children(recursive=True):
                        try:
                            child.suspend()
                        except psutil.NoSuchProcess:
                            pass
                    proc.suspend()
                    task.status = "paused"
                    self._broadcast_update(task)
                    logger.info(f"[{task_id}] Paused")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                logger.warning(f"[{task_id}] Pause failed: {exc}")
            return False

    def resume_download(self, task_id: str) -> bool:
        """
        Resume a paused or errored download.
        If the process is currently suspended, un-suspends it.
        If the process died, crashed, or errored, re-launches the worker
        with yt-dlp --continue so it resumes downloading from the existing .part file.
        Returns True on success.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in ("paused", "paused (game mode)", "error"):
                return False

            # If the process is still running and was suspended, resume it directly
            if task._process and task._process.poll() is None:
                try:
                    proc = psutil.Process(task._process.pid)
                    proc.resume()
                    for child in proc.children(recursive=True):
                        try:
                            child.resume()
                        except psutil.NoSuchProcess:
                            pass
                    task.status = "downloading"
                    self._broadcast_update(task)
                    logger.info(f"[{task_id}] Resumed suspended process")
                    return True
                except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                    logger.warning(f"[{task_id}] Resume failed: {exc}. Re-launching worker from disk...")

            # Process is no longer running or direct resume failed:
            # Re-queue and re-launch worker thread. yt-dlp's --continue will resume the .part file.
            task.status = "queued"
            task.error_message = None
            task.speed = None
            task.eta = "Resuming..."
            self._broadcast_update(task)

            thread = threading.Thread(
                target=self._run_download,
                args=(task,),
                name=f"hvd-worker-{task_id}",
                daemon=True,
            )
            task._thread = thread
            thread.start()
            logger.info(f"[{task_id}] Re-launched worker thread to resume download from .part file")
            return True

    def get_task(self, task_id: str) -> DownloadTask | None:
        """Return a single task by ID, or None."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """Return all tasks as serialized dictionaries (newest first)."""
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks]

    def shutdown(self) -> None:
        """Kill every active download. Called on server shutdown."""
        logger.info("DownloadManager shutting down — terminating active tasks…")
        for task in list(self._tasks.values()):
            if task.status in ("downloading", "paused", "paused (game mode)", "queued"):
                self._kill_process_tree(task)
                task.status = "cancelled"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Worker Thread
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _run_download(self, task: DownloadTask) -> None:
        """
        Worker function — runs in a dedicated daemon thread.
        Launches yt-dlp as a subprocess, streams structured JSON
        progress, and pushes updates to WebSocket clients.
        """
        task.status = "queued"
        self._broadcast_update(task)

        with self._semaphore:
            try:
                cmd = self._build_command(task)
                logger.debug(f"[{task.task_id}] CMD: {' '.join(cmd)}")

                # Ensure output directory exists
                os.makedirs(task.output_dir, exist_ok=True)

                last_log_time = 0.0
                retry_count = 0
                max_retries = 10

                while True:
                    task._process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,  # Line-buffered
                        creationflags=SUBPROCESS_FLAGS,
                        cwd=task.output_dir,
                        env=dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8"),
                    )
                    task.status = "downloading"
                    self._broadcast_update(task)

                    logged_lines = []
                    assert task._process.stdout is not None
                    for raw_line in iter(task._process.stdout.readline, ''):
                        line = raw_line.strip()
                        if not line:
                            continue

                        logged_lines.append(line)

                        # Match yt-dlp unbuffered real-time progress lines:
                        # e.g.: [download]  42.9% of  510.78MiB at   17.58MiB/s ETA 00:25
                        m_prog = PROGRESS_RE.search(line)
                        if m_prog:
                            try:
                                pct = float(m_prog.group(1))
                                total_str = m_prog.group(2)
                                spd_raw = m_prog.group(3).strip()
                                eta_raw = m_prog.group(4).strip()

                                tot_bytes = _parse_size_bytes(total_str)
                                if tot_bytes > 0:
                                    task.total_bytes = tot_bytes
                                    task.downloaded_bytes = int((pct / 100.0) * tot_bytes)

                                task.progress = min(99.0, pct)
                                if spd_raw and spd_raw != "Unknown B/s":
                                    task.speed = spd_raw
                                if eta_raw and eta_raw != "Unknown":
                                    task.eta = eta_raw

                                if task.status not in ("paused", "paused (game mode)"):
                                    task.status = "downloading"

                                now = time.time()
                                if (now - task._last_broadcast_time >= 0.10):
                                    task._last_broadcast_time = now
                                    self._broadcast_update(task)

                                if now - last_log_time >= 1.0:
                                    last_log_time = now
                                    dl_mb = task.downloaded_bytes / (1024 * 1024)
                                    tot_mb = task.total_bytes / (1024 * 1024) if task.total_bytes > 0 else 0
                                    sz_disp = f"{dl_mb:.1f} MB / {tot_mb:.1f} MB" if tot_mb > 0 else f"{dl_mb:.1f} MB"
                                    fmt_str = f"Progress: {task.progress:.1f}% | Speed: {task.speed or 'N/A'} | ETA: {task.eta or 'N/A'} | {sz_disp}"
                                    self._broadcast_log(task.task_id, fmt_str)
                            except Exception:
                                pass
                            continue

                        # JSON progress from --progress-template (if present)
                        if line.startswith("{"):
                            try:
                                data = json.loads(line)
                                self._handle_progress(task, data)
                                if data.get("status") == "downloading":
                                    now = time.time()
                                    if now - last_log_time >= 1.0:
                                        last_log_time = now
                                        downloaded = data.get("downloaded_bytes") or 0
                                        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                                        pct = (downloaded / total * 100) if total > 0 else 0.0
                                        spd_str = task.speed or "0 B/s"
                                        eta_str = task.eta or "00:00"
                                        dl_mb = downloaded / (1024 * 1024)
                                        tot_mb = total / (1024 * 1024) if total > 0 else 0
                                        sz_disp = f"{dl_mb:.1f} MB / {tot_mb:.1f} MB" if total > 0 else f"{dl_mb:.1f} MB"
                                        fmt_str = f"Progress: {pct:.1f}% | Speed: {spd_str} | ETA: {eta_str} | {sz_disp}"
                                        self._broadcast_log(task.task_id, fmt_str)
                            except json.JSONDecodeError:
                                logger.debug(f"[{task.task_id}] Non-JSON brace line: {line[:80]}")
                            continue

                        # Final filepath from --print "after_move:…"
                        if line.startswith("HVD_FILEPATH:"):
                            file_part = line[len("HVD_FILEPATH:"):]
                            p = Path(file_part)
                            if not p.is_absolute():
                                p = Path(task.output_dir) / p
                            task.output_path = str(p.resolve())
                            task.filename = p.name
                            self._broadcast_log(task.task_id, f"File saved: {task.filename}")
                            continue

                        if "[download] Destination:" in line:
                            dest_name = line.split("[download] Destination:", 1)[1].strip()
                            if dest_name and not task.filename:
                                clean_name = re.sub(r'(\.f\d+)?(\.part)?$', '', Path(dest_name).name)
                                target_ext = task.video_format if task.format_type == "video" else task.audio_format
                                if not clean_name.endswith(f".{target_ext}"):
                                    clean_name += f".{target_ext}"
                                task.filename = clean_name
                                update_title(task.task_id, Path(clean_name).stem)
                                if task.status not in ("paused", "paused (game mode)"):
                                    task.status = "downloading"
                                self._broadcast_update(task)

                        # Finalizing / Converting states (post-processing steps only)
                        elif any(kw in line for kw in ["[Merger]", "[VideoConvertor]", "[VideoRemuxer]", "[FixupM3u8]", "[EmbedSubtitle]", "[EmbedThumbnail]", "[Metadata]"]):
                            task.status = "converting"
                            task.progress = 99.0
                            task.speed = None
                            task.eta = "Finalizing video..."
                            self._broadcast_update(task)

                        # Broadcast normal status and log lines
                        is_verbose = line.startswith("[debug]")
                        if self._dev_mode or not is_verbose:
                            self._broadcast_log(task.task_id, line)

                    return_code = task._process.wait()

                    if task.status == "cancelled":
                        break  # Already handled by cancel_download()

                    if return_code == 0:
                        task.status = "completed"
                        task.progress = 100.0
                        task.speed = None
                        task.eta = None
                        logger.info(f"[{task.task_id}] Completed: {task.filename}")
                        break
                    else:
                        # 1. Detect invalid / rotated cookies or 403 Forbidden with cookies
                        is_cookie_invalid = any("cookies are no longer valid" in ln or "rotated in the browser" in ln for ln in logged_lines)
                        is_forbidden = any("HTTP Error 403" in ln or "Forbidden" in ln for ln in logged_lines)

                        if task.cookie_file and (is_cookie_invalid or is_forbidden):
                            self._broadcast_log(
                                task.task_id,
                                "[Auth Fallback] Cookie file is invalid or expired (HTTP 403 Forbidden). "
                                "Retrying download automatically without cookies..."
                            )
                            logger.warning(
                                f"[{task.task_id}] Cookie file '{task.cookie_file}' rejected by YouTube. "
                                "Retrying without cookies..."
                            )
                            task.cookie_file = None  # Remove cookie file
                            cmd = self._build_command(task)  # Rebuild command without --cookies
                            time.sleep(1)
                            continue

                        # 2. If it's a fatal authorization or blocked stream, do NOT loop endlessly
                        if is_forbidden or any(kw in ln for ln in logged_lines for kw in ["Private video", "Sign in if you've been granted access", "This video is private"]):
                            error_detail = "HTTP Error 403: Forbidden (Access blocked or session expired)."
                            if is_cookie_invalid:
                                error_detail = "YouTube cookies expired/invalid. Please clear or update cookie file in Settings."
                            task.status = "error"
                            task.error_message = error_detail
                            self._broadcast_log(task.task_id, f"[Fatal Error] {error_detail}")
                            logger.error(f"[{task.task_id}] {error_detail}")
                            break

                        # 3. Check for genuine network drops/timeouts
                        has_network_error = False
                        network_keywords = [
                            "HTTPSConnectionPool", "timeout", "Connection reset",
                            "Connection refused", "Network is unreachable",
                            "Name or service not known",
                            "Temporary failure in name resolution",
                            "HTTP Error 429", "Too Many Requests",
                        ]
                        for ln in logged_lines:
                            if any(kw in ln for kw in network_keywords):
                                has_network_error = True
                                break

                        if has_network_error and retry_count < max_retries:
                            retry_count += 1
                            self._broadcast_log(
                                task.task_id,
                                f"[Network Drop Guard] Connection timeout/drop detected. "
                                f"Retry {retry_count}/{max_retries} in 5 seconds..."
                            )
                            logger.warning(
                                f"[{task.task_id}] Network timeout/drop detected. "
                                f"Retry {retry_count}/{max_retries} in 5 seconds..."
                            )
                            time.sleep(5)
                            continue  # --continue is already in YTDLP_RESILIENCE_FLAGS
                        else:
                            task.status = "error"
                            err_line = next((ln for ln in reversed(logged_lines) if ln.startswith("ERROR:")), None)
                            task.error_message = (
                                err_line if err_line else f"yt-dlp exited with code {return_code}"
                            )
                            logger.error(f"[{task.task_id}] Failed (exit {return_code}): {task.error_message}")
                            break

            except FileNotFoundError:
                task.status = "error"
                task.error_message = (
                    f"yt-dlp not found at '{YTDLP_PATH}'. "
                    "Ensure yt-dlp.exe is in the application directory."
                )
                logger.error(f"[{task.task_id}] {task.error_message}")

            except Exception as exc:
                task.status = "error"
                task.error_message = str(exc)
                logger.exception(f"[{task.task_id}] Worker exception")

            finally:
                db_status = task.status
                if task.status == "error":
                    db_status = "failed"
                if task.status == "completed" and (task.output_path or task.filename):
                    from database import update_download_completed
                    size = 0
                    if task.output_path and os.path.exists(task.output_path):
                        try:
                            size = os.path.getsize(task.output_path)
                        except Exception:
                            pass
                    update_download_completed(task.task_id, task.output_path or "", task.filename, size, getattr(task, "thumbnail", None))
                else:
                    update_status(task.task_id, db_status)
                self._broadcast_update(task)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Command Builder
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_command(self, task: DownloadTask) -> list[str]:
        """Construct the full yt-dlp command for a task."""
        cmd: list[str] = [
            YTDLP_PATH,
            "--ffmpeg-location", FFMPEG_PATH,
            # Real-time unbuffered progress output
            "--newline",
            "--no-colors",
            "--progress",
            "--progress-delta", "0.2",
            # Print final filepath after all post-processing
            "--print", "after_move:HVD_FILEPATH:%(filepath)s",
            # Network resilience
            *YTDLP_RESILIENCE_FLAGS,
            # Embed metadata & cover art
            "--embed-metadata",
            "--embed-thumbnail",
        ]

        # Output template (respect custom title from sniffer if present)
        if getattr(task, "custom_title", None):
            clean_t = "".join(c for c in task.custom_title if c.isalnum() or c in (" ", "-", "_", "(", ")", ".")).strip()[:140]
            if clean_t:
                cmd.extend(["-o", f"{clean_t}.%(ext)s"])
            else:
                cmd.extend(["-o", "%(playlist_index&%s - |)s%(title).200s.%(ext)s"])
        else:
            cmd.extend(["-o", "%(playlist_index&%s - |)s%(title).200s.%(ext)s"])

        # ── Playlist vs Single ────────────────────────────────
        if not task.playlist:
            cmd.append("--no-playlist")
        # (If playlist=True, omit --no-playlist so yt-dlp expands the list)

        # ── Cookie File ───────────────────────────────────────
        if task.cookie_file:
            from config import resolve_and_convert_cookie
            converted_cookie = resolve_and_convert_cookie(task.cookie_file)
            if converted_cookie:
                cmd.extend(["--cookies", converted_cookie])
            
        # ── Proxy ─────────────────────────────────────────────
        if task.proxy:
            cmd.extend(["--proxy", task.proxy])

        # ── Format Selection ──────────────────────────────────
        if task.format_type == "audio":
            if task.audio_format == "best":
                cmd.extend(['-f', 'ba/b', '-x'])
            else:
                cmd.extend(["-x", "--audio-format", task.audio_format, "--audio-quality", "0"])
        elif task.format_type == "video":
            vcodec_filter = ""
            if task.video_format in ["mov", "avi"]:
                vcodec_filter = "[vcodec^=avc]"
            
            ext_filter = ""
            if task.video_format == "mp4":
                ext_filter = "[ext=mp4]"
            
            format_str = f"bv*{ext_filter}{vcodec_filter}+ba/b"
            if task.video_format == "mp4":
                format_str = f"bv*[ext=mp4]{vcodec_filter}+ba[ext=m4a]/b"
                
            cmd.extend(["-f", format_str, "--merge-output-format", task.video_format])
            
            # Ensure container format always matches the user's choice (.mkv, .mp4, .webm)
            if task.video_format in ["mkv", "mp4", "webm", "mov", "avi"]:
                cmd.extend(["--remux-video", task.video_format])
            
            if task.quality and task.quality != "best":
                cmd.extend(["-S", f"res:{task.quality}"])
            if task.video_format == "mov":
                cmd.extend(["--postprocessor-args", "Merger+ffmpeg:-c:a aac"])
                
        # ── GPU Hardware Acceleration ──────────────────────────
        if task.gpu_acceleration:
            cmd.extend(['--postprocessor-args', 'VideoConvertor:-c:v h264_nvenc'])

        # ── Subtitles ─────────────────────────────────────────
        if task.subtitles != "none":
            lang = task.subtitle_lang or "en"
            if not lang or lang.startswith("live_chat"):
                lang = "en"
            cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", f"{lang}.*"])
            # Embed subs into video container if video download
            if task.format_type == "video":
                cmd.extend(["--embed-subs", "--convert-subs", "srt", "--compat-options", "no-keep-subs"])

        # ── Power-User Features ──────────────────────────────
        if task.rate_limit:
            cmd.extend(["--limit-rate", task.rate_limit])

        if task.start_time or task.end_time:
            st = (task.start_time or "").strip() or "0"
            et = (task.end_time or "").strip() or "inf"
            cmd.extend(["--download-sections", f"*{st}-{et}"])
            cmd.append("--force-keyframes-at-cuts")

        if task.referer:
            cmd.extend(["--referer", task.referer.strip()])

        cmd.append("--verbose")
        # URL must be last
        cmd.append(task.url)
        return cmd

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Progress Handler
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _handle_progress(self, task: DownloadTask, data: dict[str, Any]) -> None:
        """Process a parsed JSON progress object from yt-dlp."""
        status = data.get("status", "")

        # Track temp files for targeted cleanup on cancel
        tmpfile = data.get("tmpfilename")
        if tmpfile:
            task._temp_files.add(tmpfile)

        # Extract filename (prefer clean target filename over temp name)
        fname = data.get("filename") or tmpfile
        if fname and not task.filename:
            raw_stem = Path(fname).name
            clean_name = re.sub(r'(\.f\d+)?(\.part)?$', '', raw_stem)
            target_ext = task.video_format if task.format_type == "video" else task.audio_format
            if not clean_name.endswith(f".{target_ext}"):
                clean_name += f".{target_ext}"
            task.filename = clean_name
            update_title(task.task_id, Path(clean_name).stem)

        # Extract title from info_dict if available
        title = data.get("info_dict", {}).get("title")
        if title:
            update_title(task.task_id, title)

        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes", 0)

            if total > 0:
                task.progress = min((downloaded / total) * 100.0, 99.0)

            task.downloaded_bytes = downloaded
            task.total_bytes = total

            # Speed — prefer raw numeric value, fall back to formatted string
            raw_speed = data.get("speed")
            if raw_speed and isinstance(raw_speed, (int, float)):
                task.speed = self._format_speed(raw_speed)
            else:
                task.speed = (data.get("_speed_str") or "").strip() or None

            # ETA — prefer raw seconds, fall back to formatted string
            raw_eta = data.get("eta")
            if raw_eta is not None and isinstance(raw_eta, (int, float)):
                task.eta = self._format_eta(int(raw_eta))
            else:
                task.eta = (data.get("_eta_str") or "").strip() or None

            # Append readable total size to ETA (e.g. 01:25 • 222.4 MB)
            size_str = data.get("_total_bytes_str") or (f"{total / (1024*1024):.1f} MB" if total > 0 else None)
            if size_str and task.eta:
                task.eta = f"{task.eta} • {size_str.strip()}"

            if task.status not in ("paused", "paused (game mode)"):
                task.status = "downloading"

        elif status == "finished":
            # Intermediate stream finished (e.g. video stream finished, audio or merging next)
            task.speed = None
            task.eta = "Processing..."

        # Broadcast update at 100ms interval for silky-smooth live meter
        now = time.time()
        if (now - task._last_broadcast_time >= 0.10) or (status != "downloading"):
            task._last_broadcast_time = now
            self._broadcast_update(task)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Internal Helpers
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _broadcast_update(self, task: DownloadTask) -> None:
        """
        Push current task state to every connected WebSocket client.
        Thread-safe: uses asyncio.run_coroutine_threadsafe() to bridge
        from worker threads into the server's async event loop.
        """
        if not self._broadcast_fn or not self._loop:
            return

        payload: dict[str, Any] = {"type": "progress", **task.to_dict()}
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_fn(payload), self._loop
            )
        except RuntimeError:
            # Event loop is closed (server shutting down)
            pass

    def broadcast_custom_progress(self, payload: dict[str, Any]) -> None:
        """Push arbitrary progress payload to connected WebSockets safely across threads."""
        if not self._broadcast_fn or not self._loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_fn(payload), self._loop
            )
        except RuntimeError:
            pass

    def _broadcast_log(self, task_id: str, message: str) -> None:
        """Push a raw log line to WebSocket clients."""
        if not self._broadcast_fn or not self._loop:
            return
        payload: dict[str, Any] = {
            "type": "log",
            "task_id": task_id,
            "message": message,
        }
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_fn(payload), self._loop
            )
        except RuntimeError:
            pass

    def _kill_process_tree(self, task: DownloadTask) -> None:
        """Terminate a subprocess and all its child processes."""
        if not task._process:
            return
        try:
            parent = psutil.Process(task._process.pid)
            # If the process was suspended, resume first so Windows OS can terminate it cleanly
            try:
                parent.resume()
            except Exception:
                pass
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.resume()
                except Exception:
                    pass
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            task._process.wait(timeout=5)
        except psutil.NoSuchProcess:
            pass  # Already dead
        except subprocess.TimeoutExpired:
            logger.warning(f"[{task.task_id}] Process didn't exit within 5s timeout")
        except Exception as exc:
            logger.warning(f"[{task.task_id}] Kill error: {exc}")

    def _cleanup_temp_files(self, task: DownloadTask) -> None:
        """
        Remove temporary .part / .ytdl files left by a cancelled download.
        Only targets files explicitly tracked via progress updates
        (safe — won't touch unrelated files in the Downloads folder).
        """
        for filepath in task._temp_files:
            try:
                p = Path(filepath)
                if p.exists():
                    p.unlink()
                    logger.debug(f"[{task.task_id}] Cleaned: {p.name}")
            except OSError as exc:
                logger.debug(f"[{task.task_id}] Cleanup skip: {exc}")

        # Also try to remove the .part variant of the main filename
        if task.filename:
            part_file = Path(task.output_dir) / (task.filename + ".part")
            try:
                if part_file.exists():
                    part_file.unlink()
                    logger.debug(f"[{task.task_id}] Cleaned: {part_file.name}")
            except OSError:
                pass

    # ── Formatting Utilities ──────────────────────────────────

    @staticmethod
    def _format_speed(bytes_per_sec: float) -> str:
        """Convert bytes/sec to a human-readable string."""
        if bytes_per_sec <= 0:
            return "0 B/s"
        units = [
            (1024**3, "GB/s"),
            (1024**2, "MB/s"),
            (1024, "KB/s"),
            (1, "B/s"),
        ]
        for threshold, label in units:
            if bytes_per_sec >= threshold:
                value = bytes_per_sec / threshold
                # 1 decimal for GB/s (rare), 2 decimals for MB/s and smaller
                precision = 1 if threshold >= 1024**3 else 2
                return f"{value:.{precision}f} {label}"
        return f"{bytes_per_sec:.0f} B/s"

    @staticmethod
    def _format_eta(seconds: int) -> str:
        """Convert seconds to mm:ss or h:mm:ss."""
        if seconds < 0:
            return "∞"
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
