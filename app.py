from flask import Flask, render_template_string, request, redirect
import sqlite3, os, requests, feedparser
import json

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

# ---------------- HTML Templates ----------------
PODCAST_GRID_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body{font-family:sans-serif;padding:10px;background:#f8f9fa;}
.grid{display:grid;gap:12px;}
.card{border-radius:12px;padding:20px;color:white;text-align:center;font-size:18px;background:#f97316;}
.searchbox input, .searchbox button{width:100%;padding:10px;margin:6px 0;font-size:18px;border-radius:6px;box-sizing:border-box;}
.saved-grid{display:grid;grid-template-columns:1fr;gap:10px;}
.saved-item{background:white;color:black;border-radius:12px;padding:12px;box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:center;}
.saved-item img{border-radius:8px;max-width:100px;margin-bottom:8px;}
.saved-item b{display:block;font-size:16px;margin-bottom:6px;}
.saved-item button{padding:8px;font-size:14px;margin-top:6px;margin-right:4px;border-radius:6px;border:none;}
.saved-item audio{width:100%;margin-top:6px;}
.podcast{background:white;padding:10px;margin:10px 0;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);}
.podcast img{max-width:80px;float:left;margin-right:10px;border-radius:6px;}
</style>
</head>
<body>
<div class="grid">
  <div class="card">🎙️ Podcasts</div>
</div>

<div class="searchbox">
  <form method="get" action="/podcast">
    <input type="text" name="q" placeholder="Search podcasts..." value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
  </form>
</div>

{% if results %}
<div class="results">
  <h3>Search Results</h3>
  {% for r in results %}
    <div class="podcast">
      <img src="{{ r.cover }}">
      <b>{{ r.title }}</b><br>
      <small>{{ r.description }}</small><br>
      <form method="post" action="/podcast">
        <input type="hidden" name="title" value="{{ r.title }}">
        <input type="hidden" name="rss" value="{{ r.rss }}">
        <input type="hidden" name="cover" value="{{ r.cover }}">
        <button type="submit" style="background:#2563eb;color:white;padding:6px 12px;margin-top:6px;">➕ Add</button>
      </form>
      <div style="clear:both;"></div>
    </div>
  {% endfor %}
</div>
{% endif %}

{% if saved %}
<div class="saved">
  <h3>Saved Podcasts</h3>
  <div class="saved-grid">
    {% for pid, title, rss, cover in saved %}
      <div class="saved-item" id="podcast-{{ pid }}">
        {% if cover %}<img src="{{ cover }}">{% endif %}
        <b>{{ title }}</b>
        {% if latest_episodes.get(pid) %}
          <audio id="player-{{ pid }}" controls autoplay src="{{ latest_episodes[pid][0]['audio_url'] }}"></audio>
          <div>
            <button onclick="prevEpisode({{ pid }})">⏮ Prev</button>
            <button onclick="nextEpisode({{ pid }})">⏭ Next</button>
            <button onclick="togglePlayPause({{ pid }})" id="playPause-{{ pid }}">⏸ Pause</button>
          </div>
        {% endif %}
        <div>
          <a href="/podcast/{{ pid }}"><button style="background:#4CAF50;color:white;">Open</button></a>
          <form method="post" action="/podcast/delete/{{ pid }}" style="display:inline;">
            <button type="submit" style="background:#dc2626;color:white;">Delete</button>
          </form>
        </div>
      </div>
    {% endfor %}
  </div>
</div>
{% endif %}

<script>
let allEpisodes = {{ latest_episodes|tojson }};

// JS functions for multiple podcasts
function loadEpisode(pid, index){
    let player = document.getElementById("player-" + pid);
    let ep = allEpisodes[pid][index];
    player.src = ep.audio_url;
    player.play();
    document.getElementById("playPause-" + pid).innerText = "⏸ Pause";
    allEpisodes[pid].current = index;
}

function nextEpisode(pid){
    let episodes = allEpisodes[pid];
    let index = (episodes.current + 1) % episodes.length;
    loadEpisode(pid, index);
}

function prevEpisode(pid){
    let episodes = allEpisodes[pid];
    let index = (episodes.current - 1 + episodes.length) % episodes.length;
    loadEpisode(pid, index);
}

function togglePlayPause(pid){
    let player = document.getElementById("player-" + pid);
    let btn = document.getElementById("playPause-" + pid);
    if(player.paused){
        player.play();
        btn.innerText = "⏸ Pause";
    } else {
        player.pause();
        btn.innerText = "▶ Play";
    }
}

// Initialize current index
for(let pid in allEpisodes){
    allEpisodes[pid].current = 0;
}
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

# ---------------- Podcast Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return redirect("/podcast")

@app.route("/podcast", methods=["GET","POST"])
def podcast_search():
    if request.method=="POST":
        title=request.form.get("title")
        rss=request.form.get("rss")
        cover=request.form.get("cover")
        if rss:
            conn=sqlite3.connect(DB_FILE)
            c=conn.cursor()
            c.execute("INSERT INTO podcasts (title,rss,cover) VALUES (?,?,?)",(title,rss,cover))
            conn.commit()
            conn.close()
        return redirect("/podcast")

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
    return render_template_string(PODCAST_GRID_HTML, results=results, saved=saved, latest_episodes=latest_episodes)

@app.route("/podcast/<int:pid>")
def podcast_detail(pid):
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("SELECT title,rss,cover FROM podcasts WHERE id=?",(pid,))
    r=c.fetchone()
    conn.close()
    if not r: return "Not found",404
    title,rss,cover=r

    feed = feedparser.parse(rss)
    episodes = []
    for entry in feed.entries[:10]:
        audio=''
        for enc in entry.get('enclosures',[]):
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

    return render_template_string(PODCAST_GRID_HTML, results=[], saved=[(pid, title, rss, cover)], latest_episodes={pid: episodes})

@app.route("/podcast/delete/<int:pid>", methods=["POST"])
def podcast_delete(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM podcasts WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect("/podcast")

# ---------------- Run App ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)