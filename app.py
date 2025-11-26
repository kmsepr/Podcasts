from flask import Flask, send_file
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

CACHE_DIR = "podcache"
LOG_FILE = os.path.join(CACHE_DIR, "log.txt")
META_FILE = os.path.join(CACHE_DIR, "meta.json")
RSS_URL = "https://feeds.buzzsprout.com/2050847.rss"

os.makedirs(CACHE_DIR, exist_ok=True)

def log(msg):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_meta():
    if not os.path.exists(META_FILE):
        return {}
    try:
        return json.load(open(META_FILE))
    except:
        return {}

def save_meta(data):
    with open(META_FILE, "w") as f:
        json.dump(data, f)

def refresh_latest_episode(force=False):

    meta = load_meta()

    if not force and "last_update" in meta:
        last = datetime.fromisoformat(meta["last_update"])
        if datetime.now() - last < timedelta(hours=24):
            log("⏳ Already updated in last 24 hours. Skipping refresh.")
            return

    log("------------------------------------------------------------")
    log("Refreshing latest episode (forced=" + str(force) + ")")
    log("------------------------------------------------------------")

    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        log("❌ ERROR: Feed has no episodes!")
        return

    latest = feed.entries[0]

    if not latest.enclosures:
        log("❌ ERROR: No audio file found in feed.")
        return

    audio_url = latest.enclosures[0].href
    log(f"Audio URL: {audio_url}")

    original_audio = os.path.join(CACHE_DIR, "latest_original.mp3")
    final_mp3 = os.path.join(CACHE_DIR, "latest.mp3")

    log("Downloading audio via FFmpeg...")
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-headers", "User-Agent: Mozilla/5.0",
        "-i", audio_url,
        original_audio
    ], capture_output=True, text=True)

    log(proc.stdout)
    log(proc.stderr)

    if not os.path.exists(original_audio) or os.path.getsize(original_audio) < 50000:
        log("❌ Download failed (file too small). Aborting refresh.")
        return

    log("Converting to 40kbps MP3...")
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-i", original_audio,
        "-b:a", "40k",
        final_mp3
    ], capture_output=True, text=True)

    log(proc.stdout)
    log(proc.stderr)

    if not os.path.exists(final_mp3):
        log("❌ Conversion failed. No MP3 created.")
        return

    # ----------------------------------
    # Save description (NEW)
    # ----------------------------------
    desc = latest.get("summary") or latest.get("description") or ""
    meta["description"] = desc

    meta["last_update"] = datetime.now().isoformat()
    meta["title"] = latest.title
    save_meta(meta)

    log("✔ Refresh complete.")

@app.route("/")
def home():
    meta = load_meta()
    mp3_exists = os.path.exists(os.path.join(CACHE_DIR, "latest.mp3"))

    html = "<html><body style='font-family:Arial;padding:20px;'>"
    html += "<h2>Latest Episode</h2>"

    if "title" in meta:
        html += f"<h3>{meta['title']}</h3>"

    if "description" in meta:
        html += f"<p>{meta['description']}</p><br>"

    if mp3_exists:
        html += "<a href='/download' style='padding:10px 20px;background:#2196F3;color:white;text-decoration:none;border-radius:6px;'>⬇ Download MP3</a>"
    else:
        html += "MP3 not ready."

    html += "</body></html>"
    return html

@app.route("/download")
def download():
    file_path = os.path.join(CACHE_DIR, "latest.mp3")
    if not os.path.exists(file_path):
        return "MP3 not ready.", 404
    return send_file(file_path, as_attachment=True)

@app.route("/refresh")
def manual_refresh():
    refresh_latest_episode(force=True)
    return "Manual refresh done."

@app.route("/log")
def view_log():
    if not os.path.exists(LOG_FILE):
        return "No logs yet."
    return send_file(LOG_FILE)

log("Checking if daily refresh required...")
refresh_latest_episode(force=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)