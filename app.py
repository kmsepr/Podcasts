from flask import Flask, jsonify, send_file
import feedparser
import subprocess
import uuid
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Add all your podcast RSS feeds here:
PODCASTS = {
    "outoffocus": "https://feeds.buzzsprout.com/2050847.rss",
    "show2": "https://example.com/feed.xml",
    "show3": "https://example.com/feed2.xml"
}

# Store latest episodes here:
latest = {pid: {"title": None, "audio": None, "published": None} for pid in PODCASTS}

def fetch_latest(pid, url):
    feed = feedparser.parse(url)
    if not feed.entries:
        return
    entry = feed.entries[0]

    audio = None
    if "enclosures" in entry and entry.enclosures:
        audio = entry.enclosures[0].get("url")

    latest[pid] = {
        "title": entry.get("title"),
        "audio": audio,
        "published": entry.get("published")
    }

def update_all():
    for pid, url in PODCASTS.items():
        fetch_latest(pid, url)

# Scheduler: twice daily update
scheduler = BackgroundScheduler()
scheduler.add_job(update_all, "cron", hour="6,18")
scheduler.start()

# First update on startup
with app.app_context():
    update_all()

@app.route("/api/latest/<pid>")
def api_latest(pid):
    if pid not in latest:
        return jsonify({"error": "Podcast ID not found"}), 404
    if latest[pid]["audio"] is None:
        return jsonify({"error": "No audio found"}), 404
    return jsonify(latest[pid])

@app.route("/api/transcoded_latest/<pid>")
def api_transcoded_latest(pid):
    if pid not in latest:
        return jsonify({"error": "Podcast ID not found"}), 404

    audio_url = latest[pid]["audio"]
    if not audio_url:
        return jsonify({"error": "No audio URL"}), 404

    tmp = f"/tmp/{uuid.uuid4()}.mp3"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_url,
            "-b:a", "24k", "-bufsize", "24k",
            "-ac", "1", "-ar", "24000",
            tmp
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        return send_file(tmp, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": "ffmpeg failed", "details": str(e)})

@app.route("/")
def home():
    return {
        "podcasts": list(PODCASTS.keys()),
        "endpoints": {
            "latest": "/api/latest/<podcast_id>",
            "transcoded": "/api/transcoded_latest/<podcast_id>"
        }
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
