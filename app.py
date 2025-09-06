import os
import sqlite3
import requests
import feedparser
import subprocess
import threading
import time
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

@app.route('/api/favorites')
def get_favorites():
    offset = int(request.args.get('offset', 0))
    limit = 5
    default_feeds = [
        "https://muslimcentral.com/audio/hamza-yusuf/feed/",
        "https://feeds.megaphone.fm/THGU4956605070",
        "https://feeds.buzzsprout.com/2050847.rss",
        "https://muslimcentral.com/audio/the-deen-show/feed/",
        "https://feeds.buzzsprout.com/1194665.rss",
        "https://www.spreaker.com/show/5085297/episodes/feed",
    ]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for rss_url in default_feeds:
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
            podcast_id = rss_url
            title = feed.feed.get('title', 'Untitled')
            author = feed.feed.get('author', 'Unknown')
            image = (feed.feed.get('image', {}) or {}).get('href', '') or \
                    feed.feed.get('itunes_image', {}).get('href', '')
            c.execute('''
                INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (podcast_id, title, author, image, rss_url))
        except:
            continue

    conn.commit()
    c.execute('SELECT * FROM podcasts WHERE podcast_id IN (%s) ORDER BY last_played DESC LIMIT ? OFFSET ?'
              % ','.join('?' * len(default_feeds)),
              (*default_feeds, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/mark_played/<path:pid>', methods=['POST'])
def mark_played(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE podcasts SET last_played = CURRENT_TIMESTAMP WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Marked as played'})

@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 9
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_date DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    if rows:
        conn.close()
        return jsonify(rows)

    c.execute('SELECT rss_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    feed = feedparser.parse(row[0])
    all_eps = []
    for item in feed.entries:
        eid = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
        audio = ''
        for enc in item.get('enclosures', []):
            if enc.get('href', '').startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue
        title = item.get('title', '')
        desc = item.get('summary', '') or item.get('description', '')
        pub_date = item.get('published', '')
        duration = item.get('itunes_duration', '')
        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (pid, eid, title, desc, audio, pub_date, duration))
        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'duration': duration
        })
    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

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
# LANDING PAGE + ROUTES
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
    return "<h3>📺 YouTube → MP3 Page</h3><p>Use /babu.mp3 to test audio download.</p>"

@app.route('/podcast')
def podcast_ui():
    return render_template_string(open(__file__).read().split("return '''")[1].split("'''")[0])

# =============================
# MAIN
# =============================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)