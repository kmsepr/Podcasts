from flask import Flask, jsonify, render_template_string, request
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            total INTEGER DEFAULT 0
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_total (id, total) VALUES (1, 0)')
    conn.commit()
    conn.close()
init_db()

# ---------------- APIs ----------------
@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total FROM swalath_total WHERE id=1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number', 0)
    try:
        number = int(number)
        if number <= 0:
            raise ValueError
    except:
        return jsonify({'error': 'Enter a positive number'}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE swalath_total SET total = total + ? WHERE id=1', (number,))
    conn.commit()
    c.execute('SELECT total FROM swalath_total WHERE id=1')
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcast & Swalath</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:0;padding:0;background:#f7f7f7;color:#333}
.container{max-width:400px;margin:0 auto;padding:10px}
h3{margin-top:20px;color:#444}
.card{background:#fff;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);padding:10px;margin-top:10px}
input,button{width:100%;padding:8px;margin:6px 0;border-radius:4px;border:1px solid #ccc;box-sizing:border-box}
button{background:#4CAF50;color:white;border:none;cursor:pointer;font-size:14px}
button:hover{background:#45a049}
.tiny{font-size:11px;color:#666}
audio{width:100%;margin-top:5px;border-radius:4px}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>

<div class="container">

  <h3>🙏 Add Swalath</h3>
  <div class="card">
    <input type="number" id="swalathNumber" placeholder="Enter number of Swalath" min="1">
    <button onclick="submitSwalath()">➕ Add</button>
    <p>Total Swalath: <span id="swalathTotal">0</span></p>
  </div>

  <h3>⭐ Favorites</h3>
  <div id="favResults"></div>

</div>

<script>
// Load current total
async function loadSwalathTotal(){
  let r = await fetch('/api/swalath/total');
  let d = await r.json();
  document.getElementById('swalathTotal').innerText = d.total;
}

// Submit number and increment total
async function submitSwalath(){
  let number = document.getElementById('swalathNumber').value;
  if(!number){ Swal.fire({icon:'error',title:'Error',text:'Enter a number'}); return; }
  let r = await fetch('/api/swalath/add', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({number})
  });
  let d = await r.json();
  if(r.ok){
    document.getElementById('swalathTotal').innerText = d.total;
    Swal.fire({icon:'success',title:'Added!',text:`Total: ${d.total}`,timer:1200,showConfirmButton:false});
    document.getElementById('swalathNumber').value='';
  } else {
    Swal.fire({icon:'error',title:'Error',text:d.error});
  }
}

// Load favorites automatically
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