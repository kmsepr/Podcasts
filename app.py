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

# ==============================
# 🔹 YOUTUBE MP3 SECTION
# ==============================
REFRESH_INTERVAL = 1200       # 20 minutes
RECHECK_INTERVAL = 3600       # 60 minutes
EXPIRE_AGE = 7200             # 2 hours
FIXED_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CHANNELS = {
    "max": "https://youtube.com/@maxvelocitywx/videos",
    "vallathorukatha": "https://www.youtube.com/@babu_ramachandran/videos",
    "dhruvrathee": "https://youtube.com/@dhruvrathee/videos",
    "safari": "https://youtube.com/@safaritvlive/videos",
}
VIDEO_CACHE = {name: {"url": None, "last_checked": 0, "thumbnail": "", "upload_date": "", "title": "", "channel": ""} for name in CHANNELS}
LAST_VIDEO_ID = {name: None for name in CHANNELS}
TMP_DIR = Path("/tmp/ytmp3")
TMP_DIR.mkdir(exist_ok=True)

def fetch_latest_video_url(name, channel_url):
    try:
        result = subprocess.run([
            "yt-dlp", "--dump-single-json",
            "--playlist-end", "1",
            "--user-agent", FIXED_USER_AGENT,
            channel_url
        ], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video = data["entries"][0]
        return (
            f"https://www.youtube.com/watch?v={video['id']}",
            video.get("thumbnail", ""),
            video["id"],
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
    if final_path.exists() or not video_url:
        return final_path if final_path.exists() else None
    try:
        base_path = TMP_DIR / channel
        audio_path = base_path.with_suffix(".webm")
        thumb_path = base_path.with_suffix(".jpg")

        subprocess.run([
            "yt-dlp", "-f", "bestaudio",
            "--output", str(base_path) + ".%(ext)s",
            "--write-thumbnail", "--convert-thumbnails", "jpg",
            "--user-agent", FIXED_USER_AGENT,
            video_url
        ], check=True)

        if not audio_path.exists() or not thumb_path.exists():
            return None

        info = VIDEO_CACHE[channel]
        title, artist = info.get("title", channel), info.get("channel", channel)
        album = format_upload_month(info.get("upload_date", ""))

        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(audio_path), "-i", str(thumb_path),
            "-map", "0:a", "-map", "1:v",
            "-c:a", "libmp3lame", "-c:v", "mjpeg",
            "-b:a", "64k", "-ar", "22050", "-ac", "1",
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
                    logging.error(f"Cleanup error: {e}")
        time.sleep(EXPIRE_AGE)

def update_video_cache_loop():
    while True:
        for name, url in CHANNELS.items():
            video_url, thumbnail, vid, upload_date, title, channel_name = fetch_latest_video_url(name, url)
            if video_url and vid and LAST_VIDEO_ID[name] != vid:
                LAST_VIDEO_ID[name] = vid
                VIDEO_CACHE[name].update({
                    "url": video_url, "last_checked": time.time(),
                    "thumbnail": thumbnail, "upload_date": upload_date,
                    "title": title, "channel": channel_name
                })
                download_and_convert(name, video_url)
            time.sleep(3)
        time.sleep(REFRESH_INTERVAL)

@app.route("/<channel>.mp3")
def stream_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    data = VIDEO_CACHE[channel]
    video_url = data.get("url")
    if not video_url:
        video_url, thumbnail, vid, upload_date, title, chname = fetch_latest_video_url(channel, CHANNELS[channel])
        if not video_url: return "Unable to fetch video", 500
        LAST_VIDEO_ID[channel] = vid
        VIDEO_CACHE[channel].update({"url": video_url, "thumbnail": thumbnail, "upload_date": upload_date, "title": title, "channel": chname})
    mp3_path = download_and_convert(channel, video_url)
    if not mp3_path: return "Error preparing stream", 500
    return Response(open(mp3_path, "rb"), mimetype="audio/mpeg")

@app.route("/yt")
def yt_index():
    html = "<h3>YouTube MP3</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,140px);gap:10px'>"
    for channel, info in VIDEO_CACHE.items():
        mp3_path = TMP_DIR / f"{channel}.mp3"
        if not mp3_path.exists(): continue
        thumb = info.get("thumbnail", "http://via.placeholder.com/120x80?text=YT")
        html += f"<div style='border:1px solid #ccc;padding:5px'><img src='{thumb}' style='width:100%'><br><a href='/{channel}.mp3'>{channel}</a></div>"
    return html + "</div>"

# ==============================
# 🔹 PODCAST SECTION
# ==============================
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
        podcast_id TEXT UNIQUE, title TEXT, author TEXT, cover_url TEXT, rss_url TEXT,
        last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        podcast_id TEXT, episode_id TEXT UNIQUE, title TEXT, description TEXT,
        audio_url TEXT, pub_date TEXT, duration TEXT,
        FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id))''')
    conn.commit(); conn.close()
init_db()

@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    for rss_url in DEFAULT_FEEDS:
        c.execute('SELECT COUNT(*) FROM episodes WHERE podcast_id=?', (rss_url,))
        if c.fetchone()[0] == 0:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                c.execute('INSERT OR IGNORE INTO podcasts (podcast_id,title,author,cover_url,rss_url) VALUES (?,?,?,?,?)',
                          (rss_url, feed.feed.get('title','Untitled'), feed.feed.get('author','Unknown'),
                           (feed.feed.get('image') or {}).get('href',''), rss_url))
                ep = feed.entries[0]
                audio = next((e['href'] for e in ep.get('enclosures',[]) if e.get('href','').startswith('http')), '')
                if audio:
                    eid = ep.get('id') or ep.get('guid') or ep.get('link') or ep.get('title')
                    c.execute('INSERT OR IGNORE INTO episodes (podcast_id,episode_id,title,description,audio_url,pub_date,duration) VALUES (?,?,?,?,?,?,?)',
                              (rss_url, eid, ep.get('title',''), ep.get('summary',''), audio, ep.get('published',''), ep.get('itunes_duration','')))
    conn.commit()
    c.execute('SELECT * FROM podcasts ORDER BY last_played DESC LIMIT 5')
    rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    conn.close(); return jsonify(rows)

@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id=? ORDER BY pub_date DESC LIMIT 9', (pid,))
    rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    conn.close(); return jsonify(rows)

HTML_TEMPLATE = "<h3>🎧 Podcast Player</h3><p>Use API endpoints or expand here later.</p>"
@app.route('/podcast')
def podcast_home():
    return render_template_string(HTML_TEMPLATE)

# ==============================
# 🔹 LANDING PAGE
# ==============================
@app.route('/')
def home():
    return "<h2>Welcome</h2><ul><li><a href='/yt'>🎬 YouTube MP3</a></li><li><a href='/podcast'>🎧 Podcasts</a></li></ul>"

# ==============================
# 🔹 THREADS
# ==============================
threading.Thread(target=update_video_cache_loop, daemon=True).start()
threading.Thread(target=cleanup_old_files, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)