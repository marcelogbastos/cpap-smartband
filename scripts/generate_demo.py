"""
Gera HTML estático criptografado — réplica fiel do dashboard original com dados embutidos.

Uso:
    python scripts/generate_demo.py --password minhasenha [--output docs/demo.html]
"""

import os, sys, json, time, base64, hashlib, subprocess, argparse, urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "src", "visualization", "static", "index.html")

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
    raise RuntimeError("Servidor não iniciou")

def fetch(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read())

def derive_key(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)

def encrypt(plaintext, password):
    salt = os.urandom(16)
    key = derive_key(password, salt)
    data = plaintext.encode('utf-8')
    cipher = bytearray(len(data))
    for i, b in enumerate(data):
        cipher[i] = b ^ key[i % 32]
    return base64.b64encode(salt + bytes(cipher)).decode()

def build_encrypted_payload(password):
    print("Iniciando servidor...")
    proc = start_server()
    base = "http://127.0.0.1:8765"

    try:
        print("Coletando dados...")
        patients = fetch(f"{base}/api/patients")
        patient = patients[0] if patients else "marcelo"

        patient_data = fetch(f"{base}/api/data/{patient}")
        periods = fetch(f"{base}/api/available-periods?patient={patient}")
        periods_list = periods.get("periods", [])

        cpap_rows = []
        sleep_rows = []
        year, month = None, None
        if periods_list:
            p = periods_list[0]
            year, month = p['year'], p['month']
            cpap_rows = fetch(f"{base}/api/cpap/{patient}/monthly?year={year}&month={month}").get("rows", [])
            sleep_rows = fetch(f"{base}/api/smartband/{patient}/monthly-sleep?year={year}&month={month}").get("rows", [])

        mi_data = fetch(f"{base}/api/smartband/{patient}/daily")

        payload = {
            "patient": patient,
            "patientData": patient_data,
            "miData": mi_data,
            "periods": periods_list,
            "year": year,
            "month": month,
            "cpapRows": cpap_rows,
            "sleepRows": sleep_rows
        }

        print("Criptografando...")
        plain = json.dumps(payload, ensure_ascii=False, default=str)
        return encrypt(plain, password)

    finally:
        proc.terminate()
        proc.wait()


LOCK_CSS = """
#demo-lock {
    position:fixed;inset:0;background:#0e1117;z-index:9999;
    display:flex;align-items:center;justify-content:center;
}
#demo-lock.hide{display:none;}
"""

LOCK_HTML = """
<div id="demo-lock">
    <div class="card text-center" style="max-width:360px;width:90%;padding:30px;">
        <div style="font-size:40px;margin-bottom:10px;">🔒</div>
        <h2 class="text-lg font-semibold mb-1">Dashboard Apneia do Sono</h2>
        <p class="text-sm opacity-60 mb-4">Demonstração — insira a senha</p>
        <input id="demo-pwd" type="password" placeholder="Senha"
            class="w-full px-3 py-2 rounded bg-gray-800 border border-gray-600 text-white text-sm mb-3 outline-none focus:border-blue-500"
            onkeydown="if(event.key==='Enter')demoUnlock()">
        <button onclick="demoUnlock()"
            class="w-full py-2 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition">
            Desbloquear
        </button>
        <p id="demo-err" class="text-red-400 text-xs mt-2 hidden">Senha incorreta</p>
    </div>
</div>
"""

INJECT_SCRIPT = r"""
const DEMO_ENC = "###ENCRYPTED###";

async function demoDeriveKey(password, salt) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey('raw', enc.encode(password), {name:'PBKDF2'}, false, ['deriveBits']);
    return crypto.subtle.deriveBits({name:'PBKDF2', salt, iterations:100000, hash:'SHA-256'}, key, 256);
}

async function demoDecrypt(encrypted, password) {
    const raw = Uint8Array.from(atob(encrypted), c=>c.charCodeAt(0));
    const salt = raw.slice(0,16);
    const data = raw.slice(16);
    const key = new Uint8Array(await demoDeriveKey(password, salt));
    const out = [];
    for(let i=0;i<data.length;i++) out.push(data[i] ^ key[i%32]);
    return new TextDecoder().decode(new Uint8Array(out));
}

async function demoUnlock() {
    const pwd = document.getElementById('demo-pwd');
    const err = document.getElementById('demo-err');
    err.classList.add('hidden');
    try {
        const json = await demoDecrypt(DEMO_ENC, pwd.value);
        const D = JSON.parse(json);
        document.getElementById('demo-lock').classList.add('hide');
        demoInit(D);
    } catch(e) {
        err.classList.remove('hidden');
        pwd.value = '';
        pwd.focus();
    }
}

function demoInit(D) {
    // Hide patient selector
    const sel = document.getElementById('patientSelect');
    if (sel) { sel.style.display = 'none'; }
    document.querySelectorAll('label[for="patientSelect"]').forEach(l => l.style.display = 'none');

    // Set global state
    currentPatientData = D.patientData;
    currentMiData = D.miData;

    // Set globalSelectedDate to most recent date
    if (D.patientData && D.patientData.timeseries && D.patientData.timeseries.data_sessao) {
        const dates = D.patientData.timeseries.data_sessao;
        if (dates.length > 0) {
            globalSelectedDate = dates[dates.length - 1];
        }
    }

    // Populate period selectors
    if (D.periods && D.periods.length) {
        availablePeriods = D.periods;
        updateDateSelectors();
        if (D.month && D.year) {
            currentMonth = D.month;
            currentYear = D.year;
            const ms = document.getElementById('monthSelect');
            const ys = document.getElementById('yearSelect');
            if (ms) ms.value = String(D.month);
            if (ys) ys.value = String(D.year);
        }
    }

    // Inject cpap data directly
    if (D.cpapRows) {
        cpapData = D.cpapRows;
        sortState.cpap = { col: 'data_sessao', dir: 'desc' };
        updateSortIcons('cpap');
        sortTable('cpap', 'data_sessao', 'desc');
    }

    // Inject sleep data with rem_pct
    if (D.sleepRows) {
        sleepData = D.sleepRows.map(row => {
            const total = row.total_duration_min || 0;
            const rem = row.rem_min || 0;
            return { ...row, rem_pct: total > 0 ? ((rem / total) * 100) : 0 };
        });
        sortState.sleep = { col: 'report_date', dir: 'desc' };
        updateSortIcons('sleep');
        sortTable('sleep', 'report_date', 'desc');
    }

    // Update KPIs, averages and charts using current app.js functions
    updateKPIs(D.patientData, D.miData);
    updateAverages(D.patientData, D.miData);
    renderGraficosCharts(D.patientData, D.miData);
}
"""


STATIC_DIR = os.path.join(BASE_DIR, "src", "visualization", "static")

def inline_assets(html):
    """Substitui referências a /static/... por conteúdo inline (CSS e JS locais)."""
    import re

    # Inline CSS: <link rel="stylesheet" href="/static/css/...">
    def replace_css(m):
        path = m.group(1).lstrip("/").replace("/", os.sep)
        full = os.path.join(BASE_DIR, "src", "visualization", path)
        if not os.path.exists(full):
            return m.group(0)
        content = open(full, encoding="utf-8").read()
        return f"<style>{content}</style>"

    html = re.sub(r'<link[^>]+href="(/static/[^"]+\.css)"[^>]*>', replace_css, html)

    # Inline JS: <script src="/static/js/...">
    def replace_js(m):
        path = m.group(1).lstrip("/").replace("/", os.sep)
        full = os.path.join(BASE_DIR, "src", "visualization", path)
        if not os.path.exists(full):
            return m.group(0)
        content = open(full, encoding="utf-8").read()
        return f"<script>{content}</script>"

    html = re.sub(r'<script\s+src="(/static/[^"]+\.js)"[^>]*></script>', replace_js, html)

    return html


def generate():
    parser = argparse.ArgumentParser(description="Gera HTML estático criptografado do dashboard")
    parser.add_argument("--password", "-p", required=True, help="Senha para desbloquear")
    parser.add_argument("--output", "-o", default=os.path.join(BASE_DIR, "docs", "demo.html"), help="Arquivo de saída")
    args = parser.parse_args()

    encrypted = build_encrypted_payload(args.password)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Inline /static/css/*.css e /static/js/*.js antes de qualquer modificação
    html = inline_assets(html)

    # Inject lock CSS no primeiro <style> inline
    html = html.replace("</style>", LOCK_CSS + "\n</style>", 1)

    # Inject lock HTML after <body>
    html = html.replace("<body>", "<body>\n" + LOCK_HTML)

    # Replace fetchPatients() call with demo init
    html = html.replace("fetchPatients();", INJECT_SCRIPT.replace("###ENCRYPTED###", encrypted))

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"OK — {args.output} ({size_kb:.0f} KB)")
    print(f"Tamanho payload criptografado: {len(encrypted)} chars")


if __name__ == "__main__":
    generate()
