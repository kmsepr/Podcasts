import os
import requests
import feedparser
from flask import Flask, send_file, render_template_string, abort

app = Flask(__name__)

# -----------------------------
# CONFIG: Add podcasts here
# -----------------------------
PODCASTS = {
    "outoffocus": "https://feeds.buzzsprout.com/2050847.rss",
    # add more:
    # "show2": "https://example.com/feed.xml",
    # "show3": "https://example.com/feed.xml"
}

# Storage folder
MEDIA = "media"
os.makedirs(MEDIA, exist_ok=True)

# -----------------------------
# Fetch latest episode
# -----------------------------
def fetch_latest(podcast_name):
    if podcast_name not in PODCASTS:
        return None

    rss_url = PODCASTS[podcast_name]
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        return None

    e = feed.entries[0]

    # audio URL
    audio = None
    for link in e.links:
        if "audio" in link.type:
            audio = link.href
            break

    if not audio:
        return None

    # Create date stamp (YYYYMMDD)
    if "published_parsed" in e:
        date = e.published_parsed
        date_tag = f"{date.tm_year}{date.tm_mon:02d}{date.tm_mday:02d}"
    else:
        date_tag = "latest"

    # File path
    folder = os.path.join(MEDIA, podcast_name)
    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, f"{date_tag}.mp3")

    return {
        "title": e.title,
        "published": e.get("published", ""),
        "audio_url": audio,
        "file_path": file_path,
        "file_name": f"{date_tag}.mp3",
        "folder": folder
    }

# -----------------------------
# HOME PAGE: List all podcasts
# -----------------------------
@app.route("/")
def home():
    HTML = """
    <html><body>
    <h2>Podcast List</h2>
    {% for name in podcasts %}
        <p><a href="/podcast/{{name}}">{{name}}</a></p>
    {% endfor %}
    </body></html>
    """
    return render_template_string(HTML, podcasts=PODCASTS.keys())

# -----------------------------
# PODCAST PAGE
# -----------------------------
@app.route("/podcast/<podcast_name>")
def podcast_page(podcast_name):
    info = fetch_latest(podcast_name)
    if not info:
        abort(404)

    # Simple page with download link
    HTML = """
    <html><body>
    <h2>{{name}}</h2>
    <p><b>{{info.title}}</b></p>
    <p>{{info.published}}</p>

    <a href="/download/{{name}}">Download 40kbps MP3</a>
    </body></html>
    """
    return render_template_string(HTML, name=podcast_name, info=info)

# -----------------------------
# DOWNLOAD + TRANSCODE
# -----------------------------
@app.route("/download/<podcast_name>")
def download(podcast_name):
    info = fetch_latest(podcast_name)
    if not info:
        abort(404)

    out_file = info["file_path"]

    # Already processed? Serve it.
    if os.path.exists(out_file):
        return send_file(out_file, as_attachment=True)

    # Download source
    src_tmp = "/tmp/src_audio"
    r = requests.get(info["audio_url"], stream=True)
    with open(src_tmp, "wb") as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)

    # Convert → 40 kbps mono MP3
    os.system(
        f"ffmpeg -y -i {src_tmp} -ac 1 -ar 44100 -b:a 40k {out_file}"
    )

    return send_file(out_file, as_attachment=True)

# -----------------------------
# Run server
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
