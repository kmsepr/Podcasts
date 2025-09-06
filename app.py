import os
import sqlite3
import requests
import feedparser
import subprocess
import logging
from flask import Flask, request, jsonify, render_template_string, send_file

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

logging.basicConfig(level=logging.INFO)

# -------------------- PODCAST SECTION --------------------

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

# -------------------- YOUTUBE SECTION --------------------

CHANNELS = {
    "maxvelocity": "https://youtube.com/@maxvelocitywx/videos",
    "babu": "https://www.youtube.com/@babu_ramachandran/videos",
    "dhruv": "https://youtube.com/@dhruvrathee/videos",
    "safari": "https://youtube.com/@safaritvlive/videos"
}

COOKIES_FILE = "/mnt/data/cookies.txt"

def fetch_latest_mp3(url):
    try:
        result = subprocess.run([
            "yt-dlp", "--dump-single-json",
            "--playlist-end", "1",
            "--cookies", COOKIES_FILE,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            url
        ], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Error fetching video from {url}: {e}")
        return None

@app.route('/<channel>.mp3')
def channel_mp3(channel):
    if channel not in CHANNELS:
        return "Channel not found", 404
    data = fetch_latest_mp3(CHANNELS[channel])
    if not data:
        return "Error fetching video", 500
    return jsonify(data)

@app.route('/yt')
def youtube_index():
    return '''
    <html><head><title>YouTube MP3</title></head><body>
    <h3>🎬 YouTube to MP3</h3>
    <ul>
      <li><a href="/maxvelocity.mp3">Max Velocity</a></li>
      <li><a href="/babu.mp3">Babu Ramachandran</a></li>
      <li><a href="/dhruv.mp3">Dhruv Rathee</a></li>
      <li><a href="/safari.mp3">Safari TV</a></li>
    </ul>
    </body></html>
    '''

# -------------------- UI ROUTES --------------------

@app.route('/')
def landing_page():
    return '''
    <!DOCTYPE html>
    <html><head>
      <title>Media Hub</title>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
    </head><body class="p-3">
      <div class="container">
        <h2 class="mb-4">📺 Media Hub</h2>
        <div class="row g-3">
          <div class="col-6">
            <div class="card shadow-sm">
              <div class="card-body text-center">
                <h5 class="card-title">🎬 YouTube MP3</h5>
                <p class="card-text">Convert latest videos to MP3</p>
                <a href="/yt" class="btn btn-primary">Open</a>
              </div>
            </div>
          </div>
          <div class="col-6">
            <div class="card shadow-sm">
              <div class="card-body text-center">
                <h5 class="card-title">🎧 Podcast</h5>
                <p class="card-text">Stream and download podcasts</p>
                <a href="/podcast" class="btn btn-success">Open</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </body></html>
    '''

@app.route('/podcast')
def podcast_ui():
    return homepage()  # reuse podcast HTML UI

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)