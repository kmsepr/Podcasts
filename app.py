import os
import requests
import feedparser
import subprocess
from flask import Flask, render_template_string, send_file, abort

app = Flask(__name__)

PODCAST_NAME = "outoffocus"
FEED_URL = "https://feeds.buzzsprout.com/2050847.rss"
MEDIA_ROOT = "/mnt/data/media/outoffocus"

os.makedirs(MEDIA_ROOT, exist_ok=True)

# -----------------------------
#  HTML TEMPLATE (INLINE)
# -----------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Out Of Focus Podcast</title>
    <style>
        body { font-family: Arial; background:#f2f2f2; padding:20px; }
        .card {
            background:white; padding:20px; margin-bottom:20px;
            border-radius:10px; box-shadow:0 3px 8px rgba(0,0,0,0.15);
        }
        h2 { margin:0; }
        .btn {
            display:inline-block; padding:10px 15px;
            background:#007bff; color:white; text-decoration:none;
            border-radius:6px;
        }
    </style>
</head>
<body>
    <h1>Out Of Focus - All Episodes</h1>

    {% for ep in episodes %}
    <div class="card">
        <h2>{{ ep.title }}</h2>
        <small>{{ ep.published }}</small>
        <p>{{ ep.description }}</p>

        <a class="btn" href="/download/outoffocus/{{ ep.id }}">Download (40 kbps mono)</a>
    </div>
    {% endfor %}
</body>
</html>
"""


# -----------------------------------------------------
#  HOME PAGE -> LIST EPISODES WITH FULL DESCRIPTION
# -----------------------------------------------------
@app.route("/")
def home():
    feed = feedparser.parse(FEED_URL)
    episodes = []

    # Limit to latest 3
    latest = feed.entries[:3]

    for i, item in enumerate(latest):
        if not item.enclosures:
            continue

        episodes.append({
            "id": i,
            "title": item.title,
            "published": item.published,
            "description": item.summary,
        })

    return render_template_string(HTML_TEMPLATE, episodes=episodes)

# -----------------------------------------------------
#  DOWNLOAD + TRANSCODE ENDPOINT
# -----------------------------------------------------
@app.route("/download/outoffocus/<int:ep_id>")
def download_episode(ep_id):
    feed = feedparser.parse(FEED_URL)

    if ep_id >= len(feed.entries):
        abort(404)

    entry = feed.entries[ep_id]

    if not entry.enclosures:
        abort(404)

    audio_url = entry.enclosures[0].href

    # unique file name per-episode
    safe_title = entry.title.replace(" ", "_").replace("|", "").replace("/", "_")
    output_mp3 = os.path.join(MEDIA_ROOT, f"{safe_title}.mp3")

    if os.path.exists(output_mp3):
        return send_file(output_mp3, as_attachment=True)

    # -------------------------
    # DOWNLOAD ORIGINAL FILE
    # -------------------------
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    tmp_file = "/tmp/original_download"

    try:
        r = requests.get(audio_url, headers=headers, stream=True, timeout=60)
        r.raise_for_status()

        with open(tmp_file, "wb") as f:
            for chunk in r.iter_content(1024 * 32):
                f.write(chunk)

        if os.path.getsize(tmp_file) < 5000:
            return "Source audio too small / invalid.", 500

    except Exception as e:
        return f"Download failed: {e}", 500

    # -------------------------
    # FFMPEG TRANSCODE → 40 kbps mono mp3
    # -------------------------
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_file,
            "-ar", "44100",
            "-ac", "1",
            "-b:a", "40k",
            output_mp3
        ]
        subprocess.run(cmd, check=True)
    except Exception as e:
        return f"FFmpeg error: {e}", 500

    return send_file(output_mp3, as_attachment=True)


# -----------------------------------------------------
#  START SERVER
# -----------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
