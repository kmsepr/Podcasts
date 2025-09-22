from flask import Flask, jsonify, render_template_string, request
import sqlite3
import os
import requests

app = Flask(__name__)

DB_FILE = '/mnt/data/podcasts.db'
os.makedirs('/mnt/data', exist_ok=True)

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS swalath_total (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            total INTEGER DEFAULT 0
        )
    ''')
    c.execute('INSERT OR IGNORE INTO swalath_total (id, total) VALUES (1, 0)')
    conn.commit()
    conn.close()
init_db()

# ---------------- APIs ----------------
@app.route('/api/swalath/total')
def get_total_swalath():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT total FROM swalath_total WHERE id=1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/swalath/add', methods=['POST'])
def add_swalath():
    data = request.json
    number = data.get('number', 0)
    try:
        number = int(number)
        if number <= 0:
            raise ValueError
    except:
        return jsonify({'error': 'Enter a positive number'}), 400
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE swalath_total SET total = total + ? WHERE id=1', (number,))
    conn.commit()
    c.execute('SELECT total FROM swalath_total WHERE id=1')
    total = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total})

@app.route('/api/search_podcasts')
def search_podcasts():
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'results': []})
    url = "https://itunes.apple.com/search"
    params = {'term': query, 'media': 'podcast', 'limit': 10}
    try:
        r = requests.get(url, params=params, timeout=10)
        return jsonify(r.json())
    except:
        return jsonify({'results': []})

# ---------------- HTML ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Podcast & Swalath</title>
<style>
body{font-family:sans-serif;font-size:14px;margin:0;padding:0;background:#f7f7f7;color:#333}
.container{max-width:400px;margin:0 auto;padding:10px}
h3{margin-top:0;color:#444}
.card{background:#fff;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);padding:10px;margin-top:10px}
input,button{width:100%;padding:8px;margin:6px 0;border-radius:4px;border:1px solid #ccc;box-sizing:border-box}
button{background:#4CAF50;color:white;border:none;cursor:pointer;font-size:14px}
button:hover{background:#45a049}
.tiny{font-size:11px;color:#666}
audio{width:100%;margin-top:5px;border-radius:4px}

/* Tabs */
.tab {overflow: hidden;border-bottom: 1px solid #ccc;margin-top:10px;}
.tab button {background-color: inherit;float: left;border: none;outline: none;padding: 10px 16px;cursor: pointer;font-size: 14px;}
.tab button:hover {background-color: #ddd;}
.tab button.active {background-color: #4CAF50;color:white;}
.tabcontent {display: none;animation: fadeEffect 0.3s;}
@keyframes fadeEffect {from {opacity: 0;} to {opacity: 1;}}
</style>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
</head>
<body>

<div class="container">

  <div class="tab">
    <button class="tablinks active" onclick="openTab(event,'Swalath')">🙏 Add Swalath</button>
    <button class="tablinks" onclick="openTab(event,'Favorites')">⭐ Favorites</button>
  </div>

  <!-- Swalath Tab -->
  <div id="Swalath" class="tabcontent" style="display:block">
    <div class="card">
      <input type="number" id="swalathNumber" placeholder="Enter number of Swalath" min="1">
      <button onclick="submitSwalath()">➕ Add</button>
      <p>Total Swalath: <span id="swalathTotal">0</span></p>
    </div>
  </div>

  <!-- Favorites Tab -->
  <div id="Favorites" class="tabcontent">
    <input type="text" id="searchQuery" placeholder="Search podcasts...">
    <button onclick="searchPodcasts()">🔍 Search</button>
    <div id="favResults"></div>
  </div>

</div>

<script>
// Tabs
function openTab(evt, tabName){
  let i, tabcontent, tablinks;
  tabcontent = document.getElementsByClassName("tabcontent");
  for(i=0;i<tabcontent.length;i++){tabcontent[i].style.display="none";}
  tablinks = document.getElementsByClassName("tablinks");
  for(i=0;i<tablinks.length;i++){tablinks[i].className=tablinks[i].className.replace(" active","");}
  document.getElementById(tabName).style.display="block";
  evt.currentTarget.className += " active";
}

// Load current Swalath total
async function loadSwalathTotal(){
  let r = await fetch('/api/swalath/total');
  let d = await r.json();
  document.getElementById('swalathTotal').innerText = d.total;
}

// Submit number and increment total
async function submitSwalath(){
  let number = document.getElementById('swalathNumber').value;
  if(!number){ Swal.fire({icon:'error',title:'Error',text:'Enter a number'}); return; }
  let r = await fetch('/api/swalath/add', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({number})
  });
  let d = await r.json();
  if(r.ok){
    document.getElementById('swalathTotal').innerText = d.total;
    Swal.fire({icon:'success',title:'Added!',text:`Total: ${d.total}`,timer:1200,showConfirmButton:false});
    document.getElementById('swalathNumber').value='';
  } else {
    Swal.fire({icon:'error',title:'Error',text:d.error});
  }
}

// Search podcasts via iTunes API
async function searchPodcasts() {
  const query = document.getElementById('searchQuery').value.trim();
  if (!query) return;
  const r = await fetch(`/api/search_podcasts?query=${encodeURIComponent(query)}`);
  const data = await r.json();
  const o = document.getElementById('favResults');
  o.innerHTML = '';
  data.results.forEach(f => {
    let div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<b>${f.collectionName}</b><br>
                     <span class='tiny'>${f.artistName}</span><br>
                     <audio controls src="${f.previewUrl || ''}"></audio>`;
    o.appendChild(div);
  });
}

// On page load
loadSwalathTotal();
</script>

</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)