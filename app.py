from flask import Flask, request, jsonify, render_template_string
import sqlite3, os, requests, feedparser

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
  h1 { font-size:22px; margin:10px 0; }
  input[type=text] { width:70%; padding:8px; font-size:16px; }
  button { padding:10px; margin:5px; font-size:16px; border:none; border-radius:6px; background:#28a; color:#fff; }
  .podcast-card { background:#222; margin:8px; padding:10px; border-radius:8px; }
  .podcast-card img { width:80px; height:80px; border-radius:10px; }
  .podcast-title { font-size:18px; margin:6px 0; }
  .mini-player { position:fixed; bottom:0; left:0; right:0; background:#333; padding:10px; display:none; }
  .scroll-desc { white-space:nowrap; overflow:hidden; box-sizing:border-box; }
  .scroll-desc span { display:inline-block; padding-left:100%; animation: scroll 15s linear infinite; }
  @keyframes scroll { 0%{transform:translateX(0);} 100%{transform:translateX(-100%);} }
  .full-player { position:fixed; top:0; left:0; right:0; bottom:0; background:#000; color:#fff;
                 display:none; flex-direction:column; align-items:center; justify-content:center; }
  .full-player img { width:220px; height:220px; border-radius:12px; }
  .controls { margin-top:15px; }
  .controls button { font-size:20px; padding:12px; margin:6px; }
  .big-text { font-size:20px; }
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

<div class="mini-player" id="miniPlayer">
  <div><b id="miniTitle"></b></div>
  <div class="scroll-desc"><span id="miniDesc"></span></div>
  <button onclick="toggleFullPlayer()">Open</button>
  <button onclick="closeMini()">Close</button>
</div>

<div class="full-player" id="fullPlayer">
  <img id="fullCover" src="">
  <div class="big-text" id="fullTitle"></div>
  <div class="scroll-desc"><span id="fullDesc"></span></div>
  <div class="controls">
    <button onclick="prevEpisode()">⏮</button>
    <button onclick="togglePlay()">⏯</button>
    <button onclick="nextEpisode()">⏭</button>
    <button onclick="closeFull()">❌</button>
  </div>
</div>

<audio id="player" controls style="display:none"></audio>

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
     if(eps.length==0){alert("No episodes");return;}
     current={list:eps, idx:0, title:title, cover:cover};
     startEpisode();
   });
}

function startEpisode(){
  let ep=current.list[current.idx];
  document.getElementById('player').src=ep.audio;
  document.getElementById('player').play();
  document.getElementById('miniPlayer').style.display='block';
  document.getElementById('miniTitle').innerText=current.title;
  document.getElementById('miniDesc').innerText=ep.desc || "";
  document.getElementById('fullCover').src=current.cover;
  document.getElementById('fullTitle').innerText=current.title;
  document.getElementById('fullDesc').innerText=ep.desc || "";
}

function toggleFullPlayer(){
  document.getElementById('fullPlayer').style.display='flex';
}
function closeFull(){
  document.getElementById('fullPlayer').style.display='none';
}
function closeMini(){
  document.getElementById('miniPlayer').style.display='none';
  document.getElementById('player').pause();
}
function togglePlay(){
  let p=document.getElementById('player');
  if(p.paused) p.play(); else p.pause();
}
function nextEpisode(){
  if(current && current.idx<current.list.length-1){current.idx++; startEpisode();}
}
function prevEpisode(){
  if(current && current.idx>0){current.idx--; startEpisode();}
}

// keypad controls
document.addEventListener('keydown',function(e){
  switch(e.key){
    case "5": togglePlay(); break;
    case "2": prevEpisode(); break;
    case "8": nextEpisode(); break;
    case "0": closeMini(); closeFull(); break;
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
    url=f"https://itunes.apple.com/search?media=podcast&term={q}"
    r=requests.get(url)
    results=[]
    for item in r.json().get("results",[]):
        results.append({
            "title": item.get("collectionName"),
            "rss": item.get("feedUrl"),
            "cover": item.get("artworkUrl600")
        })
    return jsonify(results)

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
    for e in feed.entries[:10]:
        audio=None
        for link in e.get("links",[]):
            if link.get("type","").startswith("audio"):
                audio=link["href"]
        if audio:
            eps.append({"title":e.get("title"),"audio":audio,"desc":e.get("description","")})
    return jsonify(eps)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)