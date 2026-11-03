# Horizon Video Downloader v5.1 🚀

<div align="center">

![Horizon Downloader](static/img/instagram_icon.jpg)

**High-Performance Portable Media Downloader with Companion Stream Sniffer & Turbo Speed Acceleration**

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg?style=flat-square&logo=python)](https://python.org)
[![Engine](https://img.shields.io/badge/Engine-yt--dlp%202026.10-red.svg?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078d7.svg?style=flat-square&logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

</div>

---

## 🌟 What is Horizon?

**Horizon Video Downloader** is a high-speed, modern desktop media downloader built with Python, Starlette, yt-dlp, and Chrome DevTools Protocol (CDP). Designed with a cyber-glassmorphism dark UI, Horizon delivers a commercial-grade downloading experience with zero ads, zero tracking, and native speed.

---

## ✨ Flagship Features

### ⚡ 1. Turbo Speed 8x Multi-Threading
* **8x Parallel Chunk Splitting**: Uses `--concurrent-fragments 8` to download fragmented HLS and DASH streams concurrently.
* **Instant Finish**: 140+ fragment video streams that normally take 3–4 minutes finish in under 25 seconds.

### 🌐 2. Companion Browser & Web Stream Sniffer
* **Chromium DevTools Protocol (CDP)**: Launches an isolated companion browser that hooks network requests, child iframes, and HTML5 media players.
* **Captures Hidden Streams**: Intercepts elusive `.m3u8` and `.mpd` links from anime portals and streaming sites (Aniwave, 9anime, MegaCloud, Vidplay, StreamTape, etc.).
* **Intelligent Title Resolution**: Automatically extracts clean anime series names and episode numbers (`Granblue Fantasy Season 2 - Episode 1.mp4`) instead of raw CDN hex hash IDs.
* **Live Terminal Logs**: Real-time console tab displays browser navigation, hooked iframes, and stream captures live.

### 🖼️ 3. Ultra HD Thumbnail & Cover Art Extractor
* **Universal Support**: Extracts raw, maximum-resolution thumbnails and album art from **YouTube (Long-form & Shorts)**, **Instagram**, **TikTok**, **Twitter/X**, **Twitch**, and web media.
* **Quality Selector**: Download in **Ultra HD (1080p/4K)**, **High Def (720p)**, or **Standard**.
* **Lossless PNG & JPG**: Save directly to your Downloads folder with clean, auto-sanitized filenames.
* **1-Click Clipboard Copy**: Copies the full-res image directly into your Windows clipboard for instant pasting (`Ctrl+V`) into Photoshop, Figma, or Discord.

### 📋 4. Selective Playlist & Batch Downloader
* **Rapid Flattening**: Loads 100+ playlist items in under 2 seconds.
* **Selective Checkboxes**: Choose exactly which episodes or songs to download without downloading unwanted videos.

### 🔐 5. Master Cookie Vault
* **Auto-Merge Engine**: Merges cookies from multiple platforms (YouTube, Instagram, etc.) into a unified master cookie vault.
* **Bypasses Age & Bot Restrictions**: Eliminates YouTube Sign-in Required and Instagram Login walls effortlessly.

### 📱 6. Wi-Fi QR Code Transfer
* **Send to Phone**: Scan a generated QR code from your phone's camera to instantly stream or download the video onto your iPhone or Android over local Wi-Fi.

---

## 📥 Download & Installation

### Option 1: Standalone Windows Installer (Recommended)
1. Download **`HorizonDownloader_Setup_v5.1.exe`** from [Releases](https://github.com/umaraslam282/Horizon_Video_Downloader5/releases).
2. Run the installer and launch Horizon from your Start Menu or Desktop shortcut.
3. *Zero configuration required — includes bundled yt-dlp, FFmpeg, and Deno.*

### Option 2: Run from Source
```bash
# Clone the repository
git clone https://github.com/umaraslam282/Horizon_Video_Downloader5.git
cd Horizon_Video_Downloader5

# Install dependencies
pip install -r requirements.txt

# Launch Horizon
python main.py
```

---

## 🛠️ Tech Stack & Architecture

* **Backend**: Python 3.13, Starlette, Uvicorn (ASGI), WebSockets
* **Extraction Core**: yt-dlp, FFmpeg, Deno JavaScript Runtime
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
