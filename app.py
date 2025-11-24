from flask import Flask, request, jsonify, render_template_string, send_file
import sqlite3, os, requests, feedparser, time, subprocess, uuid, hashlib

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    rss TEXT UNIQUE,
                    cover TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# ---------------- CACHE FOLDER ----------------
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def hash_url(url):
    return hashlib.md5(url.encode()).hexdigest()

# ---------------- HTML Template ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Podcast App</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body { font-family: sans-serif; background:#111; color:#eee; margin:0; text-align:center; }
h1 { font-size:20px; margin:5px 0; }
input[type=text] { width:90%; padding:6px; font-size:14px; margin-bottom:5px; }
button { padding:8px; margin:3px; font-size:14px; border:none; border-radius:6px; background:#28a; color:#fff; }
.podcast-card { background:#222; margin:4px; padding:6px; border-radius:6px; display:flex; align-items:center; flex-wrap:wrap; }
.podcast-card img { width:60px; height:60px; border-radius:8px; margin-right:6px; }
.podcast-title { font-size:16px; margin:4px 0; flex:1; text-align:left; word-break:break-word; }
.mini-player { position:fixed; bottom:0; left:0; right:0; background:#333; padding:6px; display:none; display:flex; align-items:center; height:50px; box-sizing:border-box; }
.mini-player img { width:40px; height:40px; border-radius:6px; margin-right:6px; }
.scroll-desc { white-space:nowrap; overflow:hidden; width:70%; }
.scroll-desc span { display:inline-block; padding-left:100%; animation: scroll 15s linear infinite; }
@keyframes scroll { 0%{transform:translateX(0);} 100%{transform:translateX(-100%);} }
.full-player { position:fixed; top:0; left:0; right:0; bottom:0; background:#000; color:#fff;
               display:none; flex-direction:column; align-items:center; padding:10px; }
.full-player img { width:40vw; max-width:220px; border-radius:10px; margin-top:5px; }
.controls { margin-top:8px; display:flex; flex-wrap:wrap; justify-content:center; }
.controls button { font-size:16px; padding:8px; margin:4px; }
.big-text { font-size:18px; margin-top:8px; text-align:center; }
.desc-text { margin-top:6px; font-size:14px; max-width:95%; overflow-y:auto; flex:1; }
#player { display:none; }
</style>
</head>
<body>
<h1>🎧 Podcast App</h1>

<!-- Search Form -->
<form onsubmit="searchPodcast(); return false;">
  <input type="text" id="query" placeholder="Search podcasts...">
  <button type="submit">Search</button>
</form>

<h2>⭐ Favorites</h2>
<div id="favorites"></div>

<h2>🔎 Results</h2>
<div id="results"></div>

<div class="mini-player" id="miniPlayer">
  <img id="miniCover" src="">
  <div class="scroll-desc"><span id="miniTitle"></span></div>
</div>

<div class="full-player" id="fullPlayer">
  <img id="fullCover" src="">
  <div class="big-text" id="fullTitle"></div>
  <div class="desc-text" id="fullDesc"></div>
  <div class="controls">
    <button onclick="prevEpisode()">⏮</button>
    <button onclick="seek(-30)">⏪ 30s</button>
    <button onclick="togglePlay()">⏯</button>
    <button onclick="seek(30)">⏩ 30s</button>
    <button onclick="nextEpisode()">⏭</button>
  </div>
</div>

<audio id="player" controls></audio>

<script>
let current = null;
let keyDownTime = {};

function searchPodcast(){
  let q=document.getElementById('query').value;
  fetch('/api/search?q='+encodeURIComponent(q))
   .then(r=>r.json()).then(data=>{
     let out="";
     if(data.length===0){ out="<p>No results or API limit reached</p>"; }
     data.forEach(p=>{
       out+=`<div class="podcast-card">
         <img src="${p.cover}">
         <div class="podcast-title">${p.title}</div>
         <button onclick='addFavorite(${JSON.stringify(p)})'>Add</button>
       </div>`;
     });
     document.getElementById('results').innerHTML=out;
   });
}

function loadFavorites(){
  fetch('/api/favorites').then(r=>r.json()).then(data=>{
    let out="";
    data.forEach(p=>{
      out+=`<div class="podcast-card">
        <img src="${p.cover}">
        <div class="podcast-title">${p.title}</div>
        <button onclick='playPodcast("${p.rss}","${p.title}","${p.cover}")'>Play</button>
      </div>`;
    });
    document.getElementById('favorites').innerHTML=out;
  });
}

function addFavorite(p){
  fetch('/api/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p)})
  .then(()=>loadFavorites());
}

function playPodcast(rss,title,cover){
  fetch('/api/episodes?rss='+encodeURIComponent(rss))
   .then(r=>r.json()).then(eps=>{
     if(eps.length==0){alert("No episodes");return;}
     current={list:eps, idx:0, title:title, cover:cover};
     startEpisode();
   });
}

function startEpisode(){
  let ep=current.list[current.idx];
  let player=document.getElementById('player');

  player.src="/api/transcoded?url=" + encodeURIComponent(ep.audio);
  player.play();

  document.getElementById('miniPlayer').style.display='flex';
  document.getElementById('miniTitle').innerText=ep.title;
  document.getElementById('miniCover').src = ep.cover || current.cover;

  document.getElementById('fullCover').src = ep.cover || current.cover;
  document.getElementById('fullTitle').innerText=current.title;
  document.getElementById('fullDesc').innerHTML=ep.desc;
}

function toggleFullPlayer(){
  let full = document.getElementById('fullPlayer');
  let mini = document.getElementById('miniPlayer');
  if(full.style.display === 'flex'){
    full.style.display = 'none';
    mini.style.display = 'flex';
  } else {
    full.style.display = 'flex';
    mini.style.display = 'none';
  }
}

function togglePlay(){
  let p=document.getElementById('player');
  if(p.paused) p.play(); else p.pause();
}
function nextEpisode(){ if(current && current.idx<current.list.length-1){current.idx++; startEpisode();} }
function prevEpisode(){ if(current && current.idx>0){current.idx--; startEpisode();} }
function seek(seconds){ let p=document.getElementById('player'); p.currentTime += seconds; }

document.addEventListener('keydown',function(e){
  if(!keyDownTime[e.key]) keyDownTime[e.key]=Date.now();
});
document.addEventListener('keyup',function(e){
  let duration=Date.now()- (keyDownTime[e.key]||0);
  delete keyDownTime[e.key];
  switch(e.key){
    case "5": togglePlay(); break;
    case "4": duration>500 ? seek(-30) : prevEpisode(); break;
    case "6": duration>500 ? seek(30) : nextEpisode(); break;
    case "0": toggleFullPlayer(); break;
  }
});

loadFavorites();
</script>
</body>
</html>
"""

# ---------------- Flask Routes ----------------
@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/search")
def search():
    q=request.args.get("q","")
    try:
        url=f"https://itunes.apple.com/search?media=podcast&term={q}"
        r=requests.get(url, timeout=5)
        results=[]
        for item in r.json().get("results",[]):
            results.append({
                "title": item.get("collectionName"),
                "rss": item.get("feedUrl"),
                "cover": item.get("artworkUrl600")
            })
        return jsonify(results)
    except:
        return jsonify([])

@app.route("/api/add",methods=["POST"])
def add():
    data=request.json
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO podcasts(title,rss,cover) VALUES(?,?,?)",
                  (data["title"],data["rss"],data["cover"]))
        conn.commit()
    finally:
        conn.close()
    return "ok"

@app.route("/api/favorites")
def favorites():
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("SELECT title,rss,cover FROM podcasts")
    rows=[{"title":t,"rss":r,"cover":c} for t,r,c in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/episodes")
def episodes():
    rss=request.args.get("rss")
    feed=feedparser.parse(rss)
    eps=[]
    for e in feed.entries[:20]:
        audio=None
        for link in e.get("links",[]):
            if link.get("type","").startswith("audio"):
                audio=link["href"]

        cover=None
        if "image" in e: 
            cover=e.image.get("href")
        elif "itunes_image" in e:
            cover=e.itunes_image
        elif "media_thumbnail" in e:
            cover=e.media_thumbnail[0]['url']

        if audio:
            eps.append({
                "title": e.get("title"),
                "audio": audio,
                "desc": e.get("description",""),
                "cover": cover
            })
    return jsonify(eps)

# -------------- 24 Kbps Ultra Low-Bandwidth Transcoding --------------
@app.route("/api/transcoded")
def transcoded():
    url = request.args.get("url")
    if not url:
        return "missing url", 400

    key = hash_url(url)
    cached_file = os.path.join(CACHE_DIR, key + ".mp3")

    # return cached if exists
    if os.path.exists(cached_file):
        return send_file(cached_file, mimetype="audio/mpeg")

    temp_original = os.path.join(CACHE_DIR, key + ".orig")

    # ---- Download original audio ----
    try:
        with requests.get(url, stream=True, timeout=20) as r:
            r.raise_for_status()
            with open(temp_original, "wb") as f:
                for chunk in r.iter_content(1024 * 64):
                    f.write(chunk)
    except:
        return "download error", 500

    # ---- Transcode to 24kbps mono ----
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_original,
            "-ac", "1",
            "-b:a", "24k",
            "-map", "a",
            cached_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        return "ffmpeg error", 500

    return send_file(cached_file, mimetype="audio/mpeg")


# ---------------- Run ----------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
