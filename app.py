from flask import Flask, render_template_string, request, jsonify
import requests, feedparser

app = Flask(__name__)

# ---------------- HTML TEMPLATE ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Podcasts</title>
  <style>
    body { font-family: sans-serif; margin:0; padding:0; background:#f9f9f9; }
    header { padding:10px; background:#333; color:#fff; text-align:center; }
    .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; padding:10px; }
    .card { background:#fff; border-radius:10px; padding:10px; text-align:center; cursor:pointer; box-shadow:0 2px 4px rgba(0,0,0,0.2); }
    .card img { width:100%; border-radius:8px; }
    form { padding:10px; text-align:center; }
    input[type=text] { padding:8px; width:70%; }
    button { padding:8px 12px; margin:5px; cursor:pointer; }

    /* Mini player */
    .mini-player { position:fixed; bottom:0; left:0; right:0; background:#222; color:#fff; padding:8px; display:none; }
    #mini-title { font-size:14px; font-weight:bold; display:block; }
    #mini-description { white-space:nowrap; overflow:hidden; }
    #mini-description span { display:inline-block; padding-left:100%; animation:scroll-left 20s linear infinite; }
    @keyframes scroll-left { 0%{transform:translateX(100%);} 100%{transform:translateX(-100%);} }
    audio { width:100%; margin-top:5px; }

    /* Full player */
    #full-player { display:none; padding:20px; text-align:center; }
    #full-cover { max-width:90%; border-radius:12px; }
    #full-title { font-size:18px; margin:10px 0; }
    #full-desc { font-size:14px; text-align:left; max-height:150px; overflow:auto; background:#f0f0f0; padding:10px; border-radius:8px; }
  </style>
</head>
<body>
  <header><h2>Podcast Player</h2></header>
  <form onsubmit="searchPodcasts(); return false;">
    <input type="text" id="q" placeholder="Search podcast...">
    <button type="submit">Search</button>
  </form>

  <div class="grid" id="results"></div>

  <!-- Mini Player -->
  <div class="mini-player" id="mini-player" onclick="openFullPlayer()">
    <span id="mini-title"></span>
    <div id="mini-description"><span id="mini-desc-text"></span></div>
    <audio id="mini-audio" controls></audio>
  </div>

  <!-- Full Player -->
  <div id="full-player">
    <img id="full-cover" src="">
    <h2 id="full-title"></h2>
    <p id="full-desc"></p>
    <audio id="full-audio" controls></audio>
    <br><button onclick="closeFullPlayer()">Close</button>
  </div>

<script>
let podcasts = [];
let currentEpisode = null;

async function searchPodcasts(){
  let q = document.getElementById("q").value;
  let res = await fetch("/api/search?q="+encodeURIComponent(q));
  let data = await res.json();
  podcasts = data;
  let grid = document.getElementById("results");
  grid.innerHTML = "";
  data.forEach((p,i)=>{
    let card = document.createElement("div");
    card.className="card";
    card.innerHTML = "<img src='"+p.cover+"'><br>"+p.title+
      "<br><button onclick='playPodcast("+i+")'>Play</button>";
    grid.appendChild(card);
  });
}

async function playPodcast(i){
  let p = podcasts[i];
  let res = await fetch("/api/play?rss="+encodeURIComponent(p.rss));
  let ep = await res.json();
  if(ep.error){ alert(ep.error); return; }
  currentEpisode = ep;

  document.getElementById("mini-player").style.display="block";
  document.getElementById("mini-title").innerText = ep.title;
  document.getElementById("mini-desc-text").innerText = ep.description;
  let audio = document.getElementById("mini-audio");
  audio.src = ep.audio;
  audio.play();
}

function openFullPlayer(){
  if(!currentEpisode) return;
  document.getElementById("full-cover").src = currentEpisode.cover || "";
  document.getElementById("full-title").innerText = currentEpisode.title;
  document.getElementById("full-desc").innerText = currentEpisode.description;
  document.getElementById("full-audio").src = currentEpisode.audio;
  document.getElementById("full-audio").play();
  document.getElementById("full-player").style.display="block";
}

function closeFullPlayer(){
  document.getElementById("full-player").style.display="none";
}

// Keypad controls
document.addEventListener("keydown", e=>{
  if(e.key>="1" && e.key<="9"){
    let idx = parseInt(e.key)-1;
    if(idx<podcasts.length){ playPodcast(idx); }
  }
  if(e.key==="0"){ document.getElementById("mini-player").style.display="none"; }
});
</script>
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/api/search")
def api_search():
    q = request.args.get("q","")
    url = f"https://itunes.apple.com/search?media=podcast&term={q}"
    r = requests.get(url)
    results = r.json().get("results",[])
    out=[]
    for it in results:
        out.append({
            "title": it.get("collectionName"),
            "rss": it.get("feedUrl"),
            "cover": it.get("artworkUrl600")
        })
    return jsonify(out)

@app.route("/api/play")
def api_play():
    rss = request.args.get("rss")
    if not rss:
        return jsonify({"error":"missing rss"})
    feed = feedparser.parse(rss)
    if not feed.entries:
        return jsonify({"error":"no episodes"})
    ep = feed.entries[0]
    audio = ep.enclosures[0].href if ep.enclosures else None
    return jsonify({
        "title": ep.title,
        "description": ep.get("summary",""),
        "audio": audio,
        "cover": feed.feed.get("image",{}).get("href")
    })

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)