from flask import Flask, render_template_string, request, jsonify, redirect
import requests, sqlite3, os

app = Flask(__name__)

DB_FILE = "podcasts.db"
os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

# ---------------- DB Init ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            cover TEXT,
            rss TEXT UNIQUE
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Podcast App</title>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
        header { background: #333; color: white; padding: 10px; text-align: center; }
        form { margin: 10px; text-align: center; }
        input[type=text] { width: 60%; padding: 8px; }
        button { padding: 8px 12px; margin-left: 5px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(150px,1fr)); gap: 10px; margin: 10px; }
        .card { background: white; border-radius: 8px; padding: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .card img { width: 100%; border-radius: 6px; }
        .mini-player { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #222; color: white; padding: 10px; }
        .mini-player audio { width: 100%; }
        #mini-description { white-space: nowrap; overflow: hidden; }
        #mini-description span { display: inline-block; padding-left: 100%; animation: scroll-left 12s linear infinite; }
        @keyframes scroll-left { 0% { transform: translateX(0%);} 100% { transform: translateX(-100%);} }
    </style>
</head>
<body>
<header><h2>Podcast Search</h2></header>
<form id="search-form">
    <input type="text" name="q" placeholder="Search podcasts...">
    <button type="submit">Search</button>
</form>

<h3 style="margin-left:10px;">Favourites</h3>
<div class="grid" id="favorites"></div>

<h3 style="margin-left:10px;">Results</h3>
<div class="grid" id="results"></div>

<div class="mini-player" id="mini-player">
    <strong id="mini-title"></strong>
    <div id="mini-description"><span id="mini-desc-text"></span></div>
    <audio id="mini-audio" controls></audio>
</div>

<script>
async function loadFavorites() {
    let res = await fetch("/api/favorites");
    let data = await res.json();
    let favDiv = document.getElementById("favorites");
    favDiv.innerHTML = "";
    data.forEach((p,i) => {
        favDiv.innerHTML += `
        <div class="card podcast-card" data-rss="${p.rss}" data-title="${p.title}" data-cover="${p.cover}">
            <img src="${p.cover}"><br>${p.title}<br>
            <button onclick="playPodcast('${p.rss}','${p.title}','${p.cover}')">Play</button>
        </div>`;
    });
}

document.getElementById("search-form").onsubmit = async (e) => {
    e.preventDefault();
    let q = e.target.q.value;
    let res = await fetch("/api/search?q=" + encodeURIComponent(q));
    let data = await res.json();
    let resDiv = document.getElementById("results");
    resDiv.innerHTML = "";
    data.forEach((p,i) => {
        resDiv.innerHTML += `
        <div class="card podcast-card" data-rss="${p.rss}" data-title="${p.title}" data-cover="${p.cover}">
            <img src="${p.cover}"><br>${p.title}<br>
            <button onclick="addFav('${p.rss}','${p.title}','${p.cover}')">Add</button>
            <button onclick="playPodcast('${p.rss}','${p.title}','${p.cover}')">Play</button>
        </div>`;
    });
};

async function addFav(rss,title,cover) {
    await fetch("/api/add", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({rss,title,cover})
    });
    loadFavorites();
}

function playPodcast(rss,title,cover) {
    let mini = document.getElementById("mini-player");
    mini.style.display = "block";
    document.getElementById("mini-title").innerText = title;
    document.getElementById("mini-desc-text").innerText = rss;
    document.getElementById("mini-audio").src = rss; // placeholder, should be episode audio
    document.getElementById("mini-audio").play();
}

document.addEventListener("keydown", e => {
    if (e.key >= "1" && e.key <= "9") {
        let idx = parseInt(e.key)-1;
        let cards = document.querySelectorAll(".podcast-card");
        if (cards[idx]) {
            let btn = cards[idx].querySelector("button:last-of-type");
            if (btn) btn.click();
        }
    } else if (e.key === "5") {
        let audio = document.getElementById("mini-audio");
        if (audio) { if (audio.paused) audio.play(); else audio.pause(); }
    } else if (e.key === "0") {
        document.getElementById("mini-player").style.display = "none";
    }
});

loadFavorites();
</script>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/api/search")
def search():
    q = request.args.get("q","")
    if not q: return jsonify([])
    url = f"https://itunes.apple.com/search?media=podcast&term={q}"
    try:
        res = requests.get(url).json()
    except:
        return jsonify([])
    results = []
    seen = set()
    for item in res.get("results", []):
        rss = item.get("feedUrl")
        if not rss or rss in seen: continue
        seen.add(rss)
        results.append({
            "title": item.get("collectionName"),
            "cover": item.get("artworkUrl600"),
            "rss": rss
        })
    return jsonify(results)

@app.route("/api/add", methods=["POST"])
def add():
    data = request.json
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO podcasts (title,cover,rss) VALUES (?,?,?)",
              (data["title"],data["cover"],data["rss"]))
    conn.commit()
    conn.close()
    return jsonify({"status":"ok"})

@app.route("/api/favorites")
def favorites():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title,cover,rss FROM podcasts ORDER BY id DESC")
    rows = [{"title":t,"cover":cvr,"rss":rss} for t,cvr,rss in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ---------------- Run ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)