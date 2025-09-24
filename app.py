from flask import Flask, render_template_string, request, redirect
import sqlite3, os, requests, feedparser

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
            rss TEXT,
            cover TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML Templates ----------------
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
.saved-item button{width:48%;padding:10px;font-size:16px;margin-top:6px;margin-right:4px;}
.podcast{background:white;color:black;border-radius:12px;padding:12px;margin:10px 0;box-shadow:0 2px 6px rgba(0,0,0,0.1);}
.podcast img{border-radius:8px;float:left;margin-right:10px;width:70px;}
.podcast b{font-size:16px;}
.podcast small{color:#555;display:block;margin-top:4px;}
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
        <div>
          <a href="/podcast/{{ pid }}"><button style="background:#4CAF50;color:white;">Open</button></a>
          <form method="post" action="/podcast/delete/{{ pid }}" style="display:inline;">
            <button type="submit" style="background:#dc2626;color:white;">Delete</button>
          </form>
        </div>
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

# ---------------- Podcast Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return redirect("/podcast")

@app.route("/podcast", methods=["GET","POST"])
def podcast_search():
    if request.method=="POST":
        title=request.form.get("title")
        rss=request.form.get("rss")
        cover=request.form.get("cover")
        if rss:  # save only if RSS exists
            conn=sqlite3.connect(DB_FILE)
            c=conn.cursor()
            c.execute("INSERT INTO podcasts (title,rss,cover) VALUES (?,?,?)",(title,rss,cover))
            conn.commit()
            conn.close()
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
    conn=sqlite3.connect(DB_FILE)
    c=conn.cursor()
    c.execute("SELECT title,rss,cover FROM podcasts WHERE id=?",(pid,))
    r=c.fetchone()
    conn.close()
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

@app.route("/podcast/delete/<int:pid>", methods=["POST"])
def podcast_delete(pid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM podcasts WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return redirect("/podcast")

# ---------------- Run App ----------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
