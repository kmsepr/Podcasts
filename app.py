from flask import Flask, jsonify, render_template_string, request, redirect
import sqlite3, os, requests, feedparser
from datetime import datetime
import pytz

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'  # local file in project folder for persistence
os.makedirs(os.path.dirname(DB_FILE) or '.', exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Swalath total (single row)
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id=1),
            total INTEGER DEFAULT 0,
            last_added TEXT
        )
    ''')
    c.execute('INSERT INTO swalath_total (id,total,last_added) SELECT 1,0,NULL WHERE NOT EXISTS (SELECT 1 FROM swalath_total)')

    # Swalath entries
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER,
            added_at TEXT
        )
    ''')

    # Podcasts
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

# ---------------- HTML Templates ----------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Home</title>
<style>
body{font-family:sans-serif;margin:0;padding:0;background:#f7f7f7;color:#333}
.container{max-width:500px;margin:0 auto;padding:10px;display:grid;grid-template-columns:1fr;gap:12px}
.card{background:#fff;padding:20px;border-radius:12px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.1);cursor:pointer;font-size:20px;font-weight:bold}
.card:hover{box-shadow:0 4px 10px rgba(0,0,0,0.2)}
.green{background:#4CAF50;color:white}
.orange{background:#f97316;color:white}
.violet{background:#7c3aed;color:white}
.red{background:#dc2626;color:white}
</style>
</head>
<body>
<div class="container">
  <div class="card green" onclick="location.href='/swalath'">📿 Dikr</div>
  <div class="card violet" onclick="window.open('http://zippy-gretta-pscjunction-b779efe8.koyeb.app/','_blank')">📰 Suprabhatam</div>
  <div class="card red" onclick="window.open('http://capitalist-anthe-pscj-4a28f285.koyeb.app/','_blank')">📺 YouTube Live</div>
  <div class="card orange" onclick="location.href='/podcast'">🎙️ Podcasts</div>
</div>
</body>
</html>
"""

SWALATH_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Swalath</title>
<style>
body{font-family:sans-serif;background:#f7f7f7;margin:0;padding:10px;color:#333}
.card{background:#fff;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,0.1);padding:15px;margin-top:10px}
input,button{width:100%;padding:12px;margin:8px 0;border-radius:6px;border:1px solid #ccc;box-sizing:border-box;font-size:18px}
button{background:#4CAF50;color:white;border:none;cursor:pointer;font-weight:bold}
button:hover{opacity:0.9}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>
<h2 style="text-align:center;">📿 Swalath</h2>
<div class="card">
  <input type="number" id="swalathNumber" placeholder="Enter number" min="1">
  <button onclick="submitSwalath()">➕ Add</button>
  <p>Total: <span id="swalathTotal">0</span></p>
  <p>Last added: <span id="lastAdded">-</span></p>
</div>
<div id="swalathEntries"></div>
<script>
async function loadSwalathTotal(){
  let r=await fetch('/api/swalath/total'); let d=await r.json();
  document.getElementById('swalathTotal').innerText=d.total;
  document.getElementById('lastAdded').innerText=d.last_added||'-';
  loadEntries();
}
async function submitSwalath(){
  let n=document.getElementById('swalathNumber').value;
  if(!n){Swal.fire({icon:'error',title:'Enter number'});return;}
  let r=await fetch('/api/swalath/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number:n})});
  let d=await r.json();
  if(r.ok){document.getElementById('swalathNumber').value='';loadSwalathTotal();}
  else Swal.fire({icon:'error',title:'Error',text:d.error});
}
async function loadEntries(){
  let r=await fetch('/api/swalath/entries'); let d=await r.json();
  const c=document.getElementById('swalathEntries'); c.innerHTML='';
  d.forEach(e=>{let div=document.createElement('div');div.className='card';
    div.innerHTML=`${e.number} 🕰 ${e.added_at} <button style="margin-top:6px;padding:6px 10px;font-size:16px;" onclick="deleteEntry(${e.id})">❌</button>`; c.appendChild(div);
  });
}
async function deleteEntry(id){await fetch('/api/swalath/delete/'+id,{method:'POST'}); loadSwalathTotal();}
loadSwalathTotal();
</script>
</body>
</html>
"""

PODCAST_GRID_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcasts</title>
<style>
body{font-family:sans-serif;padding:10px;background:#f8f9fa;}
.grid{display:grid;gap:12px;}
.card{border-radius:12px;padding:20px;color:white;text-align:center;font-size:18px;background:#f97316;}
.searchbox input, .searchbox button{width:100%;padding:10px;margin:6px 0;font-size:18px;border-radius:6px;box-sizing:border-box;}
.saved-grid{display:grid;grid-template-columns:1fr;gap:10px;}
.saved-item{background:white;color:black;border-radius:12px;padding:12px;box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:center;}
.saved-item img{border-radius:8px;max-width:100px;margin-bottom:8px;}
.saved-item b{display:block;font-size:16px;margin-bottom:6px;}
.saved-item button{width:100%;padding:10px;font-size:16px;margin-top:6px;}
.podcast{background:white;color:black;border-radius:12px;padding:12px;margin:10px 0;box-shadow:0 2px 6px rgba(0,0,0,0.1);}
.podcast img{border-radius:8px;float:left;margin-right:10px;width:70px;}
.podcast b{font-size:16px;}
.podcast small{color:#555;display:block;margin-top:4px;}
.podcast button{margin-top:6px;padding:6px 10px;font-size:16px;}
.clear{clear:both;}
</style>
</head>
<body>
<div class="grid">
  <div class="card">🎙️ Podcasts</div>
</div>

<div class="searchbox">
  <form method="get" action="/podcast">
    <input type="text" name="q" placeholder="Search podcasts..." value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
  </form>
</div>

{% if results %}
<div class="results">
  <h3>Search Results</h3>
  {% for r in results %}
    <div class="podcast">
      <img src="{{ r.cover }}">
      <b>{{ r.title }}</b>
      <small>{{ r.description }}</small>
      <form method="post" action="/podcast">
        <input type="hidden" name="title" value="{{ r.title }}">
        <input type="hidden" name="rss" value="{{ r.rss }}">
        <input type="hidden" name="cover" value="{{ r.cover }}">
        <button type="submit">Add</button>
      </form>
      <div class="clear"></div>
    </div>
  {% endfor %}
</div>
{% endif %}

{% if saved %}
<div class="saved">
  <h3>Saved Podcasts</h3>
  <div class="saved-grid">
    {% for pid, title, rss, cover in saved %}
      <div class="saved-item">
        {% if cover %}<img src="{{ cover }}">{% endif %}
        <b>{{ title }}</b>
        <a href="/podcast/{{ pid }}"><button>Open</button></a>
      </div>
    {% endfor %}
  </div>
</div>
{% endif %}
</body>
</html>
"""

PODCAST_DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
body{font-family:sans-serif;background:#f7f7f7;padding:10px;text-align:center;}
.card{background:#fff;border-radius:12px;padding:15px;margin:15px auto;max-width:400px;box-shadow:0 2px 6px rgba(0,0,0,0.15);}
img.cover{border-radius:12px;width:120px;margin-bottom:10px;}
audio{width:100%;margin-top:10px;}
h2{margin:10px 0;font-size:20px;}
h3{font-size:18px;margin:6px 0;}
.description{font-size:14px;color:#555;margin-top:8px;}
button{padding:10px 12px;font-size:16px;border-radius:6px;margin-top:6px;}
</style>
</head>
<body>
<div class="card">
  {% if cover %}<img class="cover" src="{{ cover }}">{% endif %}
  <h2>{{ title }}</h2>
  {% if latest %}
    <h3>{{ latest.title }}</h3>
    <small>{{ latest.pub_date }}</small>
    <div class="description">{{ latest.description|safe }}</div>
    <audio controls src="{{ latest.audio_url }}"></audio>
  {% else %}
    <p>No episodes found.</p>
  {% endif %}
</div>
</body>
</html>
"""

# ---------------- Helpers ----------------
def get_podcasts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id,title,rss,cover FROM podcasts ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# ---------------- Swalath APIs ----------------
@app.route('/swalath')
def swalath_page():
    return render_template_string(SWALATH_HTML)

@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total,last_added FROM swalath_total WHERE id=1')
    total,last_added = c.fetchone()
    conn.close()
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number',0)
    try: number=int(number); assert number>0
    except: return jsonify({'error':'Enter positive number'}),400
    now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO swalath_entries (number,added_at) VALUES (?,?)',(number,now))
    c.execute('UPDATE swalath_total SET total=total+?,last_added=? WHERE id=1',(number,now))
    conn.commit()
    c.execute('SELECT total,last_added FROM swalath_total WHERE id=1')
    total,last_added=c.fetchone()
    conn.close()
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/entries')
def get_swalath_entries():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id,number,added_at FROM swalath_entries ORDER BY id DESC')
    rows=[dict(zip(['id','number','added_at'],r)) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/swalath/delete/<int:eid>',methods=['POST'])
def delete_swalath_entry(eid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT number FROM swalath_entries WHERE id=?',(eid,))
    r=c.fetchone()
    if not r: conn.close(); return jsonify({'error':'Entry not found'}),404
    number=r[0]
    c.execute('DELETE FROM swalath_entries WHERE id=?',(eid,))
    c.execute('UPDATE swalath_total SET total=total-? WHERE id=1',(number,))
    conn.commit(); conn.close()
    return jsonify({'message':'Deleted'})

# ---------------- Podcast APIs ----------------
@app.route("/podcast", methods=["GET","POST"])
def podcast_search():
    if request.method=="POST":
        title=request.form.get("title")
        rss=request.form.get("rss")
        cover=request.form.get("cover")
        conn=sqlite3.connect(DB_FILE)
        c=conn.cursor()
        c.execute("INSERT INTO podcasts (title,rss,cover) VALUES (?,?,?)",(title,rss,cover))
        conn.commit(); conn.close()
        return redirect("/podcast")

    query = request.args.get("q")
    results = []
    if query:
        url = f"https://itunes.apple.com/search?media=podcast&term={query}"
        try:
            r = requests.get(url,timeout=10).json()
            for item in r.get("results", []):
                results.append({
                    "title": item.get("collectionName"),
                    "rss": item.get("feedUrl"),
                    "cover": item.get("artworkUrl100"),
                    "description": item.get("collectionName","")
                })
        except:
            pass
    saved = get_podcasts()
    return render_template_string(PODCAST_GRID_HTML, results=results, saved=saved)

@app.route("/podcast/<int:pid>")
def podcast_detail(pid):
    conn=sqlite3.connect(DB_FILE); c=conn.cursor()
    c.execute("SELECT title,rss,cover FROM podcasts WHERE id=?",(pid,))
    r=c.fetchone(); conn.close()
    if not r: return "Not found",404
    title,rss,cover=r
    feed=feedparser.parse(rss)
    latest=None
    if feed.entries:
        entry=feed.entries[0]
        audio=''
        for enc in entry.get('enclosures',[]):
            if enc.get('href','').startswith('http'):
                audio=enc['href']; break
        if audio:
            latest={
                'title':entry.get('title',''),
                'pub_date':entry.get('published',''),
                'audio_url':audio,
                'description':entry.get('summary','')
            }
    return render_template_string(PODCAST_DETAIL_HTML,title=title,cover=cover,latest=latest)

# ---------------- Homepage ----------------
@app.route("/")
def home():
    return render_template_string(HOME_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)