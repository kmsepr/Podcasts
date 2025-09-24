from flask import Flask, render_template_string, request, redirect
import sqlite3, os, feedparser

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
        body { font-family: sans-serif; margin:0; padding-bottom:100px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(150px,1fr)); gap: 15px; padding: 15px; }
        .item { cursor:pointer; text-align:center; border:1px solid #ddd; border-radius:12px; padding:10px; box-shadow:0 2px 5px rgba(0,0,0,0.1); transition:0.2s; }
        .item:hover { transform:scale(1.05); }
        .item img { width:100px; height:100px; object-fit:cover; border-radius:12px; }
        .form { padding: 10px; }

        /* Modern mini player */
        #player {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: #1e1e1e; color: #fff;
            display: none; align-items: center; padding: 10px;
            box-shadow: 0 -3px 10px rgba(0,0,0,0.5);
        }
        #player img {
            width: 50px; height: 50px; border-radius:8px; margin-right: 10px;
        }
        #player .info {
            flex-grow: 1; overflow: hidden;
        }
        #playingTitle { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #playingDesc { font-size: 0.85em; color:#bbb; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #player audio { width:200px; margin-left:10px; }
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
        <div class="item" onclick="playPodcast('{{p.rss}}','{{p.title}}','{{p.cover}}')">
            <img src="{{p.cover or ''}}" alt="cover"><br>
            <b>{{p.title}}</b>
        </div>
        {% endfor %}
    </div>

    <div id="player">
        <img id="coverImg" src="" alt="cover">
        <div class="info">
            <div id="playingTitle"></div>
            <div id="playingDesc"></div>
        </div>
        <audio id="audio" controls autoplay></audio>
    </div>

<script>
async function playPodcast(rss,title,cover){
    let res = await fetch("/play?rss="+encodeURIComponent(rss));
    let data = await res.json();
    if(data.url){
        document.getElementById("audio").src = data.url;
        document.getElementById("coverImg").src = cover || "";
        document.getElementById("playingTitle").innerText = title;
        document.getElementById("playingDesc").innerText = data.description || "";
        document.getElementById("player").style.display = "flex";
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
        desc = feed.entries[0].get("description", "")
        for link in feed.entries[0].enclosures:
            if link.get("type","").startswith("audio"):
                audio_url = link.get("href")
                break
        if not audio_url:
            audio_url = feed.entries[0].get("link")
        return {"url": audio_url, "description": desc}
    return {"url": None, "description": ""}
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)