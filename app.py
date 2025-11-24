from flask import Flask, request, jsonify, render_template_string, send_file
import sqlite3, os, requests, feedparser, subprocess, uuid

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
.scroll-desc { white-space:nowrap; overflow:hidden; }
.scroll-desc span { display:inline-block; padding-left:100%; animation: scroll 15s linear infinite; }
@keyframes scroll { 0%{transform:translateX(0);} 100%{transform:translateX(-100%);} }
.full-player { position:fixed; top:0; left:0; right:0; bottom:0; background:#000; color:#fff;
               display:none; flex-direction:column; align-items:center; padding:10px; box-sizing:border-box; }
.full-player img { width:40vw; height:40vw; max-width:220px; border-radius:10px; margin-top:5px; }
.controls { margin-top:8px; display:flex; flex-wrap:wrap; justify-content:center; }
.controls button { font-size:16px; padding:8px; margin:4px; }
#player { display:none; }
</style>
</head>
<body>
<h1>🎧 Podcast App</h1>

<form onsubmit="searchPodcast(); return false;">
  <input type="text" id="query" placeholder="Search podcasts...">
  <button type="submit">Search</button>
</form>

<h2>⭐ Favorites</h2>
<div id="favorites"></div>

<h2>🔎 Results</h2>
<div id="results"></div>

<div class="mini-player" id="miniPlayer" onclick="toggleFullPlayer()">
  <img id="miniCover" src="">
  <div class="scroll-desc"><span id="miniTitle"></span></div>
</div>

<div class="full-player" id="fullPlayer">
  <img id="fullCover" src="">
  <div id="fullTitle" style="font-size:18px; margin-top:8px;"></div>
  <div id="fullDesc" style="font-size:14px; margin-top:6px; max-width:95%;"></div>
  <div class="controls">
    <button onclick="prevEpisode()">⏮</button>
    <button onclick="seek(-30)">⏪ 30s</button>
    <button onclick="togglePlay()">⏯</button>
    <button onclick="seek(30)">⏩ 30s</button>
    <button onclick="nextEpisode()">⏭</button>
  </div>
</div>

<audio id="player"></audio>

<script>
let current = null;

function searchPodcast(){
  let q=document.getElementById('query').value;
  fetch('/api/search?q='+encodeURIComponent(q))
   .then(r=>r.json()).then(data=>{
     let out="";
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
  document.getElementById('fullDesc').innerText=ep.desc;
}

function toggleFullPlayer(){
  let f=document.getElementById('fullPlayer');
  let m=document.getElementById('miniPlayer');
  if(f.style.display==='flex'){ f.style.display='none'; m.style.display='flex'; }
  else { m.style.display='none'; f.style.display='flex'; }
}

function togglePlay(){
  let p=document.getElementById('player');
  if(p.paused) p.play(); else p.pause();
}

function nextEpisode(){ if(current.idx<current.list.length-1){current.idx++; startEpisode();} }
function prevEpisode(){ if(current.idx>0){current.idx--; startEpisode();} }
function seek(s){ document.getElementById('player').currentTime += s; }

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
        r=requests.get(f"https://itunes.apple.com/search?media=podcast&term={q}", timeout=5)
        out=[]
        for x in r.json().get("results",[]):
            out.append({
                "title": x.get("collectionName"),
                "rss": x.get("feedUrl"),
                "cover": x.get("artworkUrl600")
            })
        return jsonify(out)
    except:
        return jsonify([])

@app.route("/api/add",methods=["POST"])
def add():
    data=request.json
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO podcasts(title,rss,cover) VALUES (?,?,?)",
              (data["title"],data["rss"],data["cover"]))
    conn.commit()
    conn.close()
    return jsonify({"ok":True})

@app.route("/api/favorites")
def favorites():
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("SELECT title,rss,cover FROM podcasts")
    data=[{"title":t,"rss":r,"cover":cvr} for t,r,cvr in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route("/api/episodes")
def episodes():
    rss=request.args.get("rss")
    feed=feedparser.parse(rss)
    eps=[]
    for e in feed.entries:
        audio=""
        if "enclosures" in e and len(e.enclosures)>0:
            audio=e.enclosures[0].get("url","")
        eps.append({
            "title":e.get("title",""),
            "audio":audio,
            "cover":feed.feed.get("image",{}).get("href",""),
            "desc":e.get("summary","")
        })
    return jsonify(eps)

@app.route("/api/transcoded")
def transcoded():
    url=request.args.get("url","")
    tmp=f"/tmp/{uuid.uuid4()}.mp3"
    try:
        subprocess.run([
            "ffmpeg","-y","-i",url,
            "-b:a","24k",
            "-bufsize","24k",
            "-ac","1",
            "-ar","24000",
            tmp
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        return send_file(tmp, mimetype="audio/mpeg")
    except:
        return jsonify({"error":"ffmpeg failed"})

# ---------------- Run on port 3000 ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
