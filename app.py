from flask import Flask, send_file
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

CACHE_DIR = "podcache"

# Dictionary of all podcasts
RSS_FEEDS = {
    "out": "https://feeds.buzzsprout.com/2050847.rss",
    "in": "https://feeds.megaphone.fm/THGU4956605070"
}

# Ensure main cache folder exists
os.makedirs(CACHE_DIR, exist_ok=True)

# --------------------------
# Utility functions
# --------------------------
def log(msg, log_file=None):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")

def get_paths(name):
    folder = os.path.join(CACHE_DIR, name)
    os.makedirs(folder, exist_ok=True)
    return {
        "folder": folder,
        "log": os.path.join(folder, "log.txt"),
        "meta": os.path.join(folder, "meta.json"),
        "original": os.path.join(folder, "latest_original.mp3"),
        "final": os.path.join(folder, "latest.mp3")
    }

def load_meta(meta_file):
    if not os.path.exists(meta_file):
        return {}
    try:
        return json.load(open(meta_file))
    except:
        return {}

def save_meta(meta_file, data):
    with open(meta_file, "w") as f:
        json.dump(data, f)

# --------------------------
# Refresh podcast
# --------------------------
def refresh_latest_episode(podcast_name, force=False):
    if podcast_name not in RSS_FEEDS:
        print(f"Podcast '{podcast_name}' not found in RSS_FEEDS.")
        return

    rss_url = RSS_FEEDS[podcast_name]
    paths = get_paths(podcast_name)
    meta = load_meta(paths["meta"])
    log_file = paths["log"]

    if not force and "last_update" in meta:
        last = datetime.fromisoformat(meta["last_update"])
        if datetime.now() - last < timedelta(hours=24):
            log(f"⏳ Already updated in last 24 hours. Skipping refresh for {podcast_name}.", log_file)
            return

    log("------------------------------------------------------------", log_file)
    log(f"Refreshing latest episode for '{podcast_name}' (forced={force})", log_file)
    log("------------------------------------------------------------", log_file)

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        log("❌ ERROR: Feed has no episodes!", log_file)
        return

    latest = feed.entries[0]
    if not latest.enclosures:
        log("❌ ERROR: No audio file found in feed.", log_file)
        return

    audio_url = latest.enclosures[0].href
    log(f"Audio URL: {audio_url}", log_file)

    # Download original
    log("Downloading audio via FFmpeg...", log_file)
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-headers", "User-Agent: Mozilla/5.0",
        "-i", audio_url,
        paths["original"]
    ], capture_output=True, text=True)

    log(proc.stdout, log_file)
    log(proc.stderr, log_file)

    if not os.path.exists(paths["original"]) or os.path.getsize(paths["original"]) < 50000:
        log("❌ Download failed (file too small). Aborting refresh.", log_file)
        return

    # Convert to 40kbps MP3
    log("Converting to 40kbps MP3...", log_file)
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-i", paths["original"],
        "-b:a", "40k",
        paths["final"]
    ], capture_output=True, text=True)

    log(proc.stdout, log_file)
    log(proc.stderr, log_file)

    if not os.path.exists(paths["final"]):
        log("❌ Conversion failed. No MP3 created.", log_file)
        return

    # Save metadata
    desc = latest.get("summary") or latest.get("description") or ""
    meta["description"] = desc
    meta["last_update"] = datetime.now().isoformat()
    meta["title"] = latest.title
    save_meta(paths["meta"], meta)

    log("✔ Refresh complete.", log_file)

# --------------------------
# Flask Routes
# --------------------------
@app.route("/")
def home():
    html = "<html><body style='font-family:Arial;padding:20px;'>"
    html += "<h2>Available Podcasts</h2><ul>"
    for name in RSS_FEEDS:
        html += f"<li><a href='/{name}/'>{name}</a></li>"
    html += "</ul></body></html>"
    return html

@app.route("/<podcast_name>/")
def show_podcast(podcast_name):
    if podcast_name not in RSS_FEEDS:
        return "Podcast not found", 404

    paths = get_paths(podcast_name)
    meta = load_meta(paths["meta"])
    mp3_exists = os.path.exists(paths["final"])

    html = "<html><body style='font-family:Arial;padding:20px;'>"
    html += f"<h2>{podcast_name}</h2>"

    if "title" in meta:
        html += f"<h3>{meta['title']}</h3>"

    if "description" in meta:
        html += f"<p>{meta['description']}</p><br>"

    if mp3_exists:
        html += f"<a href='/{podcast_name}/download' style='padding:10px 20px;background:#2196F3;color:white;text-decoration:none;border-radius:6px;'>⬇ Download MP3</a><br><br>"
    else:
        html += "MP3 not ready.<br><br>"

    html += f"<a href='/{podcast_name}/refresh'>Refresh Now</a> | <a href='/{podcast_name}/log'>View Log</a>"
    html += "</body></html>"
    return html

@app.route("/<podcast_name>/download")
def download(podcast_name):
    paths = get_paths(podcast_name)
    file_path = paths["final"]
    if not os.path.exists(file_path):
        return "MP3 not ready.", 404
    return send_file(file_path, as_attachment=True)

@app.route("/<podcast_name>/refresh")
def manual_refresh(podcast_name):
    refresh_latest_episode(podcast_name, force=True)
    return f"Manual refresh done for {podcast_name}."

@app.route("/<podcast_name>/log")
def view_log(podcast_name):
    paths = get_paths(podcast_name)
    if not os.path.exists(paths["log"]):
        return "No logs yet."
    return send_file(paths["log"])

# --------------------------
# Initial daily check
# --------------------------
for podcast_name in RSS_FEEDS:
    log(f"Checking if daily refresh required for '{podcast_name}'...")
    refresh_latest_episode(podcast_name, force=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)