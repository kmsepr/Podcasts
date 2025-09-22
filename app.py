from flask import Flask, jsonify, render_template_string, request
import sqlite3, os, requests, feedparser
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

IST = ZoneInfo("Asia/Kolkata")

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id=1),
            total INTEGER DEFAULT 0,
            last_added TEXT,
            first_added TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER,
            added_at TEXT
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_total (id,total,last_added,first_added) VALUES(1,0,NULL,NULL)')
    conn.commit()
    conn.close()

init_db()

# ---------------- Dikr APIs ----------------
@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number', 0)
    try:
        number = int(number)
        assert number > 0
    except:
        return jsonify({'error': 'Enter positive number'}), 400

    now = datetime.now(IST).strftime("%B %d %Y %H:%M:%S")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO swalath_entries (number, added_at) VALUES (?, ?)', (number, now))

    c.execute('SELECT first_added FROM swalath_total WHERE id=1')
    first_added = c.fetchone()[0]
    if not first_added:
        c.execute('UPDATE swalath_total SET first_added=? WHERE id=1', (now,))

    c.execute('UPDATE swalath_total SET total=total+?, last_added=? WHERE id=1', (number, now))
    conn.commit()
    c.execute('SELECT total,last_added,first_added FROM swalath_total WHERE id=1')
    total,last_added,first_added = c.fetchone()
    conn.close()
    return jsonify({'total': total, 'last_added': last_added, 'first_added': first_added})

@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total,last_added,first_added FROM swalath_total WHERE id=1')
    total,last_added,first_added = c.fetchone()
    conn.close()
    return jsonify({'total': total, 'last_added': last_added, 'first_added': first_added})

@app.route('/api/swalath/entries')
def get_entries():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT number,added_at FROM swalath_entries ORDER BY id DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'number': n, 'added_at': t} for n,t in rows])

# ---------------- Podcast (latest only) ----------------
ITUNES_SEARCH = "https://itunes.apple.com/search?term={}&media=podcast&limit=1"

@app.route('/api/podcast/latest')
def latest_podcast():
    # Example: return the first podcast for "Islamic"
    query = request.args.get("q", "Islamic")
    try:
        r = requests.get(ITUNES_SEARCH.format(query), timeout=5)
        data = r.json()
        if data["resultCount"] > 0:
            p = data["results"][0]
            return jsonify({
                "title": p.get("collectionName"),
                "description": p.get("artistName"),
                "feedUrl": p.get("feedUrl"),
                "artwork": p.get("artworkUrl100")
            })
    except:
        pass
    return jsonify({})

# ---------------- Pages ----------------
@app.route('/')
def home():
    return render_template_string("""
    <html>
    <head>
      <title>Home</title>
      <style>
        body { font-family: sans-serif; padding:20px; }
        .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }
        .card {
          padding:40px; border-radius:16px; color:white; 
          font-size:20px; font-weight:bold; text-align:center;
          display:flex; align-items:center; justify-content:center;
          flex-direction:column; text-decoration:none;
        }
        .dikr { background:#22c55e; }     /* Green */
        .news { background:#7c3aed; }     /* Violet */
        .youtube { background:#dc2626; }  /* Red */
        .podcast { background:#f97316; }  /* Orange */
      </style>
    </head>
    <body>
      <h1>Dashboard</h1>
      <div class="grid">
        <a href="/swalath" class="card dikr">🕌<br>Dikr</a>
        <a href="http://zippy-gretta-pscjunction-b779efe8.koyeb.app/" target="_blank" class="card news">📰<br>Suprabhaatham</a>
        <a href="http://capitalist-anthe-pscj-4a28f285.koyeb.app/" target="_blank" class="card youtube">📺<br>YouTube Live</a>
        <a href="/podcast" class="card podcast" id="latestPodcast">🎙️<br>Podcast</a>
      </div>

      <script>
        async function loadPodcast(){
          let r = await fetch('/api/podcast/latest?q=Islamic');
          let d = await r.json();
          if(d.title){
            document.getElementById('latestPodcast').innerHTML = "🎙️<br>"+d.title+"<br><small>"+(d.description||"")+"</small>";
          }
        }
        loadPodcast();
      </script>
    </body>
    </html>
    """)

@app.route('/swalath')
def swalath_page():
    return render_template_string("""
    <html>
    <head>
      <title>Dikr Tracker</title>
      <style>
        body { font-family: sans-serif; padding:20px; }
        input, button { padding:8px; margin:4px; }
        .btn { background:#22c55e; color:white; border:none; border-radius:8px; }
      </style>
    </head>
    <body>
      <h1>🕌 Dikr Tracker</h1>
      <p>Total: <span id="swalathTotal">0</span></p>
      <p>First added: <span id="firstAdded">-</span></p>
      <p>Last added: <span id="lastAdded">-</span></p>
      <input id="number" type="number" placeholder="Enter count">
      <button onclick="addSwalath()" class="btn">Add</button>
      <h2>Entries</h2>
      <ul id="entries"></ul>
      <script>
        async function loadSwalathTotal(){
          let r=await fetch('/api/swalath/total');
          let d=await r.json();
          document.getElementById('swalathTotal').innerText=d.total;
          document.getElementById('lastAdded').innerText=d.last_added||'-';
          document.getElementById('firstAdded').innerText=d.first_added||'-';
          loadEntries();
        }
        async function loadEntries(){
          let r=await fetch('/api/swalath/entries');
          let d=await r.json();
          let ul=document.getElementById('entries');
          ul.innerHTML="";
          d.forEach(e=>{
            let li=document.createElement('li');
            li.innerText=e.number+" @ "+e.added_at;
            ul.appendChild(li);
          });
        }
        async function addSwalath(){
          let num=document.getElementById('number').value;
          let r=await fetch('/api/swalath/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({number:num})});
          let d=await r.json();
          loadSwalathTotal();
        }
        loadSwalathTotal();
      </script>
    </body>
    </html>
    """)

@app.route("/podcast")
def podcast_search():
    query = request.args.get("q")
    results = []
    if query:
        url = f"https://itunes.apple.com/search?media=podcast&term={query}"
        r = requests.get(url).json()
        for item in r.get("results", []):
            results.append({
                "title": item.get("collectionName"),
                "rss": item.get("feedUrl"),
                "cover": item.get("artworkUrl100"),
                "description": item.get("collectionName", "")
            })
    saved = get_podcasts()
    return render_template_string(PODCAST_SEARCH_HTML, results=results, saved=saved)


PODCAST_SEARCH_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Podcasts</title>
  <style>
    body { font-family: sans-serif; padding: 20px; background: #f8f9fa; }
    h2 { margin-bottom: 10px; }
    .podcast { border: 1px solid #ddd; border-radius: 8px; padding: 10px; margin: 10px 0; background: white; }
    img { border-radius: 8px; }
  </style>
</head>
<body>
  <h2>Search Podcasts</h2>
  <form method="get" action="/podcast">
    <input type="text" name="q" placeholder="Search..." value="{{ request.args.get('q','') }}">
    <button type="submit">Search</button>
  </form>

  {% if results %}
    <h3>Search Results</h3>
    {% for r in results %}
      <div class="podcast">
        <img src="{{ r.cover }}" width="80" align="left" style="margin-right:10px;">
        <b>{{ r.title }}</b><br>
        <small>{{ r.description }}</small><br>
        <form method="post" action="/podcast/add">
          <input type="hidden" name="title" value="{{ r.title }}">
          <input type="hidden" name="rss" value="{{ r.rss }}">
          <input type="hidden" name="cover" value="{{ r.cover }}">
          <button type="submit">Add</button>
        </form>
        <div style="clear:both"></div>
      </div>
    {% endfor %}
  {% endif %}

  {% if saved %}
    <h3>Saved Podcasts</h3>
    <ul>
    {% for pid, title, rss, cover in saved %}
      <li>
        <a href="/podcast/{{ pid }}">
          {% if cover %}<img src="{{ cover }}" width="50">{% endif %}
          {{ title }}
        </a>
      </li>
    {% endfor %}
    </ul>
  {% endif %}
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)