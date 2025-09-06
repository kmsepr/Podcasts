import os
import subprocess
import logging
import threading
import time
from pathlib import Path
from flask import Flask, Response, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------
# Settings
# -----------------------
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

# Channels
CHANNELS = {
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "skicr": "https://youtube.com/@skicrtv/videos",
}

# Cache for latest video URL and mp3
VIDEO_CACHE = {name: {"url": None, "mp3": None, "last_checked": 0} for name in CHANNELS}

# -----------------------
# Get latest video URL
# -----------------------
def get_latest_video(channel_url):
    try:
        cmd = [
            "yt-dlp",
            "--get-id",
            "--playlist-items", "1",
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        video_id = result.stdout.strip()
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return None
    except Exception as e:
        logging.error(f"Failed to get latest video from {channel_url}: {e}")
        return None

# -----------------------
# Download and convert to mp3
# -----------------------
def download_mp3(channel_name, video_url):
    mp3_path = TMP_DIR / f"{channel_name}.mp3"
    if mp3_path.exists():
        return mp3_path

    try:
        subprocess.run([
            "yt-dlp",
            "-f", "bestaudio",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", str(mp3_path),
            "--user-agent", FIXED_USER_AGENT,
            video_url
        ], check=True)
        return mp3_path if mp3_path.exists() else None
    except Exception as e:
        logging.error(f"Failed to download mp3 for {channel_name}: {e}")
        return None

# -----------------------
# Background updater
# -----------------------
def update_loop():
    while True:
        for name, url in CHANNELS.items():
            last_checked = VIDEO_CACHE[name]["last_checked"]
            if time.time() - last_checked > 600:  # check every 10 min
                video_url = get_latest_video(url)
                if video_url and video_url != VIDEO_CACHE[name]["url"]:
                    VIDEO_CACHE[name]["url"] = video_url
                    VIDEO_CACHE[name]["mp3"] = download_mp3(name, video_url)
                VIDEO_CACHE[name]["last_checked"] = time.time()
        time.sleep(60)

threading.Thread(target=update_loop, daemon=True).start()

# -----------------------
# Flask routes
# -----------------------
@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404

    mp3_path = VIDEO_CACHE[channel].get("mp3")
    if not mp3_path or not mp3_path.exists():
        return "MP3 not available yet", 503

    file_size = os.path.getsize(mp3_path)
    range_header = request.headers.get('Range', None)
    headers = {'Content-Type': 'audio/mpeg', 'Accept-Ranges': 'bytes'}

    if range_header:
        try:
            byte1, byte2 = range_header.replace("bytes=", "").split("-")
            byte1 = int(byte1)
            byte2 = int(byte2) if byte2 else file_size - 1
            length = byte2 - byte1 + 1
            with open(mp3_path, 'rb') as f:
                f.seek(byte1)
                chunk = f.read(length)
            headers.update({'Content-Range': f'bytes {byte1}-{byte2}/{file_size}', 'Content-Length': str(length)})
            return Response(chunk, status=206, headers=headers)
        except Exception as e:
            return f"Invalid Range header: {e}", 400

    with open(mp3_path, 'rb') as f:
        data = f.read()
    headers['Content-Length'] = str(file_size)
    return Response(data, headers=headers)

@app.route("/")
def index():
    html = "<h3>Latest YouTube Videos MP3</h3><ul>"
    for name in CHANNELS:
        if VIDEO_CACHE[name]["mp3"]:
            html += f"<li><a href='/{name}.mp3'>{name}</a></li>"
    html += "</ul>"
    return html

# -----------------------
# Run Flask
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)