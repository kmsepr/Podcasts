from flask import Flask, jsonify, send_file, render_template_string
import feedparser
import requests
import os

app = Flask(__name__)

# ------------------------------------------
# 1. Podcast list with friendly names
# ------------------------------------------
PODCASTS = {
    "outoffocus": {
        "name": "Out Of Focus",
        "rss": "https://feeds.buzzsprout.com/2050847.rss"
    },
    "show2": {
        "name": "My Second Show",
        "rss": "https://example.com/feed.xml"
    },
    "show3": {
        "name": "Third Podcast",
        "rss": "https://example.com/feed2.xml"
    }
}

# ------------------------------------------
# 2. Fetch latest episode from RSS
# ------------------------------------------
def fetch_latest(pid):
    feed = feedparser.parse(PODCASTS[pid]["rss"])

    if not feed.entries:
        return None

    e = feed.entries[0]

    # locate audio URL
    audio_url = None
    for link in e.get("links", []):
        if "audio" in link.get("type", ""):
            audio_url = link.get("href")
            break

    return {
        "podcast": pid,
        "title": e.get("title", ""),
        "published": e.get("published", ""),
        "audio_url": audio_url
    }


# ------------------------------------------
# 3. Homepage HTML listing all podcasts
# ------------------------------------------
HOME = """
<html>
<head>
<title>Podcast Downloads</title>
<style>
body { font-family: Arial; background:#f3f3f3; padding:20px; }
.card { background:white; padding:15px; margin-bottom:15px; border-radius:10px; }
.btn { padding:10px 14px; background:#0067ff; color:white; border-radius:8px; text-decoration:none; }
</style>
</head>
<body>

<h2>Podcast List</h2>

{% for pid, p in items.items() %}
<div class="card">
    <h3>{{ p.friendly }}</h3>
    <p><b>Latest:</b> {{ p.info.title }}</p>
    <p><b>Published:</b> {{ p.info.published }}</p>
    <a class="btn" href="/download/{{ pid }}">Download 40 kbps MP3</a>
</div>
{% endfor %}

</body>
</html>
"""

@app.route("/")
def home():
    data = {}
    for pid, obj in PODCASTS.items():
        info = fetch_latest(pid)
        data[pid] = {
            "friendly": obj["name"],
            "info": info or {"title": "No episodes", "published": "", "audio_url": None}
        }

    return render_template_string(HOME, items=data)


# ------------------------------------------
# 4. JSON route for API use
# ------------------------------------------
@app.route("/api/latest/<pid>")
def latest_api(pid):
    if pid not in PODCASTS:
        return {"error": "Invalid ID"}, 404
    return jsonify(fetch_latest(pid))


# ------------------------------------------
# 5. Download + Transcode (40 kbps mono)
# ------------------------------------------
@app.route("/download/<pid>")
def download(pid):
    if pid not in PODCASTS:
        return "Invalid podcast", 404

    info = fetch_latest(pid)
    if not info or not info["audio_url"]:
        return "No audio", 400

    src = info["audio_url"]
    src_file = f"/tmp/{pid}_src"
    out_file = f"/tmp/{pid}_40kbps.mp3"

    # Download original audio
    r = requests.get(src, stream=True)
    with open(src_file, "wb") as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)

    # Convert to 40 kbps mono MP3
    os.system(
        f"ffmpeg -y -i {src_file} -vn -ac 1 -ar 44100 -b:a 40k {out_file}"
    )

    return send_file(out_file, as_attachment=True, download_name=f"{pid}.mp3")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
