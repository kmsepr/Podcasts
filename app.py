from flask import Flask, send_file, Response, request
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta
import threading
import time

app = Flask(__name__)

BASE_CACHE = "podcache"
os.makedirs(BASE_CACHE, exist_ok=True)

# ---------------------------------------------------------
# PODCAST LIST
# ---------------------------------------------------------
PODCASTS = {
    "in": {
        "name": "In Focus",
        "rss": "https://feeds.megaphone.fm/THGU4956605070"
    },
    "out": {
        "name": "Out of Focus",
        "rss": "https://feeds.buzzsprout.com/2050847.rss"
    },

    "firsts": {
        "name": "The Firsts",
        "rss": "https://feeds.buzzsprout.com/1194665.rss"
    }
}

# ---------------------------------------------------------
# PATH HELPERS
# ---------------------------------------------------------
def paths(pod_id):
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
# REFRESH PODCAST
# ---------------------------------------------------------
def refresh_podcast(pod_id, force=False):
    info = PODCASTS[pod_id]
    p = paths(pod_id)
    meta = load_meta(pod_id)

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
        log(pod_id, "❌ ERROR: No audio found.")
        return

    audio_url = latest.enclosures[0].href
    log(pod_id, f"Audio URL: {audio_url}")

    # Download using ffmpeg
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
        log(pod_id, "❌ Download failed (too small).")
        return

    # Convert low bitrate
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

    meta["title"] = latest.title
    meta["description"] = latest.get("summary", "")
    meta["last_update"] = datetime.now().isoformat()
    save_meta(pod_id, meta)

    log(pod_id, "✔ Refresh complete.")

# ---------------------------------------------------------
# AUTO REFRESH THREAD (EVERY 1 HOUR)
# ---------------------------------------------------------
def auto_refresher():
    while True:
        print("⏱️ AUTO REFRESH STARTED")
        for pid in PODCASTS:
            try:
                refresh_podcast(pid, force=False)
            except Exception as e:
                print(f"❌ Auto-refresh error ({pid}): {e}")
        print("⏱️ AUTO REFRESH DONE — sleeping 1 hour...\n")
        time.sleep(3600)

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
                max-width: 700px;
                margin: auto;
                padding: 25px;
                background: #f3f4f6;
                font-size: 22px;
                line-height: 1.6;
            }
            h2 {
                text-align: center;
                margin-bottom: 30px;
                font-size: 34px;
                font-weight: bold;
            }
            .pod {
                padding: 25px;
                margin: 20px 0;
                background: white;
                border-radius: 14px;
                box-shadow: 0 3px 10px rgba(0,0,0,0.15);
            }
            .pod h3 {
                margin: 0 0 15px 0;
                font-size: 28px;
            }
            .btn-row a {
                display: inline-block;
                padding: 14px 20px;
                margin-right: 15px;
                background: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-size: 20px;
            }
            .btn-row a:last-child {
                background: #6c757d;
            }
            audio {
                width: 100%;
                margin-top: 15px;
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

    return html + "</body></html>"


@app.route("/pod/<pod_id>")
def view_podcast(pod_id):
    if pod_id not in PODCASTS:
        return "Invalid ID"

    refresh_podcast(pod_id, force=False)

    meta = load_meta(pod_id)
    p = paths(pod_id)

    html = f"""
    <html>
    <head>
    <title>{PODCASTS[pod_id]['name']}</title>
    <style>
        body {{
            font-family: Arial;
            padding: 25px;
            font-size: 22px;
            background: #f3f4f6;
            max-width: 700px;
            margin: auto;
        }}
        h2 {{ font-size: 34px; }}
        h3 {{ font-size: 28px; }}
        audio {{ width: 100%; margin-top: 20px; }}
        a {{ font-size: 20px; }}
    </style>
    </head>
    <body>
    <h2>{PODCASTS[pod_id]['name']}</h2>
    """

    if "title" in meta:
        html += f"<h3>{meta['title']}</h3>"

    html += f"<p>{meta.get('description','')}</p>"

    if os.path.exists(p["final"]):
        html += f"""
        <audio controls>
            <source src="/pod/{pod_id}/stream" type="audio/mpeg">
        </audio>
        <br><br>
        <a href='/pod/{pod_id}/download'>⬇ Download MP3</a>
        """
    else:
        html += "MP3 not ready."

    html += f"<br><br><a href='/pod/{pod_id}/refresh'>🔄 Force Refresh</a>"
    html += f"<br><a href='/pod/{pod_id}/log'>📜 View Log</a>"
    html += "</body></html>"

    return html

@app.route("/pod/<pod_id>/stream")
def stream(pod_id):
    p = paths(pod_id)
    file_path = p["final"]

    if not os.path.exists(file_path):
        return "Not ready", 404

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("Range", None)

    if range_header:
        # Parse Range header
        byte1, byte2 = 0, file_size - 1
        r = range_header.split("=")[1]
        parts = r.split("-")

        if parts[0]:
            byte1 = int(parts[0])
        if parts[1]:
            byte2 = int(parts[1])

        length = byte2 - byte1 + 1

        def generate():
            with open(file_path, "rb") as f:
                f.seek(byte1)
                remaining = length
                chunk = 64 * 1024  # 64KB chunks (safe for Cloud app)
                while remaining > 0:
                    data = f.read(min(chunk, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        resp = Response(generate(), status=206, mimetype="audio/mpeg")
        resp.headers.add("Content-Range", f"bytes {byte1}-{byte2}/{file_size}")
        resp.headers.add("Accept-Ranges", "bytes")
        resp.headers.add("Content-Length", str(length))
        return resp

    # No Range header → stream whole file in chunks
    def generate_full():
        with open(file_path, "rb") as f:
            chunk = 64 * 1024
            while True:
                data = f.read(chunk)
                if not data:
                    break
                yield data

    resp = Response(generate_full(), mimetype="audio/mpeg")
    resp.headers.add("Content-Length", str(file_size))
    resp.headers.add("Accept-Ranges", "bytes")
    return resp

@app.route("/pod/<pod_id>/download")
def download(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["final"]):
        return "Not ready", 404

    # Serve raw audio so browsers stream it instead of downloading
    return send_file(
        p["final"],
        mimetype="audio/mpeg",
        as_attachment=False  # Important: allow browser playback
    )


@app.route("/pod/<pod_id>/refresh")
def manual_refresh(pod_id):
    refresh_podcast(pod_id, force=True)
    return "Manual refresh done."


@app.route("/pod/<pod_id>/log")
def view_log(pod_id):
    p = paths(pod_id)
    if not os.path.exists(p["log"]):
        return "No logs yet"
    return send_file(p["log"])

# ---------------------------------------------------------
# START APP + AUTO THREAD
# ---------------------------------------------------------
print("🚀 App ready — auto-refresh enabled.")

if __name__ == "__main__":
    threading.Thread(target=auto_refresher, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
