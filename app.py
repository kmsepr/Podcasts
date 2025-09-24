from flask import Flask, render_template_string, request
import sqlite3, os

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
            description TEXT,
            cover TEXT,
            audio TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- Home Route ----------------
@app.route("/")
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, description, cover, audio FROM podcasts ORDER BY id DESC")
    podcasts = c.fetchall()
    conn.close()
    return render_template_string(HOME_HTML, podcasts=podcasts)

# ---------------- Full Player ----------------
@app.route("/player/<int:pid>")
def player(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, description, cover, audio FROM podcasts WHERE id=?", (pid,))
    podcast = c.fetchone()
    conn.close()
    return render_template_string(PLAYER_HTML, podcast=podcast)

# ---------------- HTML ----------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Podcasts</title>
  <style>
    body { font-family: sans-serif; margin: 10px; background: #fafafa; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr)); gap: 12px; }
    .episode-card { padding: 10px; background: white; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); cursor: pointer; }
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

<h2>Podcast Episodes</h2>
<div class="grid">
  {% for id, title, description, cover, audio in podcasts %}
  <div class="episode-card" onclick="openMiniPlayer('{{id}}','{{title}}','{{description}}','{{audio}}','{{cover}}')">
    <img src="{{cover}}" alt="cover">
    <h4>{{title}}</h4>
    <p style="font-size:12px">{{description[:50]}}...</p>
  </div>
  {% endfor %}
</div>

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

let currentId = null, currentCover = null;

function openMiniPlayer(id, title, description, audioUrl, cover) {
    currentId = id;
    currentCover = cover;
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
            gridItems[index].click(); // open mini player
        }
        if (key === "0") { // close mini player
            closeMiniPlayer();
        }
    }
    if (key === "5") { // toggle play/pause
        togglePlayPause();
    }
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
  <img src="{{podcast[3]}}" alt="cover">
  <h2>{{podcast[1]}}</h2>
  <p>{{podcast[2]}}</p>
  <audio controls autoplay src="{{podcast[4]}}"></audio>
  <a href="/">⬅️ Back</a>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)