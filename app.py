from flask import Flask, request, jsonify, render_template_string
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
            rss TEXT UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- Routes ----------------
@app.route('/')
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, rss FROM podcasts ORDER BY id DESC")
    podcasts = c.fetchall()
    conn.close()

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
  <title>Podcast App</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: sans-serif; background:#111; color:white; margin:0; padding:0; }
    .card { background:#222; margin:8px; padding:10px; border-radius:8px; }
    button { background:#444; color:white; border:none; padding:6px 10px; border-radius:5px; }
    input { width:70%; padding:5px; }
    .line-clamp-3 {
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    #miniPlayer { position:fixed; bottom:0; left:0; right:0; background:#333; padding:5px; display:none; }
    #fullPlayer { display:none; position:fixed; inset:0; background:#000; color:white; overflow-y:auto; padding:10px; }
  </style>
</head>
<body>
  <h2 style="padding:10px;">My Podcasts</h2>
  <form method="post" action="/add" style="padding:10px;">
    <input type="text" name="rss" placeholder="Add RSS feed URL">
    <button type="submit">Add</button>
  </form>

  {% for p in podcasts %}
    <div class="card">
      <b>{{p[1]}}</b><br>
      <a href="/podcast/{{p[0]}}/episodes"><button>Episodes</button></a>
    </div>
  {% endfor %}

  <!-- Mini Player -->
  <div id="miniPlayer">
    <span id="miniTitle"></span>
    <button onclick="openFullPlayer()">Open</button>
  </div>

  <!-- Full Player -->
  <div id="fullPlayer">
    <button onclick="closeFullPlayer()" style="background:red;">Close</button>
    <h3 id="fullTitle"></h3>
    <img id="fullCover" style="max-height:200px; width:100%; object-fit:cover; border-radius:8px;">
    <p id="fullDesc" class="line-clamp-3"></p>
    <button id="toggleDesc" style="background:none; color:skyblue; text-decoration:underline;">Read more >>></button>

    <div style="margin-top:10px;">
      <button onclick="seek(-20)">⏪ 20s</button>
      <button onclick="togglePlay()" id="playPauseBtn">▶</button>
      <button onclick="seek(20)">20s ⏩</button>
    </div>
  </div>

  <audio id="audio" controls style="display:none;"></audio>

  <script>
    let audio = document.getElementById("audio");
    let miniPlayer = document.getElementById("miniPlayer");
    let fullPlayer = document.getElementById("fullPlayer");
    let playPauseBtn = document.getElementById("playPauseBtn");
    let descExpanded = false;

    function playEpisode(title, cover, audioUrl, desc) {
      document.getElementById("miniTitle").innerText = title;
      document.getElementById("fullTitle").innerText = title;
      document.getElementById("fullCover").src = cover;
      document.getElementById("fullDesc").innerText = desc;

      // reset description
      descExpanded = false;
      document.getElementById("fullDesc").classList.add("line-clamp-3");
      document.getElementById("toggleDesc").innerText = "Read more >>>";

      audio.src = audioUrl;
      audio.play();
      playPauseBtn.innerText = "⏸";
      miniPlayer.style.display = "block";
    }

    function togglePlay() {
      if (audio.paused) {
        audio.play();
        playPauseBtn.innerText = "⏸";
      } else {
        audio.pause();
        playPauseBtn.innerText = "▶";
      }
    }

    function seek(seconds) {
      audio.currentTime += seconds;
    }

    function openFullPlayer() {
      fullPlayer.style.display = "block";
    }

    function closeFullPlayer() {
      fullPlayer.style.display = "none";
    }

    document.getElementById("toggleDesc").onclick = () => {
      let descEl = document.getElementById("fullDesc");
      if (descExpanded) {
        descEl.classList.add("line-clamp-3");
        document.getElementById("toggleDesc").innerText = "Read more >>>";
      } else {
        descEl.classList.remove("line-clamp-3");
        document.getElementById("toggleDesc").innerText = "<<< Read less";
      }
      descExpanded = !descExpanded;
    };
  </script>
</body>
</html>
    """, podcasts=podcasts)

@app.route('/add', methods=['POST'])
def add_podcast():
    rss = request.form['rss']
    feed = feedparser.parse(rss)
    if not feed.feed.get('title'):
        return "Invalid feed", 400
    title = feed.feed.title
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO podcasts (title, rss) VALUES (?, ?)", (title, rss))
    conn.commit()
    conn.close()
    return ('', 204)

@app.route('/podcast/<int:pid>/episodes')
def list_episodes(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT rss FROM podcasts WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    if not row: return "Not found", 404

    feed = feedparser.parse(row[0])
    items = []
    for e in feed.entries[:20]:
        audio_url = None
        if 'enclosures' in e and e.enclosures:
            audio_url = e.enclosures[0].href
        elif 'links' in e:
            for l in e.links:
                if l.get("type","").startswith("audio"):
                    audio_url = l.href
        items.append({
            "title": e.title,
            "audio": audio_url,
            "desc": e.get("description",""),
            "cover": feed.feed.get("image",{}).get("href","")
        })

    html = "<h2 style='padding:10px;'>Episodes</h2>"
    for ep in items:
        html += f"""
        <div class='card'>
          <b>{ep['title']}</b><br>
          <button onclick="playEpisode('{ep['title'].replace("'",'')}','{ep['cover']}','{ep['audio']}','{ep['desc'].replace("'",'')}')">Play</button>
        </div>
        """
    return html

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")