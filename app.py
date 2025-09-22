from flask import Flask, jsonify, render_template_string, request
import sqlite3, os, requests, feedparser
from datetime import datetime

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id=1),
            total INTEGER DEFAULT 0,
            last_added TEXT
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_total (id,total,last_added) VALUES(1,0,NULL)')
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER,
            added_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
init_db()

# ---------------- Swalath APIs ----------------
@app.route('/swalath')
def swalath_page():
    return render_template_string(SWALATH_HTML)

@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total,last_added FROM swalath_total WHERE id=1')
    total,last_added = c.fetchone()
    conn.close()
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number',0)
    try: number=int(number); assert number>0
    except: return jsonify({'error':'Enter positive number'}),400
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO swalath_entries (number,added_at) VALUES (?,?)',(number,now))
    c.execute('UPDATE swalath_total SET total=total+?,last_added=? WHERE id=1',(number,now))
    conn.commit()
    c.execute('SELECT total,last_added FROM swalath_total WHERE id=1')
    total,last_added=c.fetchone()
    conn.close()
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/entries')
def get_swalath_entries():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id,number,added_at FROM swalath_entries ORDER BY id DESC')
    rows=[dict(zip(['id','number','added_at'],r)) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/swalath/delete/<int:eid>',methods=['POST'])
def delete_swalath_entry(eid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT number FROM swalath_entries WHERE id=?',(eid,))
    r=c.fetchone()
    if not r: conn.close(); return jsonify({'error':'Entry not found'}),404
    number=r[0]
    c.execute('DELETE FROM swalath_entries WHERE id=?',(eid,))
    c.execute('UPDATE swalath_total SET total=total-? WHERE id=1',(number,))
    conn.commit(); conn.close()
    return jsonify({'message':'Deleted'})

# ---------------- Podcast APIs ----------------
@app.route('/podcasts')
def podcast_page():
    return render_template_string(PODCAST_HTML)

@app.route('/api/search_podcasts')
def search_podcasts():
    query = request.args.get('query','').strip()
    if not query: return jsonify({'results':[]})
    url="https://itunes.apple.com/search"
    params={'term':query,'media':'podcast','limit':5}
    try:
        r=requests.get(url,params=params,timeout=10)
        data=r.json()
        results=[]
        for p in data.get('results',[]):
            results.append({
                'collectionName':p.get('collectionName'),
                'artistName':p.get('artistName'),
                'feedUrl':p.get('feedUrl'),
                'artworkUrl100':p.get('artworkUrl100')
            })
        return jsonify({'results':results})
    except: return jsonify({'results':[]})

@app.route('/api/podcast_feed')
def podcast_feed():
    feed_url = request.args.get('feedUrl','').strip()
    if not feed_url: return jsonify({'episodes':[]})
    try:
        feed=feedparser.parse(feed_url)
        episodes=[]
        for entry in feed.entries[:10]:
            audio=''
            for enc in entry.get('enclosures',[]):
                if enc.get('href','').startswith('http'): audio=enc['href']; break
            if not audio: continue
            episodes.append({
                'title':entry.get('title',''),
                'description':entry.get('summary','') or entry.get('description',''),
                'audio_url':audio,
                'pub_date':entry.get('published','')
            })
        return jsonify({'episodes':episodes})
    except: return jsonify({'episodes':[]})

# ---------------- Home ----------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Home</title>
<style>
body{
    font-family:sans-serif;
    margin:0;
    padding:0;
    background:#f7f7f7;
    color:#333;
}
.container{
    display:grid;
    grid-template-columns:repeat(auto-fit, minmax(200px,1fr));
    gap:20px;
    max-width:900px;
    margin:50px auto;
    padding:0 20px;
}
.card{
    background:#4CAF50;
    color:white;
    font-size:22px;
    font-weight:bold;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    height:200px;
    border-radius:20px;
    box-shadow:0 4px 10px rgba(0,0,0,0.2);
    cursor:pointer;
    transition:transform 0.2s, box-shadow 0.2s;
    text-align:center;
    padding:10px;
}
.card:hover{
    transform:scale(1.05);
    box-shadow:0 8px 20px rgba(0,0,0,0.3);
}
.card img{
    width:60px;
    height:60px;
    margin-bottom:10px;
}
@media(max-width:500px){
    .container{
        grid-template-columns:1fr;
    }
    .card{
        height:180px;
        font-size:20px;
    }
    .card img{
        width:50px;
        height:50px;
    }
}
</style>
</head>
<body>
<div class="container">
  <div class="card" onclick="location.href='/swalath'">
    <img src="https://img.icons8.com/ios-filled/50/prayer-mat.png"/>
    🙏 Dikr / Swalath
  </div>
  <div class="card" onclick="location.href='/podcasts'">
    <img src="https://img.icons8.com/ios-filled/50/podcast.png"/>
    🎧 Podcasts
  </div>
  <div class="card" onclick="location.href='http://capitalist-anthe-pscj-4a28f285.koyeb.app/'">
    <img src="https://img.icons8.com/ios-filled/50/youtube-live.png"/>
    ▶️ YouTube Live
  </div>
  <div class="card" onclick="location.href='http://zippy-gretta-pscjunction-b779efe8.koyeb.app/'">
    <img src="https://img.icons8.com/ios-filled/50/newspaper.png"/>
    📰 Suprabhatham Newspaper
  </div>
</div>
</body>
</html>
"""

SWALATH_HTML = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swalath</title>
<style>
body{font-family:sans-serif;background:#f7f7f7;margin:0;padding:10px;color:#333}
.card{background:#fff;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);padding:10px;margin-top:10px}
input,button{width:100%;padding:8px;margin:6px 0;border-radius:4px;border:1px solid #ccc;box-sizing:border-box}
button{background:#4CAF50;color:white;border:none;cursor:pointer}
.tiny{font-size:11px;color:#666}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>
<h2>🙏 Swalath</h2>
<div class="card">
  <input type="number" id="swalathNumber" placeholder="Enter number" min="1">
  <button onclick="submitSwalath()">➕ Add</button>
  <p>Total: <span id="swalathTotal">0</span></p>
  <p>Last added: <span id="lastAdded">-</span></p>
</div>
<div id="swalathEntries"></div>
<script>
async function loadSwalathTotal(){
  let r=await fetch('/api/swalath/total'); let d=await r.json();
  document.getElementById('swalathTotal').innerText=d.total;
  document.getElementById('lastAdded').innerText=d.last_added||'-';
  loadEntries();
}
async function submitSwalath(){
  let n=document.getElementById('swalathNumber').value;
  if(!n){Swal.fire({icon:'error',title:'Enter number'});return;}
  let r=await fetch('/api/swalath/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number:n})});
  let d=await r.json();
  if(r.ok){document.getElementById('swalathNumber').value='';loadSwalathTotal();Swal.fire({icon:'success',title:'Added',text:`Total: ${d.total}`,timer:1200,showConfirmButton:false});}
  else Swal.fire({icon:'error',title:'Error',text:d.error});
}
async function loadEntries(){
  let r=await fetch('/api/swalath/entries'); let d=await r.json();
  const c=document.getElementById('swalathEntries'); c.innerHTML='';
  d.forEach(e=>{let div=document.createElement('div');div.className='card';
    div.innerHTML=`${e.number} 🕰 ${e.added_at} <button onclick="deleteEntry(${e.id})">❌</button>`; c.appendChild(div);
  });
}
async function deleteEntry(id){await fetch('/api/swalath/delete/'+id,{method:'POST'}); loadSwalathTotal();}
loadSwalathTotal();
</script>
</body>
</html>
"""

PODCAST_HTML = """
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body{font-family:sans-serif;background:#f7f7f7;margin:0;padding:10px;color:#333}
.card{background:#fff;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);padding:10px;margin-top:10px}
input,button{width:100%;padding:8px;margin:6px 0;border-radius:4px;border:1px solid #ccc;box-sizing:border-box}
button{background:#4CAF50;color:white;border:none;cursor:pointer}
.tiny{font-size:11px;color:#666}
audio{width:100%;margin-top:5px;border-radius:4px}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>
<h2>🎧 Podcasts</h2>
<input type="text" id="searchQuery" placeholder="Search podcasts...">
<button onclick="searchPodcasts()">🔍 Search</button>
<div id="favResults"></div>
<script>
async function searchPodcasts(){
  const q=document.getElementById('searchQuery').value.trim(); if(!q)return;
  const r=await fetch('/api/search_podcasts?query='+encodeURIComponent(q));
  const data=await r.json(); const o=document.getElementById('favResults'); o.innerHTML='';
  data.results.forEach(p=>{let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${p.collectionName}</b><br><span class='tiny'>${p.artistName}</span><br>
      <button onclick="loadEpisodes('${encodeURIComponent(p.feedUrl)}',this)">📥 Load Episodes</button>
      <div class="episodes"></div>`; o.appendChild(div);
  });
}
async function loadEpisodes(feedUrl,btn){
  const container=btn.nextElementSibling; container.innerHTML='⏳ Loading...';
  const r=await fetch('/api/podcast_feed?feedUrl='+feedUrl); const data=await r.json();
  container.innerHTML='';
  data.episodes.forEach(ep=>{let div=document.createElement('div'); div.className='card';
    div.innerHTML=`<b>${ep.title}</b><br><span class='tiny'>${ep.pub_date}</span><br>
      <p>${ep.description}</p>
      <audio controls src="${ep.audio_url}"></audio>
      <a href="${ep.audio_url}" download style="display:block;margin-top:5px">📥 Download</a>`;
    container.appendChild(div);
  });
}
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)