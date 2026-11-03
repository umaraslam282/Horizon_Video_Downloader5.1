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
            file_size INTEGER DEFAULT 0
        )
    """)
    # Add columns if upgrading from earlier schema
    for col, col_type in [("file_path", "TEXT"), ("filename", "TEXT"), ("file_size", "INTEGER DEFAULT 0")]:
        try:
            cursor.execute(f"ALTER TABLE downloads ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def insert_download(task_id: str, url: str, title: str = "Initializing..."):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO downloads (id, url, title, status) VALUES (?, ?, ?, ?)",
            (task_id, url, title, "queued")
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error (insert_download): {e}")
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

def update_download_completed(task_id: str, file_path: str, filename: str | None = None, file_size: int = 0):
    """Mark a task as completed and persist the exact destination path on disk."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
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
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    history = []
    try:
        cursor.execute("SELECT id, url, title, status, timestamp, file_path, filename, file_size FROM downloads ORDER BY timestamp DESC")
        for row in cursor.fetchall():
            fp = row["file_path"]
            exists = bool(fp and Path(fp).exists() and Path(fp).is_file())
            history.append({
                "id": row["id"],
                "url": row["url"],
                "title": row["title"],
                "status": row["status"],
                "timestamp": row["timestamp"],
                "file_path": fp,
                "filename": row["filename"] or (Path(fp).name if fp else None),
                "file_size": row["file_size"] or 0,
                "file_exists": exists,
            })
    except Exception as e:
        logger.error(f"DB Error (get_all_history): {e}")
    finally:
        conn.close()
    return history

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
