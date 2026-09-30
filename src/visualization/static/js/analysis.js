// ═══════════════════════════════════════════════════════════════════════════════
//  Abas de análise: Tendências, Noite detalhada, Explorador de correlações
//  (depende de Chart.js, de formatDateBR em charts.js e do #patientSelect)
// ═══════════════════════════════════════════════════════════════════════════════

const A_COLORS = {
    obstrutiva: '#f59e0b', central: '#a78bfa', nao_classificada: '#94a3b8',
    hipopneia: '#38bdf8', despertar: '#6b7280',
    profundo: '#6366f1', rem: '#22d3ee', leve: '#4ade80', acordado: '#f87171',
    good: '#22c55e', bad: '#ef4444', warn: '#facc15', line: '#e5e7eb', grid: 'rgba(255,255,255,0.06)',
};
const EVENT_LABELS = {
    obstrutiva: 'Obstrutiva', central: 'Central', nao_classificada: 'Não classif.',
    hipopneia: 'Hipopneia', despertar: 'Despertar',
};
const STAGE_LABELS = { acordado: 'Acordado', rem: 'REM', leve: 'Leve', profundo: 'Profundo', sem_registro: 'Fora do sono registrado' };

const aCharts = {};
const aState = { trendsFor: null, nightsFor: null, nights: [], matrixFor: null, matrix: null };

function aPatient() { return document.getElementById('patientSelect').value; }
function aUrl(path) { return path.replace('{p}', encodeURIComponent(aPatient())); }

async function aFetch(path) {
    const res = await fetch(aUrl(path));
    if (!res.ok) throw new Error(`${res.status} em ${path}`);
    return res.json();
}

function aChart(id, config) {
    if (aCharts[id]) { aCharts[id].destroy(); delete aCharts[id]; }
    const el = document.getElementById(id);
    if (!el) return null;
    config.options = config.options || {};
    config.options.plugins = Object.assign({ datalabels: { display: false } }, config.options.plugins || {});
    config.options.maintainAspectRatio = false;
    config.options.responsive = true;
    aCharts[id] = new Chart(el.getContext('2d'), config);
    return aCharts[id];
}

const fmt = (v, nd = 1) => (v === null || v === undefined || Number.isNaN(v)) ? '--' : Number(v).toFixed(nd);
const ddmm = (d) => { const p = d.split('-'); return `${p[2]}/${p[1]}`; };
const hhmm = (ms) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
// horários vêm como hora local sem fuso ("2026-09-29T01:29:58") → new Date() interpreta como local
const tms = (s) => new Date(s).getTime();

function kpiCard(title, value, unit, sub, color) {
    return `<div class="card text-center">
        <div class="kpi-title">${title}</div>
        <div class="font-bold text-lg ${color || 'text-white'}">${value}</div>
        <div class="text-[10px] opacity-50">${unit || ''}</div>
        ${sub ? `<div class="text-[10px] text-gray-400 mt-1">${sub}</div>` : ''}
    </div>`;
}

const gridOpts = { color: A_COLORS.grid };

// repete o último valor conhecido nos dias sem uso (a configuração não muda por não usar)
function fillForward(arr) {
    let last = null;
    const out = arr.map(v => (v === null || v === undefined) ? last : (last = v));
    const first = out.find(v => v !== null);
    return out.map(v => v === null ? first : v);
}

// marcas do eixo de tempo em horas cheias e meias-horas
function halfHourTicks(axis) {
    const step = (axis.max - axis.min) > 6 * 3600000 ? 3600000 : 1800000;
    const ticks = [];
    for (let t = Math.ceil(axis.min / step) * step; t <= axis.max; t += step) ticks.push({ value: t });
    axis.ticks = ticks;
}

// ─── TENDÊNCIAS ────────────────────────────────────────────────────────────────

async function loadTrends(force = false) {
    const patient = aPatient();
    if (!patient) return;
    const period = document.getElementById('trendPeriod').value;
    const key = `${patient}|${period}`;
    if (!force && aState.trendsFor === key) return;
    aState.trendsFor = key;

    document.getElementById('trend-loading').classList.remove('hidden');
    document.getElementById('trend-content').classList.add('hidden');
    try {
        const q = period !== '0' ? `?days=${period}` : '';
        const data = await aFetch(`/api/trends/{p}${q}`);
        document.getElementById('trend-loading').classList.add('hidden');
        if (!data.days || !data.days.length) {
            document.getElementById('trend-loading').textContent = 'Sem dados de CPAP.';
            document.getElementById('trend-loading').classList.remove('hidden');
            return;
        }
        document.getElementById('trend-content').classList.remove('hidden');
        renderTrends(data);
    } catch (e) {
        console.error('Erro em tendências', e);
        document.getElementById('trend-loading').textContent = 'Erro ao carregar tendências.';
    }
}

function renderTrends(data) {
    const s = data.summary, days = data.days;
    document.getElementById('trend-range').textContent = `${formatDateBR(s.start)} a ${formatDateBR(s.end)} · ${s.days} dias`;

    const adhColor = s.adherence_pct >= data.adherence_target ? 'text-green-400' : 'text-red-400';
    const ahiColor = s.ahi_median < 5 ? 'text-green-400' : s.ahi_median < 15 ? 'text-yellow-400' : 'text-red-400';
    const cenColor = s.central_share_pct >= 50 ? 'text-yellow-400' : 'text-gray-200';
    document.getElementById('trend-kpis').innerHTML = [
        kpiCard('Adesão', `${fmt(s.adherence_pct, 0)}%`, `noites ≥ ${data.adherence_min_h} h`, `${s.nights_adherent} de ${s.days} dias · meta ${data.adherence_target}%`, adhColor),
        kpiCard('Uso médio', `${fmt(s.usage_avg_all_days_h)} h`, 'todos os dias', `mediana ${fmt(s.usage_median_used_nights_h)} h nas ${s.nights_used} noites usadas`),
        kpiCard('IAH', fmt(s.ahi_median), 'mediana ev/h', `média pond. ${fmt(s.ahi_avg)} · ${s.nights_ahi_ge_5} noites ≥ 5`, ahiColor),
        kpiCard('Apneia central', `${fmt(s.central_share_pct, 0)}%`, 'do IAH', `mediana: IAC ${fmt(s.cai_median, 1)} · IAO ${fmt(s.oai_median, 1)} · IH ${fmt(s.hi_median, 1)}`, cenColor),
        kpiCard('Fuga P95', fmt(s.leak95_median), 'L/min (mediana)', `máx ${fmt(s.leak95_max)} · ${s.nights_leak_gt_24} noites > 24`, s.leak95_median <= 24 ? 'text-green-400' : 'text-red-400'),
        kpiCard('Pressão P95', fmt(s.press95_median), 'cmH₂O (mediana)', `faixa ${fmt(s.set_min, 0)}–${fmt(s.set_max, 0)} · no máx. em ${s.nights_press_at_max} noites`, s.nights_used && s.nights_press_at_max / s.nights_used >= 0.1 ? 'text-yellow-400' : 'text-white'),
    ].join('');

    const icon = { ok: '🟢', alerta: '🔴', atencao: '🟡' };
    document.getElementById('trend-observations').innerHTML = (data.observations || [])
        .map(o => `<li class="flex gap-2"><span>${icon[o.level] || '•'}</span><span class="text-gray-300">${o.text}</span></li>`).join('')
        || '<li class="text-gray-500">Nenhum ponto de atenção.</li>';

    const labels = days.map(d => ddmm(d.date));
    const pick = (k, onlyUsed = true) => days.map(d => (onlyUsed && !d.used) ? null : d[k]);
    const xTicks = { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 };
    const tooltipTitle = { callbacks: { title: (items) => formatDateBR(days[items[0].dataIndex].date) } };

    aChart('chartEventTypes', {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Obstrutiva', data: pick('oai'), backgroundColor: A_COLORS.obstrutiva, stack: 'e' },
            { label: 'Central', data: pick('cai'), backgroundColor: A_COLORS.central, stack: 'e' },
            { label: 'Não classif.', data: pick('uai'), backgroundColor: A_COLORS.nao_classificada, stack: 'e' },
            { label: 'Hipopneia', data: pick('hi'), backgroundColor: A_COLORS.hipopneia, stack: 'e' },
            { label: 'IAH 30 dias', data: pick('ahi_30', false), type: 'line', borderColor: A_COLORS.line, borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
        ] },
        options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: tooltipTitle, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: { stacked: true, ticks: xTicks, grid: gridOpts }, y: { stacked: true, title: { display: true, text: 'ev/h' }, grid: gridOpts } } },
    });

    aChart('chartAdherence', {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Uso (h)', data: days.map(d => d.usage_h || null), yAxisID: 'y',
              backgroundColor: days.map(d => d.usage_h >= data.adherence_min_h ? A_COLORS.good : A_COLORS.bad) },
            { label: 'Adesão 30 dias (%)', data: pick('adherence_30', false), type: 'line', yAxisID: 'y1', borderColor: A_COLORS.line, borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
            { label: `Meta ${data.adherence_target}%`, data: days.map(() => data.adherence_target), type: 'line', yAxisID: 'y1', borderColor: A_COLORS.warn, borderDash: [5, 4], borderWidth: 1, pointRadius: 0 },
        ] },
        options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: tooltipTitle, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: { ticks: xTicks, grid: gridOpts },
                y: { beginAtZero: true, title: { display: true, text: 'horas' }, grid: gridOpts },
                y1: { position: 'right', min: 0, max: 100, title: { display: true, text: '%' }, grid: { display: false } } } },
    });

    aChart('chartPressure', {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Mín. configurada', data: fillForward(pick('set_min')), borderColor: 'rgba(96,165,250,0.4)', borderWidth: 1, pointRadius: 0, stepped: true },
            { label: 'Máx. configurada', data: fillForward(pick('set_max')), borderColor: 'rgba(96,165,250,0.4)', backgroundColor: 'rgba(96,165,250,0.10)', fill: '-1', borderWidth: 1, pointRadius: 0, stepped: true },
            { label: 'P50', data: pick('press50'), borderColor: '#93c5fd', borderWidth: 1.5, pointRadius: 0, spanGaps: true },
            { label: 'P95', data: pick('press95'), borderColor: '#f9fafb', borderWidth: 1.5, pointRadius: days.map(d => d.press_at_max ? 3.5 : 0),
              pointBackgroundColor: A_COLORS.bad, pointBorderColor: A_COLORS.bad, spanGaps: true },
        ] },
        options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: tooltipTitle, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: { ticks: xTicks, grid: gridOpts }, y: { title: { display: true, text: 'cmH₂O' }, grid: gridOpts,
                suggestedMin: (s.set_min ?? 4) - 1, suggestedMax: (s.set_max ?? 20) + 1 } } },
    });

    aChart('chartLeakTrend', {
        type: 'line',
        data: { labels, datasets: [
            { label: 'Fuga P95', data: pick('leak95'), showLine: false, pointRadius: 2.5,
              pointBackgroundColor: days.map(d => d.leak95 > 24 ? A_COLORS.bad : '#60a5fa'), borderColor: '#60a5fa' },
            { label: 'Média 7 dias', data: pick('leak95_7', false), borderColor: '#f9fafb', borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
            { label: 'Média 30 dias', data: pick('leak95_30', false), borderColor: A_COLORS.warn, borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
            { label: 'Limite 24 L/min', data: days.map(() => 24), borderColor: A_COLORS.bad, borderDash: [5, 4], borderWidth: 1, pointRadius: 0 },
        ] },
        options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: tooltipTitle, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: { ticks: xTicks, grid: gridOpts }, y: { beginAtZero: true, title: { display: true, text: 'L/min' }, grid: gridOpts } } },
    });

    aChart('chartRolling', {
        type: 'line',
        data: { labels, datasets: [
            { label: 'IAH 7 dias', data: pick('ahi_7', false), borderColor: '#f9fafb', borderWidth: 1.5, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
            { label: 'IAH 30 dias', data: pick('ahi_30', false), borderColor: A_COLORS.central, borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
            { label: 'Uso médio 30 dias (h)', data: pick('usage_30', false), borderColor: A_COLORS.good, borderWidth: 1.5, pointRadius: 0, tension: 0.3, yAxisID: 'y1' },
        ] },
        options: { interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: tooltipTitle, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: { ticks: xTicks, grid: gridOpts },
                y: { beginAtZero: true, title: { display: true, text: 'IAH (ev/h)' }, grid: gridOpts },
                y1: { position: 'right', beginAtZero: true, title: { display: true, text: 'horas' }, grid: { display: false } } } },
    });

    const cs = data.current_settings || {};
    const modeName = cs.mode === 1 ? 'AutoSet' : cs.mode === 0 ? 'CPAP fixo' : `modo ${cs.mode}`;
    let txt = `Configuração atual: ${modeName}, pressão ${fmt(cs.set_min, 1)}–${fmt(cs.set_max, 1)} cmH₂O, EPR ${cs.epr_on === 0 ? `desligado (nível ${fmt(cs.epr, 0)} configurado)` : fmt(cs.epr, 0)}.`;
    txt += data.settings_changes.length
        ? ' Mudanças: ' + data.settings_changes.map(c => `${formatDateBR(c.date)} (${fmt(c.from.set_min, 0)}–${fmt(c.from.set_max, 0)} → ${fmt(c.to.set_min, 0)}–${fmt(c.to.set_max, 0)} cmH₂O, EPR ${fmt(c.from.epr, 0)} → ${fmt(c.to.epr, 0)})`).join('; ')
        : ' Sem mudanças de configuração no histórico.';
    document.getElementById('trend-settings').textContent = txt;
}

document.getElementById('trendPeriod').addEventListener('change', () => loadTrends(true));

// ─── NOITE DETALHADA ───────────────────────────────────────────────────────────

// Plugin: sombreia os intervalos com a máscara em uso
const sessionShade = {
    id: 'sessionShade',
    beforeDatasetsDraw(chart, args, opts) {
        if (!opts || !opts.ranges) return;
        const { ctx, chartArea, scales: { x } } = chart;
        ctx.save();
        ctx.fillStyle = opts.color || 'rgba(96,165,250,0.08)';
        for (const [a, b] of opts.ranges) {
            const x0 = Math.max(x.getPixelForValue(a), chartArea.left);
            const x1 = Math.min(x.getPixelForValue(b), chartArea.right);
            if (x1 > x0) ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
        }
        ctx.restore();
    },
};

async function loadNightDates(force = false) {
    const patient = aPatient();
    if (!patient) return;
    if (!force && aState.nightsFor === patient) return;
    aState.nightsFor = patient;
    const sel = document.getElementById('nightSelect');
    try {
        const data = await aFetch('/api/night/{p}/dates');
        aState.nights = data.nights || [];
        const mark = n => n.cpap && n.sleep ? '🟢' : n.cpap ? '🔵' : '🟣';
        const wd = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
        sel.innerHTML = aState.nights.slice().reverse().map(n => {
            const d = new Date(n.date + 'T12:00:00');
            return `<option value="${n.date}">${mark(n)} ${formatDateBR(n.date)} (${wd[d.getDay()]})</option>`;
        }).join('');
        if (!aState.nights.length) {
            document.getElementById('night-loading').classList.add('hidden');
            document.getElementById('night-empty').classList.remove('hidden');
            return;
        }
        // noite inicial: a selecionada no Resumo, senão a última com as duas fontes
        const dates = aState.nights.map(n => n.date);
        let initial = (typeof globalSelectedDate !== 'undefined' && dates.includes(globalSelectedDate)) ? globalSelectedDate : null;
        if (!initial) {
            const both = aState.nights.filter(n => n.cpap && n.sleep);
            initial = (both.length ? both[both.length - 1] : aState.nights[aState.nights.length - 1]).date;
        }
        sel.value = initial;
        loadNight(initial);
    } catch (e) {
        console.error('Erro ao listar noites', e);
        document.getElementById('night-loading').textContent = 'Erro ao carregar a lista de noites.';
    }
}

function stepNight(delta) {
    const sel = document.getElementById('nightSelect');
    const i = sel.selectedIndex - delta;   // lista em ordem decrescente
    if (i >= 0 && i < sel.options.length) { sel.selectedIndex = i; loadNight(sel.value); }
}
document.getElementById('nightSelect').addEventListener('change', e => loadNight(e.target.value));
document.getElementById('night-prev').addEventListener('click', () => stepNight(-1));
document.getElementById('night-next').addEventListener('click', () => stepNight(1));

async function loadNight(date) {
    document.getElementById('night-loading').classList.remove('hidden');
    document.getElementById('night-loading').textContent = 'Carregando noite...';
    document.getElementById('night-empty').classList.add('hidden');
    document.getElementById('night-content').classList.add('hidden');
    try {
        const n = await aFetch(`/api/night/{p}/${date}`);
        document.getElementById('night-loading').classList.add('hidden');
        if (!n.has_data) { document.getElementById('night-empty').classList.remove('hidden'); return; }
        document.getElementById('night-content').classList.remove('hidden');
        renderNight(n);
    } catch (e) {
        console.error('Erro na noite', e);
        document.getElementById('night-loading').textContent = 'Erro ao carregar a noite.';
    }
}

// quebra a linha entre sessões (evita ligar o fim de uma sessão ao início da outra)
function withGaps(points, maxGapMs = 90000) {
    const out = [];
    let prev = null;
    for (const p of points) {
        const x = tms(p.t);
        if (prev !== null && x - prev > maxGapMs) out.push({ x: (x + prev) / 2, y: null });
        out.push({ x, y: p.v });
        prev = x;
    }
    return out;
}

function renderNight(n) {
    const c = n.cpap_summary || {}, sl = n.sleep_summary || {}, ec = n.event_counts || {};
    const x0 = tms(n.window.start), x1 = tms(n.window.end);
    const ranges = n.sessions.map(s => [tms(s.start), tms(s.end)]);
    const usageMin = n.sessions.reduce((a, s) => a + (tms(s.end) - tms(s.start)) / 60000, 0);
    const hm = m => `${Math.floor(m / 60)}h ${String(Math.round(m % 60)).padStart(2, '0')}m`;

    document.getElementById('night-kpis').innerHTML = [
        kpiCard('Uso do CPAP', n.sessions.length ? hm(usageMin) : '--', `${n.sessions.length} sessão(ões)`, n.sessions.length ? `${hhmm(ranges[0][0])} – ${hhmm(ranges[ranges.length - 1][1])}` : ''),
        kpiCard('IAH', fmt(c.ahi), 'eventos/h', `central ${fmt(c.cai)} · obstr. ${fmt(c.oai)} · hipo ${fmt(c.hi)}`, c.ahi === undefined ? '' : c.ahi < 5 ? 'text-green-400' : 'text-yellow-400'),
        kpiCard('Eventos', (ec.central || 0) + (ec.obstrutiva || 0) + (ec.hipopneia || 0) + (ec.nao_classificada || 0), 'apneias + hipopneias', `${ec.central || 0} centr. · ${ec.obstrutiva || 0} obstr. · ${ec.hipopneia || 0} hipo`),
        kpiCard('Fuga P95', fmt(c.leak95), 'L/min', `máx ${fmt(c.leak_max)}`, c.leak95 === undefined ? '' : c.leak95 <= 24 ? 'text-green-400' : 'text-red-400'),
        kpiCard('Pressão P95', fmt(c.press95), 'cmH₂O', `P50 ${fmt(c.press50)} · faixa ${fmt(c.set_min, 0)}–${fmt(c.set_max, 0)}`),
        kpiCard('Score do sono', sl.sleep_score ?? '--', 'pulseira', sl.total_duration_min ? `${hm(sl.total_duration_min)} dormindo` : 'sem dados da pulseira', sl.sleep_score >= 80 ? 'text-green-400' : sl.sleep_score >= 60 ? 'text-yellow-400' : sl.sleep_score ? 'text-red-400' : ''),
        kpiCard('Fases', sl.deep_min !== undefined ? `${sl.deep_min}/${sl.rem_min}` : '--', 'min profundo / REM', sl.light_min !== undefined ? `leve ${sl.light_min} · acordado ${sl.awake_min}` : ''),
        kpiCard('FC no sono', sl.avg_hr ? sl.avg_hr : '--', 'bpm (média)', sl.min_hr ? `mín ${sl.min_hr} · SpO₂ méd. ${sl.avg_spo2 ?? '--'}%` : ''),
    ].join('');

    const xScale = { type: 'linear', min: x0, max: x1, afterBuildTicks: halfHourTicks,
        ticks: { callback: v => hhmm(v), autoSkip: true, maxRotation: 0 }, grid: gridOpts };
    const shade = { ranges };
    const tipTime = { callbacks: { title: items => items.length ? hhmm(items[0].parsed.x) : '' } };

    // Hipnograma (barras flutuantes horizontais)
    const order = ['acordado', 'rem', 'leve', 'profundo'];
    aChart('chartHypnogram', {
        type: 'bar',
        data: { labels: order.map(k => STAGE_LABELS[k]), datasets: order.map(k => ({
            label: STAGE_LABELS[k], backgroundColor: A_COLORS[k], borderSkipped: false, barPercentage: 0.9, categoryPercentage: 1,
            data: n.stages.filter(s => s.stage === k).map(s => ({ y: STAGE_LABELS[k], x: [tms(s.start), tms(s.end)] })),
        })) },
        options: { indexAxis: 'y', grouped: false,
            plugins: { legend: { display: false }, sessionShade: shade,
                tooltip: { callbacks: { title: () => '', label: ctx => `${ctx.dataset.label}: ${hhmm(ctx.raw.x[0])} – ${hhmm(ctx.raw.x[1])}` } } },
            scales: { x: xScale, y: { grid: gridOpts } } },
        plugins: [sessionShade],
    });

    // Eventos
    const evTypes = ['obstrutiva', 'central', 'nao_classificada', 'hipopneia', 'despertar'];
    aChart('chartNightEvents', {
        type: 'scatter',
        data: { datasets: evTypes.map(t => ({
            label: EVENT_LABELS[t], backgroundColor: A_COLORS[t], borderColor: A_COLORS[t],
            data: n.events.filter(e => e.type === t).map(e => ({ x: tms(e.t), y: EVENT_LABELS[t], d: e.duration_s, st: e.stage })),
            pointRadius: ctx => { const d = ctx.raw && ctx.raw.d; return d ? Math.min(3 + d / 4, 9) : 3.5; },
        })) },
        options: {
            plugins: { legend: { display: false }, sessionShade: shade,
                tooltip: { callbacks: { title: items => items.length ? hhmm(items[0].parsed.x) : '',
                    label: ctx => `${ctx.dataset.label}${ctx.raw.d ? ` · ${ctx.raw.d}s` : ''}${ctx.raw.st ? ` · fase: ${STAGE_LABELS[ctx.raw.st]}` : ''}` } } },
            scales: { x: xScale, y: { type: 'category', labels: evTypes.map(t => EVENT_LABELS[t]), offset: true, grid: gridOpts } } },
        plugins: [sessionShade],
    });

    const sg = n.signals || {};
    aChart('chartNightPressure', {
        type: 'line',
        data: { datasets: [
            { label: 'Pressão na máscara', data: withGaps(sg.mask_press || []), borderColor: '#f9fafb', borderWidth: 1.2, pointRadius: 0, yAxisID: 'y' },
            { label: 'Fuga (L/min)', data: withGaps(sg.leak || []), borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.15)', fill: 'origin', borderWidth: 1, pointRadius: 0, yAxisID: 'y1' },
        ] },
        options: { interaction: { mode: 'nearest', axis: 'x', intersect: false },
            plugins: { sessionShade: shade, tooltip: tipTime, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: xScale, y: { title: { display: true, text: 'cmH₂O' }, grid: gridOpts, suggestedMin: 4 },
                y1: { position: 'right', beginAtZero: true, suggestedMax: 30, title: { display: true, text: 'L/min' }, grid: { display: false } } } },
        plugins: [sessionShade],
    });

    aChart('chartNightBreath', {
        type: 'line',
        data: { datasets: [
            { label: 'Freq. respiratória (rpm)', data: withGaps(sg.resp_rate || []), borderColor: '#93c5fd', borderWidth: 1.2, pointRadius: 0, yAxisID: 'y' },
            { label: 'Ronco', data: withGaps(sg.snore || []), borderColor: A_COLORS.obstrutiva, borderWidth: 1, pointRadius: 0, yAxisID: 'y1' },
            { label: 'Limitação de fluxo', data: withGaps(sg.flow_lim || []), borderColor: A_COLORS.central, borderWidth: 1, pointRadius: 0, yAxisID: 'y1' },
        ] },
        options: { interaction: { mode: 'nearest', axis: 'x', intersect: false },
            plugins: { sessionShade: shade, tooltip: tipTime, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: xScale, y: { beginAtZero: true, title: { display: true, text: 'rpm' }, grid: gridOpts },
                y1: { position: 'right', min: 0, max: 1, title: { display: true, text: 'índice 0–1' }, grid: { display: false } } } },
        plugins: [sessionShade],
    });

    const vit = [
        { label: 'FC pulseira (bpm)', data: (n.heart_rate || []).map(p => ({ x: tms(p.t), y: p.v })), borderColor: '#f87171', backgroundColor: '#f87171', borderWidth: 1.5, pointRadius: 2.5, yAxisID: 'y' },
        { label: 'SpO₂ pulseira (%)', data: (n.spo2 || []).map(p => ({ x: tms(p.t), y: p.v })), borderColor: '#22d3ee', backgroundColor: '#22d3ee', borderWidth: 1.5, pointRadius: 2.5, yAxisID: 'y1' },
    ];
    if (n.oximetry) {
        vit.push({ label: 'Pulso oxímetro', data: withGaps(n.oximetry.pulse || []), borderColor: 'rgba(248,113,113,0.5)', borderWidth: 1, pointRadius: 0, yAxisID: 'y' });
        vit.push({ label: 'SpO₂ oxímetro', data: withGaps(n.oximetry.spo2 || []), borderColor: 'rgba(34,211,238,0.5)', borderWidth: 1, pointRadius: 0, yAxisID: 'y1' });
    }
    aChart('chartNightVitals', {
        type: 'line',
        data: { datasets: vit },
        options: { interaction: { mode: 'nearest', axis: 'x', intersect: false },
            plugins: { sessionShade: shade, tooltip: tipTime, legend: { labels: { boxWidth: 10, font: { size: 10 } } } },
            scales: { x: xScale, y: { title: { display: true, text: 'bpm' }, grid: gridOpts, suggestedMin: 40, suggestedMax: 90 },
                y1: { position: 'right', suggestedMin: 85, max: 100, title: { display: true, text: 'SpO₂ %' }, grid: { display: false } } } },
        plugins: [sessionShade],
    });

    const rows = n.events_by_stage || [];
    document.getElementById('nightStageBody').innerHTML = rows.length
        ? rows.map(r => `<tr class="border-b border-gray-800">
            <td class="px-3 py-2"><span class="inline-block w-2.5 h-2.5 rounded-sm mr-2" style="background:${A_COLORS[r.stage] || '#6b7280'}"></span>${STAGE_LABELS[r.stage] || r.stage}</td>
            <td class="px-3 py-2">${r.hours_on_cpap !== null ? hm(r.hours_on_cpap * 60) : '--'}</td>
            <td class="px-3 py-2">${r.events}</td>
            <td class="px-3 py-2 font-semibold">${r.per_hour !== null ? fmt(r.per_hour) : '--'}</td></tr>`).join('')
        : '<tr><td colspan="4" class="px-3 py-2 text-gray-500">Sem fases do sono da pulseira nesta noite.</td></tr>';
}

// ─── EXPLORADOR DE CORRELAÇÕES ─────────────────────────────────────────────────

async function loadCorrelationExplorer(force = false) {
    const patient = aPatient();
    if (!patient || (!force && aState.matrixFor === patient)) return;
    aState.matrixFor = patient;
    const box = document.getElementById('corr-matrix');
    box.innerHTML = '<p class="text-xs text-gray-500 py-4">Calculando correlações...</p>';
    try {
        const m = await aFetch('/api/correlation/{p}/matrix');
        aState.matrix = m;
        renderMatrix(m);
        const opts = Object.entries(m.vars).map(([k, v]) => `<option value="${k}">${v.label}${v.unit ? ` (${v.unit})` : ''}</option>`).join('');
        document.getElementById('corrX').innerHTML = opts;
        document.getElementById('corrY').innerHTML = opts;
        // par inicial: a correlação significativa mais forte, senão uso × score
        const sig = m.cells.filter(c => c.rho !== null && c.p < 0.05).sort((a, b) => Math.abs(b.rho) - Math.abs(a.rho));
        const first = sig[0] || { x: 'usage_h', y: 'sleep_score' };
        selectPair(first.x, first.y);
    } catch (e) {
        console.error('Erro na matriz', e);
        box.innerHTML = '<p class="text-xs text-red-400 py-2">Erro ao calcular correlações.</p>';
    }
}

function renderMatrix(m) {
    const cell = (x, y) => m.cells.find(c => c.x === x && c.y === y);
    let html = '<table class="text-[11px] border-separate" style="border-spacing:2px"><thead><tr><th></th>';
    html += m.cols.map(c => `<th class="px-1 py-1 text-gray-400 font-normal align-bottom" style="min-width:64px">${m.vars[c].label}</th>`).join('') + '</tr></thead><tbody>';
    for (const r of m.rows) {
        html += `<tr><td class="pr-2 py-1 text-gray-400 whitespace-nowrap text-right">${m.vars[r].label}</td>`;
        for (const c of m.cols) {
            const v = cell(r, c);
            if (!v || v.rho === null) { html += '<td class="text-center text-gray-600">·</td>'; continue; }
            const a = Math.min(Math.abs(v.rho) * 1.4, 0.9);
            const bg = v.rho >= 0 ? `rgba(34,197,94,${a})` : `rgba(239,68,68,${a})`;
            const op = v.p < 0.05 ? 1 : 0.35;
            html += `<td class="text-center cursor-pointer rounded hover:outline hover:outline-1 hover:outline-white" style="background:${bg};opacity:${op};padding:6px 4px"
                data-x="${r}" data-y="${c}" title="ρ=${v.rho} · p=${v.p} · ${v.n} noites · ${v.label}">${v.rho.toFixed(2)}<div class="text-[9px] opacity-70">n=${v.n}</div></td>`;
        }
        html += '</tr>';
    }
    html += '</tbody></table>';
    document.getElementById('corr-matrix').innerHTML = html;
}

document.getElementById('corr-matrix').addEventListener('click', e => {
    const td = e.target.closest('td[data-x]');
    if (td) selectPair(td.dataset.x, td.dataset.y);
});
document.getElementById('corrX').addEventListener('change', () => loadPair());
document.getElementById('corrY').addEventListener('change', () => loadPair());

function selectPair(x, y) {
    document.getElementById('corrX').value = x;
    document.getElementById('corrY').value = y;
    loadPair();
}

async function loadPair() {
    const x = document.getElementById('corrX').value, y = document.getElementById('corrY').value;
    const stats = document.getElementById('corr-pair-stats');
    if (x === y) { stats.textContent = 'Escolha duas variáveis diferentes.'; return; }
    try {
        const d = await aFetch(`/api/correlation/{p}/pair?x=${x}&y=${y}`);
        const vx = aState.matrix.vars[x], vy = aState.matrix.vars[y];
        const warn = d.n < d.min_n ? ` <span class="text-yellow-400">⚠️ Só ${d.n} noites — resultado pouco confiável.</span>` : '';
        stats.innerHTML = d.rho === null ? `Dados insuficientes (${d.n} noites com as duas variáveis).`
            : `ρ = <b>${d.rho}</b> · p = ${d.p} · ${d.n} noites · correlação <b>${d.label}</b>.${warn}`;
        const pts = d.points.map(p => ({ x: p.x, y: p.y, date: p.date }));
        const xs = pts.map(p => p.x);
        const ds = [{ label: 'Noites', data: pts, backgroundColor: 'rgba(96,165,250,0.75)', pointRadius: 4 }];
        if (d.fit && xs.length) {
            const lo = Math.min(...xs), hi = Math.max(...xs);
            ds.push({ label: 'Tendência linear', type: 'line', data: [{ x: lo, y: d.fit.intercept + d.fit.slope * lo }, { x: hi, y: d.fit.intercept + d.fit.slope * hi }],
                borderColor: A_COLORS.warn, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 });
        }
        aChart('chartCorrPair', {
            type: 'scatter',
            data: { datasets: ds },
            options: { plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } },
                    tooltip: { callbacks: { label: ctx => ctx.raw.date ? `${formatDateBR(ctx.raw.date)}: ${fmt(ctx.raw.x, 2)} × ${fmt(ctx.raw.y, 2)}` : '' } } },
                scales: { x: { title: { display: true, text: `${vx.label}${vx.unit ? ` (${vx.unit})` : ''}` }, grid: gridOpts },
                    y: { title: { display: true, text: `${vy.label}${vy.unit ? ` (${vy.unit})` : ''}` }, grid: gridOpts } } },
        });
    } catch (e) {
        console.error('Erro no par', e);
        stats.textContent = 'Erro ao carregar o gráfico.';
    }
}

// ─── Integração com as abas e o seletor de paciente ────────────────────────────

function activeTab() {
    const b = document.querySelector('.tab-btn.active');
    return b ? b.dataset.tab : null;
}

function loadActiveAnalysis(force = false) {
    const t = activeTab();
    if (t === 'tendencias') loadTrends(force);
    else if (t === 'noite') loadNightDates(force);
    else if (t === 'correlacao') loadCorrelationExplorer(force);
}

document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => loadActiveAnalysis()));
document.getElementById('patientSelect').addEventListener('change', () => {
    aState.trendsFor = aState.nightsFor = aState.matrixFor = null;
    loadActiveAnalysis(true);
});

// Botão do relatório: abre com o paciente atual
document.getElementById('btn-report').addEventListener('click', e => {
    e.currentTarget.href = `/relatorio?patient=${encodeURIComponent(aPatient())}`;
});
