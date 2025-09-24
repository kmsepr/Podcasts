from flask import Flask, render_template_string, request, redirect
import sqlite3, os, requests, feedparser

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            rss TEXT,
            cover TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML Template ----------------
PODCAST_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body{font-family:sans-serif;margin:0;padding:0;background:#f8f9fa;}
h3{margin:10px;}
.grid{display:grid;gap:12px;padding:10px;}
.card{border-radius:12px;padding:20px;color:white;text-align:center;
      font-size:18px;background:#f97316;}
.searchbox{padding:10px;}
.searchbox input, .searchbox button{width:100%;padding:10px;margin:6px 0;
      font-size:18px;border-radius:6px;box-sizing:border-box;}
.saved-grid{display:grid;grid-template-columns:1fr;gap:10px;padding:10px;}
.saved-item{background:white;color:black;border-radius:12px;padding:12px;
      box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:center;cursor:pointer;}
.saved-item img{border-radius:8px;max-width:100px;margin-bottom:8px;}
.saved-item b{display:block;font-size:16px;margin-bottom:6px;}
.saved-item button{margin-top:6px;}

/* --- Mini Player --- */
#miniPlayer {
    position:fixed;bottom:0;left:0;right:0;
    background:#222;color:#fff;
    display:none;align-items:center;justify-content:space-between;
    padding:8px 12px;cursor:pointer;z-index:1000;
}
#miniPlayer img{width:50px;height:50px;border-radius:8px;object-fit:cover;}
#miniInfo{flex:1;margin-left:10px;overflow:hidden;}
#miniTitle{font-size:14px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#miniDesc{font-size:12px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#miniControls{margin-left:10px;}
#miniControls button{background:none;border:none;color:white;font-size:18px;margin:0 4px;cursor:pointer;}

/* --- Full Player --- */
#fullPlayer {
    position:fixed;top:0;left:0;right:0;bottom:0;
    background:#121212;color:#fff;
    display:none;flex-direction:column;align-items:center;
    justify-content:flex-start;padding:20px;z-index:2000;
}
#fullPlayer img{width:70%;max-width:300px;border-radius:16px;margin:20px 0;}
#fullPlayer h2{margin:10px 0;text-align:center;}
#fullPlayer p{font-size:0.9em;color:#bbb;text-align:center;}
#fullPlayer audio{width:90%;margin-top:20px;}
#fullPlayer .header{width:100%;display:flex;justify-content:flex-end;}
#fullPlayer .header button{background:none;border:none;font-size:24px;color:white;cursor:pointer;}
#fullControls{margin-top:20px;}
#fullControls button{background:#333;border:none;color:white;padding:10px 20px;
    margin:0 10px;border-radius:8px;font-size:16px;cursor:pointer;}
</style>
</head>
<body>
<div class="grid">
  <div class="card">🎙️ Podcasts</div>
</div>

<div class="searchbox">
  <form method="get" action="/">
    <input type="text" name="q" placeholder="Search podcasts..." value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
  </form>
</div>

{% if results %}
<div class="results">
  <h3>Search Results</h3>
  {% for r in results %}
    <div class="saved-item">
      <img src="{{ r.cover }}">
      <b>{{ r.title }}</b><br>
      <a href="/add?title={{ r.title }}&rss={{ r.rss }}&cover={{ r.cover }}">
        <button type="button">➕ Add</button>
      </a>
    </div>
  {% endfor %}
</div>
{% endif %}

{% if saved %}
<div class="saved">
  <h3>Saved Podcasts</h3>
  <div class="saved-grid">
    {% for pid, title, rss, cover in saved %}
      <div class="saved-item" onclick="startPodcast({{ pid }})">
        {% if cover %}<img src="{{ cover }}">{% endif %}
        <b>{{ title }}</b>
        <form method="post" action="/podcast/delete/{{ pid }}">
          <button type="submit" style="background:#dc2626;color:white;border:none;padding:6px 12px;border-radius:6px;">Delete</button>
        </form>
      </div>
      {% if latest_episodes.get(pid) %}
        <audio id="player-{{ pid }}" style="display:none;"></audio>
      {% endif %}
    {% endfor %}
  </div>
</div>
{% endif %}

<!-- Mini Player -->
<div id="miniPlayer" onclick="openFullPlayer()">
  <img id="miniCover" src="">
  <div id="miniInfo">
    <div id="miniTitle"></div>
    <div id="miniDesc"></div>
  </div>
  <div id="miniControls">
    <button onclick="prevEpisode(currentPid);event.stopPropagation();">⏮</button>
    <button onclick="togglePlay(currentPid);event.stopPropagation();" id="miniPlayBtn">⏸</button>
    <button onclick="nextEpisode(currentPid);event.stopPropagation();">⏭</button>
  </div>
</div>

<!-- Full Player -->
<div id="fullPlayer">
  <div class="header">
    <button onclick="closeFullPlayer()">❌</button>
  </div>
  <img id="fullCover" src="">
  <h2 id="fullTitle"></h2>
  <p id="fullDesc"></p>
  <audio id="fullAudio" controls></audio>
  <div id="fullControls">
    <button onclick="prevEpisode(currentPid)">⏮ Prev</button>
    <button onclick="togglePlay(currentPid)" id="fullPlayBtn">⏸ Pause</button>
    <button onclick="nextEpisode(currentPid)">Next ⏭</button>
  </div>
</div>

<script>
let allEpisodes = {{ latest_episodes|tojson }};
let currentPid = null;

function loadEpisode(pid,index){
  let player = document.getElementById("player-" + pid);
  let ep = allEpisodes[pid][index];
  allEpisodes[pid].current = index;
  player.src = ep.audio_url;
  player.play();
  currentPid = pid;

  // update mini player
  document.getElementById("miniPlayer").style.display = "flex";
  document.getElementById("miniCover").src = "{{ saved[0][3] if saved else '' }}";
  document.getElementById("miniTitle").innerText = ep.title;
  document.getElementById("miniDesc").innerText = ep.pub_date || "";
  document.getElementById("miniPlayBtn").innerText = "⏸";

  // update full player info
  document.getElementById("fullCover").src = "{{ saved[0][3] if saved else '' }}";
  document.getElementById("fullTitle").innerText = ep.title;
  document.getElementById("fullDesc").innerText = ep.description || "";
  document.getElementById("fullAudio").src = ep.audio_url;
  document.getElementById("fullPlayBtn").innerText = "⏸ Pause";
}

function startPodcast(pid){
  if(!allEpisodes[pid]) return;
  loadEpisode(pid,0);
}

function nextEpisode(pid){
  let eps = allEpisodes[pid];
  let idx = (eps.current + 1) % eps.length;
  loadEpisode(pid, idx);
}

function prevEpisode(pid){
  let eps = allEpisodes[pid];
  let idx = (eps.current - 1 + eps.length) % eps.length;
  loadEpisode(pid, idx);
}

function togglePlay(pid){
  let player = document.getElementById("player-" + pid);
  let miniBtn = document.getElementById("miniPlayBtn");
  let fullBtn = document.getElementById("fullPlayBtn");
  if(player.paused){ 
    player.play(); 
    miniBtn.innerText = "⏸"; 
    fullBtn.innerText = "⏸ Pause"; 
  } else { 
    player.pause(); 
    miniBtn.innerText = "▶"; 
    fullBtn.innerText = "▶ Play"; 
  }
}

function openFullPlayer(){
  document.getElementById("fullPlayer").style.display = "flex";
}

function closeFullPlayer(){
  document.getElementById("fullPlayer").style.display = "none";
}

// Keypad mapping
document.addEventListener("keydown", e=>{
  if(currentPid==null) return;
  switch(e.key){
    case "4": prevEpisode(currentPid); break;
    case "5": togglePlay(currentPid); break;
    case "6": nextEpisode(currentPid); break;
  }
});
</script>
</body>
</html>
"""

# ---------------- Helpers ----------------
def get_podcasts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id,title,rss,cover FROM podcasts ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_latest_episodes(podcasts, limit=5):
    latest_episodes = {}
    for pid, title, rss, cover in podcasts:
        episodes = []
        try:
            feed = feedparser.parse(rss)
            for entry in feed.entries[:limit]:
                audio = ''
                for enc in entry.get('enclosures', []):
                    if enc.get('href','').startswith('http'):
                        audio = enc['href']
                        break
                if audio:
                    episodes.append({
                        'title': entry.get('title',''),
                        'pub_date': entry.get('published',''),
                        'audio_url': audio,
                        'description': entry.get('summary','')
                    })
            if episodes:
                latest_episodes[pid] = episodes
        except:
            pass
    return latest_episodes

# ---------------- Routes ----------------
@app.route("/")
def home():
    query = request.args.get("q")
    results = []
    if query:
        url = f"https://itunes.apple.com/search?media=podcast&term={query}"
        try:
            r = requests.get(url,timeout=10).json()
            for item in r.get("results", []):
                results.append({
                    "title": item.get("collectionName"),
                    "rss": item.get("feedUrl"),
                    "cover": item.get("artworkUrl100"),
                    "description": item.get("collectionName","")
                })
        except:
            pass

    saved = get_podcasts()
    latest_episodes = get_latest_episodes(saved)
    return render_template_string(PODCAST_HTML, results=results, saved=saved, latest_episodes=latest_episodes)

@app.route("/add")
def add_podcast():
    title = request.args.get("title")
    rss = request.args.get("rss")
    cover = request.args.get("cover")
    if rss:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO podcasts (title,rss,cover) VALUES (?,?,?)",(title,rss,cover))
        conn.commit()
        conn.close()
    return redirect("/")

@app.route("/podcast/delete/<int:pid>", methods=["POST"])
def podcast_delete(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM podcasts WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect("/")

# ---------------- Run ----------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)