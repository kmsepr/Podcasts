from flask import Flask, send_file
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

BASE_CACHE = "podcache"
os.makedirs(BASE_CACHE, exist_ok=True)

# ---------------------------------------------------------
# Multiple podcasts can be added here
# ---------------------------------------------------------
PODCASTS = {
    "in": {
        "name": "In Focus",
        "rss": "https://feeds.megaphone.fm/THGU4956605070"
    },
    "out": {
        "name": "Out of focus",
        "rss": "https://feeds.buzzsprout.com/2050847.rss"
    }
}

def paths(pod_id):
    """Return all file paths for a podcast"""
    folder = os.path.join(BASE_CACHE, pod_id)
    os.makedirs(folder, exist_ok=True)

    return {
        "folder": folder,
        "log": os.path.join(folder, "log.txt"),
        "meta": os.path.join(folder, "meta.json"),
        "original": os.path.join(folder, "latest_original.mp3"),
        "final": os.path.join(folder, "latest.mp3"),
    }

def log(pod_id, msg):
    p = paths(pod_id)
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"

    print(f"[{pod_id}] {line}")
    with open(p["log"], "a") as f:
        f.write(line + "\n")

def load_meta(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["meta"]):
        return {}
    try:
        return json.load(open(p["meta"]))
    except:
        return {}

def save_meta(pod_id, data):
    p = paths(pod_id)
    with open(p["meta"], "w") as f:
        json.dump(data, f)

# ---------------------------------------------------------
# Main download & convert function (per podcast)
# ---------------------------------------------------------
def refresh_podcast(pod_id, force=False):

    info = PODCASTS[pod_id]
    p = paths(pod_id)

    meta = load_meta(pod_id)

    # Skip if updated in last 24 hours
    if not force and "last_update" in meta:
        last = datetime.fromisoformat(meta["last_update"])
        if datetime.now() - last < timedelta(hours=24):
            log(pod_id, "⏳ Already updated in last 24 hours. Skipping refresh.")
            return

    log(pod_id, "------------------------------------------------------------")
    log(pod_id, f"Refreshing podcast: {info['name']} (forced={force})")
    log(pod_id, "------------------------------------------------------------")

    feed = feedparser.parse(info["rss"])
    if not feed.entries:
        log(pod_id, "❌ ERROR: Feed has no episodes!")
        return

    latest = feed.entries[0]

    if not latest.enclosures:
        log(pod_id, "❌ ERROR: No audio file found.")
        return

    audio_url = latest.enclosures[0].href
    log(pod_id, f"Audio URL: {audio_url}")

    # Download
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-headers", (
            "User-Agent: Mozilla/5.0\r\n"
            "Accept: */*\r\n"
            "Referer: https://www.buzzsprout.com/\r\n"
        ),
        "-i", audio_url,
        "-fflags", "nobuffer",
        "-timeout", "5000000",
        p["original"]
    ], capture_output=True, text=True)

    log(pod_id, proc.stdout)
    log(pod_id, proc.stderr)

    if not os.path.exists(p["original"]) or os.path.getsize(p["original"]) < 50000:
        log(pod_id, "❌ Download failed (file too small). Aborting.")
        return

    # ---------------------------------------------------------
    # Convert to low bitrate MP3 (40 kbps mono)
    # ---------------------------------------------------------
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-i", p["original"],
        "-ac", "1",
        "-codec:a", "libmp3lame",
        "-b:a", "40k",
        "-ar", "22050",
        p["final"]
    ], capture_output=True, text=True)

    log(pod_id, proc.stdout)
    log(pod_id, proc.stderr)

    if not os.path.exists(p["final"]):
        log(pod_id, "❌ Conversion failed.")
        return

    # Save metadata
    desc = latest.get("summary") or latest.get("description") or ""
    meta["title"] = latest.title
    meta["description"] = desc
    meta["last_update"] = datetime.now().isoformat()
    save_meta(pod_id, meta)

    log(pod_id, "✔ Refresh complete.")

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@app.route("/")
def home():
    html = """
    <html>
    <head>
        <title>Podcasts</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: auto;
                padding: 20px;
                background: #f8f9fa;
            }
            h2 {
                text-align: center;
                margin-bottom: 20px;
            }
            .pod {
                padding: 15px;
                margin: 12px 0;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }
            .pod h3 {
                margin: 0 0 10px 0;
            }
            .btn-row a {
                display: inline-block;
                padding: 8px 12px;
                margin-right: 10px;
                background: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-size: 14px;
            }
            .btn-row a:last-child {
                background: #6c757d;
            }
        </style>
    </head>
    <body>

    <h2>🎙 Available Podcasts</h2>
    """

    for pid, info in PODCASTS.items():
        html += f"""
        <div class='pod'>
            <h3>{info['name']}</h3>
            <div class='btn-row'>
                <a href='/pod/{pid}'>Open</a>
                <a href='/pod/{pid}/refresh'>Refresh</a>
            </div>
        </div>
        """

    html += """
    </body>
    </html>
    """

    return html

@app.route("/pod/<pod_id>")
def view_podcast(pod_id):
    if pod_id not in PODCASTS:
        return "Invalid podcast ID"

    refresh_podcast(pod_id, force=False)

    meta = load_meta(pod_id)
    p = paths(pod_id)
    mp3_exists = os.path.exists(p["final"])

    html = f"<h2>{PODCASTS[pod_id]['name']}</h2>"

    if "title" in meta:
        html += f"<h3>{meta['title']}</h3>"

    html += f"<p>{meta.get('description', '')}</p>"

    # -------------------------------
    # INLINE AUDIO PLAYER (added)
    # -------------------------------
    if mp3_exists:
        html += f"""
            <br><br>
            <audio controls style="width:100%;">
                <source src="/pod/{pod_id}/stream" type="audio/mpeg">
                Your browser does not support audio playback.
            </audio>
            <br><a href='/pod/{pod_id}/download'>⬇ Download MP3</a>
        """
    else:
        html += "<br>MP3 not ready."

    html += f"<br><br><a href='/pod/{pod_id}/refresh'>🔄 Force Refresh</a>"
    html += f"<br><a href='/pod/{pod_id}/log'>📜 View Log</a>"

    return html

# -------------------------------
# STREAM ROUTE (added)
# -------------------------------
@app.route("/pod/<pod_id>/stream")
def stream(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["final"]):
        return "MP3 not ready", 404
    return send_file(p["final"])

@app.route("/pod/<pod_id>/download")
def download(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["final"]):
        return "MP3 not ready", 404
    return send_file(p["final"], as_attachment=True)

@app.route("/pod/<pod_id>/refresh")
def manual_refresh(pod_id):
    refresh_podcast(pod_id, force=True)
    return "Manual refresh done."

@app.route("/pod/<pod_id>/log")
def view_log(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["log"]):
        return "No logs yet."
    return send_file(p["log"])

# ---------------------------------------------------------
# IMPORTANT: Removed startup refresh (Koyeb fix)
# ---------------------------------------------------------

print("🚀 App started — waiting for podcast requests (no startup refresh).")

# Run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)