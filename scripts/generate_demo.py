"""
Gera HTML estático criptografado — réplica fiel do dashboard original com dados embutidos.
Todos os assets (CDNs, CSS, JS) são inlinados. Nenhuma chamada externa necessária.

Uso:
    python scripts/generate_demo.py --password minhasenha [--output docs/demo.html]
"""

import os, sys, json, time, base64, hashlib, subprocess, argparse, urllib.request, re

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "src", "visualization", "static", "index.html")

# ── CDNs ──────────────────────────────────────────────────────────────────────

CDN_SCRIPTS = [
    "https://cdn.tailwindcss.com",
    "https://cdn.jsdelivr.net/npm/chart.js",
    "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.0.0",
    "https://cdn.jsdelivr.net/npm/flatpickr",
    "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/pt.js",
]
CDN_STYLES = [
    "https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",
    "https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/dark.css",
]

# ── Servidor temporário ────────────────────────────────────────────────────────

def start_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.visualization.app:app",
         "--host", "127.0.0.1", "--port", "8765"],
        cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/api/patients", timeout=2)
            return proc
        except:
            time.sleep(0.5)
    raise RuntimeError("Servidor não iniciou em 15s")

def fetch_api(url):
    return json.loads(urllib.request.urlopen(url, timeout=15).read())

# ── Criptografia ───────────────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000, dklen=32)

def encrypt(plaintext: str, password: str) -> str:
    salt   = os.urandom(16)
    key    = derive_key(password, salt)
    data   = plaintext.encode("utf-8")
    cipher = bytearray(b ^ key[i % 32] for i, b in enumerate(data))
    return base64.b64encode(salt + bytes(cipher)).decode()

# ── Coleta de dados ────────────────────────────────────────────────────────────

def build_encrypted_payload(password: str) -> str:
    print("Iniciando servidor FastAPI...")
    proc = start_server()
    base = "http://127.0.0.1:8765"

    try:
        print("Coletando dados da API...")
        patients     = fetch_api(f"{base}/api/patients")
        patient      = patients[0] if patients else "marcelo"
        patient_data = fetch_api(f"{base}/api/data/{patient}")
        periods      = fetch_api(f"{base}/api/available-periods?patient={patient}")
        periods_list = periods.get("periods", [])
        mi_data      = fetch_api(f"{base}/api/smartband/{patient}/daily")
        correlation  = fetch_api(f"{base}/api/correlation/{patient}")
        ahi_heatmap  = fetch_api(f"{base}/api/cpap/{patient}/ahi-heatmap")

        cpap_by_month  = {}
        sleep_by_month = {}
        all_cpap_rows  = []
        all_sleep_rows = []
        year = month = None

        for p in periods_list:
            yr, mo = p["year"], p["month"]
            key = f"{yr}-{mo}"
            cr = fetch_api(f"{base}/api/cpap/{patient}/monthly?year={yr}&month={mo}").get("rows", [])
            sr = fetch_api(f"{base}/api/smartband/{patient}/monthly-sleep?year={yr}&month={mo}").get("rows", [])
            cpap_by_month[key]  = cr
            sleep_by_month[key] = sr
            all_cpap_rows.extend(cr)
            all_sleep_rows.extend(sr)
            print(f"  período {key}: {len(cr)} cpap, {len(sr)} sleep")

        if periods_list:
            year, month = periods_list[0]["year"], periods_list[0]["month"]

        payload = {
            "patient":      patient,
            "patientData":  patient_data,
            "miData":       mi_data,
            "periods":      periods_list,
            "year":         year,
            "month":        month,
            "cpapRows":     all_cpap_rows,
            "sleepRows":    all_sleep_rows,
            "cpapByMonth":  cpap_by_month,
            "sleepByMonth": sleep_by_month,
            "correlation":  correlation,
            "ahiHeatmap":   ahi_heatmap,
        }

        raw = json.dumps(payload, ensure_ascii=False, default=str)
        print(f"Payload: {len(raw):,} bytes — criptografando...")
        return encrypt(raw, password)

    finally:
        proc.terminate()
        proc.wait()

# ── Download de assets externos ────────────────────────────────────────────────

def download(url: str) -> str:
    name = url.split("/")[-1] or url.split("/")[-2]
    print(f"  GET {name}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")

def inline_cdn(html: str) -> str:
    html = re.sub(
        r'<link[^>]+href="(https?://[^"]+\.css)"[^>]*>',
        lambda m: f"<style>{download(m.group(1))}</style>",
        html,
    )
    html = re.sub(
        r'<script\s+src="(https?://[^"]+)"[^>]*></script>',
        lambda m: f"<script>{download(m.group(1))}</script>",
        html,
    )
    return html

def inline_local_assets(html: str) -> str:
    def replace_css(m):
        path = m.group(1).lstrip("/").replace("/", os.sep)
        full = os.path.join(BASE_DIR, "src", "visualization", path)
        return f"<style>{open(full, encoding='utf-8').read()}</style>" if os.path.exists(full) else m.group(0)

    def replace_js(m):
        path = m.group(1).lstrip("/").replace("/", os.sep)
        full = os.path.join(BASE_DIR, "src", "visualization", path)
        return f"<script>{open(full, encoding='utf-8').read()}</script>" if os.path.exists(full) else m.group(0)

    html = re.sub(r'<link[^>]+href="(/static/[^"]+\.css)"[^>]*>', replace_css, html)
    html = re.sub(r'<script\s+src="(/static/[^"]+\.js)"[^>]*></script>', replace_js, html)
    return html

# ── Blocos HTML / JS injetados ─────────────────────────────────────────────────

LOCK_CSS = """
#demo-lock {
    position: fixed; inset: 0; background: #0e1117; z-index: 9999;
    display: flex; align-items: center; justify-content: center;
}
#demo-lock.hide { display: none; }
"""

LOCK_HTML = """\
<div id="demo-lock">
  <div class="card text-center" style="max-width:360px;width:90%;padding:32px 28px;">
    <div style="font-size:42px;margin-bottom:12px;">🌙</div>
    <h2 class="text-xl font-semibold mb-1">Dashboard Apneia do Sono</h2>
    <p class="text-sm opacity-60 mb-5">Demonstração — insira a senha para desbloquear</p>
    <input id="demo-pwd" type="password" placeholder="Senha"
      class="w-full px-3 py-2 rounded bg-gray-800 border border-gray-600 text-white text-sm mb-3 outline-none focus:border-blue-500"
      onkeydown="if(event.key==='Enter')demoUnlock()">
    <button onclick="demoUnlock()"
      class="w-full py-2 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition">
      Desbloquear
    </button>
    <p id="demo-err" class="text-red-400 text-xs mt-3 hidden">Senha incorreta. Tente novamente.</p>
  </div>
</div>"""

# Injetado imediatamente após <body> — intercepta fetch() ANTES que app.js rode
PRE_LOCK_SCRIPT = """\
<script>
(function () {
  // Silencia chamadas à API enquanto a tela de bloqueio está ativa
  window._demoUnlocked = false;
  var _origFetch = window.fetch.bind(window);
  window.fetch = function (url) {
    if (window._demoUnlocked) return window._demoFetch(String(url));
    // Retorna resposta vazia para não gerar erros no console
    var u = String(url);
    var empty = {};
    if (u.includes('/api/patients')) empty = [];
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(empty); } });
  };
})();
</script>"""

# Injetado antes de </body> — lógica de desbloqueio e inicialização demo
POST_UNLOCK_SCRIPT_TPL = r"""
<script>
(function () {
var DEMO_ENC = "###ENCRYPTED###";

async function _deriveKey(pwd, salt) {
  var enc = new TextEncoder();
  var k = await crypto.subtle.importKey('raw', enc.encode(pwd),
    { name: 'PBKDF2' }, false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: salt, iterations: 100000, hash: 'SHA-256' }, k, 256));
}

async function _decrypt(enc, pwd) {
  var raw  = Uint8Array.from(atob(enc), function(c){ return c.charCodeAt(0); });
  var salt = raw.slice(0, 16);
  var data = raw.slice(16);
  var key  = await _deriveKey(pwd, salt);
  var out  = new Uint8Array(data.length);
  for (var i = 0; i < data.length; i++) out[i] = data[i] ^ key[i % 32];
  return new TextDecoder().decode(out);
}

window.demoUnlock = async function () {
  var pwd = document.getElementById('demo-pwd');
  var err = document.getElementById('demo-err');
  err.classList.add('hidden');
  try {
    var json = await _decrypt(DEMO_ENC, pwd.value);
    var D    = JSON.parse(json);
    document.getElementById('demo-lock').classList.add('hide');
    _demoInit(D);
  } catch (e) {
    err.classList.remove('hidden');
    pwd.value = '';
    pwd.focus();
  }
};

function _buildFetch(D) {
  return function (url) {
    var u = String(url);
    var data;
    if      (u.includes('/api/patients'))                         data = [D.patient];
    else if (u.match(/\/api\/data\//))                            data = D.patientData;
    else if (u.match(/\/api\/smartband\/[^/]+\/daily/))           data = D.miData;
    else if (u.match(/\/api\/smartband\/[^/]+\/monthly-sleep/)) {
      var ym = u.match(/year=(\d+)&month=(\d+)/);
      data = { rows: ym ? (D.sleepByMonth[ym[1]+'-'+ym[2]] || []) : D.sleepRows };
    } else if (u.match(/\/api\/cpap\/[^/]+\/monthly(\?|$)/)) {
      var ym = u.match(/year=(\d+)&month=(\d+)/);
      data = { rows: ym ? (D.cpapByMonth[ym[1]+'-'+ym[2]] || []) : D.cpapRows };
    } else if (u.includes('/api/available-periods'))              data = { periods: D.periods };
    else if (u.match(/\/api\/correlation\//))                     data = D.correlation;
    else if (u.match(/\/api\/cpap\/[^/]+\/ahi-heatmap/))          data = D.ahiHeatmap;
    else                                                          data = {};
    return Promise.resolve({ ok: true, json: function(){ return Promise.resolve(data); } });
  };
}

function _demoInit(D) {
  // Ativa o fetch mock com dados reais
  window._demoFetch    = _buildFetch(D);
  window._demoUnlocked = true;

  // Preenche select de paciente (necessário para listeners já registrados)
  var sel = document.getElementById('patientSelect');
  if (sel) {
    sel.innerHTML = '<option value="' + D.patient + '">' + D.patient + '</option>';
  }

  // Popula globals do app.js
  currentPatientData = D.patientData;
  currentMiData      = D.miData;

  if (D.patientData && D.patientData.timeseries && D.patientData.timeseries.data_sessao) {
    var dates = D.patientData.timeseries.data_sessao;
    globalSelectedDate = dates.length > 0 ? dates[dates.length - 1] : null;
    if (globalSelectedDate && typeof datePickerInstance !== 'undefined' && datePickerInstance) {
      try { datePickerInstance.setDate(globalSelectedDate); } catch(e) {}
    }
  }

  if (D.periods && D.periods.length) {
    availablePeriods = D.periods;
    updateDateSelectors();
    if (D.year && D.month) {
      currentYear  = D.year;
      currentMonth = D.month;
      var ys = document.getElementById('yearSelect');
      var ms = document.getElementById('monthSelect');
      if (ys) ys.value = String(D.year);
      if (ms) ms.value = String(D.month);
    }
  }

  // Popula tabelas
  if (D.cpapRows) {
    cpapData = D.cpapRows;
    sortState.cpap = { col: 'data_sessao', dir: 'desc' };
    updateSortIcons('cpap');
    sortTable('cpap', 'data_sessao', 'desc');
  }
  if (D.sleepRows) {
    sleepData = D.sleepRows.map(function(row) {
      var total = row.total_duration_min || 0;
      var rem   = row.rem_min || 0;
      return Object.assign({}, row, { rem_pct: total > 0 ? (rem / total) * 100 : 0 });
    });
    sortState.sleep = { col: 'report_date', dir: 'desc' };
    updateSortIcons('sleep');
    sortTable('sleep', 'report_date', 'desc');
  }

  // Renderiza gráficos e KPIs
  updateKPIs(D.patientData, D.miData);
  updateAverages(D.patientData, D.miData);
  renderGraficosCharts(D.patientData, D.miData);
  loadAhiHeatmap(D.patient);
}

})();
</script>"""


def generate():
    parser = argparse.ArgumentParser(description="Gera demo.html completamente auto-contido")
    parser.add_argument("--password", "-p", required=True, help="Senha para desbloquear a demo")
    parser.add_argument("--output", "-o", default=os.path.join(BASE_DIR, "docs", "demo.html"))
    args = parser.parse_args()

    encrypted = build_encrypted_payload(args.password)

    with open(INDEX_PATH, encoding="utf-8") as f:
        html = f.read()

    print("Inlinando assets locais (/static/css/, /static/js/)...")
    html = inline_local_assets(html)

    print("Baixando e inlinando CDNs...")
    html = inline_cdn(html)

    # Injeta CSS do lock no primeiro </style>
    html = html.replace("</style>", LOCK_CSS + "\n</style>", 1)

    # Após <body>: pré-script de lock + overlay
    html = html.replace(
        "<body",
        "<body",
        1,
    )
    body_open = html.index(">", html.index("<body")) + 1
    insert = "\n" + PRE_LOCK_SCRIPT + "\n" + LOCK_HTML + "\n"
    html = html[:body_open] + insert + html[body_open:]

    # Antes de </body>: script de desbloqueio com payload
    post = POST_UNLOCK_SCRIPT_TPL.replace("###ENCRYPTED###", encrypted)
    html = html.replace("</body>", post + "\n</body>")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"\n✓ {args.output}  ({size_kb:,.0f} KB)")
    print(f"  Payload cifrado: {len(encrypted):,} chars")
    print(f"  Senha: {args.password}")


if __name__ == "__main__":
    generate()
