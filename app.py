from flask import Flask, render_template_string, request, redirect
import sqlite3, os, feedparser, requests

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = "podcasts.db"
os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            rss TEXT UNIQUE,
            cover TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML Template ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Podcasts</title>
    <style>
        body { font-family: sans-serif; margin:0; padding:0; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(150px,1fr)); gap: 15px; padding: 15px; }
        .item { cursor:pointer; text-align:center; border:1px solid #ccc; border-radius:10px; padding:10px; }
        .item img { width:100px; height:100px; object-fit:cover; border-radius:10px; }
        #player { position: fixed; bottom: 0; left: 0; right: 0; background:#111; color:#fff;
                  padding: 10px; display:none; }
        #player audio { width: 100%; }
        .form { padding: 10px; }
    </style>
</head>
<body>
    <div class="form">
        <form method="post" action="/add">
            <input type="text" name="rss" placeholder="Enter podcast RSS feed" size="40">
            <button type="submit">Add</button>
        </form>
    </div>
    <div class="grid">
        {% for p in podcasts %}
        <div class="item" onclick="playPodcast('{{p.rss}}','{{p.title}}')">
            <img src="{{p.cover or ''}}" alt="cover"><br>
            <b>{{p.title}}</b>
        </div>
        {% endfor %}
    </div>

    <div id="player">
        <span id="playingTitle"></span><br>
        <audio id="audio" controls autoplay></audio>
    </div>

<script>
async function playPodcast(rss,title){
    let res = await fetch("/play?rss="+encodeURIComponent(rss));
    let data = await res.json();
    if(data.url){
        document.getElementById("audio").src = data.url;
        document.getElementById("playingTitle").innerText = title;
        document.getElementById("player").style.display = "block";
    }
}
</script>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route("/")
def home():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, rss, cover FROM podcasts ORDER BY id DESC")
    podcasts = [{"title": r[0], "rss": r[1], "cover": r[2]} for r in c.fetchall()]
    conn.close()
    return render_template_string(HTML, podcasts=podcasts)

@app.route("/add", methods=["POST"])
def add():
    rss = request.form.get("rss")
    if rss:
        try:
            feed = feedparser.parse(rss)
            title = feed.feed.get("title", "Unknown Podcast")
            cover = None
            if "image" in feed.feed:
                cover = feed.feed.image.get("href")
            elif "itunes_image" in feed.feed:
                cover = feed.feed.itunes_image
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO podcasts(title,rss,cover) VALUES(?,?,?)",(title,rss,cover))
            conn.commit()
            conn.close()
        except Exception as e:
            print("Error adding feed:", e)
    return redirect("/")

@app.route("/play")
def play():
    rss = request.args.get("rss")
    feed = feedparser.parse(rss)
    if feed.entries:
        audio_url = None
        for link in feed.entries[0].enclosures:
            if link.get("type","").startswith("audio"):
                audio_url = link.get("href")
                break
        if not audio_url:
            audio_url = feed.entries[0].get("link")
        return {"url": audio_url}
    return {"url": None}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)