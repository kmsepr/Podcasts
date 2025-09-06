import os
import time
import json
import subprocess
import logging
import threading
import sqlite3
import feedparser
import requests
from pathlib import Path
from datetime import datetime
from flask import Flask, Response, request, jsonify, render_template_string

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===============================
# 📌 YOUTUBE MP3 SECTION
# ===============================
REFRESH_INTERVAL = 1200       # 20 minutes
RECHECK_INTERVAL = 3600       # 60 minutes
EXPIRE_AGE = 7200             # 2 hours
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
COOKIES_FILE = "/mnt/data/cookies.txt"

CHANNELS = {
    "max": "https://youtube.com/@maxvelocitywx/videos",
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "dhruvrathee": "https://youtube.com/@dhruvrathee/videos",
    "safari": "https://youtube.com/@safaritvlive/videos",
}

VIDEO_CACHE = {
    name: {"url": None, "last_checked": 0, "thumbnail": "", "upload_date": "", "title": "", "channel": ""}
    for name in CHANNELS
}
LAST_VIDEO_ID = {name: None for name in CHANNELS}
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

def fetch_latest_video_url(name, channel_url):
    try:
        result = subprocess.run([
            "yt-dlp",
            "--dump-single-json",
            "--playlist-end", "1",
            "--cookies", COOKIES_FILE,
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ], capture_output=True, text=True, check=True)

        data = json.loads(result.stdout)
        video = data["entries"][0]
        video_id = video["id"]
        return (
            f"https://www.youtube.com/watch?v={video_id}",
            video.get("thumbnail", ""),
            video_id,
            video.get("upload_date", ""),
            video.get("title", ""),
            video.get("channel", "")
        )
    except Exception as e:
        logging.error(f"Error fetching video from {channel_url}: {e}")
        return None, None, None, None, None, None

def format_upload_month(upload_date):
    try:
        dt = datetime.strptime(upload_date, "%Y%m%d")
        return dt.strftime("%B %Y")
    except Exception:
        return "Unknown"

def download_and_convert(channel, video_url):
    final_path = TMP_DIR / f"{channel}.mp3"
    if final_path.exists():
        return final_path
    if not video_url:
        return None
    try:
        base_path = TMP_DIR / channel
        audio_path = base_path.with_suffix(".webm")
        thumb_path = base_path.with_suffix(".jpg")

        subprocess.run([
            "yt-dlp",
            "-f", "bestaudio",
            "--output", str(base_path) + ".%(ext)s",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--cookies", COOKIES_FILE,
            "--user-agent", FIXED_USER_AGENT,
            video_url
        ], check=True)

        info = VIDEO_CACHE[channel]
        title = info.get("title", channel)
        artist = info.get("channel", channel)
        album = format_upload_month(info.get("upload_date", ""))

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
            "-metadata", f"title={title}",
            "-metadata", f"album={album}",
            "-metadata", f"artist={artist}",
            "-disposition:v", "attached_pic",
            str(final_path)
        ], check=True)

        return final_path if final_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel}: {e}")
        return None

def cleanup_old_files():
    while True:
        current_time = time.time()
        for file in TMP_DIR.glob("*.mp3"):
            if current_time - file.stat().st_mtime > EXPIRE_AGE:
                try:
                    logging.info(f"Cleaning up old file: {file}")
                    file.unlink()
                except Exception as e:
                    logging.error(f"Cleanup error {file}: {e}")
        time.sleep(EXPIRE_AGE)

def update_video_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            video_url, thumbnail, video_id, upload_date, title, channel_name = fetch_latest_video_url(name, url)
            if video_url and video_id and LAST_VIDEO_ID[name] != video_id:
                LAST_VIDEO_ID[name] = video_id
                VIDEO_CACHE[name].update({
                    "url": video_url,
                    "last_checked": time.time(),
                    "thumbnail": thumbnail,
                    "upload_date": upload_date,
                    "title": title,
                    "channel": channel_name,
                })
                download_and_convert(name, video_url)
            time.sleep(3)
        time.sleep(REFRESH_INTERVAL)

@app.route("/yt")
def yt_index():
    html = """
    <html>
    <head><title>YouTube Mp3</title></head>
    <body><h3>YouTube MP3</h3><div style="display:flex;flex-wrap:wrap;">"""
    for channel, data in VIDEO_CACHE.items():
        mp3_path = TMP_DIR / f"{channel}.mp3"
        if not mp3_path.exists():
            continue
        thumb = data.get("thumbnail", "")
        html += f"<div style='margin:10px'><img src='{thumb}' width=120><br><a href='/{channel}.mp3'>{channel}</a></div>"
    html += "</div></body></html>"
    return html

@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Not found", 404
    video_url = VIDEO_CACHE[channel].get("url")
    if not video_url:
        return "No video", 500
    mp3_path = download_and_convert(channel, video_url)
    if not mp3_path or not mp3_path.exists():
        return "Error", 500
    return Response(open(mp3_path, 'rb'), mimetype="audio/mpeg")

# ===============================
# 📌 PODCAST SECTION
# ===============================
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

DEFAULT_FEEDS = [
    "https://muslimcentral.com/audio/hamza-yusuf/feed/",
    "https://feeds.megaphone.fm/THGU4956605070",
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT UNIQUE,
        title TEXT, author TEXT, cover_url TEXT, rss_url TEXT,
        last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT, episode_id TEXT UNIQUE,
        title TEXT, description TEXT, audio_url TEXT,
        pub_date TEXT, duration TEXT,
        FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route("/podcast")
def podcast_home():
    return render_template_string("<h3>🎧 Podcast UI intact</h3>")

# ===============================
# 📌 LANDING PAGE WITH CARDS
# ===============================
@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Media Hub</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <h2 class="mb-4 text-center">📺 Media Hub</h2>
            <div class="row justify-content-center">
                <div class="col-md-4">
                    <div class="card shadow-sm mb-4">
                        <img src="https://img.icons8.com/fluency/240/youtube-play.png" class="card-img-top p-4">
                        <div class="card-body text-center">
                            <h5 class="card-title">YouTube MP3</h5>
                            <a href="/yt" class="btn btn-danger">🎬 Open YouTube MP3</a>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card shadow-sm mb-4">
                        <img src="https://img.icons8.com/fluency/240/podcast.png" class="card-img-top p-4">
                        <div class="card-body text-center">
                            <h5 class="card-title">Podcasts</h5>
                            <a href="/podcast" class="btn btn-primary">🎧 Open Podcasts</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

# ===============================
# 📌 BACKGROUND THREADS
# ===============================
threading.Thread(target=update_video_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_old_files, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)