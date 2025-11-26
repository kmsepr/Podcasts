from flask import Flask, send_file
import requests
import feedparser
import subprocess
import os
from datetime import datetime

app = Flask(__name__)

CACHE_DIR = "podcache"
LOG_FILE = os.path.join(CACHE_DIR, "log.txt")
RSS_URL = "https://feeds.buzzsprout.com/2050847.rss"

os.makedirs(CACHE_DIR, exist_ok=True)


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(msg):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ------------------------------------------------------------
# Fetch only the latest episode → convert → save thumbnail
# ------------------------------------------------------------
def refresh_latest_episode():

    log("------------------------------------------------------------")
    log("Starting refresh for latest episode...")
    log("------------------------------------------------------------")

    log(f"Fetching RSS feed: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        log("❌ ERROR: Feed has no episodes!")
        return

    latest = feed.entries[0]
    log(f"Latest title: {latest.title}")

    # ----------------------------------
    # 1️⃣  Get Audio URL
    # ----------------------------------
    if not latest.enclosures:
        log("❌ ERROR: No audio enclosure found.")
        return

    audio_url = latest.enclosures[0].href
    log(f"Audio URL: {audio_url}")

    original_audio = os.path.join(CACHE_DIR, "latest_original.mp3")

    try:
        log("Downloading original audio...")
        r = requests.get(audio_url, timeout=30)
        with open(original_audio, "wb") as f:
            f.write(r.content)
        log("✔ Audio downloaded.")
    except Exception as e:
        log(f"❌ Audio download failed: {e}")
        return

    # ----------------------------------
    # 2️⃣  Convert to 40 kbps
    # ----------------------------------
    final_mp3 = os.path.join(CACHE_DIR, "latest.mp3")

    try:
        log("Converting to 40kbps MP3...")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", original_audio,
            "-b:a", "40k",
            final_mp3
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        log("✔ Conversion complete.")
    except Exception as e:
        log(f"❌ FFmpeg failed: {e}")
        return

    # ----------------------------------
    # 3️⃣  Download Thumbnail (Buzzsprout uses `image.href`)
    # ----------------------------------
    thumb_path = os.path.join(CACHE_DIR, "latest_thumb.jpg")
    image_url = None

    # Buzzsprout uses: latest.image.href
    if hasattr(latest, "image") and hasattr(latest.image, "href"):
        image_url = latest.image.href

    if image_url:
        try:
            log(f"Downloading thumbnail → {thumb_path}")
            img = requests.get(image_url, timeout=15)
            with open(thumb_path, "wb") as f:
                f.write(img.content)
            log("✔ Thumbnail saved.")
        except Exception as e:
            log(f"❌ Thumbnail error: {e}")
    else:
        log("ℹ No thumbnail found.")

    log("✔ Refresh complete.")


# ------------------------------------------------------------
# Manual refresh trigger
# ------------------------------------------------------------
@app.route("/refresh")
def refresh_route():
    refresh_latest_episode()
    return "Refreshed. Visit / to view."


# ------------------------------------------------------------
# Download MP3
# ------------------------------------------------------------
@app.route("/download")
def download():
    file_path = os.path.join(CACHE_DIR, "latest.mp3")
    if not os.path.exists(file_path):
        return "MP3 not ready. Run /refresh.", 404
    return send_file(file_path, as_attachment=True)


# ------------------------------------------------------------
# Serve thumbnail
# ------------------------------------------------------------
@app.route("/thumbnail")
def thumbnail():
    file_path = os.path.join(CACHE_DIR, "latest_thumb.jpg")
    if not os.path.exists(file_path):
        return "Thumbnail not ready.", 404
    return send_file(file_path)


# ------------------------------------------------------------
# Log viewer
# ------------------------------------------------------------
@app.route("/log")
def view_log():
    if not os.path.exists(LOG_FILE):
        return "No logs yet."
    return send_file(LOG_FILE)


# ------------------------------------------------------------
# Home page with thumbnail + download button
# ------------------------------------------------------------
@app.route("/")
def home():
    thumb_exists = os.path.exists(os.path.join(CACHE_DIR, "latest_thumb.jpg"))
    mp3_exists = os.path.exists(os.path.join(CACHE_DIR, "latest.mp3"))

    html = """
    <html>
    <head>
        <title>Latest Episode</title>
        <style>
            body { font-family: Arial; padding: 20px; }
            img { width: 300px; border-radius: 10px; }
            .btn {
                display: inline-block;
                padding: 12px 20px;
                background: #2196F3;
                color: white;
                border-radius: 8px;
                text-decoration: none;
                font-size: 18px;
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <h2>Latest Episode</h2>
    """

    if thumb_exists:
        html += '<img src="/thumbnail"><br><br>'
    else:
        html += "<b>Thumbnail loading...</b><br><br>"

    if mp3_exists:
        html += '<a class="btn" href="/download">⬇ Download MP3</a>'
    else:
        html += "<b>MP3 loading… please wait</b>"

    html += "</body></html>"

    return html


# ------------------------------------------------------------
# Auto-refresh at startup
# ------------------------------------------------------------
log("Initial refresh on startup...")
refresh_latest_episode()


# ------------------------------------------------------------
# Run Flask
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
