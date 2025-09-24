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

# ---------------- Helpers ----------------
def get_podcasts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id,title,rss,cover FROM podcasts ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_latest_episode(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            for enc in entry.get("enclosures", []):
                if enc.get("href", "").startswith("http"):
                    return {
                        "title": entry.get("title", ""),
                        "description": entry.get("summary", ""),
                        "audio": enc["href"],
                        "cover": feed.feed.get("image", {}).get("href", "")
                    }
    except:
        return None
    return None

# ---------------- HTML ----------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body { font-family: sans-serif; margin: 10px; background: #fafafa; }
.searchbox input, .searchbox button { width:100%; padding:10px; margin:6px 0; font-size:16px; border-radius:6px; box-sizing:border-box; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr)); gap: 12px; }
.episode-card { padding: 10px; background: white; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); cursor: pointer; text-align:center; }
.episode-card img { width: 100%; border-radius: 8px; }
.mini-player { position: fixed; bottom: 0; left: 0; right: 0; background: #333; color: white; padding: 10px;
               display: flex; align-items: center; justify-content: space-between; }
.mini-player.hidden { display: none; }
.mini-info { flex: 1; margin-left: 10px; }
.mini-title { font-weight: bold; font-size: 14px; }
.mini-desc { font-size: 12px; opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.button { cursor: pointer; font-size: 20px; padding: 0 10px; }
</style>
</head>
<body>

<h2>🎙️ Podcast Explorer</h2>

<div class="searchbox">
  <form method="get" action="/">
    <input type="text" name="q" placeholder="Search podcasts..." value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
  </form>
</div>

{% if results %}
<div>
  <h3>Search Results</h3>
  <div class="grid">
  {% for r in results %}
    <div class="episode-card">
      <img src="{{ r.cover }}">
      <h4>{{ r.title }}</h4>
      <a href="/add?title={{ r.title }}&rss={{ r.rss }}&cover={{ r.cover }}">
        <button type="button">➕ Add</button>
      </a>
    </div>
  {% endfor %}
  </div>
</div>
{% endif %}

{% if saved %}
<div>
  <h3>Saved Podcasts</h3>
  <div class="grid">
    {% for pid, title, rss, cover, ep in saved %}
      {% if ep %}
      <div class="episode-card" onclick="openMiniPlayer('{{pid}}','{{ep.title}}','{{ep.description}}','{{ep.audio}}','{{ep.cover or cover}}')">
        <img src="{{ep.cover or cover}}">
        <h4>{{title}}</h4>
        <p style="font-size:12px">{{ep.title}}</p>
      </div>
      {% endif %}
    {% endfor %}
  </div>
</div>
{% endif %}

<!-- Mini Player -->
<div id="miniPlayer" class="mini-player hidden" onclick="goToFullPlayer()">
  <div class="mini-info">
    <div id="miniTitle" class="mini-title"></div>
    <div id="miniDesc" class="mini-desc"></div>
  </div>
  <div class="button" id="miniPlayPause" onclick="event.stopPropagation(); togglePlayPause()">▶️</div>
  <audio id="miniAudio"></audio>
</div>

<script>
let miniPlayer = document.getElementById("miniPlayer");
let miniTitle = document.getElementById("miniTitle");
let miniDesc = document.getElementById("miniDesc");
let miniAudio = document.getElementById("miniAudio");
let miniPlayPause = document.getElementById("miniPlayPause");

let currentId = null;

function openMiniPlayer(id, title, description, audioUrl, cover) {
    currentId = id;
    miniTitle.innerText = title;
    miniDesc.innerText = description;
    miniAudio.src = audioUrl;
    miniAudio.play();
    miniPlayPause.innerText = "⏸";
    miniPlayer.classList.remove("hidden");
}

function togglePlayPause() {
    if (miniAudio.paused) {
        miniAudio.play();
        miniPlayPause.innerText = "⏸";
    } else {
        miniAudio.pause();
        miniPlayPause.innerText = "▶️";
    }
}

function closeMiniPlayer() {
    miniAudio.pause();
    miniAudio.src = "";
    miniPlayer.classList.add("hidden");
}

function goToFullPlayer() {
    if (currentId) {
        window.location.href = "/player/" + currentId;
    }
}

// Keypad mapping
document.addEventListener("keydown", function(e) {
    let key = e.key;
    if (!isNaN(key)) {
        let index = parseInt(key) - 1;
        let gridItems = document.querySelectorAll(".episode-card");
        if (index >= 0 && index < gridItems.length) {
            gridItems[index].click();
        }
        if (key === "0") { closeMiniPlayer(); }
        if (key === "9") { goToFullPlayer(); }
    }
    if (key === "5") { togglePlayPause(); }
});
</script>

</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{podcast[1]}}</title>
  <style>
    body { font-family: sans-serif; text-align: center; background: #111; color: white; }
    img { max-width: 300px; border-radius: 15px; margin-top: 20px; }
    h2 { margin: 10px 0; }
    p { color: #ccc; margin: 10px; }
    audio { width: 90%; margin-top: 15px; }
    a { color: #0af; display: block; margin-top: 20px; }
  </style>
</head>
<body>
  <img src="{{cover}}" alt="cover">
  <h2>{{title}}</h2>
  <p>{{description}}</p>
  <audio controls autoplay src="{{audio}}"></audio>
  <a href="/">⬅️ Back</a>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route("/")
def home():
    query = request.args.get("q")
    results = []
    if query:
        url = f"https://itunes.apple.com/search?media=podcast&term={query}"
        try:
            r = requests.get(url, timeout=10).json()
            for item in r.get("results", []):
                results.append({
                    "title": item.get("collectionName"),
                    "rss": item.get("feedUrl"),
                    "cover": item.get("artworkUrl100")
                })
        except:
            pass

    saved = []
    for pid, title, rss, cover in get_podcasts():
        ep = get_latest_episode(rss)
        saved.append((pid, title, rss, cover, ep))

    return render_template_string(HOME_HTML, results=results, saved=saved)

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

@app.route("/player/<int:pid>")
def player(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id,title,rss,cover FROM podcasts WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    if not row:
        return "Podcast not found"
    pid, title, rss, cover = row
    ep = get_latest_episode(rss)
    return render_template_string(PLAYER_HTML,
        podcast=row,
        title=title, description=ep["title"] if ep else "",
        cover=ep["cover"] or cover if ep else cover,
        audio=ep["audio"] if ep else "")

# ---------------- Run ----------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)