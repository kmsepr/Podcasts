# app.py
from flask import Flask, render_template_string, request, redirect, jsonify
import sqlite3, os, requests, feedparser

app = Flask(__name__)

DB = "podcasts.db"
os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS podcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rss TEXT UNIQUE,
        title TEXT,
        cover TEXT
      )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- helpers ----------------
def insert_podcast(rss, title, cover):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO podcasts (rss,title,cover) VALUES (?,?,?)",
              (rss, title, cover))
    conn.commit()
    conn.close()

def fetch_saved():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, rss, title, cover FROM podcasts ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def fetch_latest_episode_for_rss(rss):
    """Return dict with title, description, audio, cover (may be None) or error"""
    try:
        feed = feedparser.parse(rss)
    except Exception as e:
        return {"error": "Failed to fetch feed."}
    if not getattr(feed, "entries", None):
        return {"error": "No episodes found in feed."}

    # Prefer the first entry with an audio enclosure
    chosen = None
    audio_url = None
    for entry in feed.entries:
        # enclosures
        if entry.get("enclosures"):
            for enc in entry.enclosures:
                href = enc.get("href") or enc.get("url")
                if href and ("audio" in (enc.get("type","")) or href.endswith(".mp3") or href.endswith(".m4a")):
                    audio_url = href
                    chosen = entry
                    break
        if chosen: break
        # fallback links
        if entry.get("links"):
            for ln in entry.links:
                if ln.get("type","",).startswith("audio"):
                    audio_url = ln.get("href")
                    chosen = entry
                    break
        if chosen: break

    if not chosen:
        # fallback to first entry, try to extract audio if available
        chosen = feed.entries[0]
        audio_url = None
        if chosen.get("enclosures"):
            audio_url = chosen.enclosures[0].get("href") if chosen.enclosures else None
        elif chosen.get("links"):
            for ln in chosen.links:
                if ln.get("type","").startswith("audio"):
                    audio_url = ln.get("href"); break

    # extract episode cover if available
    ep_cover = None
    try:
        if chosen.get("image"):
            img = chosen.image
            if isinstance(img, dict):
                ep_cover = img.get("href") or img.get("url")
            else:
                ep_cover = img
    except:
        ep_cover = None
    if not ep_cover and chosen.get("itunes_image"):
        ep_cover = chosen.get("itunes_image")
    if not ep_cover and chosen.get("media_thumbnail"):
        mt = chosen.media_thumbnail
        if isinstance(mt, list) and mt:
            ep_cover = mt[0].get("url")
        elif isinstance(mt, dict):
            ep_cover = mt.get("url")

    # channel cover fallback
    channel_cover = ""
    try:
        channel_cover = feed.feed.get("image", {}).get("href") or feed.feed.get("itunes_image", "") or ""
    except:
        channel_cover = ""

    return {
        "title": chosen.get("title","(no title)"),
        "description": chosen.get("summary","") or chosen.get("description","") or "",
        "audio": audio_url,
        "cover": ep_cover or channel_cover
    }

# ---------------- template ----------------
TEMPLATE = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Podcast App</title>
<style>
  body{font-family:sans-serif;margin:0;background:#f7f8fa;color:#111}
  header{background:#0f172a;color:#fff;padding:12px;text-align:center}
  .container{padding:12px;max-width:980px;margin:0 auto}
  form.search{display:flex;gap:8px;margin-bottom:12px}
  input[type=text]{flex:1;padding:10px;border-radius:8px;border:1px solid #ccc;font-size:16px}
  button{padding:10px 12px;border-radius:8px;border:none;background:#0f62fe;color:#fff;cursor:pointer}
  .section-title{margin:12px 0 6px 0;font-weight:600}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
  .card{background:#fff;border-radius:10px;padding:10px;box-shadow:0 4px 12px rgba(2,6,23,0.06);display:flex;flex-direction:column;min-height:220px}
  .card .num{font-weight:700;color:#111;font-size:20px;margin-bottom:6px}
  .card img{width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:8px}
  .card .title{font-size:15px;height:44px;overflow:hidden}
  .card .row{margin-top:auto;display:flex;gap:8px;justify-content:space-between}
  .btn{flex:1;padding:8px;border-radius:8px;border:none;cursor:pointer}
  .btn.add{background:#10b981;color:#fff}
  .btn.play{background:#2563eb;color:#fff}

  /* mini player: title + scrolling description only */
  #mini { position:fixed; left:12px; right:12px; bottom:12px; background:#111;color:#fff;border-radius:12px;padding:10px; display:none; z-index:9999; box-shadow:0 10px 30px rgba(2,6,23,0.3)}
  #mini .row {display:flex;align-items:center;gap:10px}
  #mini img{width:56px;height:56px;border-radius:8px;object-fit:cover}
  #mini .info{flex:1;overflow:hidden}
  #mini .title{font-weight:700}
  #mini .desc{white-space:nowrap;overflow:hidden}
  #mini .desc span{display:inline-block;padding-left:100%;animation:scroll 18s linear infinite}
  @keyframes scroll{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}

  /* full player */
  #full{position:fixed;left:0;right:0;top:0;bottom:0;background:#071029;color:#fff;display:none;overflow:auto;padding:20px}
  #full .wrap{max-width:720px;margin:0 auto;text-align:center}
  #full img{max-width:80%;border-radius:12px;margin-bottom:12px}
  #full h2{font-size:22px;margin:6px 0}
  #full p{background:#031725;color:#dbeafe;padding:12px;border-radius:8px;text-align:left;max-height:320px;overflow:auto}
  #full audio{width:100%;margin-top:12px}

  @media (max-width:420px){
    .card img{height:100px}
    #mini img{width:48px;height:48px}
  }
</style>
</head>
<body>
<header><strong>Podcast Explorer</strong></header>
<div class="container">

  <form class="search" method="get" action="/">
    <input type="text" name="q" placeholder="Search podcasts (e.g. 'news', 'malayalam')"
           value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
    <button type="button" onclick="document.location='/'">Clear</button>
  </form>

  {% if results %}
    <div class="section-title">Search Results</div>
    <div class="grid" id="results-grid">
      {% for r in results %}
        <div class="card" data-rss="{{ r.rss|e }}" data-title="{{ r.title|e }}" data-cover="{{ r.cover|e }}">
          <div class="num">[{{ loop.index }}]</div>
          <img src="{{ r.cover|e }}" alt="cover">
          <div class="title">{{ r.title }}</div>
          <div class="row">
            <form method="post" action="/add" style="margin:0;flex:1">
              <input type="hidden" name="rss" value="{{ r.rss|e }}">
              <input type="hidden" name="title" value="{{ r.title|e }}">
              <input type="hidden" name="cover" value="{{ r.cover|e }}">
              <button class="btn add" type="submit">Add</button>
            </form>
            <button class="btn play" type="button" onclick="playCard(this.closest('.card'))">Play</button>
          </div>
        </div>
      {% endfor %}
    </div>
  {% endif %}

  <div class="section-title">Saved Podcasts</div>
  <div class="grid" id="saved-grid">
    {% for id, rss, title, cover in saved %}
      <div class="card" data-rss="{{ rss|e }}" data-title="{{ title|e }}" data-cover="{{ cover|e }}">
        <div class="num">[{{ loop.index }}]</div>
        <img src="{{ cover|e }}" alt="cover">
        <div class="title">{{ title }}</div>
        <div class="row">
          <button class="btn play" onclick="playCard(this.closest('.card'))">Play</button>
          <form method="post" action="/delete" style="margin:0">
            <input type="hidden" name="id" value="{{ id }}">
            <button class="btn add" style="background:#ef4444">Delete</button>
          </form>
        </div>
      </div>
    {% endfor %}
  </div>

</div>

<!-- Mini player (title + scrolling description only) -->
<div id="mini" onclick="openFull()">
  <div class="row">
    <img id="mini-cover" src="">
    <div class="info">
      <div id="mini-title" class="title"></div>
      <div class="desc"><span id="mini-desc"></span></div>
    </div>
    <div>
      <button onclick="prevEpisode(event)">⏮</button>
      <button onclick="togglePlay(event)">⏯</button>
      <button onclick="nextEpisode(event)">⏭</button>
      <button onclick="closeMini(event)">✖</button>
    </div>
  </div>
  <audio id="mini-audio" style="width:100%;display:block;margin-top:8px"></audio>
</div>

<!-- Full player -->
<div id="full">
  <div class="wrap">
    <img id="full-cover" src="">
    <h2 id="full-title"></h2>
    <p id="full-desc"></p>
    <audio id="full-audio" controls></audio>
    <div style="margin-top:12px">
      <button onclick="prevEpisode()">⏮ (4)</button>
      <button onclick="togglePlay()">⏯ (5)</button>
      <button onclick="nextEpisode()">⏭ (6)</button>
      <button onclick="closeFull()">✖ (0)</button>
    </div>
  </div>
</div>

<script>
/* Client-side player logic */
let current = {rss: null, episodes: [], index: 0}; // episodes list for current feed (if you expand later)
let visibleCards = []; // updated on each render

function playCard(card){
  // card element has data attributes
  const rss = card.dataset.rss;
  const title = card.dataset.title;
  const cover = card.dataset.cover;
  if(!rss){ alert("No RSS for this item"); return; }
  fetch("/api/play?rss=" + encodeURIComponent(rss))
    .then(r => r.json())
    .then(json => {
      if(json.error){ alert(json.error); return; }
      // set current episode (we keep single latest episode)
      current.rss = rss;
      current.episodes = [json]; current.index = 0;
      // mini player
      document.getElementById("mini-cover").src = json.cover || cover || "";
      document.getElementById("mini-title").innerText = json.title || title || "";
      document.getElementById("mini-desc").innerText = json.description || "";
      const miniAudio = document.getElementById("mini-audio");
      miniAudio.src = json.audio || "";
      miniAudio.play().catch(()=>{});
      document.getElementById("mini").style.display = "block";
      // full fill
      document.getElementById("full-cover").src = json.cover || cover || "";
      document.getElementById("full-title").innerText = json.title || title || "";
      document.getElementById("full-desc").innerText = json.description || "";
      document.getElementById("full-audio").src = json.audio || "";
    })
    .catch(err => { alert("Failed to fetch episode"); console.error(err); });
}

function togglePlay(e){
  if(e) e.stopPropagation();
  const a = document.getElementById("mini-audio");
  if(a.paused) a.play(); else a.pause();
  const fa = document.getElementById("full-audio");
  if(fa && !fa.paused) { /* keep in sync? we don't auto-sync now */ }
}

function closeMini(e){
  if(e) e.stopPropagation();
  document.getElementById("mini").style.display = "none";
  const a = document.getElementById("mini-audio"); a.pause(); a.src = "";
  current = {rss:null, episodes:[], index:0};
}

function openFull(){
  document.getElementById("full").style.display = "block";
}
function closeFull(){ document.getElementById("full").style.display = "none"; }

function nextEpisode(e){
  if(e) e.stopPropagation();
  // placeholder: if you fetch multiple eps, implement index++ here
  alert("Next episode (not implemented).");
}
function prevEpisode(e){
  if(e) e.stopPropagation();
  alert("Previous episode (not implemented).");
}

// number keypad mapping to visible cards
document.addEventListener("keydown", (ev)=>{
  const k = ev.key;
  if(k >= "1" && k <= "9"){
    const idx = parseInt(k,10) - 1;
    const cards = Array.from(document.querySelectorAll('.card'));
    if(cards[idx]) {
      // play the card
      playCard(cards[idx]);
      // scroll it into view for visibility
      cards[idx].scrollIntoView({behavior:"smooth",block:"center"});
    }
  } else if(k === "5"){
    togglePlay();
  } else if(k === "0"){
    closeMini(); closeFull();
  }
});
</script>
</body>
</html>
"""

# ---------------- routes ----------------
@app.route("/", methods=["GET"])
def home():
    q = request.args.get("q","").strip()
    results = []
    if q:
        try:
            r = requests.get("https://itunes.apple.com/search", params={"term": q, "media": "podcast", "limit": 30}, timeout=8)
            r.raise_for_status()
            js = r.json()
            for it in js.get("results", []):
                rss = it.get("feedUrl")
                if not rss: continue
                results.append({
                    "title": it.get("collectionName"),
                    "rss": rss,
                    "cover": it.get("artworkUrl600") or it.get("artworkUrl100") or ""
                })
            # dedupe by rss
            seen=set(); ded=[]
            for r0 in results:
                if r0["rss"] in seen: continue
                seen.add(r0["rss"]); ded.append(r0)
            results = ded
        except Exception:
            results = []
    saved = fetch_saved()
    return render_template_string(TEMPLATE, results=results, saved=saved)

@app.route("/add", methods=["POST", "GET"])
def add():
    # support both POST form and GET query (for convenience)
    if request.method == "POST":
        rss = request.form.get("rss","").strip()
        title = request.form.get("title","").strip()
        cover = request.form.get("cover","").strip()
    else:
        rss = request.args.get("rss","").strip()
        title = request.args.get("title","").strip()
        cover = request.args.get("cover","").strip()

    if not rss:
        return "Missing rss", 400
    # if title or cover missing, try to parse feed
    if not title or not cover:
        try:
            feed = feedparser.parse(rss)
            if not title:
                title = feed.feed.get("title","")
            if not cover:
                cover = feed.feed.get("image",{}).get("href","") or feed.feed.get("itunes_image","") or ""
        except:
            pass
    insert_podcast(rss, title or rss, cover or "")
    return redirect("/")

@app.route("/delete", methods=["POST"])
def delete():
    idv = request.form.get("id")
    if not idv:
        return redirect("/")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM podcasts WHERE id=?", (idv,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/api/play")
def api_play():
    rss = request.args.get("rss","").strip()
    if not rss:
        return jsonify({"error":"missing rss"})
    ep = fetch_latest_episode_for_rss(rss)
    if "error" in ep:
        return jsonify({"error": ep["error"]})
    # ensure audio present
    if not ep.get("audio"):
        return jsonify({"error":"no playable audio found for latest episode."})
    return jsonify({
        "title": ep.get("title"),
        "description": ep.get("description"),
        "audio": ep.get("audio"),
        "cover": ep.get("cover")
    })

# ---------------- run ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)