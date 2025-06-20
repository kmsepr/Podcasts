import os
import sqlite3
import requests
import feedparser
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ─── DB INIT ─────────────────────────────
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
            rss_url TEXT
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
            pub_timestamp INTEGER,
            duration INTEGER,
            FOREIGN KEY(podcast_id) REFERENCES podcasts(podcast_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── Add Podcast by RSS ────────────────
@app.route('/api/add_by_rss', methods=['POST'])
def add_by_rss():
    data = request.get_json()
    rss_url = data.get('rss_url')
    if not rss_url:
        return jsonify({'error': 'Missing rss_url'}), 400

    feed = feedparser.parse(rss_url)
    if not feed.entries:
        return jsonify({'error': 'Invalid RSS'}), 400

    podcast_id = rss_url
    title = feed.feed.get('title', 'Untitled')
    author = feed.feed.get('author', 'Unknown')
    image = feed.feed.get('image', {}).get('href', '')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
        VALUES (?, ?, ?, ?, ?)
    ''', (podcast_id, title, author, image, rss_url))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Added from RSS', 'title': title})

# ─── List Favorite Podcasts ─────────────
@app.route('/api/favorites')
def get_favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM podcasts')
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ─── Get Episodes for Podcast ───────────
@app.route('/api/podcast/<path:pid>/episodes')
def get_episodes(pid):
    offset = int(request.args.get('offset', 0))
    limit = 5

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM episodes WHERE podcast_id = ? ORDER BY pub_timestamp DESC LIMIT ? OFFSET ?', (pid, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    if rows:
        conn.close()
        return jsonify(rows)

    # Not found in cache, fetch from RSS
    c.execute('SELECT rss_url, cover_url FROM podcasts WHERE podcast_id = ?', (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Podcast not found'}), 404

    feed = feedparser.parse(row[0])
    cover_url = row[1]
    entries = sorted(feed.entries, key=lambda e: e.get('published_parsed', time.gmtime(0)), reverse=True)
    all_eps = []
    for item in entries:
        eid = item.get('id') or item.get('guid') or item.get('link') or item.get('title')
        audio = ''
        for enc in item.get('enclosures', []):
            if enc['href'].startswith('http'):
                audio = enc['href']
                break
        if not audio:
            continue

        title = item.get('title', '')
        desc = item.get('summary', '') or item.get('description', '')
        pub_date = item.get('published', '')
        pub_parsed = item.get('published_parsed')
        pub_ts = int(time.mktime(pub_parsed)) if pub_parsed else 0

        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, pub_timestamp, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pid, eid, title, desc, audio, pub_date, pub_ts, 0))

        all_eps.append({
            'episode_id': eid,
            'title': title,
            'description': desc,
            'audio_url': audio,
            'pub_date': pub_date,
            'cover': cover_url,
            'duration': 0
        })

    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

# ─── Delete Podcast ─────────────────────
@app.route('/api/delete_podcast/<path:pid>', methods=['DELETE'])
def delete_podcast(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM episodes WHERE podcast_id = ?', (pid,))
    c.execute('DELETE FROM podcasts WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})

# ─── Search iTunes Podcasts ─────────────
@app.route('/api/search_podcasts')
def search_podcasts():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    r = requests.get("https://itunes.apple.com/search", params={"term": q, "media": "podcast"})
    data = r.json()
    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("collectionName"),
            "author": item.get("artistName"),
            "cover": item.get("artworkUrl100"),
            "rss": item.get("feedUrl")
        })
    return jsonify(results)

# ─── Frontend ───────────────────────────
@app.route('/')
def homepage():
    return '''
<!DOCTYPE html><html><head><meta name="viewport" content="width=320"><title>🎧 Podcast</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}
.card{border:1px solid #ccc;padding:6px;margin-top:8px;border-radius:8px;background:#fafafa}
.tiny{font-size:11px;color:#555}
#sidebar {
  position: fixed; top: 0; left: 0; width: 80%; height: 100%; background: #eee; z-index: 9; padding: 10px;
  transform: translateX(-100%); transition: transform .3s ease; overflow-y: auto;
}
#sidebar.open { transform: translateX(0); }
#toggle {
  position: fixed; top: 10px; left: 10px; font-size: 20px; z-index: 10; background: #ddd;
  padding: 2px 6px; border-radius: 4px; cursor: pointer;
}
</style></head><body>
<div id="toggle" onclick="toggleSidebar()">☰</div>
<div id="sidebar"><b>⭐ Favorites</b><div id="favList"></div></div>
<h3>🎧 Podcast Player</h3>
<input id="rss" placeholder="Paste RSS feed"><button onclick="addRss()">➕ Add RSS</button>
<h4>🔍 Search (iTunes)</h4>
<input id="searchInput" placeholder="Search podcasts"><button onclick="searchPodcasts()">🔍 Search</button>
<div id="results"></div>
<script>
const B = location.origin;
let epOffset = 0, currentId = '', state = 'home';
function e(id){ return document.getElementById(id); }
function toggleSidebar(){ e("sidebar").classList.toggle("open"); }
document.addEventListener("keydown", e => { if (e.key === "1") toggleSidebar(); });
async function addRss() {
  let url = e('rss').value.trim();
  if (!url) return alert("Paste a URL");
  await fetch('/api/add_by_rss', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({rss_url:url}) });
  alert('Added!'); loadFavs();
}
async function addRssFromSearch(rss) {
  await fetch('/api/add_by_rss', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({rss_url:rss}) });
  alert("Added to favorites!"); loadFavs();
}
async function searchPodcasts() {
  const q = e('searchInput').value.trim();
  if (!q) return;
  let r = await fetch('/api/search_podcasts?q=' + encodeURIComponent(q));
  let d = await r.json();
  let o = e('results'); o.innerHTML = '';
  d.forEach(p => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${p.title}</b><br><span class="tiny">${p.author || ''}</span><br>
    <img src="${p.cover || ''}" width="100"><br>
    <button onclick="addRssFromSearch('${p.rss}')">❤️ Add</button>`;
    o.appendChild(div);
  });
}
async function loadFavs() {
  let r = await fetch('/api/favorites');
  let d = await r.json();
  let fl = e('favList'); fl.innerHTML = '';
  d.forEach(p => {
    let div = document.createElement('div');
    div.innerHTML = `<b>${p.title}</b><br><span class="tiny">${p.author}</span><br>
      <button onclick="loadEp('${p.podcast_id}', '${p.cover_url}')">🎧 Episodes</button>
      <button onclick="deleteFeed('${p.podcast_id}')">🗑</button><hr>`;
    fl.appendChild(div);
  });
}
loadFavs();
async function deleteFeed(id) {
  if (!confirm('Are you sure?')) return;
  await fetch('/api/delete_podcast/' + encodeURIComponent(id), { method: 'DELETE' });
  loadFavs();
}
async function loadEp(id, cover) {
  currentId = id; epOffset = 0;
  e('results').innerHTML = '⏳ Loading...';
  let r = await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes?offset=0`);
  let d = await r.json();
  d.forEach(ep => ep.cover = cover);
  showEpisodes(d, true);
}
async function loadMore() {
  epOffset += 5;
  let r = await fetch(`/api/podcast/${encodeURIComponent(currentId)}/episodes?offset=${epOffset}`);
  let d = await r.json();
  showEpisodes(d, false);
}
function showEpisodes(data, reset) {
  let o = e('results'); if (reset) o.innerHTML = '';
  data.forEach(ep => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${ep.title}</b><br>
      <span class="tiny">${ep.pub_date}</span><br>
      <img src="${ep.cover || ''}" width="100"><br>
      <p>${ep.description || ''}</p>
      <a href="${ep.audio_url}" target="_blank">▶ Play</a>`;
    o.appendChild(div);
  });
  if (data.length === 5) {
    let b = document.createElement('button');
    b.innerText = '⬇️ Load More';
    b.onclick = loadMore;
    o.appendChild(b);
  }
}
</script></body></html>
'''

# ─── Start the App ──────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)