import os
import sqlite3
import requests
import feedparser
import subprocess
import json
import time
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ---------------------- Database setup ----------------------
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

# ---------------------- Podcast API ----------------------
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

# ---------------------- YouTube API ----------------------
YTDLP_COOKIES = '/mnt/data/cookies.txt'
YTDLP_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

def fetch_youtube_json(url, retries=3):
    for i in range(retries):
        try:
            cmd = [
                "yt-dlp",
                "--dump-single-json",
                "--playlist-end", "5",
                "--cookies", YTDLP_COOKIES,
                "--user-agent", YTDLP_USER_AGENT,
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            if i < retries - 1:
                time.sleep(2)
            else:
                return {"error": e.stderr}

@app.route('/yt')
def yt_ui():
    channels = [
        "https://www.youtube.com/@babu_ramachandran/videos",
        "https://www.youtube.com/@dhruvrathee/videos"
    ]
    videos = []
    for ch in channels:
        data = fetch_youtube_json(ch)
        if 'entries' in data:
            for v in data['entries'][:1]:
                videos.append({
                    'title': v.get('title'),
                    'url': v.get('webpage_url')
                })
        else:
            videos.append({'title': f"Error fetching {ch}", 'url': ''})

    html = "<h3>YouTube Channels</h3>"
    for v in videos:
        html += f"<div class='card'><b>{v['title']}</b><br><a href='{v['url']}' target='_blank'>▶ Watch</a></div>"
    return html

# ---------------------- Podcast Page ----------------------
@app.route('/podcast')
def podcast_ui():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT title, cover_url, podcast_id FROM podcasts ORDER BY last_played DESC LIMIT 10')
    rows = c.fetchall()
    conn.close()
    html = "<h3>🎙️ Podcasts</h3>"
    for title, cover, pid in rows:
        html += f"<div class='card'><b>{title}</b><br>"
        if cover: html += f"<img src='{cover}' width='100'><br>"
        html += f"<a href='/api/podcast/{pid}/episodes'>View Episodes</a></div>"
    return html

# ---------------------- Homepage ----------------------
@app.route('/')
def homepage():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320"><title>Podcast</title><style>
body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666} audio{width:100%; margin-top:5px}
</style></head><body><h3>🎧 Podcast</h3>
<p style="font-size:12px;color:#666">🔢 Press 1 to view Favorites</p>
<input id="q" placeholder="Search..."><button onclick="search()">🔍 Search</button>
<button onclick="showFavs()">⭐ My Favorites</button>
<div id="results"></div>
<div id="playerBox" style="display:none">
  <div class="card">
    <b id="epTitle"></b><br><span class="tiny" id="epDate"></span><br>
    <audio id="player" controls></audio><br>
    <p id="epDesc" style="margin-top:6px"></p>
    <a id="downloadBtn" href="#" download style="display:inline-block;margin:5px 0">📥 Download MP3</a><br>
    <button onclick="prevEp()">⏮️</button>
    <button onclick="togglePlay()">⏯️</button>
    <button onclick="nextEp()">⏭️</button>
  </div>
</div>
<script>
const B = location.origin;
function e(id){return document.getElementById(id);}
document.addEventListener('keydown', ev => { if (ev.key === '1') showFavs(); });
async function search(){ let q=e('q').value; let r=await fetch(`/api/search?q=${encodeURIComponent(q)}`); let d=await r.json(); let o=e('results'); o.innerHTML=''; d.forEach(p=>{if(!p.feedUrl)return; let div=document.createElement('div'); div.className='card'; div.innerHTML=`<b>${p.collectionName}</b><br><span class='tiny'>${p.artistName}</span><br><button onclick="previewFeed('${p.feedUrl}')">📻 Episodes</button>`; o.appendChild(div); }); }
async function previewFeed(url){ e('results').innerHTML='⏳ Fetching latest episode...'; let r=await fetch('/api/episodes_from_rss',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rss_url:url})}); let d=await r.json(); if(d.length) e('results').innerHTML='✅ Episodes fetched.'; else e('results').innerHTML='❌ No episodes found.'; }
async function showFavs(){ let r=await fetch('/api/favorites'); let d=await r.json(); let o=e('results'); o.innerHTML=''; d.forEach(p=>{let div=document.createElement('div'); div.className='card'; div.innerHTML=`<b>${p['title']}</b><br><span class='tiny'>${p['author']}</span><br><button onclick="previewFeed('${p['rss_url']}')">📻 Episodes</button>`; o.appendChild(div); }); }
</script>
</body></html>
'''

# =============================
# MAIN
# =============================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)