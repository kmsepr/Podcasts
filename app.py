from flask import Flask, send_file, Response, request
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
import logging

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

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

"yaqeen": {
        "name": "Yaqeen",
        "rss":"https://rss.buzzsprout.com/1014445.rss"
    
    },

    "eft": {
        "name": "EFT",
        "rss":"https://tappingqanda.libsyn.com/rss"
    
    }
}

# =========================================================
# PATH HELPERS
# =========================================================
def paths(pid):
    folder = os.path.join(BASE_CACHE, pid)
    os.makedirs(folder, exist_ok=True)
    return {
        "folder": folder,
        "meta": os.path.join(folder, "meta.json"),
        "orig": os.path.join(folder, "orig.mp3"),
        "final": os.path.join(folder, "final.mp3"),
        "tmp": os.path.join(folder, "final.tmp.mp3"),  # 👈 NEW (safe)
    }

def load_meta(pid):
    p = paths(pid)["meta"]
    if os.path.exists(p):
        return json.load(open(p))
    return {}

def save_meta(pid, data):
    json.dump(data, open(paths(pid)["meta"], "w"))

# =========================================================
# PODCAST REFRESH (FULL LOGGING)
# =========================================================
def refresh_podcast(pid, force=False):
    logging.info(f"[{pid}] refresh started")

    meta = load_meta(pid)
    if not force and "updated" in meta:
        age = datetime.now() - datetime.fromisoformat(meta["updated"])
        if age < timedelta(hours=24):
            logging.info(f"[{pid}] skipped (updated {age})")
            return

    rss = PODCASTS[pid]["rss"]
    logging.info(f"[{pid}] parsing feed: {rss}")

    feed = feedparser.parse(rss)

    if feed.bozo:
        logging.error(f"[{pid}] feed parse error: {feed.bozo_exception}")

    if not feed.entries:
        logging.error(f"[{pid}] no entries found")
        return

    entry = feed.entries[0]
    logging.info(f"[{pid}] episode: {entry.get('title')}")

    audio = None
    if entry.enclosures:
        audio = entry.enclosures[0].href
        logging.info(f"[{pid}] audio from enclosure")
    else:
        for l in entry.links:
            if l.get("type", "").startswith("audio"):
                audio = l.get("href")
                logging.info(f"[{pid}] audio from links")
                break

    if not audio:
        logging.error(f"[{pid}] AUDIO URL NOT FOUND")
        return

    logging.info(f"[{pid}] audio URL: {audio}")

    p = paths(pid)

    # ---------- DOWNLOAD ----------
    logging.info(f"[{pid}] downloading orig.mp3")

    headers = (
        "User-Agent: Mozilla/5.0 (X11; Linux x86_64)\r\n"
        "Referer: https://www.buzzsprout.com\r\n"
    )

    r = subprocess.run(
        ["ffmpeg", "-y", "-headers", headers, "-i", audio, p["orig"]],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if r.returncode != 0:
        logging.error(r.stderr.decode())
        return

    logging.info(f"[{pid}] orig.mp3 OK")

    # ---------- TRANSCODE (SAFE) ----------
    logging.info(f"[{pid}] transcoding to temp file")

    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", p["orig"],
            "-ac", "1", "-b:a", "40k", "-ar", "22050",
            p["tmp"]
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if r.returncode != 0:
        logging.error(r.stderr.decode())
        return

    # 🔒 ATOMIC REPLACE (NO STREAM RESET)
    os.replace(p["tmp"], p["final"])

    logging.info(f"[{pid}] final.mp3 READY (atomic swap)")

    meta = {
        "title": entry.get("title", ""),
        "description": entry.get("summary", ""),
        "updated": datetime.now().isoformat()
    }
    save_meta(pid, meta)

    logging.info(f"[{pid}] metadata saved")

# =========================================================
# AUTO REFRESH
# =========================================================
def auto_refresher():
    while True:
        for pid in PODCASTS:
            try:
                refresh_podcast(pid)
            except Exception as e:
                logging.exception(f"[{pid}] refresh error: {e}")
        time.sleep(3600)

# =========================================================
# HOME
# =========================================================
@app.route("/")
def home():
    html = """
    <html><head>
    <meta name="viewport" content="width=device-width">
    <style>
    body{background:#020617;font-family:Arial;margin:0}
    .box{max-width:1000px;margin:auto;background:#fff;padding:30px;border-radius:20px}
    h1{text-align:center}
    .card{background:#f1f5f9;padding:24px;border-radius:16px;margin-bottom:22px}
    .btn{display:block;padding:22px;font-size:26px;border-radius:14px;
         text-decoration:none;color:#fff;text-align:center;background:#2563eb}
    </style></head><body>
    <div class="box">
    <h1>🎧 Podcasts</h1>
    """

    for pid, info in PODCASTS.items():
        html += f"""
        <div class="card">
            <h2>🎙 {info['name']}</h2>
            <a class="btn" href="/pod/{pid}">▶ Open Podcast</a>
        </div>
        """

    return html + "</div></body></html>"

# =========================================================
# PODCAST PAGE
# =========================================================
@app.route("/pod/<pid>")
def pod(pid):
    if pid not in PODCASTS:
        return "Podcast not found", 404

    refresh_podcast(pid)
    meta = load_meta(pid)

    return f"""
    <html>
    <head>
    <meta name="viewport" content="width=device-width">
    <style>
    body {{
        font-family: Arial;
        background: #020617;
        margin: 0;
    }}
    .box {{
        max-width: 900px;
        margin: auto;
        background: #ffffff;
        padding: 28px;
        border-radius: 20px;
        margin-top: 20px;
    }}
    h1 {{
        margin-top: 0;
    }}
    .btn {{
        display: inline-block;
        padding: 14px 22px;
        font-size: 18px;
        border-radius: 10px;
        text-decoration: none;
        color: #fff;
        margin-top: 15px;
    }}
    .download {{
        background: #16a34a;
    }}
    .home {{
        background: #2563eb;
        margin-left: 10px;
    }}
    audio {{
        margin-top: 20px;
        width: 100%;
    }}
    </style>
    </head>
    <body>
    <div class="box">
        <h1>🎙 {PODCASTS[pid]['name']}</h1>
        <h2>{meta.get('title','')}</h2>
        <div>{meta.get('description','')}</div>

        <audio controls src="/pod/{pid}/stream"></audio>

        <br>

        <a class="btn download" href="/pod/{pid}/download">
            ⬇ Download Episode
        </a>

        <a class="btn home" href="/">
            ⬅ Home
        </a>
    </div>
    </body>
    </html>
    """

@app.route("/pod/<pid>/stream")
def stream(pid):
    f = paths(pid)["final"]
    if not os.path.exists(f):
        return "Not ready", 404

    def gen():
        with open(f, "rb") as fh:
            while True:
                b = fh.read(65536)
                if not b:
                    break
                yield b

    return Response(gen(), mimetype="audio/mpeg")


@app.route("/pod/<pid>/download")
def download(pid):
    if pid not in PODCASTS:
        return "Podcast not found", 404

    f = paths(pid)["final"]
    if not os.path.exists(f):
        return "Not ready", 404

    return send_file(
        f,
        as_attachment=True,
        download_name=f"{pid}.mp3",
        mimetype="audio/mpeg"
    )

# =========================================================
# MCQ SECTION (UNCHANGED)
# =========================================================
def parse_mcqs(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows, qno, question, options, answer = [], None, "", {}, None

    def flush():
        nonlocal qno, question, options, answer
        if qno and question and answer:
            rows.append([qno, question, options.get("A",""),
                         options.get("B",""), options.get("C",""),
                         options.get("D",""),
                         {"A":1,"B":2,"C":3,"D":4}.get(answer)])
        qno, question, options, answer = None, "", {}, None

    for l in lines:
        if m := re.match(r'(\d+)[\.\)]\s*(.*)', l):
            flush(); qno, question = m.group(1), m.group(2)
        elif m := re.match(r'([A-D])[\.\)]\s*(.*)', l):
            options[m.group(1)] = m.group(2)
        elif m := re.search(r'Answer\s*[:\-]\s*([A-D])$', l, re.I):
            answer = m.group(1)
        elif question:
            question += " " + l

    flush()
    return rows

@app.route("/mcq")
def mcq():
    return """
    <form method="post" action="/mcq/convert">
        <textarea name="mcq_text" style="width:100%;height:400px"></textarea>
        <button>Convert</button>
    </form>
    """

@app.route("/mcq/convert", methods=["POST"])
def convert():
    rows = parse_mcqs(request.form.get("mcq_text",""))
    df = pd.DataFrame(rows)
    out = io.BytesIO()
    df.to_excel(out, index=False, header=False)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name="mcqs.xlsx")

# =========================================================
# START
# =========================================================
if __name__ == "__main__":
    threading.Thread(target=auto_refresher, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
