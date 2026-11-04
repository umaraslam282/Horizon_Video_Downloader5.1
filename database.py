import sqlite3
import logging
from pathlib import Path
import time

from config import RUNTIME_DIR

logger = logging.getLogger("hvd.db")

# Use RUNTIME_DIR so the DB is always next to the EXE when frozen,
# and next to the source files in dev mode.
DB_PATH = RUNTIME_DIR / "history.db"

def get_connection():
    """Return a SQLite connection with timeout and WAL mode enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id TEXT PRIMARY KEY,
            url TEXT,
            title TEXT,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            filename TEXT,
            file_size INTEGER DEFAULT 0,
            thumbnail TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_archive (
            creator TEXT,
            media_id TEXT PRIMARY KEY,
            media_url TEXT,
            title TEXT,
            downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add columns if upgrading from earlier schema
    for col, col_type in [
        ("file_path", "TEXT"),
        ("filename", "TEXT"),
        ("file_size", "INTEGER DEFAULT 0"),
        ("thumbnail", "TEXT"),
        ("batch_id", "TEXT"),
        ("batch_title", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE downloads ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    conn.commit()
    conn.close()
    try:
        sync_existing_downloads()
    except Exception:
        pass

def insert_download(
    task_id: str,
    url: str,
    title: str = "Initializing...",
    thumbnail: str | None = None,
    batch_id: str | None = None,
    batch_title: str | None = None,
    file_path: str | None = None,
    filename: str | None = None,
    file_size: int = 0,
):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO downloads 
               (id, url, title, status, thumbnail, batch_id, batch_title, file_path, filename, file_size) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, url, title, "queued", thumbnail, batch_id, batch_title, file_path, filename, file_size)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (insert_download): {e}")
    finally:
        conn.close()

def update_download_thumbnail(task_id: str, thumbnail: str):
    """Update thumbnail URL for a task."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE downloads SET thumbnail = ? WHERE id = ?", (thumbnail, task_id))
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (update_download_thumbnail): {e}")
    finally:
        conn.close()

def update_status(task_id: str, status: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE downloads SET status = ? WHERE id = ?",
            (status, task_id)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (update_status): {e}")
    finally:
        conn.close()

def update_download_completed(
    task_id: str,
    file_path: str,
    filename: str | None = None,
    file_size: int = 0,
    thumbnail: str | None = None,
    batch_id: str | None = None,
    batch_title: str | None = None,
):
    """Mark a task as completed and persist the exact destination path on disk."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if batch_id:
            cursor.execute(
                """UPDATE downloads 
                   SET status = 'completed', file_path = ?, filename = ?, file_size = ?, thumbnail = ?, batch_id = ?, batch_title = ? 
                   WHERE id = ?""",
                (file_path, filename, file_size, thumbnail, batch_id, batch_title, task_id)
            )
        elif thumbnail:
            cursor.execute(
                """UPDATE downloads 
                   SET status = 'completed', file_path = ?, filename = ?, file_size = ?, thumbnail = ? 
                   WHERE id = ?""",
                (file_path, filename, file_size, thumbnail, task_id)
            )
        else:
            cursor.execute(
                """UPDATE downloads 
                   SET status = 'completed', file_path = ?, filename = ?, file_size = ? 
                   WHERE id = ?""",
                (file_path, filename, file_size, task_id)
            )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (update_download_completed): {e}")
    finally:
        conn.close()

def get_download_by_id(task_id: str) -> dict | None:
    """Retrieve full record for a specific download task."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    row = None
    try:
        cursor.execute(
            "SELECT id, url, title, status, timestamp, file_path, filename, file_size FROM downloads WHERE id = ?",
            (task_id,)
        )
        r = cursor.fetchone()
        if r:
            row = dict(r)
    except Exception as e:
        logger.error(f"DB Error (get_download_by_id): {e}")
    finally:
        conn.close()
    return row

def clear_all_history():
    """Clear all records from downloads history."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM downloads")
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (clear_all_history): {e}")
    finally:
        conn.close()

def update_title(task_id: str, title: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE downloads SET title = ? WHERE id = ?",
            (title, task_id)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (update_title): {e}")
    finally:
        conn.close()

def get_all_history():
    import re
    from config import DEFAULT_DOWNLOAD_DIR, load_settings
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    history = []
    try:
        cursor.execute(
            """SELECT id, url, title, status, timestamp, file_path, filename, file_size, thumbnail, batch_id, batch_title 
               FROM downloads ORDER BY timestamp DESC"""
        )
        settings = load_settings()
        search_dirs = [
            settings.get("social_output_dir"),
            settings.get("output_dir"),
            DEFAULT_DOWNLOAD_DIR,
            str(Path.home() / "Downloads"),
            str(Path.home() / "Downloads" / "Instagram"),
        ]

        for row in cursor.fetchall():
            fp = row["file_path"]
            exists = bool(fp and Path(fp).exists() and Path(fp).is_file())
            raw_url = row["url"] or ""
            thumb = row["thumbnail"]
            fname = row["filename"] or row["title"]

            # Auto-heal path if file exists in standard locations
            if not exists and fname:
                for sdir in search_dirs:
                    if not sdir or not Path(sdir).exists():
                        continue
                    p_sdir = Path(sdir)
                    cand = p_sdir / fname
                    if cand.exists() and cand.is_file():
                        fp = str(cand.resolve())
                        exists = True
                        break
                    try:
                        for subcand in p_sdir.glob(f"**/{fname}"):
                            if subcand.is_file():
                                fp = str(subcand.resolve())
                                exists = True
                                break
                        if exists:
                            break
                    except Exception:
                        pass
                if exists and fp:
                    try:
                        cursor.execute("UPDATE downloads SET file_path = ? WHERE id = ?", (fp, row["id"]))
                    except Exception:
                        pass

            if exists:
                thumb = f"/api/history/thumbnail/{row['id']}"
            elif not thumb and raw_url and ("youtube.com" in raw_url or "youtu.be" in raw_url):
                yt_m = re.search(r"(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", raw_url)
                if yt_m:
                    thumb = f"https://i.ytimg.com/vi/{yt_m.group(1)}/hqdefault.jpg"

            # Check / infer batch collection
            bid = row["batch_id"] or ""
            btitle = row["batch_title"] or ""
            fn = row["filename"] or row["title"] or ""
            if not bid and (fn.startswith("Instagram_") or (fp and "Instagram" in fp)):
                m = re.search(r"Instagram_([a-zA-Z0-9_\.]+)_", fn)
                if m:
                    creator_name = m.group(1)
                    bid = f"batch_ig_{creator_name.lower()}"
                    btitle = f"Instagram: @{creator_name}"

            history.append({
                "id": row["id"],
                "url": raw_url,
                "title": row["title"],
                "status": row["status"],
                "timestamp": row["timestamp"],
                "file_path": fp,
                "filename": row["filename"] or (Path(fp).name if fp else None),
                "file_size": row["file_size"] or 0,
                "file_exists": exists,
                "thumbnail": thumb or "",
                "batch_id": bid,
                "batch_title": btitle,
            })
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (get_all_history): {e}")
    finally:
        conn.close()
    return history


def sync_existing_downloads():
    """Auto-discover downloaded files from user Downloads and sync into database history."""
    import hashlib
    import re
    from config import load_settings, DEFAULT_DOWNLOAD_DIR

    settings = load_settings()
    scan_roots = []
    social_dir = settings.get("social_output_dir")
    if social_dir and Path(social_dir).exists():
        scan_roots.append(Path(social_dir))

    default_ig = Path(DEFAULT_DOWNLOAD_DIR) / "Instagram"
    if default_ig.exists():
        scan_roots.append(default_ig)

    user_ig = Path.home() / "Downloads" / "Instagram"
    if user_ig.exists() and user_ig not in scan_roots:
        scan_roots.append(user_ig)

    if not scan_roots:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT file_path, filename FROM downloads")
        existing_paths = set()
        existing_names = set()
        for r in cursor.fetchall():
            if r[0]:
                try:
                    existing_paths.add(str(Path(r[0]).resolve()).lower())
                except Exception:
                    pass
            if r[1]:
                existing_names.add(r[1].lower())

        for root in scan_roots:
            for f in root.glob("**/*"):
                if not f.is_file():
                    continue
                suf = f.suffix.lower()
                if suf not in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".jpg", ".jpeg", ".png", ".webp", ".mp3", ".m4a", ".wav"):
                    continue
                if f.name.startswith("temp_") or f.name.startswith("."):
                    continue

                f_res = f.resolve()
                if str(f_res).lower() in existing_paths or f.name.lower() in existing_names:
                    continue

                # Creator and batch detection
                parent_folder = f.parent.name
                grandparent = f.parent.parent.name
                creator = ""
                if parent_folder.startswith("@"):
                    creator = parent_folder[1:]
                elif grandparent.startswith("@"):
                    creator = grandparent[1:]
                else:
                    m = re.search(r"Instagram_([a-zA-Z0-9_\.]+)_", f.name)
                    if m:
                        creator = m.group(1)

                clean_creator = creator.strip()
                batch_id = f"batch_ig_{clean_creator.lower()}" if clean_creator else "batch_ig_downloads"
                batch_title = f"Instagram: @{clean_creator}" if clean_creator else "Instagram Downloads"

                task_id = f"soc_{hashlib.md5(str(f_res).encode()).hexdigest()[:8]}"
                sz = f.stat().st_size
                mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f.stat().st_mtime))

                cursor.execute(
                    """INSERT OR IGNORE INTO downloads 
                       (id, url, title, status, timestamp, file_path, filename, file_size, thumbnail, batch_id, batch_title)
                       VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task_id,
                        f"https://www.instagram.com/{clean_creator}/" if clean_creator else "",
                        f.name,
                        mtime_str,
                        str(f_res),
                        f.name,
                        sz,
                        f"/api/history/thumbnail/{task_id}",
                        batch_id,
                        batch_title,
                    )
                )
                existing_paths.add(str(f_res).lower())
                existing_names.add(f.name.lower())
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (sync_existing_downloads): {e}")
    finally:
        conn.close()

def delete_history_item(task_id: str) -> bool:
    """Delete a single record from downloads history."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM downloads WHERE id = ?", (task_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"DB Error (delete_history_item): {e}")
        return False
    finally:
        conn.close()

def delete_batch_history(batch_id: str) -> bool:
    """Delete an entire batch/collection from downloads history."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM downloads WHERE batch_id = ?", (batch_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"DB Error (delete_batch_history): {e}")
        return False
    finally:
        conn.close()

def is_media_archived(creator: str, media_id: str) -> bool:
    """Check if a creator's post or video is already in the inventory archive."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT media_id FROM inventory_archive WHERE creator = ? AND media_id = ?", (creator.lower(), str(media_id)))
        return bool(cursor.fetchone())
    except Exception as e:
        logger.error(f"DB Error (is_media_archived): {e}")
        return False
    finally:
        conn.close()

def archive_media(creator: str, media_id: str, media_url: str = "", title: str = ""):
    """Record a media item as downloaded for a creator."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO inventory_archive (creator, media_id, media_url, title) VALUES (?, ?, ?, ?)",
            (creator.lower(), str(media_id), media_url, title)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (archive_media): {e}")
    finally:
        conn.close()

def get_archived_count(creator: str | None = None) -> int:
    """Return count of downloaded items for a creator, or total if None."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if creator:
            cursor.execute("SELECT COUNT(*) FROM inventory_archive WHERE creator = ?", (creator.lower(),))
        else:
            cursor.execute("SELECT COUNT(*) FROM inventory_archive")
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"DB Error (get_archived_count): {e}")
        return 0
    finally:
        conn.close()

def check_duplicate(url: str) -> bool:
    """Check if a URL has already been downloaded successfully."""
    conn = get_connection()
    cursor = conn.cursor()
    has_dup = False
    try:
        cursor.execute("SELECT id FROM downloads WHERE url = ? AND status = 'completed'", (url,))
        if cursor.fetchone():
            has_dup = True
    except Exception as e:
        logger.error(f"DB Error (check_duplicate): {e}")
    finally:
        conn.close()
    return has_dup

# Automatically initialize database on module import
init_db()
