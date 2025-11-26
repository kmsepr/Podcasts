import os
import datetime
import requests
import feedparser
from flask import Flask, send_file
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
import traceback

app = Flask(__name__)

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------

RSS_URL = "https://feeds.buzzsprout.com/2050847.rss"
CACHE_DIR = "/mnt/data/podcache"

CACHED_MP3 = os.path.join(CACHE_DIR, "todays_episode.mp3")
CACHED_IMG = os.path.join(CACHE_DIR, "todays_thumbnail.jpg")
LAST_REFRESH_FILE = os.path.join(CACHE_DIR, "last_refresh.txt")

os.makedirs(CACHE_DIR, exist_ok=True)

# ----------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------

def log(msg):
    """Better logging output with timestamp."""
    print(f"[{datetime.datetime.utcnow().isoformat()}] {msg}")

def write_last_refresh():
    with open(LAST_REFRESH_FILE, "w") as f:
        f.write(datetime.datetime.utcnow().isoformat())

def read_last_refresh():
    if not os.path.exists(LAST_REFRESH_FILE):
        return None
    with open(LAST_REFRESH_FILE, "r") as f:
        return datetime.datetime.fromisoformat(f.read().strip())

def ffmpeg_exists():
    ok = subprocess.call(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0
    log(f"FFmpeg detected: {ok}")
    return ok

# ----------------------------------------------------------
# LOGIC: FETCH TODAY'S EPISODE + THUMBNAIL
# ----------------------------------------------------------

def refresh_today_episode():
    log("------------------------------------------------------------")
    log("Starting refresh process for today's episode...")
    log("------------------------------------------------------------")

    try:
        log(f"Fetching RSS feed: {RSS_URL}")
        feed = feedparser.parse(RSS_URL)

        if not feed.entries:
            log("ERROR: RSS feed has no entries.")
            return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        log(f"Today's UTC date: {today_str}")

        today_episode = None

        log("Scanning RSS entries for today's episode...")
        for entry in feed.entries:
            if hasattr(entry, "published"):
                pub = datetime.datetime(*entry.published_parsed[:6])
                pub_str = pub.strftime("%Y-%m-%d")
                log(f"Checking episode: {entry.title} (Published: {pub_str})")

                if pub_str == today_str:
                    log("MATCH FOUND — This is today's episode.")
                    today_episode = entry
                    break

        if not today_episode:
            log("No episode was published today. Task finished.")
            return

        # -----------------------------
        # AUDIO DOWNLOAD
        # -----------------------------

        audio_url = today_episode.enclosures[0]["href"]
        log(f"Today's audio URL: {audio_url}")

        log("Downloading audio...")
        audio_data = requests.get(audio_url, timeout=30).content
        log(f"Downloaded {len(audio_data)} bytes.")

        temp_in = os.path.join(CACHE_DIR, "temp_in.mp3")
        temp_out = os.path.join(CACHE_DIR, "temp_out.mp3")

        log(f"Writing input temp file: {temp_in}")
        with open(temp_in, "wb") as f:
            f.write(audio_data)

        # -----------------------------
        # 40 kbps TRANSCODING
        # -----------------------------

        if ffmpeg_exists():
            log("Converting audio to 40 kbps MP3 using FFmpeg...")

            subprocess.call([
                "ffmpeg", "-y",
                "-i", temp_in,
                "-codec:a", "libmp3lame",
                "-b:a", "40k",
                temp_out
            ])

            log("FFmpeg conversion complete. Replacing cached MP3...")
            os.replace(temp_out, CACHED_MP3)
        else:
            log("FFmpeg not found — using original file.")
            os.replace(temp_in, CACHED_MP3)

        log("Audio caching complete.")

        # -----------------------------
        # THUMBNAIL DOWNLOAD
        # -----------------------------

        log("Checking for thumbnail URL...")

        img_url = None

        if "image" in today_episode:
            img_url = today_episode.image.get("href")
        elif "itunes_image" in today_episode:
            img_url = today_episode.itunes_image.get("href")

        if img_url:
            log(f"Thumbnail URL: {img_url}")
            log("Downloading thumbnail...")
            img_data = requests.get(img_url, timeout=20).content
            log(f"Downloaded {len(img_data)} bytes of image data.")

            log(f"Writing thumbnail file: {CACHED_IMG}")
            with open(CACHED_IMG, "wb") as f:
                f.write(img_data)
        else:
            log("No thumbnail found for this episode.")

        # -----------------------------
        # FINALIZE
        # -----------------------------

        write_last_refresh()
        log("Refresh completed successfully.")
        log("------------------------------------------------------------")

    except Exception as e:
        log("ERROR during refresh!")
        log(str(e))
        log(traceback.format_exc())


# ----------------------------------------------------------
# SCHEDULER – runs every 24 hours
# ----------------------------------------------------------

scheduler = BackgroundScheduler()
scheduler.add_job(refresh_today_episode, "interval", hours=24)
scheduler.start()

# First run (force refresh if missing)
if not os.path.exists(CACHED_MP3):
    log("Cache empty — forcing first refresh.")
    refresh_today_episode()
else:
    log("Cached MP3 already exists — skipping first refresh.")

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

@app.route("/thumbnail")
def thumbnail():
    if not os.path.exists(CACHED_IMG):
        return "Thumbnail not ready yet.", 404
    return send_file(CACHED_IMG, mimetype="image/jpeg")

# ----------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
