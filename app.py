from flask import Flask, render_template_string, request, redirect
import sqlite3, os, requests, feedparser

app = Flask(__name__)

DB_FILE = 'podcasts.db'
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS podcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            rss TEXT UNIQUE,
            cover TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body{font-family:sans-serif;background:#f8f9fa;margin:0;padding:0;}
h3{margin:10px 0;}
.container{padding:10px;}

.searchbox input, .searchbox button{
  width:100%;padding:10px;margin:6px 0;font-size:18px;
  border-radius:6px;box-sizing:border-box;
}

.result-item, .saved-item{
  background:white;border-radius:12px;padding:12px;margin:8px 0;
  box-shadow:0 2px 6px rgba(0,0,0,0.1);font-size:18px;
}
.result-item img, .saved-item img{
  max-width:100px;border-radius:8px;display:block;margin-bottom:6px;
}
.result-item b, .saved-item b{display:block;margin-bottom:4px;}

#mini-player{
  position:fixed;bottom:0;left:0;right:0;background:#111;color:white;
  padding:10px;display:none;align-items:center;gap:10px;font-size:16px;
}
#mini-player img{width:50px;height:50px;object-fit:cover;border-radius:6px;}
.scroll-text{overflow:hidden;white-space:nowrap;flex:1;}
.scroll-text span{display:inline-block;padding-left:100%;animation:scroll 12s linear infinite;}
@keyframes scroll{0%{transform:translateX(0);}100%{transform:translateX(-100%);}}

#full-player{
  position:fixed;top:0;left:0;right:0;bottom:0;background:#222;color:white;
  display:none;flex-direction:column;align-items:center;padding:15px;overflow:auto;
}
#full-player img{max-width:80%;border-radius:12px;margin:15px 0;}
#full-title{font-size:22px;text-align:center;margin:10px 0;}
#full-desc{font-size:18px;line-height:1.4;text-align:center;
  white-space:nowrap;overflow:hidden;}
#full-desc span{display:inline-block;padding-left:100%;animation:scroll 20s linear infinite;}

.controls button{
  font-size:22px;margin:8px;padding:10px 20px;border-radius:8px;
}
</style>
</head>
<body>
<div class="container">
  <h2>🎙️ Podcasts</h2>

  <div class="searchbox">
    <form method="get" action="/">
      <input type="text" name="q" placeholder="Search podcasts..." value="{{ request.args.get('q','') }}">
      <button type="submit">Search</button>
    </form>
  </div>

  {% if results %}
    <h3>Search Results</h3>
    {% for r in results %}
      <div class="result-item">
        <img src="{{ r.cover }}">
        <b>[{{ loop.index }}] {{ r.title }}</b>
        <a href="/add?title={{ r.title }}&rss={{ r.rss }}&cover={{ r.cover }}">
          <button type="button">➕ Add</button>
        </a>
      </div>
    {% endfor %}
  {% endif %}

  {% if saved %}
    <h3>Saved Podcasts</h3>
    {% for pid,title,rss,cover in saved %}
      <div class="saved-item" onclick="startPodcast({{ pid }})">
        {% if cover %}<img src="{{ cover }}">{% endif %}
        <b>[{{ loop.index }}] {{ title }}</b>
      </div>
      <audio id="player-{{ pid }}" class="hidden-player"></audio>
    {% endfor %}
  {% endif %}
</div>

<!-- Mini player -->
<div id="mini-player" onclick="openFullPlayer()">
  <img id="mini-cover" src="">
  <div class="scroll-text"><span id="mini-title"></span></div>
  <button onclick="togglePlay(currentPid);event.stopPropagation();">⏯</button>
  <button onclick="closeMiniPlayer();event.stopPropagation();">❌</button>
</div>

<!-- Full player -->
<div id="full-player">
  <img id="full-cover" src="">
  <div id="full-title"></div>
  <div id="full-desc"><span></span></div>
  <div class="controls">
    <button onclick="prevEpisode(currentPid)">⏮ (4)</button>
    <button onclick="togglePlay(currentPid)">⏯ (5)</button>
    <button onclick="nextEpisode(currentPid)">⏭ (6)</button>
    <button onclick="closeFullPlayer()">❌ (0)</button>
  </div>
</div>

<script>
let allEpisodes={{ latest_episodes|tojson }};
let currentPid=null;

function loadEpisode(pid,index){
  let player=document.getElementById("player-"+pid);
  let ep=allEpisodes[pid][index];
  allEpisodes[pid].current=index;
  player.src=ep.audio_url;
  player.play();
  currentPid=pid;

  // mini player
  document.getElementById("mini-player").style.display="flex";
  document.getElementById("mini-cover").src=ep.cover||"";
  document.getElementById("mini-title").textContent=ep.title+" - "+ep.pub_date;

  // full player
  document.getElementById("full-cover").src=ep.cover||"";
  document.getElementById("full-title").textContent=ep.title;
  document.querySelector("#full-desc span").textContent=ep.description||"";
}

function startPodcast(pid){if(!allEpisodes[pid])return;loadEpisode(pid,0);}
function nextEpisode(pid){let eps=allEpisodes[pid];let i=(eps.current+1)%eps.length;loadEpisode(pid,i);}
function prevEpisode(pid){let eps=allEpisodes[pid];let i=(eps.current-1+eps.length)%eps.length;loadEpisode(pid,i);}
function togglePlay(pid){let p=document.getElementById("player-"+pid);if(p.paused)p.play();else p.pause();}
function closeMiniPlayer(){document.getElementById("mini-player").style.display="none";currentPid=null;}
function openFullPlayer(){document.getElementById("full-player").style.display="flex";}
function closeFullPlayer(){document.getElementById("full-player").style.display="none";}

document.addEventListener("keydown",e=>{
  if(currentPid==null){
    let num=parseInt(e.key);
    if(num && num<=Object.keys(allEpisodes).length){
      let pid=Object.keys(allEpisodes)[num-1];
      startPodcast(pid);
    }
    return;
  }
  switch(e.key){
    case "4": prevEpisode(currentPid);break;
    case "5": togglePlay(currentPid);break;
    case "6": nextEpisode(currentPid);break;
    case "0": closeMiniPlayer();closeFullPlayer();break;
  }
});
</script>
</body>
</html>
"""

def get_podcasts():
    conn=sqlite3.connect(DB_FILE);c=conn.cursor()
    c.execute("SELECT id,title,rss,cover FROM podcasts ORDER BY id DESC")
    rows=c.fetchall();conn.close();return rows

def get_latest_episodes(podcasts,limit=5):
    data={}
    for pid,title,rss,cover in podcasts:
        episodes=[]
        try:
            feed=feedparser.parse(rss)
            for entry in feed.entries[:limit]:
                audio=""
                for enc in entry.get("enclosures",[]):
                    if enc.get("href","").startswith("http"):audio=enc["href"];break
                if audio:
                    episodes.append({
                        "title":entry.get("title",""),
                        "pub_date":entry.get("published",""),
                        "audio_url":audio,
                        "description":entry.get("summary",""),
                        "cover":cover
                    })
            if episodes:data[pid]=episodes
        except:pass
    return data

@app.route("/")
def home():
    query=request.args.get("q");results=[]
    if query:
        url=f"https://itunes.apple.com/search?media=podcast&term={query}"
        try:
            r=requests.get(url,timeout=10).json()
            for item in r.get("results",[]):
                if not item.get("feedUrl"):continue
                results.append({
                    "title":item.get("collectionName"),
                    "rss":item.get("feedUrl"),
                    "cover":item.get("artworkUrl100")
                })
        except:pass
    saved=get_podcasts()
    latest=get_latest_episodes(saved)
    return render_template_string(HTML,results=results,saved=saved,latest_episodes=latest)

@app.route("/add")
def add_podcast():
    title=request.args.get("title");rss=request.args.get("rss");cover=request.args.get("cover")
    if rss:
        conn=sqlite3.connect(DB_FILE);c=conn.cursor()
        try:c.execute("INSERT INTO podcasts(title,rss,cover) VALUES(?,?,?)",(title,rss,cover));conn.commit()
        except sqlite3.IntegrityError:pass
        conn.close()
    return redirect("/")

@app.route("/podcast/delete/<int:pid>",methods=["POST"])
def podcast_delete(pid):
    conn=sqlite3.connect(DB_FILE);c=conn.cursor()
    c.execute("DELETE FROM podcasts WHERE id=?",(pid,));conn.commit();conn.close()
    return redirect("/")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)