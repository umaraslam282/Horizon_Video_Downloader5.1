import os
import shutil
import sys
from pathlib import Path


def ignore_patterns(path, names):
    """Filter out standard development noise, build caches, and large media."""
    ignored = []
    for name in names:
        if name in ("__pycache__", ".git", ".venv", "dist", "build"):
            ignored.append(name)
        elif name.endswith((".tmp", ".part", ".ytdl", ".mp4", ".m4a", ".webm")):
            ignored.append(name)
    return ignored


def make_backup():
    # Current project directory
    src_dir = Path(__file__).resolve().parent
    # Target directory (one level up)
    dest_dir = (src_dir.parent / "complete vid downloader project").resolve()

    print(f"Backup Initiated...")
    print(f"Source:      {src_dir}")
    print(f"Destination: {dest_dir}")

    if dest_dir.exists():
        print("Clearing old backup copy at destination...")
        try:
            shutil.rmtree(dest_dir, ignore_errors=True)
        except Exception as e:
            print(f"Error: Unable to remove existing backup directory: {e}")
            sys.exit(1)

    try:
        shutil.copytree(src_dir, dest_dir, ignore=ignore_patterns)
        print("Backup Completed Successfully!")
    except Exception as e:
        print(f"Error during file copy: {e}")
        sys.exit(1)


if __name__ == "__main__":
    make_backup()
