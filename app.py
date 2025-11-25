import os
import datetime
import requests
import feedparser
from flask import Flask, send_file, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess

app = Flask(__name__)

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------

RSS_URL = "https://anchor.fm/s/8fd39f70/podcast/rss"
CACHE_DIR = "/mnt/data/podcache"
CACHED_MP3 = os.path.join(CACHE_DIR, "latest.mp3")
LAST_REFRESH_FILE = os.path.join(CACHE_DIR, "last_refresh.txt")

# Create directories
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


def ffmpeg_available():
    """Check if ffmpeg exists in container."""
    return subprocess.call(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0


# ----------------------------------------------------------
# FETCH + TRANSCODE LOGIC
# ----------------------------------------------------------

def refresh_latest_episode():
    """Fetch RSS → download audio → transcode → cache."""
    try:
        print("Refreshing latest episode...")

        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            print("RSS empty")
            return

        # Get Top 3 Episodes Only
        latest_entries = feed.entries[:3]

        # Use episode #1 (most recent)
        episode = latest_entries[0]
        audio_url = episode.enclosures[0]["href"]

        print("Downloading:", audio_url)
        audio_data = requests.get(audio_url, timeout=20).content

        temp_in = os.path.join(CACHE_DIR, "temp_in.mp3")
        temp_out = os.path.join(CACHE_DIR, "temp_out.mp3")

        with open(temp_in, "wb") as f:
            f.write(audio_data)

        # Transcoding — only if ffmpeg exists
        if ffmpeg_available():
            subprocess.call([
                "ffmpeg", "-y",
                "-i", temp_in,
                "-codec:a", "libmp3lame",
                "-b:a", "128k",
                temp_out
            ])
            os.replace(temp_out, CACHED_MP3)
        else:
            # No ffmpeg — save original
            os.replace(temp_in, CACHED_MP3)

        write_last_refresh()
        print("Refresh complete.")

    except Exception as e:
        print("Refresh error:", e)


# ----------------------------------------------------------
# APSCHEDULER – refresh every 12 hours
# ----------------------------------------------------------

scheduler = BackgroundScheduler()
scheduler.add_job(refresh_latest_episode, "interval", hours=12)
scheduler.start()

# First run: if cache missing → force refresh
if not os.path.exists(CACHED_MP3):
    refresh_latest_episode()


# ----------------------------------------------------------
# FLASK ROUTES
# ----------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Podcast Cache</title>
<style>
body { font-family: Arial; padding: 20px; }
.btn {
  padding: 14px 20px;
  background: #007bff; color: white;
  border-radius: 6px; text-decoration: none;
}
</style>
</head>
<body>
<h2>Latest 3 Episodes</h2>
<ul>
{% for ep in episodes %}
  <li><b>{{ep.title}}</b> — {{ep.published}}</li>
{% endfor %}
</ul>

<h3>Download Cached Latest Episode</h3>
<a href="/download" class="btn">Download MP3</a>

<p>Last refresh: <b>{{last_refresh}}</b></p>
</body>
</html>
"""

@app.route("/")
def index():
    feed = feedparser.parse(RSS_URL)
    episodes = feed.entries[:3]

    last_refresh = read_last_refresh()

    return render_template_string(
        HTML_TEMPLATE,
        episodes=episodes,
        last_refresh=last_refresh if last_refresh else "Never"
    )


@app.route("/download")
def download():
    if not os.path.exists(CACHED_MP3):
        return "File not cached yet. Try again later.", 404

    return send_file(CACHED_MP3, as_attachment=True)


# ----------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
