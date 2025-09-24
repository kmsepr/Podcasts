from flask import Flask, render_template_string, request, redirect, jsonify
import sqlite3, os, requests, feedparser

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS podcasts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rss TEXT UNIQUE,
                  title TEXT,
                  description TEXT,
                  image TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ---------------- Helpers ----------------
def add_podcast(rss):
    feed = feedparser.parse(rss)
    if not feed.feed:
        return None
    title = feed.feed.get("title", "Untitled")
    desc = feed.feed.get("description", "")
    img = feed.feed.get("image", {}).get("href", "")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO podcasts (rss,title,description,image) VALUES (?,?,?,?)",
                  (rss, title, desc, img))
        conn.commit()
    except Exception as e:
        print("DB insert error:", e)
    conn.close()
    return {"rss": rss, "title": title, "description": desc, "image": img}

def get_podcasts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id,rss,title,description,image FROM podcasts")
    rows = c.fetchall()
    conn.close()
    return rows

# ---------------- HTML Template ----------------
TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: sans-serif; margin:0; padding:0; background:#f5f5f5; }
    h1 { font-size:20px; padding:10px; text-align:center; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
            gap:10px; padding:10px; }
    .card { background:#fff; padding:10px; border-radius:10px; text-align:center;
            box-shadow:0 2px 4px rgba(0,0,0,0.2); }
    .card img { max-width:100%; height:100px; object-fit:cover; border-radius:6px; }
    .card h3 { font-size:14px; margin:5px 0; }
    .card button { font-size:12px; padding:5px 10px; margin-top:5px; }
    form { display:flex; gap:5px; justify-content:center; padding:10px; }
    input { flex:1; padding:6px; font-size:14px; }
    button { padding:6px 12px; }
    /* Mini Player */
    #miniPlayer { position:fixed; bottom:0; left:0; right:0;
                  background:#222; color:#fff; padding:8px;
                  display:none; align-items:center; }
    #miniPlayer img { width:40px; height:40px; object-fit:cover; margin-right:8px; }
    #scrollDesc { white-space:nowrap; overflow:hidden; flex:1; }
    #scrollDesc span { display:inline-block; padding-left:100%; animation:scroll 12s linear infinite; }
    @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-100%);} }
    /* Full Player */
    #fullPlayer { display:none; position:fixed; top:0; left:0; right:0; bottom:0;
                  background:#111; color:#fff; padding:20px; overflow:auto; }
    #fullPlayer img { width:100%; border-radius:12px; }
    #fullPlayer h2 { margin:10px 0; font-size:18px; }
    #closeBtn { background:red; color:#fff; padding:6px 12px; border:none; margin-top:10px; }
  </style>
</head>
<body>
  <h1>Podcast App</h1>

  <!-- Search -->
  <form method="get" action="/">
    <input type="text" name="q" placeholder="Search podcast">
    <button type="submit">Search</button>
  </form>

  {% if results %}
  <div class="grid">
    {% for r in results %}
    <div class="card">
      <img src="{{r.image}}" alt="">
      <h3>{{r.title}}</h3>
      <form method="post" action="/add">
        <input type="hidden" name="rss" value="{{r.rss}}">
        <button type="submit">Add</button>
      </form>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Grid of saved podcasts -->
  <div class="grid">
    {% for id,rss,title,desc,img in podcasts %}
    <div class="card" onclick="playPodcast({{id}},'{{title}}','{{desc}}','{{img}}','{{rss}}')">
      <img src="{{img}}" alt="">
      <h3>{{title}}</h3>
    </div>
    {% endfor %}
  </div>

  <!-- Mini Player -->
  <div id="miniPlayer" onclick="openFullPlayer()">
    <img id="miniImg" src="">
    <div id="scrollDesc"><span id="miniDesc"></span></div>
    <button onclick="togglePlay(event)">⏯</button>
    <button onclick="closeMini(event)">❌</button>
  </div>

  <!-- Full Player -->
  <div id="fullPlayer">
    <img id="fullImg" src="">
    <h2 id="fullTitle"></h2>
    <p id="fullDesc"></p>
    <audio id="fullAudio" controls autoplay style="width:100%"></audio>
    <button id="closeBtn" onclick="closeFull()">Close</button>
  </div>

  <script>
    let current={};

    function playPodcast(id,title,desc,img,rss){
      current={id,title,desc,img,rss};
      document.getElementById('miniPlayer').style.display='flex';
      document.getElementById('miniImg').src=img;
      document.getElementById('miniDesc').innerText=desc || title;
      // demo audio
      document.getElementById('fullAudio').src='https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3';
    }

    function togglePlay(ev){
      ev.stopPropagation();
      let audio=document.getElementById('fullAudio');
      if(audio.paused) audio.play(); else audio.pause();
    }

    function closeMini(ev){
      ev.stopPropagation();
      document.getElementById('miniPlayer').style.display='none';
    }

    function openFullPlayer(){
      document.getElementById('fullPlayer').style.display='block';
      document.getElementById('fullImg').src=current.img;
      document.getElementById('fullTitle').innerText=current.title;
      document.getElementById('fullDesc').innerText=current.desc;
    }

    function closeFull(){
      document.getElementById('fullPlayer').style.display='none';
    }

    // Keypad shortcuts 1-9
    document.addEventListener('keydown',e=>{
      let num=parseInt(e.key);
      if(num>=1 && num<=9){
        let cards=document.querySelectorAll('.card');
        if(cards[num-1]) cards[num-1].click();
      }
      if(e.key==='0'){ closeMini(e); closeFull(); }
      if(e.key==='5'){ togglePlay(e); }
    });
  </script>
</body>
</html>
"""

# ---------------- Routes ----------------
@app.route("/", methods=["GET","POST"])
def home():
    if request.method=="POST":
        rss=request.form.get("rss")
        if rss: add_podcast(rss)
        return redirect("/")
    q=request.args.get("q")
    results=[]
    if q:
        # iTunes search
        r=requests.get("https://itunes.apple.com/search",
                       params={"term":q,"media":"podcast","limit":10})
        if r.ok:
            data=r.json()
            for it in data.get("results",[]):
                results.append({
                    "title":it.get("collectionName"),
                    "image":it.get("artworkUrl100"),
                    "rss":it.get("feedUrl")
                })
    podcasts=get_podcasts()
    return render_template_string(TEMPLATE, podcasts=podcasts, results=results)

# ---------------- Run ----------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)