import sys
import os
import subprocess

def pick_folder(initial_dir=""):
    if initial_dir and not os.path.isdir(initial_dir):
        initial_dir = ""
    # 1. Try Tkinter in this dedicated process
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder = filedialog.askdirectory(initialdir=initial_dir or None, title="Select Destination Folder")
        root.destroy()
        if folder and os.path.isdir(folder):
            print(os.path.abspath(folder))
            return
    except Exception:
        pass

    # 2. Native Windows COM fallback
    try:
        ps_cmd = (
            "$s = New-Object -ComObject Shell.Application; "
            "$f = $s.BrowseForFolder(0, 'Select Destination Folder', 0x50, 0); "
            "if ($f) { [Console]::WriteLine($f.Self.Path) }"
        )
        res = subprocess.run(
            ["powershell", "-STA", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=60
        )
        p = res.stdout.strip()
        if p and os.path.isdir(p):
            print(p)
            return
    except Exception:
        pass

if __name__ == "__main__":
    init_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    pick_folder(init_dir)
