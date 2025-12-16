from flask import Flask, send_file, Response, request
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta
import threading
import time
import pandas as pd
import re
import io

app = Flask(__name__)

# =========================================================
# BASE CACHE
# =========================================================
BASE_CACHE = "podcache"
os.makedirs(BASE_CACHE, exist_ok=True)

# =========================================================
# PODCAST LIST
# =========================================================
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

# =========================================================
# PATH HELPERS
# =========================================================
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
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
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
    with open(paths(pod_id)["meta"], "w") as f:
        json.dump(data, f)

# =========================================================
# PODCAST REFRESH
# =========================================================
def refresh_podcast(pod_id, force=False):
    info = PODCASTS[pod_id]
    p = paths(pod_id)
    meta = load_meta(pod_id)

    if not force and "last_update" in meta:
        if datetime.now() - datetime.fromisoformat(meta["last_update"]) < timedelta(hours=24):
            log(pod_id, "Already updated < 24h")
            return

    feed = feedparser.parse(info["rss"])
    if not feed.entries or not feed.entries[0].enclosures:
        log(pod_id, "Feed error / no audio")
        return

    audio_url = feed.entries[0].enclosures[0].href
    log(pod_id, f"Downloading {audio_url}")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", audio_url,
        p["original"]
    ], capture_output=True)

    if not os.path.exists(p["original"]):
        log(pod_id, "Download failed")
        return

    subprocess.run([
        "ffmpeg", "-y",
        "-i", p["original"],
        "-ac", "1",
        "-b:a", "40k",
        "-ar", "22050",
        p["final"]
    ], capture_output=True)

    meta["title"] = feed.entries[0].title
    meta["description"] = feed.entries[0].get("summary", "")
    meta["last_update"] = datetime.now().isoformat()
    save_meta(pod_id, meta)

    log(pod_id, "Refresh done")

# =========================================================
# AUTO REFRESH THREAD
# =========================================================
def auto_refresher():
    while True:
        for pid in PODCASTS:
            try:
                refresh_podcast(pid)
            except Exception as e:
                print("Auto error:", e)
        time.sleep(3600)

# =========================================================
# PODCAST ROUTES
# =========================================================
@app.route("/")
def home():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>Media Hub</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin: 0;
            min-height: 100vh;
            background: #020617;
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            width: 96%;
            max-width: 1000px;
            background: #ffffff;
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 15px 40px rgba(0,0,0,0.45);
        }
        h1 {
            font-size: 44px;
            text-align: center;
            margin-bottom: 35px;
        }
        .card {
            background: #f1f5f9;
            padding: 25px;
            border-radius: 16px;
            margin-bottom: 22px;
        }
        .card h2 {
            font-size: 32px;
            margin: 0 0 18px 0;
        }
        .btn {
            display: block;
            width: 100%;
            padding: 22px;
            font-size: 26px;
            font-weight: bold;
            border-radius: 14px;
            border: none;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            margin-top: 12px;
        }
        .btn-primary {
            background: #2563eb;
            color: white;
        }
        .btn-secondary {
            background: #16a34a;
            color: white;
        }
        .btn:active {
            opacity: 0.85;
        }
        .footer {
            text-align: center;
            font-size: 18px;
            margin-top: 25px;
            color: #555;
        }
    </style>
    </head>
    <body>
        <div class="container">
            <h1>🎧 Media Hub</h1>
    """

    for pid, info in PODCASTS.items():
        html += f"""
            <div class="card">
                <h2>🎙 {info['name']}</h2>
                <a class="btn btn-primary" href="/pod/{pid}">▶ Open Podcast</a>
                <a class="btn btn-secondary" href="/pod/{pid}/refresh">🔄 Refresh Podcast</a>
            </div>
        """

    html += """
            <div class="card">
                <h2>📘 MCQ Tools</h2>
                <a class="btn btn-primary" href="/mcq">📝 MCQ → Excel Converter</a>
            </div>

            <div class="footer">
                Large UI · Touch friendly · Keypad safe
            </div>
        </div>
    </body>
    </html>
    """
    return html
@app.route("/pod/<pod_id>")
def pod(pod_id):
    if pod_id not in PODCASTS:
        return "Invalid"

    refresh_podcast(pod_id)
    meta = load_meta(pod_id)

    return f"""
    <h2>{PODCASTS[pod_id]['name']}</h2>
    <h3>{meta.get('title','')}</h3>
    <p>{meta.get('description','')}</p>
    <audio controls src="/pod/{pod_id}/stream"></audio><br>
    <a href="/pod/{pod_id}/download">Download</a><br>
    <a href="/">Home</a>
    """

@app.route("/pod/<pod_id>/stream")
def stream(pod_id):
    f = paths(pod_id)["final"]
    if not os.path.exists(f):
        return "Not ready", 404

    def gen():
        with open(f, "rb") as fh:
            while True:
                data = fh.read(65536)
                if not data:
                    break
                yield data

    return Response(gen(), mimetype="audio/mpeg")

@app.route("/pod/<pod_id>/download")
def download(pod_id):
    f = paths(pod_id)["final"]
    if not os.path.exists(f):
        return "Not ready", 404
    return send_file(f, as_attachment=False)

# =========================================================
# MCQ PARSER
# =========================================================
def parse_mcqs(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows, q, opts = [], "", {}
    qno, ans = None, None

    for l in lines:
        if re.match(r'^[A-Da-d][\)\:\-]', l):
            opts[l[0].upper()] = l[2:].strip()
        elif re.match(r'^\d+\.\s*[A-Da-d]$', l):
            qno, ans = l.split(".")
            rows.append([
                qno,
                q + "\n" + "\n".join([f"{k}) {v}" for k,v in opts.items()]),
                "A","B","C","D",
                {"A":1,"B":2,"C":3,"D":4}[ans.upper()]
            ])
            q, opts = "", {}
        elif re.match(r'^\d+\.', l):
            qno = l.split(".")[0]
            q = l
    return rows

# =========================================================
# MCQ ROUTES
# =========================================================
@app.route("/mcq")
def mcq():
    return """
    <!DOCTYPE html>
    <html>
    <head>
    <title>MCQ Converter</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin: 0;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: #0f172a;
            font-family: Arial, sans-serif;
        }
        .box {
            width: 96%;
            max-width: 1000px;
            background: #ffffff;
            padding: 30px;
            border-radius: 18px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.4);
        }
        h1 {
            font-size: 42px;
            text-align: center;
            margin-bottom: 25px;
        }
        textarea {
            width: 100%;
            height: 420px;
            font-size: 22px;
            padding: 18px;
            border-radius: 12px;
            border: 2px solid #444;
            line-height: 1.6;
        }
        button {
            width: 100%;
            margin-top: 25px;
            padding: 22px;
            font-size: 26px;
            font-weight: bold;
            border-radius: 14px;
            border: none;
            background: #2563eb;
            color: white;
            cursor: pointer;
        }
        button:active {
            background: #1e40af;
        }
        .hint {
            text-align: center;
            margin-top: 15px;
            font-size: 18px;
            color: #555;
        }
        a {
            display: block;
            text-align: center;
            margin-top: 20px;
            font-size: 22px;
            text-decoration: none;
            color: #2563eb;
        }
    </style>
    </head>
    <body>
        <div class="box">
            <h1>📘 MCQ → Excel</h1>
            <form method="post" action="/mcq/convert">
                <textarea name="mcq_text" placeholder="Paste MCQs here..."></textarea>
                <button type="submit">⬇ Convert to Excel</button>
            </form>
            <div class="hint">
                One question per number · Options A–D · Answer like: 12.C
            </div>
            <a href="/">⬅ Back to Home</a>
        </div>
    </body>
    </html>
    """
# =========================================================
# START APP
# =========================================================
if __name__ == "__main__":
    threading.Thread(target=auto_refresher, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)