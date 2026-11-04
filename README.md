# Horizon Video Downloader v5.2 🚀

<div align="center">

![Horizon Downloader](static/img/instagram_icon.jpg)

**High-Performance Portable Media Downloader with Companion Stream Sniffer & Instagram Profile Archiver**

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg?style=flat-square&logo=python)](https://python.org)
[![Engine](https://img.shields.io/badge/Engine-yt--dlp%202026.10-red.svg?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078d7.svg?style=flat-square&logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

</div>

---

## 🌟 What is Horizon?

**Horizon Video Downloader** is a high-speed, modern desktop media downloader built with Python, Starlette, yt-dlp, and Chrome DevTools Protocol (CDP). Designed with a cyber-glassmorphism dark UI, Horizon delivers a commercial-grade downloading experience with zero ads, zero tracking, and native speed.

---

## ✨ Flagship Features in v5.2

### 📸 1. Instagram Profile & Creator Archiver
* **Unlimited Extraction**: Paste any creator's profile URL to grab all public Posts, Reels, Carousels, and HD profile avatars without the artificial limits.
* **Auto-Categorized Subfolders**: Automatically organizes media into structured folders (`@username/posts/`, `@username/reels/`, `@username/avatar/`).
* **Live Scraping Stream**: Real-time progress bar with an instant "Stop" button and media item count counters.

### 🔄 2. Creator Watchlist & Inventory Sync
* **Watchlist Engine**: Add your favorite content creators to your watchlist in Settings.
* **Incremental Sync**: The "Update Inventory" engine scans for new posts and downloads newly published media without re-downloading previously archived content.
* **Windows Startup Integration**: Optional silent background startup so your favorite feeds stay synchronized.

### 📁 3. Interactive In-App Folder Picker
* **Drive Switcher**: 1-click access to all available storage volumes (`C:\`, `D:\`, `E:\`, `J:\`).
* **Quick Access Shortcuts**: Instant jump to `Downloads`, `Instagram`, `Videos`, `Desktop`, and `Documents`.
* **Inline Folder Management**: Create new directories on the fly directly inside the app with zero freezes or delays.

### 🖼️ 4. Visual Media History & Batch Collections
* **Dual Views**: Switch seamlessly between **Card View** with live video frame thumbnails and **Table View**.
* **Batch Collections**: Bulk profile downloads are neatly organized into collapsible collections with item counters, total sizes, and folder shortcuts.
* **Auto-Generated Thumbnails**: Automatic 1-second frame previews for all video formats (`.mp4`, `.mov`, `.webm`, `.mkv`) generated via FFmpeg.

### ⚡ 5. Turbo Speed 8x Multi-Threading
* **8x Parallel Chunk Splitting**: Uses `--concurrent-fragments 8` to download fragmented HLS and DASH streams concurrently.
* **Instant Finish**: 140+ fragment video streams finish in seconds.

### 🌐 6. Companion Browser & Web Stream Sniffer
* **Chromium DevTools Protocol (CDP)**: Launches an isolated companion browser that hooks network requests, child iframes, and HTML5 media players.
* **Captures Hidden Streams**: Intercepts elusive `.m3u8` and `.mpd` links from anime portals and streaming sites (Aniwave, 9anime, MegaCloud, Vidplay, StreamTape, etc.).
* **Intelligent Title Resolution**: Automatically extracts clean episode titles instead of raw CDN hex hashes.

### 🔐 7. Master Cookie Vault
* **Auto-Merge Engine**: Merges cookies from multiple platforms (YouTube, Instagram, etc.) into a unified master cookie vault to bypass age gates and login walls.

### 📱 8. Wi-Fi QR Code Transfer
* **Send to Phone**: Scan a generated QR code with your phone camera to stream or download media directly over your local Wi-Fi.

---

## 📥 Download & Installation

### Option 1: Standalone Windows Installer
1. Download **`HorizonDownloader_Setup_v5.2.exe`** from [Releases](https://github.com/umaraslam282/Horizon_Video_Downloader5.1/releases).
2. Run the installer and launch Horizon from your Start Menu or Desktop shortcut.
3. *Zero configuration required — includes bundled yt-dlp, FFmpeg, and Deno.*

### Option 2: Run from Source
```bash
# Clone the repository
git clone https://github.com/umaraslam282/Horizon_Video_Downloader5.1.git
cd Horizon_Video_Downloader5.1

# Install dependencies
pip install -r requirements.txt

# Launch Horizon
python main.py
```

---

## 🛠️ Tech Stack & Architecture

* **Backend**: Python 3.13, Starlette, Uvicorn (ASGI), WebSockets, SQLite
* **Extraction Core**: yt-dlp, gallery-dl, FFmpeg, Deno JavaScript Runtime
* **Sniffer Engine**: Chrome DevTools Protocol (CDP) over WebSockets
* **Image Processing**: Pillow (PIL)
* **Frontend**: Vanilla JavaScript (ES6+), HTML5, Glassmorphism CSS3
* **Packaging**: PyInstaller & Inno Setup 7

---

## 👤 Author & Credits

Created with ❤️ by **Umar Aslam**

* **Instagram**: [@_omar_aslam_](https://www.instagram.com/_omar_aslam_/)
* **GitHub**: [@umaraslam282](https://github.com/umaraslam282)
* **Email**: realumaraslam@gmail.com

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
