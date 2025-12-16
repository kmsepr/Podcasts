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
    html = "<h1>🎙 Podcasts</h1><ul>"
    for pid, p in PODCASTS.items():
        html += f"<li><a href='/pod/{pid}'>{p['name']}</a></li>"
    html += "</ul><br><a href='/mcq'>📘 MCQ Converter</a>"
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
    <h2>📘 MCQ to Excel</h2>
    <form method="post" action="/mcq/convert">
    <textarea name="mcq_text" rows="20" cols="80"></textarea><br>
    <button>Convert</button>
    </form>
    <br><a href="/">Home</a>
    """

@app.route("/mcq/convert", methods=["POST"])
def mcq_convert():
    text = request.form.get("mcq_text", "")
    rows = parse_mcqs(text)
    if not rows:
        return "Parsing failed"

    df = pd.DataFrame(rows, columns=["Sl","Question","A","B","C","D","Answer"])
    out = io.BytesIO()
    df.to_excel(out, index=False, header=False)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name="mcqs.xlsx")

# =========================================================
# START APP
# =========================================================
if __name__ == "__main__":
    threading.Thread(target=auto_refresher, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)