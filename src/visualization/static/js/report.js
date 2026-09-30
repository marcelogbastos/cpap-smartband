// Relatório para consulta — página imprimível (/relatorio?patient=...&days=30)

const R = { charts: {} };
const params = new URLSearchParams(location.search);

const f = (v, nd = 1) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(nd).replace('.', ',');
const br = d => { if (!d) return '—'; const p = d.split('-'); return `${p[2]}/${p[1]}/${p[0]}`; };
const hm = h => { if (h === null || h === undefined) return '—'; const m = Math.round(h * 60); return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`; };

Chart.defaults.font.family = "'Segoe UI', Roboto, Arial, sans-serif";
Chart.defaults.font.size = 9;
Chart.defaults.color = '#374151';
Chart.defaults.animation = false;
Chart.defaults.devicePixelRatio = 2;   // nitidez na impressão

function stat(label, value, sub, cls) {
    return `<div class="stat"><div class="label">${label}</div><div class="value ${cls || ''}">${value}</div><div class="sub">${sub || ''}</div></div>`;
}

async function init() {
    const sel = document.getElementById('rPatient');
    const patients = await (await fetch('/api/patients')).json();
    sel.innerHTML = patients.map(p => `<option>${p}</option>`).join('');
    if (params.get('patient')) sel.value = params.get('patient');

    const period = document.getElementById('rPeriod');
    if (params.get('start') || params.get('end')) {
        period.value = 'custom';
        document.getElementById('rStart').value = params.get('start') || '';
        document.getElementById('rEnd').value = params.get('end') || '';
    } else if (params.get('days')) {
        period.value = [...period.options].some(o => o.value === params.get('days')) ? params.get('days') : '30';
    }
    toggleCustom();
    period.addEventListener('change', toggleCustom);
    document.getElementById('rApply').addEventListener('click', apply);
    sel.addEventListener('change', apply);
    document.getElementById('rPrint').addEventListener('click', () => window.print());
    load();
}

function toggleCustom() {
    document.getElementById('rCustom').style.display = document.getElementById('rPeriod').value === 'custom' ? '' : 'none';
}

function query() {
    const q = new URLSearchParams({ patient: document.getElementById('rPatient').value });
    const period = document.getElementById('rPeriod').value;
    if (period === 'custom') {
        const s = document.getElementById('rStart').value, e = document.getElementById('rEnd').value;
        if (s) q.set('start', s);
        if (e) q.set('end', e);
    } else {
        q.set('days', period);
    }
    return q;
}

function apply() {
    history.replaceState(null, '', `/relatorio?${query().toString()}`);
    load();
}

async function load() {
    const q = query();
    const patient = q.get('patient');
    q.delete('patient');
    document.getElementById('loading').style.display = '';
    document.getElementById('loading').textContent = 'Carregando relatório…';
    document.getElementById('report').style.display = 'none';
    try {
        const res = await fetch(`/api/report/${encodeURIComponent(patient)}?${q.toString()}`);
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        if (!data.days || !data.days.length) {
            document.getElementById('loading').textContent = 'Sem dados de CPAP no período.';
            return;
        }
        document.getElementById('loading').style.display = 'none';
        document.getElementById('report').style.display = '';
        render(data);
    } catch (e) {
        console.error(e);
        document.getElementById('loading').textContent = 'Erro ao carregar o relatório.';
    }
}

function render(d) {
    const s = d.summary, cs = d.current_settings || {};
    const mode = cs.mode === 1 ? 'AutoSet' : cs.mode === 0 ? 'CPAP fixo' : '—';
    document.title = `Relatório CPAP — ${d.patient} — ${br(s.start)} a ${br(s.end)}`;
    document.getElementById('r-patient').textContent = d.patient;
    document.getElementById('r-period').textContent = `${br(s.start)} a ${br(s.end)} (${s.days} dias)`;
    document.getElementById('r-device').textContent = `ResMed ${mode}`;
    document.getElementById('r-generated').textContent = new Date().toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    document.getElementById('r-minh').textContent = d.adherence_min_h;

    document.getElementById('r-stats').innerHTML = [
        stat('Adesão (noites ≥ 4 h)', `${f(s.adherence_pct, 0)}%`, `${s.nights_adherent} de ${s.days} dias · meta ${d.adherence_target}%`, s.adherence_ok ? 'good' : 'bad'),
        stat('Dias com uso', `${s.nights_used} / ${s.days}`, `${f(100 * s.nights_used / s.days, 0)}% dos dias · ${f(s.total_hours, 0)} h no total`),
        stat('Uso médio', hm(s.usage_avg_all_days_h), `por dia (sem uso = 0) · ${hm(s.usage_avg_used_nights_h)} por noite usada`),
        stat('IAH residual', f(s.ahi_avg), `eventos/h · mediana ${f(s.ahi_median)} · máx ${f(s.ahi_max)} · ${s.nights_ahi_ge_5} noites ≥ 5`, s.ahi_avg < 5 ? 'good' : 'bad'),
        stat('Fuga P95', `${f(s.leak95_avg)} L/min`, `média · máx ${f(s.leak95_max)} · ${s.nights_leak_gt_24} noites > 24 L/min`, s.leak95_avg <= 24 ? 'good' : 'bad'),
        stat('Pressão P95', `${f(s.press95_avg)} cmH₂O`, `média · P50 ${f(s.press50_avg)} · faixa ${f(s.set_min, 0)}–${f(s.set_max, 0)}`),
    ].join('');

    document.getElementById('r-obs').innerHTML = (d.observations || []).map(o => `<li class="${o.level}">${o.text}</li>`).join('')
        || '<li>Nenhum ponto de atenção no período.</li>';

    const rows = [
        ['IAH total', s.ahi_avg, true],
        ['Apneia central (IAC)', s.cai_avg],
        ['Apneia obstrutiva (IAO)', s.oai_avg],
        ['Apneia não classificada', s.uai_avg],
        ['Hipopneia (IH)', s.hi_avg],
    ];
    document.getElementById('r-events').innerHTML = rows.map(([l, v, b]) => `<tr><td>${b ? `<b>${l}</b>` : l}</td><td class="num">${b ? `<b>${f(v, 2)}</b>` : f(v, 2)}</td></tr>`).join('')
        + `<tr><td>Proporção central no IAH</td><td class="num"><b>${f(s.central_share_pct, 0)}%</b></td></tr>`;

    const changes = (d.settings_changes || []).filter(c => c.date >= s.start && c.date <= s.end);
    document.getElementById('r-settings').innerHTML = [
        ['Modo', mode],
        ['Faixa de pressão configurada', `${f(cs.set_min)} – ${f(cs.set_max)} cmH₂O`],
        ['EPR (alívio expiratório)', f(cs.epr, 0)],
        ['Pressão mediana (P50) média', `${f(s.press50_avg)} cmH₂O`],
        ['Pressão P95 média', `${f(s.press95_avg)} cmH₂O`],
        ['Noites com P95 no máximo', `${s.nights_press_at_max} de ${s.nights_used}`],
        ['Mudanças de configuração', changes.length ? changes.map(c => `${br(c.date)}: ${f(c.from.set_min, 0)}–${f(c.from.set_max, 0)} → ${f(c.to.set_min, 0)}–${f(c.to.set_max, 0)}`).join('; ') : 'nenhuma no período'],
    ].map(([k, v]) => `<tr><td>${k}</td><td class="num">${v}</td></tr>`).join('');

    document.getElementById('r-worst').innerHTML = (d.worst_nights || []).map(n => `<tr>
        <td>${br(n.date)}</td><td class="num">${hm(n.usage_h)}</td><td class="num"><b class="${n.ahi >= 5 ? 'bad' : ''}">${f(n.ahi)}</b></td>
        <td class="num">${f(n.cai)}</td><td class="num">${f(n.oai)}</td><td class="num">${f(n.hi)}</td>
        <td class="num">${f(n.leak95)}</td><td class="num">${f(n.press95)}</td></tr>`).join('')
        || '<tr><td colspan="8">Sem noites no período.</td></tr>';

    const sl = d.sleep;
    document.getElementById('r-sleep').innerHTML = sl ? `
        <div class="stats">
            ${stat('Noites registradas', sl.nights, `de ${s.days} dias do período`)}
            ${stat('Score do sono', f(sl.score_avg, 0), 'média (0–100)', sl.score_avg >= 80 ? 'good' : sl.score_avg >= 60 ? 'warn' : 'bad')}
            ${stat('Sono total', hm(sl.total_h_avg), 'média por noite')}
            ${stat('Profundo / REM', `${f(sl.deep_min_avg, 0)} / ${f(sl.rem_min_avg, 0)} min`, `leve ${f(sl.light_min_avg, 0)} min`)}
            ${stat('Acordado', `${f(sl.awake_min_avg, 0)} min`, 'média por noite')}
            ${stat('FC média no sono', sl.avg_hr ? `${f(sl.avg_hr, 0)} bpm` : '—', '')}
        </div>
        ${sl.nights < 0.5 * s.days ? `<p class="note">A pulseira registrou apenas ${sl.nights} das ${s.days} noites; as médias podem não representar o período.</p>` : ''}`
        : '<p class="note">Sem dados da pulseira no período.</p>';

    const days = d.days;
    const labels = days.map(x => { const p = x.date.split('-'); return `${p[2]}/${p[1]}`; });
    const common = { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { boxWidth: 8, font: { size: 8 } } } },
        scales: { x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } }, y: { beginAtZero: true, grid: { color: '#f3f4f6' } } } };

    for (const k of Object.keys(R.charts)) R.charts[k].destroy();
    R.charts.usage = new Chart(document.getElementById('rChartUsage'), {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Uso (h)', data: days.map(x => x.usage_h || 0), backgroundColor: days.map(x => x.usage_h >= d.adherence_min_h ? '#16a34a' : x.usage_h > 0 ? '#dc2626' : '#d1d5db') },
            { label: `${d.adherence_min_h} h`, type: 'line', data: days.map(() => d.adherence_min_h), borderColor: '#111827', borderDash: [4, 3], borderWidth: 1, pointRadius: 0 },
        ] },
        options: common,
    });
    const nz = k => days.map(x => x.used ? x[k] : null);
    R.charts.ahi = new Chart(document.getElementById('rChartAhi'), {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Obstrutiva', data: nz('oai'), backgroundColor: '#d97706', stack: 's' },
            { label: 'Central', data: nz('cai'), backgroundColor: '#7c3aed', stack: 's' },
            { label: 'Não classif.', data: nz('uai'), backgroundColor: '#9ca3af', stack: 's' },
            { label: 'Hipopneia', data: nz('hi'), backgroundColor: '#0284c7', stack: 's' },
        ] },
        options: { ...common, scales: { x: { ...common.scales.x, stacked: true }, y: { ...common.scales.y, stacked: true } } },
    });
}

init();
