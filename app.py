from flask import Flask, jsonify, render_template_string
import sqlite3
import os
import feedparser

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# Hardcoded podcast RSS feeds
DEFAULT_FEEDS = [
    "https://muslimcentral.com/audio/hamza-yusuf/feed/",
    "https://feeds.megaphone.fm/THGU4956605070",
    "https://feeds.buzzsprout.com/2050847.rss",
    "https://muslimcentral.com/audio/the-deen-show/feed/",
    "https://feeds.buzzsprout.com/1194665.rss",
    "https://www.spreaker.com/show/5085297/episodes/feed"
]

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Swalath counter
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_counter (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            total INTEGER DEFAULT 0
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_counter (id, total) VALUES (1, 0)')
    conn.commit()
    conn.close()
init_db()

# ---------------- APIs ----------------
@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total FROM swalath_counter WHERE id=1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE swalath_counter SET total = total + 1 WHERE id=1')
    conn.commit()
    c.execute('SELECT total FROM swalath_counter WHERE id=1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/favorites')
def get_favorites():
    results = []
    for rss in DEFAULT_FEEDS:
        feed = feedparser.parse(rss)
        if not feed.entries: continue
        latest = feed.entries[0]
        audio_url = ''
        for enc in latest.get('enclosures', []):
            if enc.get('href', '').startswith('http'):
                audio_url = enc['href']
                break
        results.append({
            'title': feed.feed.get('title', 'Untitled'),
            'author': feed.feed.get('author', 'Unknown'),
            'episode_title': latest.get('title', ''),
            'pub_date': latest.get('published', ''),
            'audio_url': audio_url
        })
    return jsonify(results)

# ---------------- HTML ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=320">
<title>Podcast & Swalath</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:4px}
button{width:100%;margin:4px 0}
.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666}
audio{width:100%; margin-top:5px}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>

<h3>📿 Swalath</h3>
<div class="card">
  <b>Swalath Counter</b><br>
  <span id="swalathTotal">Total: 0</span><br>
  <button onclick="addSwalath()">➕ Add Swalath</button>
</div>

<h3>⭐ Favorites</h3>
<div id="favResults"></div>

<script>
async function loadSwalathTotal(){
  let r = await fetch('/api/swalath/total');
  let d = await r.json();
  document.getElementById('swalathTotal').innerText = `Total: ${d.total}`;
}

async function addSwalath(){
  let r = await fetch('/api/swalath/add', {method:'POST'});
  let d = await r.json();
  document.getElementById('swalathTotal').innerText = `Total: ${d.total}`;
  Swal.fire({icon:'success',title:'✅ Added!',text:`Total Swalath: ${d.total}`,timer:1500,showConfirmButton:false});
}

async function loadFavorites(){
  let r = await fetch('/api/favorites');
  let d = await r.json();
  let o = document.getElementById('favResults');
  o.innerHTML = '';
  d.forEach(f => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${f.title}</b> - ${f.author}<br>
                     <span class='tiny'>${f.episode_title} (${f.pub_date})</span><br>
                     <audio controls src="${f.audio_url}"></audio>`;
    o.appendChild(div);
  });
}

// On page load
loadSwalathTotal();
loadFavorites();
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)