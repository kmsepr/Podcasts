import os
import datetime
import requests
import feedparser
from flask import Flask, send_file
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------

RSS_URL = "https://anchor.fm/s/8fd39f70/podcast/rss"
CACHE_DIR = "/mnt/data/podcache"
CACHED_MP3 = os.path.join(CACHE_DIR, "todays_episode.mp3")
LAST_REFRESH_FILE = os.path.join(CACHE_DIR, "last_refresh.txt")

os.makedirs(CACHE_DIR, exist_ok=True)

# ----------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------

def write_last_refresh():
    with open(LAST_REFRESH_FILE, "w") as f:
        f.write(datetime.datetime.utcnow().isoformat())

def read_last_refresh():
    if not os.path.exists(LAST_REFRESH_FILE):
        return None
    with open(LAST_REFRESH_FILE, "r") as f:
        return datetime.datetime.fromisoformat(f.read().strip())

def ffmpeg_exists():
    return subprocess.call(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0

# ----------------------------------------------------------
# LOGIC: FETCH TODAY'S EPISODE ONLY
# ----------------------------------------------------------

def refresh_today_episode():
    """Identify today's episode → download → transcode to 40kbps → cache."""
    print("Refreshing today's episode...")

    try:
        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            print("RSS feed empty.")
            return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        today_episode = None

        for entry in feed.entries:
            if hasattr(entry, "published"):
                pub_date = datetime.datetime(*entry.published_parsed[:6])
                if pub_date.strftime("%Y-%m-%d") == today_str:
                    today_episode = entry
                    break

        if not today_episode:
            print("No episode published today.")
            return

        audio_url = today_episode.enclosures[0]["href"]
        print("Today's episode URL:", audio_url)

        audio_data = requests.get(audio_url, timeout=30).content

        temp_in = os.path.join(CACHE_DIR, "temp_in.mp3")
        temp_out = os.path.join(CACHE_DIR, "temp_out.mp3")

        with open(temp_in, "wb") as f:
            f.write(audio_data)

        # Convert to 40 kbps MP3
        if ffmpeg_exists():
            subprocess.call([
                "ffmpeg", "-y",
                "-i", temp_in,
                "-codec:a", "libmp3lame",
                "-b:a", "40k",
                temp_out
            ])
            os.replace(temp_out, CACHED_MP3)
        else:
            os.replace(temp_in, CACHED_MP3)

        write_last_refresh()
        print("Today's episode refreshed.")

    except Exception as e:
        print("Error:", e)

# ----------------------------------------------------------
# SCHEDULER – runs every 24 hours
# ----------------------------------------------------------

scheduler = BackgroundScheduler()
scheduler.add_job(refresh_today_episode, "interval", hours=24)
scheduler.start()

# First run: if cache missing → force refresh
if not os.path.exists(CACHED_MP3):
    refresh_today_episode()

# ----------------------------------------------------------
# ROUTES
# ----------------------------------------------------------

@app.route("/")
def home():
    last = read_last_refresh()
    return f"Last refreshed: {last if last else 'Never'}"

@app.route("/download")
def download():
    if not os.path.exists(CACHED_MP3):
        return "File not ready yet.", 404
    return send_file(CACHED_MP3, as_attachment=True)

# ----------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
