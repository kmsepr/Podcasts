from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import feedparser
import requests
import threading

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# 🎯 Hardcoded RSS Feeds
DEFAULT_FEEDS = [
    "https://muslimcentral.com/audio/hamza-yusuf/feed/",
    "https://feeds.megaphone.fm/THGU4956605070",
    "https://feeds.buzzsprout.com/2050847.rss",
    "https://muslimcentral.com/audio/the-deen-show/feed/",
    "https://feeds.buzzsprout.com/1194665.rss",
    "https://www.spreaker.com/show/5085297/episodes/feed"
]

# ---------------- Database Initialization ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Podcasts table
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
    # Episodes table
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
    # Swalath counter
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_counter (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            total INTEGER DEFAULT 0
        )
    ''')
    # Initialize counter if not exists
    c.execute('INSERT OR IGNORE INTO swalath_counter (id, total) VALUES (1, 0)')
    conn.commit()
    conn.close()

init_db()

# ---------------- Swalath APIs ----------------
@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total FROM swalath_counter WHERE id = 1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE swalath_counter SET total = total + 1 WHERE id = 1')
    conn.commit()
    c.execute('SELECT total FROM swalath_counter WHERE id = 1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

# ---------------- Podcast APIs ----------------
@app.route('/api/favorites')
def get_favorites():
    offset = int(request.args.get('offset', 0))
    limit = 5
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for rss_url in DEFAULT_FEEDS:
        try:
            c.execute('SELECT COUNT(*) FROM episodes WHERE podcast_id = ?', (rss_url,))
            if c.fetchone()[0] > 0: continue

            feed = feedparser.parse(rss_url)
            if not feed.entries: continue

            podcast_id = rss_url
            title = feed.feed.get('title', 'Untitled')
            author = feed.feed.get('author', 'Unknown')
            image = (feed.feed.get('image', {}) or {}).get('href', '') or \
                    feed.feed.get('itunes_image', {}).get('href', '')

            c.execute('''
                INSERT OR IGNORE INTO podcasts (podcast_id, title, author, cover_url, rss_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (podcast_id, title, author, image, rss_url))

            latest = feed.entries[0]
            eid = latest.get('id') or latest.get('guid') or latest.get('link') or latest.get('title')
            audio = ''
            for enc in latest.get('enclosures', []):
                if enc.get('href', '').startswith('http'):
                    audio = enc['href']
                    break
            if audio:
                c.execute('''
                    INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    podcast_id,
                    eid,
                    latest.get('title', ''),
                    latest.get('summary', '') or latest.get('description', ''),
                    audio,
                    latest.get('published', ''),
                    latest.get('itunes_duration', '')
                ))
        except Exception as e:
            print("Feed parse error", rss_url, e)
            continue

    conn.commit()
    placeholders = ','.join('?' for _ in DEFAULT_FEEDS)
    c.execute(f'''
        SELECT * FROM podcasts
        WHERE podcast_id IN ({placeholders})
        ORDER BY last_played DESC
        LIMIT ? OFFSET ?
    ''', (*DEFAULT_FEEDS, limit, offset))
    rows = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(rows)

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
        c.execute('''
            INSERT OR IGNORE INTO episodes (podcast_id, episode_id, title, description, audio_url, pub_date, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            pid,
            eid,
            item.get('title', ''),
            item.get('summary', '') or item.get('description', ''),
            audio,
            item.get('published', ''),
            item.get('itunes_duration', '')
        ))
        all_eps.append({
            'episode_id': eid,
            'title': item.get('title', ''),
            'description': item.get('summary', '') or item.get('description', ''),
            'audio_url': audio,
            'pub_date': item.get('published', ''),
            'duration': item.get('itunes_duration', '')
        })

    conn.commit()
    conn.close()
    return jsonify(all_eps[offset:offset + limit])

@app.route('/api/mark_played/<path:pid>', methods=['POST'])
def mark_played(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE podcasts SET last_played = CURRENT_TIMESTAMP WHERE podcast_id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Marked as played'})

# ---------------- Background Refresh ----------------
def refresh_favorites():
    print("[One-time Refresh] Triggering favorite update...")
    try:
        requests.get('http://localhost:3000/api/favorites', timeout=10)
    except Exception as e:
        print("[Refresh Error]:", e)

threading.Timer(5, refresh_favorites).start()

# ---------------- HTML Template ----------------
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=320">
<title>Podcast & Swalath</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:4px}
input,button{width:100%;margin:4px 0}
.card{border:1px solid #ccc;padding:5px;margin-top:6px}
.tiny{font-size:11px;color:#666}
audio{width:100%; margin-top:5px}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>
<h3>🎧 Podcast & 🙏 Swalath</h3>

<!-- Swalath Counter -->
<div class="card">
  <b>🙏 Swalath Counter</b><br>
  <span id="swalathTotal">Total: 0</span><br>
  <button onclick="addSwalath()">➕ Add Swalath</button>
</div>

<!-- Podcast Section -->
<button onclick="showFavs()">⭐ My Favorites</button>
<div id="results"></div>
<div id="playerBox" style="display:none">
  <div class="card">
    <b id="epTitle"></b><br><span class="tiny" id="epDate"></span><br>
    <audio id="player" controls></audio><br>
    <p id="epDesc" style="margin-top:6px;white-space:pre-wrap"></p>
    <a id="downloadBtn" href="#" download style="display:inline-block;margin:5px 0">📥 Download MP3</a><br>
    <button onclick="prevEp()">⏮️</button>
    <button onclick="togglePlay()">⏯️</button>
    <button onclick="nextEp()">⏭️</button>
  </div>
</div>

<script>
const B = location.origin;
function e(id){return document.getElementById(id);}

// Swalath counter
async function loadSwalathTotal(){
  let r = await fetch('/api/swalath/total');
  let d = await r.json();
  e('swalathTotal').innerText = `Total: ${d.total}`;
}

async function addSwalath(){
  let r = await fetch('/api/swalath/add', { method: 'POST' });
  let d = await r.json();
  e('swalathTotal').innerText = `Total: ${d.total}`;
  Swal.fire({icon:'success',title:'✅ Added!',text:`Total Swalath: ${d.total}`,timer:1500,showConfirmButton:false});
}

// Podcast key controls
let keyDownTime = {};
document.addEventListener('keydown', ev => { keyDownTime[ev.key] = Date.now(); });
document.addEventListener('keyup', ev => {
  const k = ev.key; const heldTime = Date.now() - (keyDownTime[k]||0);
  if(k==='1') showFavs();
  else if(k==='2') prevEp();
  else if(k==='8') nextEp();
  else if(k==='4') seek(heldTime>600?-60:-15);
  else if(k==='6') seek(heldTime>600?60:30);
  else if(k==='5') togglePlay();
  delete keyDownTime[k];
});

let favOffset=0;
async function showFavs(){ favOffset=0; loadFavPage(true); }
async function loadFavPage(reset){
  let r = await fetch(`/api/favorites?offset=${favOffset}`);
  let d = await r.json();
  let o = e('results'); if(reset) o.innerHTML='';
  d.forEach(p=>{
    let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${p.title}</b><br><span class='tiny'>${p.author}</span><br>
    <button onclick="loadEp('${p.podcast_id}')">📻 Latest Episode</button>`;
    o.appendChild(div);
  });
  if(d.length===5){let btn=document.createElement('button'); btn.innerText='⏬ More'; btn.onclick=()=>{favOffset+=5;loadFavPage(false);}; o.appendChild(btn);}
}

let currentId='',currentList=[],currentIndex=0;
async function loadEp(id){
  currentId=id; currentIndex=0; e('results').innerHTML='⏳ Loading latest...';
  await fetch(`/api/mark_played/${encodeURIComponent(id)}`,{method:'POST'});
  let r = await fetch(`/api/podcast/${encodeURIComponent(id)}/episodes?offset=0`);
  let d = await r.json();
  if(d.length) showPlayer(d,true); else e('results').innerHTML='❌ No episodes found.';
}

function showPlayer(data,reset){
  currentList=data; currentIndex=0;
  showEpisode(currentList[currentIndex]);
  e('playerBox').style.display='block';
  e('results').innerHTML='';
}

function showEpisode(ep){
  e('epTitle').innerText=ep.title;
  e('epDate').innerText=ep.pub_date;
  let dur = ep.duration?`⏱ Duration: ${ep.duration}\n\n`:'';
  e('epDesc').innerText=dur+(ep.description||'');
  e('player').src=ep.audio_url;
  e('downloadBtn').href=ep.audio_url;
  e('player').play();
}

function prevEp(){ if(currentIndex>0){currentIndex--;showEpisode(currentList[currentIndex]);} }
function nextEp(){ if(currentIndex<currentList.length-1){currentIndex++;showEpisode(currentList[currentIndex]);} }
function togglePlay(){ let p=e('player'); if(p.paused)p.play(); else p.pause(); }
function seek(s){ let p=e('player'); p.currentTime=Math.max(0,p.currentTime+s); }

// Load Swalath total on page load
loadSwalathTotal();
</script>
</body></html>
'''

@app.route('/')
def homepage():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)