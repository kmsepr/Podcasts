import os
import requests
import feedparser
from flask import Flask, jsonify, send_file, render_template_string
import subprocess
from datetime import datetime

app = Flask(__name__)

# Persistent media folder
MEDIA_DIR = "/app/media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# Podcast feeds dictionary
PODCAST_FEEDS = {
    "outoffocus": "https://feeds.buzzsprout.com/2050847.rss"
}

# Simple home page listing all podcasts
@app.route("/")
def home():
    podcasts = list(PODCAST_FEEDS.keys())
    html = "<h1>Available Podcasts</h1><ul>"
    for p in podcasts:
        html += f'<li><a href="/podcast/{p}">{p}</a></li>'
    html += "</ul>"
    return html

# Podcast page showing latest episode and download link
@app.route("/podcast/<name>")
def podcast_page(name):
    if name not in PODCAST_FEEDS:
        return "Podcast not found", 404
    
    feed = feedparser.parse(PODCAST_FEEDS[name])
    if not feed.entries:
        return "No episodes found", 404

    latest = feed.entries[0]
    title = latest.title
    published = latest.published
    html = f"""
        <h1>{name}</h1>
        <p>Latest: {title} ({published})</p>
        <a href="/download/{name}">Download MP3</a>
    """
    return html

# Download & convert endpoint
@app.route("/download/<name>")
def download(name):
    if name not in PODCAST_FEEDS:
        return "Podcast not found", 404

    feed = feedparser.parse(PODCAST_FEEDS[name])
    if not feed.entries:
        return "No episodes found", 404

    latest = feed.entries[0]
    audio_url = latest.enclosures[0].href

    # Destination folder
    podcast_dir = os.path.join(MEDIA_DIR, name)
    os.makedirs(podcast_dir, exist_ok=True)

    # Unique filename by date
    date_str = datetime.utcnow().strftime("%Y%m%d")
    out_file = os.path.join(podcast_dir, f"{date_str}.mp3")

    # If file already exists, serve it
    if os.path.exists(out_file):
        return send_file(out_file, as_attachment=True)

    # Download source
    tmp_file = "/tmp/src_audio"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}  # Buzzsprout sometimes blocks default requests
        r = requests.get(audio_url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()
        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if os.path.getsize(tmp_file) == 0:
            return "Downloaded file is empty", 500
    except Exception as e:
        return f"Error downloading audio: {e}", 500

    # Convert to 40kbps mono MP3 using ffmpeg
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
    except subprocess.CalledProcessError as e:
        return f"Error converting audio: {e}", 500

    return send_file(out_file, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
