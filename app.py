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

# -----------------------
# Settings
# -----------------------
REFRESH_INTERVAL = 1200       # 20 minutes
EXPIRE_AGE = 7200             # 2 hours
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
COOKIES_PATH = "/mnt/data/cookies.txt"  # Must exist (exported from browser)
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

# -----------------------
# YouTube channels
# -----------------------
CHANNELS = {
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "skicr": "https://youtube.com/@skicrtv/videos",
}

# -----------------------
# Video cache
# -----------------------
VIDEO_CACHE = {
    name: {"url": None, "last_checked": 0, "video_id": None, "title": "", "thumbnail": "", "upload_date": ""}
    for name in CHANNELS
}

# -----------------------
# Fetch latest video info
# -----------------------
def fetch_latest_video(name, channel_url):
    try:
        cmd = [
            "yt-dlp",
            "--dump-single-json",
            "--playlist-end", "1",
            "--cookies", COOKIES_PATH,
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video = data["entries"][0]
        video_id = video["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        VIDEO_CACHE[name] = {
            "url": video_url,
            "last_checked": time.time(),
            "video_id": video_id,
            "title": video.get("title", ""),
            "thumbnail": video.get("thumbnail", ""),
            "upload_date": video.get("upload_date", "")
        }
        logging.info(f"✅ Fetched latest video for {name}: {video_url}")
        return video_url
    except Exception as e:
        logging.error(f"Failed to fetch latest video from {channel_url}: {e}")
        return None

# -----------------------
# Download & convert to MP3
# -----------------------
def download_mp3(name):
    info = VIDEO_CACHE[name]
    video_url = info.get("url")
    if not video_url:
        return None

    final_path = TMP_DIR / f"{name}.mp3"
    if final_path.exists():
        return final_path

    base_path = TMP_DIR / name
    audio_path = base_path.with_suffix(".webm")
    thumb_path = base_path.with_suffix(".jpg")

    try:
        # Download audio + thumbnail
        subprocess.run([
            "yt-dlp",
            "-f", "bestaudio",
            "--output", str(base_path) + ".%(ext)s",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--cookies", COOKIES_PATH,
            "--user-agent", FIXED_USER_AGENT,
            video_url
        ], check=True)

        # Convert to MP3 with embedded thumbnail
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-i", str(thumb_path),
            "-map", "0:a",
            "-map", "1:v",
            "-c:a", "libmp3lame",
            "-c:v", "mjpeg",
            "-b:a", "64k",
            "-ar", "22050",
            "-ac", "1",
            "-id3v2_version", "3",
            "-metadata", f"title={info.get('title','')}",
            "-metadata", f"artist={name}",
            "-metadata", f"album=YouTube",
            "-disposition:v", "attached_pic",
            str(final_path)
        ], check=True)

        audio_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
        logging.info(f"✅ Downloaded MP3 for {name}")
        return final_path
    except Exception as e:
        logging.error(f"Failed to download/convert {name}: {e}")
        return None

# -----------------------
# Background thread to refresh videos
# -----------------------
def refresh_videos_loop():
    while True:
        for name, url in CHANNELS.items():
            fetch_latest_video(name, url)
            download_mp3(name)
            time.sleep(3)
        time.sleep(REFRESH_INTERVAL)

# -----------------------
# Cleanup old files
# -----------------------
def cleanup_loop():
    while True:
        now = time.time()
        for file in TMP_DIR.glob("*.mp3"):
            if now - file.stat().st_mtime > EXPIRE_AGE:
                logging.info(f"Deleting old file: {file}")
                file.unlink()
        time.sleep(EXPIRE_AGE)

# -----------------------
# Flask routes
# -----------------------
@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    mp3_path = TMP_DIR / f"{channel}.mp3"
    if not mp3_path.exists():
        download_mp3(channel)
        if not mp3_path.exists():
            return "Error preparing stream", 500

    range_header = request.headers.get('Range', None)
    file_size = os.path.getsize(mp3_path)
    headers = {'Content-Type': 'audio/mpeg', 'Accept-Ranges': 'bytes'}

    if range_header:
        try:
            byte1, byte2 = (range_header.strip().split('=')[1].split('-') + [file_size - 1])[:2]
            byte1, byte2 = int(byte1), int(byte2)
            length = byte2 - byte1 + 1
            with open(mp3_path, 'rb') as f:
                f.seek(byte1)
                chunk = f.read(length)
            headers.update({
                'Content-Range': f'bytes {byte1}-{byte2}/{file_size}',
                'Content-Length': str(length)
            })
            return Response(chunk, status=206, headers=headers)
        except Exception:
            return "Invalid Range header", 400

    with open(mp3_path, 'rb') as f:
        data = f.read()
    headers['Content-Length'] = str(file_size)
    return Response(data, headers=headers)

@app.route("/")
def index():
    html = "<h3>YouTube Latest Videos (MP3)</h3><ul>"
    for name, info in VIDEO_CACHE.items():
        if info["url"]:
            html += f"<li><a href='/{name}.mp3'>{name} - {info.get('title','')}</a></li>"
    html += "</ul>"
    return html

# -----------------------
# Start background threads
# -----------------------
threading.Thread(target=refresh_videos_loop, daemon=True).start()
threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)