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
    dest_dir = (src_dir.parent / "Horizon_Video_Downloader_v5.2_BACKUP").resolve()

    print(f"Backup Initiated...")
    print(f"Source:      {src_dir}")
    print(f"Destination: {dest_dir}")

    src_sub = dest_dir / "1_SOURCE_CODE"
    src_sub.parent.mkdir(parents=True, exist_ok=True)

    if src_sub.exists():
        print("Refreshing 1_SOURCE_CODE...")
        try:
            shutil.rmtree(src_sub, ignore_errors=True)
        except Exception as e:
            print(f"Warning: Could not clear existing source directory: {e}")

    try:
        shutil.copytree(src_dir, src_sub, ignore=ignore_patterns)
        print("Source Code Backup Completed Successfully!")
    except Exception as e:
        print(f"Error during file copy: {e}")
        sys.exit(1)


if __name__ == "__main__":
    make_backup()
