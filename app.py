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
# PODCAST REFRESH
# =========================================================
def refresh_podcast(pid, force=False):
    meta = load_meta(pid)
    if not force and "updated" in meta:
        if datetime.now() - datetime.fromisoformat(meta["updated"]) < timedelta(hours=24):
            return

    feed = feedparser.parse(PODCASTS[pid]["rss"])
    if not feed.entries:
        return

    entry = feed.entries[0]
    audio = entry.enclosures[0].href

    p = paths(pid)

    subprocess.run(["ffmpeg", "-y", "-i", audio, p["orig"]],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run([
        "ffmpeg", "-y", "-i", p["orig"],
        "-ac", "1", "-b:a", "40k", "-ar", "22050",
        p["final"]
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    meta = {
        "title": entry.title,
        "description": entry.get("summary", ""),
        "updated": datetime.now().isoformat()
    }
    save_meta(pid, meta)

# =========================================================
# AUTO REFRESH
# =========================================================
def auto_refresher():
    while True:
        for pid in PODCASTS:
            try:
                refresh_podcast(pid)
            except:
                pass
        time.sleep(3600)

# =========================================================
# HOME (MCQ BUTTON AT TOP)
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
        body { background:#020617; font-family:Arial; margin:0; }
        .box {
            max-width:1000px; margin:auto; background:#fff;
            padding:30px; border-radius:20px;
            box-shadow:0 15px 40px rgba(0,0,0,.45);
        }
        h1 { font-size:42px; text-align:center; margin-bottom:30px; }
        .card {
            background:#f1f5f9; padding:24px;
            border-radius:16px; margin-bottom:22px;
        }
        .card h2 { font-size:32px; margin-bottom:16px; }
        .btn {
            display:block; width:100%; padding:22px;
            font-size:26px; border-radius:14px;
            text-decoration:none; color:#fff;
            margin-top:12px; text-align:center;
        }
        .blue { background:#2563eb; }
        .green { background:#16a34a; }
    </style>
    </head>
    <body>
    <div class="box">
    <h1>🎧 Media Hub</h1>

    <!-- MCQ FIRST -->
    <div class="card">
        <h2>📘 MCQ Tools</h2>
        <a class="btn blue" href="/mcq">📝 MCQ → Excel Converter</a>
    </div>
    """

    for pid, info in PODCASTS.items():
        html += f"""
        <div class="card">
            <h2>🎙 {info['name']}</h2>
            <a class="btn blue" href="/pod/{pid}">▶ Open Podcast</a>
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
    <html><head>
    <meta name="viewport" content="width=device-width">
    <style>
        body {{ background:#020617; font-family:Arial; margin:0; }}
        .box {{
            max-width:900px; margin:auto; background:#fff;
            padding:28px; border-radius:20px;
        }}
        h1 {{ font-size:36px; }}
        h2 {{ font-size:28px; }}
        .desc {{ font-size:22px; background:#f1f5f9; padding:18px; border-radius:14px; }}
        audio {{ width:100%; margin:20px 0; }}
        .btn {{ padding:22px; display:block; text-align:center;
                background:#2563eb; color:#fff; border-radius:14px;
                font-size:26px; text-decoration:none; margin-bottom:14px; }}
    </style></head>
    <body>
    <div class="box">
        <h1>{PODCASTS[pid]['name']}</h1>
        <h2>{meta.get('title','')}</h2>
        <div class="desc">{meta.get('description','')}</div>
        <audio controls src="/pod/{pid}/stream"></audio>
        <a class="btn" href="/">⬅ Home</a>
    </div>
    </body></html>
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
# MCQ PARSER (UNCHANGED)
# =========================================================
def parse_mcqs(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = []

    qno = None
    question = ""
    options = {}
    answer = None

    def flush():
        nonlocal qno, question, options, answer
        if qno and question and len(options) >= 2 and answer:
            rows.append([
                qno,
                question,
                options.get("A",""),
                options.get("B",""),
                options.get("C",""),
                options.get("D",""),
                {"A":1,"B":2,"C":3,"D":4}.get(answer, "")
            ])
        qno = None
        question = ""
        options = {}
        answer = None

    for l in lines:

        # ---------- QUESTION ----------
        m = re.match(r'^(?:Q\.?\s*)?(\d+)[\.\)\-\:]\s*(.*)', l, re.I)
        if m:
            flush()
            qno = m.group(1)
            question = m.group(2)
            continue

        # ---------- OPTION ----------
        m = re.match(r'^\(?([A-Da-d])\)?[\.\)\:\-\s]+(.*)', l)
        if m:
            options[m.group(1).upper()] = m.group(2).strip()
            continue

        # ---------- ANSWER ----------
        m = re.search(r'(?:Ans|Answer|Correct Answer)?\s*[:\-]?\s*([A-Da-d])$', l, re.I)
        if m:
            answer = m.group(1).upper()
            continue

        # ---------- MULTI-LINE QUESTION ----------
        if question and not answer:
            question += " " + l

    flush()
    return rows

# =========================================================
# MCQ UI + CONVERT
# =========================================================
@app.route("/mcq")
def mcq():
    return """
    <html><head><meta name="viewport" content="width=device-width">
    <style>
        body{background:#0f172a;font-family:Arial;margin:0}
        .box{max-width:1000px;margin:auto;background:#fff;padding:30px;border-radius:18px}
        textarea{width:100%;height:420px;font-size:22px;padding:18px}
        button{width:100%;padding:22px;font-size:26px;background:#2563eb;color:#fff;border:none;border-radius:14px}
    </style></head>
    <body><div class="box">
    <h1>📘 MCQ → Excel</h1>
    <form method="post" action="/mcq/convert">
        <textarea name="mcq_text"></textarea>
        <button type="submit">⬇ Convert</button>
    </form>
    <a href="/">⬅ Home</a>
    </div></body></html>
    """

@app.route("/mcq/convert", methods=["POST"])
def convert():
    rows = parse_mcqs(request.form.get("mcq_text",""))
    df = pd.DataFrame(rows, columns=["Sl.No","Question","A","B","C","D","Correct Answer"])
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