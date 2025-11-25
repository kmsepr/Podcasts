import os
import requests
import feedparser
from flask import Flask, jsonify, send_file
import subprocess
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Persistent media folder
MEDIA_DIR = "/app/media"
PODCAST_NAME = "outoffocus"
os.makedirs(os.path.join(MEDIA_DIR, PODCAST_NAME), exist_ok=True)

PODCAST_FEED = "https://feeds.buzzsprout.com/2050847.rss"

def download_and_convert():
    """Download latest Out Of Focus episode and convert to 40kbps mono MP3."""
    feed = feedparser.parse(PODCAST_FEED)
    if not feed.entries:
        print("No episodes found")
        return

    latest = feed.entries[0]
    audio_url = latest.enclosures[0].href

    date_str = datetime.utcnow().strftime("%Y%m%d")
    out_file = os.path.join(MEDIA_DIR, PODCAST_NAME, f"{date_str}.mp3")

    if os.path.exists(out_file):
        print(f"File already exists: {out_file}")
        return

    tmp_file = "/tmp/src_audio"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(audio_url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()
        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if os.path.getsize(tmp_file) == 0:
            print("Downloaded file empty")
            return
    except Exception as e:
        print(f"Error downloading audio: {e}")
        return

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_file,
            "-ar", "44100",
            "-ac", "1",
            "-b:a", "40k",
            out_file
        ]
        subprocess.run(cmd, check=True)
        print(f"Converted and saved -> {out_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting audio: {e}")

# Schedule twice daily (UTC)
scheduler = BackgroundScheduler()
for hour in [8, 20]:  # 8 AM and 8 PM UTC
    scheduler.add_job(download_and_convert, 'cron', hour=hour, minute=0)
scheduler.start()

@app.route("/")
def home():
    html = f"<h1>Out Of Focus</h1><a href='/podcast/{PODCAST_NAME}'>Latest Episode</a>"
    return html

@app.route("/podcast/<name>")
def podcast_page(name):
    if name != PODCAST_NAME:
        return "Podcast not found", 404

    feed = feedparser.parse(PODCAST_FEED)
    if not feed.entries:
        return "No episodes found", 404

    latest = feed.entries[0]
    title = latest.title
    published = latest.published
    html = f"""
        <h1>{PODCAST_NAME}</h1>
        <p>Latest: {title} ({published})</p>
        <a href="/download/{PODCAST_NAME}">Download MP3</a>
    """
    return html

@app.route("/download/<name>")
def download(name):
    if name != PODCAST_NAME:
        return "Podcast not found", 404

    date_str = datetime.utcnow().strftime("%Y%m%d")
    out_file = os.path.join(MEDIA_DIR, PODCAST_NAME, f"{date_str}.mp3")

    if os.path.exists(out_file):
        return send_file(out_file, as_attachment=True)
    else:
        # Generate on-demand
        download_and_convert()
        if os.path.exists(out_file):
            return send_file(out_file, as_attachment=True)
        else:
            return "MP3 not available yet, try later.", 503

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
