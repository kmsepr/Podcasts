import os
import time
import json
import subprocess
import logging
import threading
from flask import Flask, Response, request
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ------------------------
# Settings
# ------------------------
REFRESH_INTERVAL = 1200
RECHECK_INTERVAL = 3600
EXPIRE_AGE = 7200
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

CHANNELS = {
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "skicr": "https://youtube.com/@skicrtv/videos"
    # Add more as needed
}

VIDEO_CACHE = {name: {"url": None, "last_checked": 0} for name in CHANNELS}
LAST_VIDEO_ID = {name: None for name in CHANNELS}
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

# ------------------------
# Fetch direct media URL (bypasses JSON)
# ------------------------
def fetch_latest_media_url(channel_url):
    try:
        # Get direct URL for the first video
        command = [
            "yt-dlp",
            "--get-url",
            "--playlist-items", "1",
            "--cookies", "/mnt/data/cookies.txt",
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        direct_url = result.stdout.strip()
        return direct_url if direct_url else None
    except Exception as e:
        logging.error(f"Failed to get direct media URL from {channel_url}: {e}")
        return None

# ------------------------
# Download and convert MP3
# ------------------------
def download_mp3(channel_name, direct_url):
    if not direct_url:
        return None
    final_path = TMP_DIR / f"{channel_name}.mp3"
    if final_path.exists():
        return final_path
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", direct_url,
            "-vn",
            "-ac", "1",
            "-b:a", "64k",
            "-ar", "22050",
            str(final_path)
        ], check=True)
        return final_path if final_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel_name}: {e}")
        return None

# ------------------------
# Update cache loop
# ------------------------
def update_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            direct_url = fetch_latest_media_url(url)
            if direct_url:
                VIDEO_CACHE[name]["url"] = direct_url
                LAST_VIDEO_ID[name] = direct_url  # Use URL as ID for simplicity
                download_mp3(name, direct_url)
            time.sleep(2)
        time.sleep(REFRESH_INTERVAL)

# ------------------------
# Cleanup old files
# ------------------------
def cleanup_files():
    while True:
        current_time = time.time()
        for file in TMP_DIR.glob("*.mp3"):
            if current_time - file.stat().st_mtime > EXPIRE_AGE:
                logging.info(f"Deleting old file: {file}")
                file.unlink(missing_ok=True)
        time.sleep(EXPIRE_AGE)

# ------------------------
# Flask route to stream MP3
# ------------------------
@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    mp3_path = TMP_DIR / f"{channel}.mp3"
    if not mp3_path.exists():
        url = VIDEO_CACHE[channel]["url"]
        if not url:
            return "Video not ready", 503
        download_mp3(channel, url)
    return Response(open(mp3_path, "rb"), mimetype="audio/mpeg")

@app.route("/")
def index():
    html = "<h3>Available MP3s:</h3><ul>"
    for c in CHANNELS:
        mp3_path = TMP_DIR / f"{c}.mp3"
        if mp3_path.exists():
            html += f"<li><a href='/{c}.mp3'>{c}</a></li>"
    html += "</ul>"
    return html

# ------------------------
# Start background threads
# ------------------------
threading.Thread(target=update_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_files, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)