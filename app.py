from flask import Flask, send_file
import requests
import feedparser
import subprocess
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------------------------------------
# SIMPLE PODCAST DICTIONARY
# ------------------------------------------------------------
PODCASTS = {
    "out": "https://feeds.buzzsprout.com/2050847.rss",
    "in": "https://feeds.megaphone.fm/THGU4956605070",
    "firsts": "https://feeds.buzzsprout.com/1194665.rss",
}

def get_rss_and_cache(pid):
    """Returns RSS URL and cache directory for a podcast ID."""
    if pid not in PODCASTS:
        return None, None
    rss = PODCASTS[pid]
    cache = f"podcache_{pid}"
    os.makedirs(cache, exist_ok=True)
    return rss, cache


# ------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------
def log(msg, cache):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)

    with open(os.path.join(cache, "log.txt"), "a") as f:
        f.write(line + "\n")


# ------------------------------------------------------------
# Load / Save metadata
# ------------------------------------------------------------
def load_meta(cache):
    meta_file = os.path.join(cache, "meta.json")
    if not os.path.exists(meta_file):
        return {}
    try:
        return json.load(open(meta_file))
    except:
        return {}

def save_meta(cache, data):
    meta_file = os.path.join(cache, "meta.json")
    with open(meta_file, "w") as f:
        json.dump(data, f)


# ------------------------------------------------------------
# MAIN REFRESH (runs only if 24 hours passed)
# ------------------------------------------------------------
def refresh_latest_episode(pid, force=False):

    rss_url, CACHE_DIR = get_rss_and_cache(pid)
    if not rss_url:
        return

    meta = load_meta(CACHE_DIR)

    # Check last update time
    if not force and "last_update" in meta:
        last = datetime.fromisoformat(meta["last_update"])
        if datetime.now() - last < timedelta(hours=24):
            log("⏳ Already updated in last 24 hours. Skipping refresh.", CACHE_DIR)
            return

    log("------------------------------------------------------------", CACHE_DIR)
    log(f"Refreshing latest episode for {pid} (force={force})", CACHE_DIR)
    log("------------------------------------------------------------", CACHE_DIR)

    log(f"Fetching RSS feed: {rss_url}", CACHE_DIR)
    feed = feedparser.parse(rss_url)

    if not feed.entries:
        log("❌ ERROR: Feed has no episodes!", CACHE_DIR)
        return

    latest = feed.entries[0]

    # ----------------------------------
    # Get audio URL
    # ----------------------------------
    if not latest.enclosures:
        log("❌ ERROR: No audio file found in feed.", CACHE_DIR)
        return

    audio_url = latest.enclosures[0].href
    log(f"Audio URL: {audio_url}", CACHE_DIR)

    original_audio = os.path.join(CACHE_DIR, "latest_original.mp3")
    final_mp3 = os.path.join(CACHE_DIR, "latest.mp3")
    thumb_path = os.path.join(CACHE_DIR, "latest_thumb.jpg")

    # ----------------------------------
    # Download audio using FFmpeg
    # ----------------------------------
    log("Downloading audio via FFmpeg...", CACHE_DIR)
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-headers", "User-Agent: Mozilla/5.0",
        "-i", audio_url,
        original_audio
    ], capture_output=True, text=True)

    log(proc.stdout, CACHE_DIR)
    log(proc.stderr, CACHE_DIR)

    if not os.path.exists(original_audio) or os.path.getsize(original_audio) < 50000:
        log("❌ Download failed (file too small). Aborting refresh.", CACHE_DIR)
        return

    # ----------------------------------
    # Convert to 40 kbps MP3
    # ----------------------------------
    log("Converting to 40kbps MP3...", CACHE_DIR)
    proc = subprocess.run([
        "ffmpeg", "-y",
        "-i", original_audio,
        "-b:a", "40k",
        final_mp3
    ], capture_output=True, text=True)

    log(proc.stdout, CACHE_DIR)
    log(proc.stderr, CACHE_DIR)

    if not os.path.exists(final_mp3):
        log("❌ Conversion failed. No MP3 created.", CACHE_DIR)
        return

    # ----------------------------------
    # Download thumbnail
    # ----------------------------------
    image_url = None
    if hasattr(latest, "image") and hasattr(latest.image, "href"):
        image_url = latest.image.href

    if image_url:
        try:
            log(f"Downloading thumbnail → {thumb_path}", CACHE_DIR)
            img = requests.get(image_url, timeout=20)
            with open(thumb_path, "wb") as f:
                f.write(img.content)
            log("✔ Thumbnail saved.", CACHE_DIR)
        except:
            log("❌ Thumbnail download error.", CACHE_DIR)

    # ----------------------------------
    # Save metadata
    # ----------------------------------
    meta["last_update"] = datetime.now().isoformat()
    meta["title"] = latest.title
    save_meta(CACHE_DIR, meta)

    log("✔ Refresh complete.", CACHE_DIR)



# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------

@app.route("/<pid>")
def home(pid):

    rss_url, CACHE_DIR = get_rss_and_cache(pid)
    if not rss_url:
        return "Podcast ID not found.", 404

    meta = load_meta(CACHE_DIR)
    mp3_exists = os.path.exists(os.path.join(CACHE_DIR, "latest.mp3"))
    thumb_exists = os.path.exists(os.path.join(CACHE_DIR, "latest_thumb.jpg"))

    html = "<html><body style='font-family:Arial;padding:20px;'>"
    html += f"<h2>Latest Episode ({pid})</h2>"

    if "title" in meta:
        html += f"<h3>{meta['title']}</h3>"

    if thumb_exists:
        html += f"<img src='/{pid}/thumbnail' width='300' style='border-radius:10px;'><br><br>"
    else:
        html += "Thumbnail loading…<br><br>"

    if mp3_exists:
        html += f"<a href='/{pid}/download' style='padding:10px 20px;background:#2196F3;color:white;text-decoration:none;border-radius:6px;'>⬇ Download MP3</a>"
    else:
        html += "MP3 not ready."

    html += "</body></html>"
    return html



@app.route("/<pid>/download")
def download(pid):
    rss_url, CACHE_DIR = get_rss_and_cache(pid)
    if not rss_url:
        return "Invalid ID", 404

    file_path = os.path.join(CACHE_DIR, "latest.mp3")
    if not os.path.exists(file_path):
        return "MP3 not ready.", 404

    return send_file(file_path, as_attachment=True)



@app.route("/<pid>/thumbnail")
def thumbnail(pid):
    rss_url, CACHE_DIR = get_rss_and_cache(pid)
    if not rss_url:
        return "Invalid ID", 404

    file_path = os.path.join(CACHE_DIR, "latest_thumb.jpg")
    if not os.path.exists(file_path):
        return "Thumbnail not ready.", 404

    return send_file(file_path)



@app.route("/<pid>/refresh")
def manual_refresh(pid):
    refresh_latest_episode(pid, force=True)
    return f"Manual refresh done for {pid}."


@app.route("/<pid>/log")
def view_log(pid):
    rss_url, CACHE_DIR = get_rss_and_cache(pid)
    if not rss_url:
        return "Invalid ID", 404

    file_path = os.path.join(CACHE_DIR, "log.txt")
    if not os.path.exists(file_path):
        return "No logs yet."
    return send_file(file_path)

@app.route("/")
def index():
    html = "<html><body style='font-family:Arial;padding:20px;'>"
    html += "<h2>Available Podcasts</h2>"
    html += "<div style='display:flex;gap:20px;flex-wrap:wrap;'>"

    for pid in PODCASTS:
        rss_url, CACHE_DIR = get_rss_and_cache(pid)
        meta = load_meta(CACHE_DIR)

        thumb_path = f"/{pid}/thumbnail" if os.path.exists(os.path.join(CACHE_DIR, 'latest_thumb.jpg')) else None
        title = meta.get("title", "Latest episode not fetched yet")

        html += "<div style='width:250px;border:1px solid #ccc;border-radius:10px;padding:15px;text-align:center;'>"
        html += f"<h3>{pid.upper()}</h3>"

        if thumb_path:
            html += f"<img src='{thumb_path}' width='220' style='border-radius:10px;'><br><br>"
        else:
            html += "<div style='width:220px;height:220px;background:#eee;border-radius:10px;line-height:220px;'>No Thumbnail</div><br>"

        html += f"<p>{title}</p>"
        html += f"<a href='/{pid}' style='padding:8px 16px;background:#2196F3;color:white;text-decoration:none;border-radius:6px;'>Open</a>"
        html += "</div>"

    html += "</div></body></html>"
    return html


# ------------------------------------------------------------
# On startup auto-refresh each podcast only if needed
# ------------------------------------------------------------
for pid in PODCASTS:
    refresh_latest_episode(pid, force=False)


# ------------------------------------------------------------
# Run app
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)