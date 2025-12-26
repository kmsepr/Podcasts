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

    # ---------- LOG ENCLOSURES ----------
    if entry.enclosures:
        logging.info(f"[{pid}] enclosures:")
        for e in entry.enclosures:
            logging.info(f"  href={e.href} type={getattr(e,'type',None)}")
    else:
        logging.warning(f"[{pid}] no enclosures")

    # ---------- LOG LINKS ----------
    if "links" in entry:
        logging.info(f"[{pid}] links:")
        for l in entry.links:
            logging.info(f"  href={l.get('href')} type={l.get('type')}")

    # ---------- FIND AUDIO ----------
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

    # ---------- DOWNLOAD (Buzzsprout safe) ----------
    logging.info(f"[{pid}] downloading orig.mp3")

    headers = (
        "User-Agent: Mozilla/5.0 (X11; Linux x86_64)\r\n"
        "Referer: https://www.buzzsprout.com\r\n"
    )

    r = subprocess.run(
        [
            "ffmpeg", "-y",
            "-headers", headers,
            "-i", audio,
            p["orig"]
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if r.returncode != 0:
        logging.error(f"[{pid}] ffmpeg download failed")
        logging.error(r.stderr.decode())
        return

    if not os.path.exists(p["orig"]):
        logging.error(f"[{pid}] orig.mp3 missing")
        return

    logging.info(f"[{pid}] orig.mp3 OK")

    # ---------- TRANSCODE ----------
    logging.info(f"[{pid}] transcoding to final.mp3")
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", p["orig"],
            "-ac", "1", "-b:a", "40k", "-ar", "22050",
            p["final"]
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if r.returncode != 0:
        logging.error(f"[{pid}] ffmpeg transcode failed")
        logging.error(r.stderr.decode())
        return

    if not os.path.exists(p["final"]):
        logging.error(f"[{pid}] final.mp3 missing")
        return

    logging.info(f"[{pid}] final.mp3 READY")

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
    <h1>🎧 Media Hub</h1>
    <div class="card">
        <h2>📘 MCQ Tools</h2>
        <a class="btn" href="/mcq">📝 MCQ → Excel Converter</a>
    </div>
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
    refresh_podcast(pid)
    meta = load_meta(pid)

    return f"""
    <html><body style="font-family:Arial;background:#020617;margin:0">
    <div style="max-width:900px;margin:auto;background:#fff;padding:28px;border-radius:20px">
        <h1>{PODCASTS[pid]['name']}</h1>
        <h2>{meta.get('title','')}</h2>
        <div>{meta.get('description','')}</div>
        <audio controls style="width:100%" src="/pod/{pid}/stream"></audio>
        <a href="/">⬅ Home</a>
    </div></body></html>
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

# =========================================================
# MCQ PARSER + UI (UNCHANGED)
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