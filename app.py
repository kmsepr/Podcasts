import os
import time
import subprocess
import logging
import threading
from flask import Flask, Response
from pathlib import Path
from datetime import datetime
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ------------------------
# Settings
# ------------------------
REFRESH_INTERVAL = 1200
EXPIRE_AGE = 7200
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

CHANNELS = {
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "skicr": "https://youtube.com/@skicrtv/videos"
}

VIDEO_CACHE = {name: {"url": None, "title": "", "channel": "", "upload_date": ""} for name in CHANNELS}

# ------------------------
# Fetch latest video info
# ------------------------
def fetch_latest_video_info(channel_url):
    try:
        result = subprocess.run([
            "yt-dlp",
            "--dump-single-json",
            "--playlist-end", "1",
            "--cookies", "/mnt/data/cookies.txt",
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ], capture_output=True, text=True, check=True)

        data = json.loads(result.stdout)
        video = data["entries"][0]
        video_id = video["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        thumbnail = video.get("thumbnail", "")
        upload_date = video.get("upload_date", "")
        title = video.get("title", "")
        channel_name = video.get("channel", "")
        return video_url, thumbnail, video_id, upload_date, title, channel_name
    except Exception as e:
        logging.error(f"Failed to fetch latest video from {channel_url}: {e}")
        return None, None, None, None, None, None

# ------------------------
# Download MP3 with thumbnail & metadata
# ------------------------
def download_mp3(channel_name, video_url, thumbnail_url="", title="", artist="", upload_date=""):
    mp3_path = TMP_DIR / f"{channel_name}.mp3"
    if mp3_path.exists():
        return mp3_path

    album = datetime.strptime(upload_date, "%Y%m%d").strftime("%B %Y") if upload_date else "Unknown"
    base_path = TMP_DIR / channel_name
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
            "--cookies", "/mnt/data/cookies.txt",
            "--user-agent", FIXED_USER_AGENT,
            video_url
        ], check=True)

        if not audio_path.exists():
            logging.error(f"Audio download failed for {channel_name}")
            return None

        # Convert to MP3 with metadata + thumbnail
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
        ]

        if thumb_path.exists():
            ffmpeg_cmd += ["-i", str(thumb_path), "-map", "0:a", "-map", "1:v", "-disposition:v", "attached_pic"]

        ffmpeg_cmd += [
            "-vn", "-ac", "1", "-b:a", "64k", "-ar", "22050",
            "-metadata", f"title={title}",
            "-metadata", f"album={album}",
            "-metadata", f"artist={artist}",
            str(mp3_path)
        ]

        subprocess.run(ffmpeg_cmd, check=True)

        audio_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)

        return mp3_path if mp3_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel_name}: {e}")
        return None

# ------------------------
# Update cache loop
# ------------------------
def update_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            video_url, thumbnail, video_id, upload_date, title, channel_name = fetch_latest_video_info(url)
            if video_url:
                VIDEO_CACHE[name].update({
                    "url": video_url,
                    "title": title,
                    "channel": channel_name,
                    "upload_date": upload_date,
                    "thumbnail": thumbnail
                })
                download_mp3(name, video_url, thumbnail, title, channel_name, upload_date)
            time.sleep(2)
        time.sleep(REFRESH_INTERVAL)

# ------------------------
# Cleanup old files
# ------------------------
def cleanup_files():
    while True:
        now = time.time()
        for f in TMP_DIR.glob("*.mp3"):
            if now - f.stat().st_mtime > EXPIRE_AGE:
                logging.info(f"Deleting old file {f}")
                f.unlink(missing_ok=True)
        time.sleep(EXPIRE_AGE)

# ------------------------
# Flask routes
# ------------------------
@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    mp3_path = TMP_DIR / f"{channel}.mp3"
    if not mp3_path.exists():
        data = VIDEO_CACHE[channel]
        mp3_path = download_mp3(channel, data.get("url"), data.get("thumbnail"), data.get("title"), data.get("channel"), data.get("upload_date"))
    if not mp3_path:
        return "Video not ready", 503
    return Response(open(mp3_path, "rb"), mimetype="audio/mpeg")

@app.route("/")
def index():
    html = "<h3>Available MP3s:</h3><ul>"
    for c in CHANNELS:
        if (TMP_DIR / f"{c}.mp3").exists():
            html += f"<li><a href='/{c}.mp3'>{c}</a></li>"
    html += "</ul>"
    return html

# ------------------------
# Start threads
# ------------------------
threading.Thread(target=update_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_files, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)