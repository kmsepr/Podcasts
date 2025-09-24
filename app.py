from flask import Flask, jsonify, render_template_string, request, redirect
import sqlite3, os, requests, feedparser

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rss TEXT UNIQUE,
                  title TEXT,
                  cover TEXT,
                  last_played TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML Template ----------------
HOME_HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: sans-serif; margin:0; padding:0; background:#f4f4f4; }
    h2 { margin:10px; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; padding:10px; }
    .card { background:white; padding:10px; border-radius:12px; text-align:center; cursor:pointer; }
    .card img { width:100%; border-radius:12px; max-height:120px; object-fit:cover; }
    .mini-player {
        position:fixed; bottom:0; left:0; right:0;
        background:#222; color:white; display:flex;
        align-items:center; padding:5px 10px;
    }
    .mini-cover { width:40px; height:40px; margin-right:10px; border-radius:8px; object-fit:cover; }
    .ticker { flex:1; white-space:nowrap; overflow:hidden; }
    .ticker span { display:inline-block; padding-left:100%; animation:scroll 12s linear infinite; }
    @keyframes scroll { from {transform:translateX(0);} to {transform:translateX(-100%);} }
    .mini-controls button { background:none; border:none; color:white; font-size:20px; margin-left:10px; cursor:pointer; }
    .full-player {
        position:fixed; top:0; left:0; right:0; bottom:0; background:#111; color:white;
        display:flex; flex-direction:column; align-items:center; justify-content:center;
        padding:20px; z-index:1000; display:none;
    }
    .full-player img { max-width:80%; max-height:40%; border-radius:12px; margin-bottom:20px; }
    .full-player h2, .full-player p { text-align:center; }
    .full-controls button {
        background:#444; border:none; color:white; padding:10px 20px;
        margin:10px; border-radius:8px; font-size:18px;
    }
  </style>
</head>
<body>
  <h2>Podcasts</h2>
  <form method="get" action="/search" style="padding:10px;">
    <input name="q" placeholder="Search podcasts" style="width:70%">
    <button type="submit">Search</button>
  </form>

  <div class="grid">
    {% for p in podcasts %}
      <div class="card" onclick="loadPodcast('{{p[0]}}')" data-key="{{loop.index}}">
        <img src="{{p[2]}}">
        <div>{{p[1]}}</div>
      </div>
    {% endfor %}
  </div>

  <!-- Mini Player -->
  <div id="miniPlayer" class="mini-player" style="display:none;" onclick="openFullPlayer()">
    <img id="miniCover" class="mini-cover">
    <div class="ticker"><span id="miniTitle"></span></div>
    <div class="mini-controls">
      <button onclick="togglePlay(event)">⏯</button>
      <button onclick="closeMini(event)">✖</button>
    </div>
  </div>

  <!-- Full Player -->
  <div id="fullPlayer" class="full-player">
    <img id="fullCover">
    <h2 id="fullTitle"></h2>
    <p id="fullDesc"></p>
    <div class="full-controls">
      <button onclick="togglePlay(event)">⏯ Play/Pause</button>
      <button onclick="closeFull(event)">Close</button>
    </div>
  </div>

<script>
let audio = new Audio();
let current = null;

function loadPodcast(pid){
  fetch(`/api/podcast/${pid}/episodes`)
   .then(r=>r.json()).then(data=>{
     if(data.length > 0){
       let ep = data[0];
       playEpisode(ep);
     }
   });
}

function playEpisode(ep){
  current = ep;
  audio.src = ep.url;
  audio.play();
  document.getElementById("miniPlayer").style.display = "flex";
  document.getElementById("miniCover").src = ep.cover || ep.channel_cover;
  document.getElementById("miniTitle").innerText = ep.title;
  document.getElementById("fullCover").src = ep.cover || ep.channel_cover;
  document.getElementById("fullTitle").innerText = ep.title;
  document.getElementById("fullDesc").innerText = ep.description || "";
}

function togglePlay(e){
  e.stopPropagation();
  if(audio.paused) audio.play(); else audio.pause();
}

function closeMini(e){
  e.stopPropagation();
  document.getElementById("miniPlayer").style.display="none";
  audio.pause();
}

function openFullPlayer(){
  if(!current) return;
  document.getElementById("fullPlayer").style.display="flex";
}

function closeFull(e){
  e.stopPropagation();
  document.getElementById("fullPlayer").style.display="none";
}

document.addEventListener("keydown", function(e){
  if(e.key >= "1" && e.key <= "9"){
    let index = parseInt(e.key);
    let card = document.querySelector(`.card[data-key='${index}']`);
    if(card) card.click();
  }
  if(e.key === "5"){ togglePlay(e); }
  if(e.key === "0"){ closeMini(e); }
});
</script>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route("/")
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, cover FROM podcasts ORDER BY id DESC")
    podcasts = c.fetchall()
    conn.close()
    return render_template_string(HOME_HTML, podcasts=podcasts)

@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q: return redirect("/")
    r = requests.get("https://itunes.apple.com/search", params={"term":q,"media":"podcast"})
    results = []
    if r.ok:
        js = r.json()
        results = [{"title":t["collectionName"],"cover":t["artworkUrl600"],"rss":t.get("feedUrl")} for t in js.get("results",[]) if t.get("feedUrl")]
    return jsonify(results)

@app.route("/api/add_by_rss", methods=["POST"])
def add_by_rss():
    rss = request.form.get("rss")
    if not rss: return "Missing",400
    d = feedparser.parse(rss)
    if not d.feed: return "Invalid RSS",400
    title = d.feed.get("title","(no title)")
    cover = d.feed.get("image",{}).get("href") or ""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO podcasts(rss,title,cover) VALUES(?,?,?)",(rss,title,cover))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect("/")

@app.route("/api/podcast/<int:pid>/episodes")
def episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT rss, cover FROM podcasts WHERE id=?",(pid,))
    row = c.fetchone()
    conn.close()
    if not row: return jsonify([])
    rss, channel_cover = row
    d = feedparser.parse(rss)
    eps = []
    for e in d.entries:
        audio_url = None
        cover = None
        for l in e.get("links",[]):
            if l.get("type","").startswith("audio"):
                audio_url = l.get("href")
        if "image" in e: cover = e.image.get("href")
        eps.append({
          "title": e.get("title",""),
          "url": audio_url,
          "description": e.get("summary",""),
          "cover": cover,
          "channel_cover": channel_cover
        })
    return jsonify(eps)

# ---------------- Run Server ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)