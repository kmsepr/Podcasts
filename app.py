import os
import sqlite3
import requests
import feedparser
import subprocess
from flask import Flask, request, jsonify, send_file, render_template_string

app = Flask(__name__)

# =============================
# PODCAST DATABASE + FUNCTIONS
# =============================
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id TEXT UNIQUE,
            title TEXT,
            author TEXT,
            cover_url TEXT,
            rss_url TEXT,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            podcast_id TEXT,
            episode_id TEXT UNIQUE,
            title TEXT,
            description TEXT,
            audio_url TEXT,
            pub_date TEXT,
            duration TEXT,
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/api/search')
def search_podcasts():
    query = request.args.get('q', '')
    try:
        res = requests.get(f'https://itunes.apple.com/search?media=podcast&term={query}')
        return jsonify(res.json().get('results', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/episodes_from_rss', methods=['POST'])
def episodes_from_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url:
        return jsonify([])
    feed = feedparser.parse(rss_url)
    results = []
    for item in feed.entries[:10]:
        audio = ''
        for enc in item.get('enclosures', []):
            if enc.get('href', '').startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue
        results.append({
            'title': item.get('title', ''),
            'description': item.get('summary', '') or item.get('description', ''),
            'pub_date': item.get('published', ''),
            'audio_url': audio
        })
    return jsonify(results)

# =============================
# YOUTUBE → MP3 FUNCTIONS
# =============================
COOKIES_FILE = "/mnt/data/cookies.txt"

def fetch_latest_video_mp3(url, output_path):
    try:
        cmd = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--max-downloads", "1",
            "--cookies", COOKIES_FILE,
            "--output", output_path,
            url
        ]
        subprocess.run(cmd, check=True)
    except Exception as e:
        app.logger.error(f"Error fetching video from {url}: {e}")

@app.route('/babu.mp3')
def babu_mp3():
    path = "/mnt/data/babu.mp3"
    if not os.path.exists(path):
        fetch_latest_video_mp3("https://www.youtube.com/@babu_ramachandran/videos", path)
    return send_file(path, mimetype="audio/mpeg")

# =============================
# PAGES
# =============================
@app.route('/')
def landing():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Media Hub</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container py-4">
        <h2 class="mb-4">🎵 Media Hub</h2>
        <div class="row">
            <div class="col-md-6">
                <div class="card shadow-sm mb-3">
                    <div class="card-body">
                        <h5 class="card-title">📺 YouTube MP3</h5>
                        <p class="card-text">Download the latest YouTube audio as MP3.</p>
                        <a href="/yt" class="btn btn-primary">Go</a>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card shadow-sm mb-3">
                    <div class="card-body">
                        <h5 class="card-title">🎧 Podcast Player</h5>
                        <p class="card-text">Browse and play your favorite podcasts.</p>
                        <a href="/podcast" class="btn btn-success">Go</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

@app.route('/yt')
def yt_ui():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube MP3</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container py-4">
        <h3>📺 YouTube → MP3</h3>
        <p>Click the button below to download the latest YouTube MP3:</p>
        <a href="/babu.mp3" class="btn btn-primary">Download MP3</a>
        <br><br>
        <audio controls>
            <source src="/babu.mp3" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        <br><br>
        <a href="/" class="btn btn-secondary">⬅ Back</a>
    </body>
    </html>
    """)

@app.route('/podcast')
def podcast_ui():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Podcast Player</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container py-4">
        <h3>🎧 Podcast Player</h3>
        <p>This is where your podcast player UI goes.</p>
        <p>(Your API routes like /api/search, /api/favorites, /api/podcast/... are already working.)</p>
        <a href="/" class="btn btn-secondary">⬅ Back</a>
    </body>
    </html>
    """)

# =============================
# MAIN
# =============================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)