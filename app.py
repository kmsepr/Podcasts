from flask import Flask, jsonify, render_template_string, request
import sqlite3, os, requests, feedparser
from datetime import datetime

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id=1),
            total INTEGER DEFAULT 0,
            last_added TEXT
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_total (id,total,last_added) VALUES(1,0,NULL)')
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER,
            added_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
init_db()

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
    # Format last_added
    if last_added:
        dt = datetime.strptime(last_added, "%Y-%m-%d %H:%M:%S")
        last_added = dt.strftime("%B %d %Y %H:%M:%S")
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number',0)
    try: number=int(number); assert number>0
    except: return jsonify({'error':'Enter positive number'}),400
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO swalath_entries (number,added_at) VALUES (?,?)',(number,now))
    c.execute('UPDATE swalath_total SET total=total+?,last_added=? WHERE id=1',(number,now))
    conn.commit()
    c.execute('SELECT total,last_added FROM swalath_total WHERE id=1')
    total,last_added=c.fetchone()
    conn.close()
    # Format last_added
    if last_added:
        dt = datetime.strptime(last_added, "%Y-%m-%d %H:%M:%S")
        last_added = dt.strftime("%B %d %Y %H:%M:%S")
    return jsonify({'total':total,'last_added':last_added})

@app.route('/api/swalath/entries')
def get_swalath_entries():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id,number,added_at FROM swalath_entries ORDER BY id DESC')
    rows=[]
    for r in c.fetchall():
        _id, number, added_at = r
        if added_at:
            dt = datetime.strptime(added_at, "%Y-%m-%d %H:%M:%S")
            added_at = dt.strftime("%B %d %Y %H:%M:%S")
        rows.append({'id':_id,'number':number,'added_at':added_at})
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
@app.route('/podcasts')
def podcast_page():
    return render_template_string(PODCAST_HTML)

@app.route('/api/search_podcasts')
def search_podcasts():
    query = request.args.get('query','').strip()
    if not query: return jsonify({'results':[]})
    url="https://itunes.apple.com/search"
    params={'term':query,'media':'podcast','limit':5}
    try:
        r=requests.get(url,params=params,timeout=10)
        data=r.json()
        results=[]
        for p in data.get('results',[]):
            results.append({
                'collectionName':p.get('collectionName'),
                'artistName':p.get('artistName'),
                'feedUrl':p.get('feedUrl'),
                'artworkUrl100':p.get('artworkUrl100')
            })
        return jsonify({'results':results})
    except: return jsonify({'results':[]})

@app.route('/api/podcast_feed')
def podcast_feed():
    feed_url = request.args.get('feedUrl','').strip()
    if not feed_url: return jsonify({'episodes':[]})
    try:
        feed=feedparser.parse(feed_url)
        episodes=[]
        for entry in feed.entries[:10]:
            audio=''
            for enc in entry.get('enclosures',[]):
                if enc.get('href','').startswith('http'): audio=enc['href']; break
            if not audio: continue
            episodes.append({
                'title':entry.get('title',''),
                'description':entry.get('summary','') or entry.get('description',''),
                'audio_url':audio,
                'pub_date':entry.get('published','')
            })
        return jsonify({'episodes':episodes})
    except: return jsonify({'episodes':[]})

# ---------------- Home ----------------
HOME_HTML = """..."""  # Your previous HOME_HTML without icons

SWALATH_HTML = """..."""  # Your previous Swalath HTML

PODCAST_HTML = """..."""  # Your previous Podcast HTML

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)