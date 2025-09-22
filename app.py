from flask import Flask, jsonify, render_template_string, request, redirect
import sqlite3, os, requests, feedparser
from datetime import datetime
import pytz

app = Flask(__name__)

# ---------------- Persistent DB ----------------
DB_FILE = 'podcasts.db'  # use local file in project folder for persistence
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
    # Only insert default row if table empty
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
        entry=feed.entries[0]  # only latest
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

# ---------------- HTML ----------------
# [Use your existing HOME_HTML, SWALATH_HTML, PODCAST_GRID_HTML, PODCAST_DETAIL_HTML here]

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)