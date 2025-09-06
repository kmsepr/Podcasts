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

# ----------------------------
# CONFIG
# ----------------------------
REFRESH_INTERVAL = 1200       # 20 minutes
RECHECK_INTERVAL = 3600       # 60 minutes
EXPIRE_AGE = 7200             # 2 hours
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
COOKIE_FILE = "/mnt/data/cookies.txt"

# ----------------------------
# YOUTUBE MP3 SECTION
# ----------------------------
CHANNELS = {
    "max": "https://youtube.com/@maxvelocitywx/videos",
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "furqan": "https://youtube.com/@alfurqan4991/videos",
    "rahmani": "https://www.youtube.com/@ShajahanRahmaniOfficial/videos",
    "skicr": "https://youtube.com/@skicrtv/videos",
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

def yt_dlp_base_args():
    args = ["yt-dlp", "--user-agent", FIXED_USER_AGENT]
    if os.path.exists(COOKIE_FILE):
        args += ["--cookies", COOKIE_FILE]
    return args

def fetch_latest_video_url(name, channel_url):
    try:
        cmd = yt_dlp_base_args() + [
            "--dump-single-json",
            "--playlist-end", "1",
            channel_url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video = data["entries"][0]
        video_id = video["id"]
        thumbnail_url = video.get("thumbnail", "")
        upload_date = video.get("upload_date", "")
        title = video.get("title", "")
        channel = video.get("channel", "")
        return f"https://www.youtube.com/watch?v={video_id}", thumbnail_url, video_id, upload_date, title, channel
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

        cmd = yt_dlp_base_args() + [
            "-f", "bestaudio",
            "--output", str(base_path) + ".%(ext)s",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            video_url
        ]
        subprocess.run(cmd, check=True)

        if not audio_path.exists() or not thumb_path.exists():
            logging.error(f"Missing audio or thumbnail for {channel}")
            return None

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

        audio_path.unlink(missing_ok=True)
        thumb_path.unlink(missing_ok=True)
        return final_path if final_path.exists() else None
    except Exception as e:
        logging.error(f"Error converting {channel}: {e}")
        return None

def cleanup_old_files():
    while True:
        now = time.time()
        for file in TMP_DIR.glob("*.mp3"):
            if now - file.stat().st_mtime > EXPIRE_AGE:
                try:
                    file.unlink()
                except Exception as e:
                    logging.error(f"Cleanup error {file}: {e}")
        time.sleep(EXPIRE_AGE)

def update_video_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            video_url, thumb, vid, up, title, ch = fetch_latest_video_url(name, url)
            if video_url and vid:
                if LAST_VIDEO_ID[name] != vid:
                    LAST_VIDEO_ID[name] = vid
                    VIDEO_CACHE[name].update({
                        "url": video_url,
                        "last_checked": time.time(),
                        "thumbnail": thumb,
                        "upload_date": up,
                        "title": title,
                        "channel": ch,
                    })
                    download_and_convert(name, video_url)
            time.sleep(3)
        time.sleep(REFRESH_INTERVAL)

def auto_download_mp3s():
    while True:
        for name, data in VIDEO_CACHE.items():
            video_url = data.get("url")
            if video_url:
                mp3_path = TMP_DIR / f"{name}.mp3"
                if not mp3_path.exists() or time.time() - mp3_path.stat().st_mtime > RECHECK_INTERVAL:
                    download_and_convert(name, video_url)
            time.sleep(3)
        time.sleep(RECHECK_INTERVAL)

@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    data = VIDEO_CACHE[channel]
    video_url = data.get("url")
    if not video_url:
        video_url, thumb, vid, up, title, ch = fetch_latest_video_url(channel, CHANNELS[channel])
        if not video_url:
            return "Unable to fetch video", 500
        if vid and LAST_VIDEO_ID[channel] != vid:
            LAST_VIDEO_ID[channel] = vid
            VIDEO_CACHE[channel].update({
                "url": video_url,
                "last_checked": time.time(),
                "thumbnail": thumb,
                "upload_date": up,
                "title": title,
                "channel": ch,
            })
    mp3_path = download_and_convert(channel, video_url)
    if not mp3_path or not mp3_path.exists():
        return "Error preparing stream", 500
    file_size = os.path.getsize(mp3_path)
    range_header = request.headers.get('Range')
    headers = {'Content-Type': 'audio/mpeg','Accept-Ranges': 'bytes'}
    if range_header:
        try:
            byte1, byte2 = range_header.split("=")[1].split("-")
            byte1 = int(byte1)
            byte2 = int(byte2) if byte2 else file_size - 1
        except:
            return "Invalid Range header", 400
        length = byte2 - byte1 + 1
        with open(mp3_path, 'rb') as f:
            f.seek(byte1)
            chunk = f.read(length)
        headers.update({'Content-Range': f'bytes {byte1}-{byte2}/{file_size}','Content-Length': str(length)})
        return Response(chunk, 206, headers)
    return Response(open(mp3_path, 'rb'), headers={**headers,'Content-Length': str(file_size)})

@app.route("/yt")
def yt_index():
    html = "<h3>YouTube Mp3</h3><div>"
    for channel in CHANNELS:
        mp3_path = TMP_DIR / f"{channel}.mp3"
        if not mp3_path.exists():
            continue
        thumb = VIDEO_CACHE[channel].get("thumbnail", "")
        html += f"<div><img src='{thumb}' width=120><br><a href='/{channel}.mp3'>{channel}</a></div>"
    html += "</div>"
    return html

# ----------------------------
# PODCAST SECTION
# ----------------------------
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
        last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT, episode_id TEXT UNIQUE,
        title TEXT, description TEXT, audio_url TEXT,
        pub_date TEXT, duration TEXT,
        FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id))''')
    conn.commit(); conn.close()
init_db()

@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    for rss_url in DEFAULT_FEEDS:
        try:
            c.execute('SELECT COUNT(*) FROM episodes WHERE podcast_id=?',(rss_url,))
            if c.fetchone()[0] > 0: continue
            feed = feedparser.parse(rss_url)
            if not feed.entries: continue
            podcast_id = rss_url
            title = feed.feed.get('title','Untitled')
            author = feed.feed.get('author','Unknown')
            image = (feed.feed.get('image',{}) or {}).get('href','') or feed.feed.get('itunes_image',{}).get('href','')
            c.execute('''INSERT OR IGNORE INTO podcasts (podcast_id,title,author,cover_url,rss_url)
                         VALUES (?,?,?,?,?)''',(podcast_id,title,author,image,rss_url))
            latest = feed.entries[0]
            eid = latest.get('id') or latest.get('guid') or latest.get('link') or latest.get('title')
            audio = ''
            for enc in latest.get('enclosures', []):
                if enc.get('href','').startswith('http'):
                    audio = enc['href']; break
            if audio:
                c.execute('''INSERT OR IGNORE INTO episodes (podcast_id,episode_id,title,description,audio_url,pub_date,duration)
                             VALUES (?,?,?,?,?,?,?)''',(podcast_id,eid,latest.get('title',''),
                             latest.get('summary','') or latest.get('description',''),audio,
                             latest.get('published',''),latest.get('itunes_duration','')))
        except Exception as e:
            logging.error(f"Feed error {rss_url}: {e}")
    conn.commit()
    placeholders = ','.join('?' for _ in DEFAULT_FEEDS)
    c.execute(f'''SELECT * FROM podcasts WHERE podcast_id IN ({placeholders})
                  ORDER BY last_played DESC LIMIT 5 OFFSET 0''', DEFAULT_FEEDS)
    rows=[dict(zip([col[0] for col in c.description],row)) for row in c.fetchall()]
    conn.close(); return jsonify(rows)

@app.route('/podcast')
def podcast_home():
    return "<h3>🎧 Podcast UI is here</h3><p>Use /api/favorites to get data.</p>"

# ----------------------------
# LANDING PAGE
# ----------------------------
@app.route("/")
def home():
    return """<h2>Welcome</h2>
    <ul>
      <li><a href="/yt">🎬 YouTube MP3</a></li>
      <li><a href="/podcast">🎧 Podcast</a></li>
    </ul>"""

# ----------------------------
# THREADS
# ----------------------------
threading.Thread(target=update_video_cache_loop, daemon=True).start()
threading.Thread(target=auto_download_mp3s, daemon=True).start()
threading.Thread(target=cleanup_old_files, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)