from flask import Flask, jsonify, send_file, render_template_string
import feedparser
import requests
import os

app = Flask(__name__)

# -------------------------------------------------
# 1. PODCAST LIST (ADD AS MANY AS YOU WANT)
# -------------------------------------------------
PODCASTS = {
    "outoffocus": "https://feeds.buzzsprout.com/2050847.rss",
    "newsminute": "https://rss.art19.com/the-news-minute",
    "tech": "https://feeds.megaphone.fm/vergecast"
}

# Store latest episode cache
CACHE = {}

# -------------------------------------------------
# 2. Helper – Fetch latest episode
# -------------------------------------------------
def fetch_latest(podcast_id):
    url = PODCASTS[podcast_id]
    feed = feedparser.parse(url)

    if not feed.entries:
        return None

    entry = feed.entries[0]

    enclosure_url = None
    if "enclosures" in entry and len(entry.enclosures) > 0:
        enclosure_url = entry.enclosures[0].href

    return {
        "podcast": podcast_id,
        "title": entry.title,
        "published": entry.get("published", "Unknown"),
        "audio_url": enclosure_url,
    }


# -------------------------------------------------
# 3. Home page HTML (with buttons)
# -------------------------------------------------
HOME_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Podcast Downloader</title>
    <style>
        body { font-family: Arial; background: #f2f2f2; padding: 20px; }
        .card {
            background: white; padding: 20px; margin-bottom: 15px;
            border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        .btn {
            background: #007bff; color: white; padding: 10px 15px;
            border-radius: 6px; text-decoration: none;
        }
        .btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <h2>Available Podcasts</h2>

    {% for pid, item in podcasts.items() %}
    <div class="card">
        <h3>{{ item.title }}</h3>
        <p><b>ID:</b> {{ pid }}</p>
        <p><b>Published:</b> {{ item.published }}</p>

        {% if item.audio_url %}
        <a class="btn"
           href="/download/{{ pid }}">
           Download Latest Episode
        </a>
        {% else %}
        <p>No audio file found.</p>
        {% endif %}
    </div>
    {% endfor %}
</body>
</html>
"""

# -------------------------------------------------
# 4. Home page route
# -------------------------------------------------
@app.route("/")
def home():
    data = {}
    for pid in PODCASTS:
        data[pid] = fetch_latest(pid)

    return render_template_string(HOME_PAGE, podcasts=data)

# -------------------------------------------------
# 5. API endpoint – Latest JSON
# -------------------------------------------------
@app.route("/api/latest/<podcast_id>")
def api_latest(podcast_id):
    if podcast_id not in PODCASTS:
        return jsonify({"error": "Invalid podcast ID"}), 404

    latest = fetch_latest(podcast_id)
    return jsonify(latest)

# -------------------------------------------------
# 6. Download handler
# -------------------------------------------------
@app.route("/download/<podcast_id>")
def download_latest(podcast_id):

    if podcast_id not in PODCASTS:
        return "Invalid podcast ID", 404

    latest = fetch_latest(podcast_id)
    if not latest or not latest["audio_url"]:
        return "No audio file available", 400

    audio_url = latest["audio_url"]

    # Download audio into temp file
    filename = f"{podcast_id}.mp3"
    filepath = f"/tmp/{filename}"

    r = requests.get(audio_url, stream=True)
    with open(filepath, "wb") as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)

    return send_file(filepath, as_attachment=True)

# -------------------------------------------------
# 7. Start app
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
