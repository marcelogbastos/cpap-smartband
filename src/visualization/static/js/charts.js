const MONTH_NAMES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
const DAY_NAMES   = ['D','S','T','Q','Q','S','S'];

Chart.register(ChartDataLabels);
Chart.defaults.color = '#a0aec0';
Chart.defaults.font.family = "'Segoe UI', sans-serif";
Chart.defaults.plugins.legend.labels.color = '#a0aec0';
Chart.defaults.plugins.datalabels = {
    color: 'white', font: { weight: 'bold', size: 10 },
    anchor: 'center', align: 'center',
    formatter: (value) => typeof value === 'number' ? (Number.isInteger(value) ? value : value.toFixed(1)) : value,
    display: function(context) { return context.dataset.data[context.dataIndex] > 0; }
};

let charts = {};

function createChart(ctxId, type, data, options) {
    if (charts[ctxId]) { charts[ctxId].destroy(); delete charts[ctxId]; }
    const el = document.getElementById(ctxId);
    if (!el) return;
    const ctx = el.getContext('2d');
    charts[ctxId] = new Chart(ctx, { type, data, options });
}

function formatDateBR(dateStr) {
    if (!dateStr) return '--/--/----';
    const parts = dateStr.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
}

// ─── GENERIC CALENDAR HEATMAP ──────────────────────────────────────────────────

function renderCalendarHeatmap(containerId, dateValueMap, colorFn, fmtFn, unit) {
    const el = document.getElementById(containerId);
    if (!el) return;

    if (!dateValueMap || Object.keys(dateValueMap).length === 0) {
        el.innerHTML = '<p style="font-size:11px;color:#6b7280;padding:8px 0;">Sem dados.</p>';
        return;
    }

    // Group dates by year+month
    const months = {};
    Object.keys(dateValueMap).sort().forEach(dateStr => {
        const [yr, mo] = dateStr.split('-');
        const key = `${yr}-${mo}`;
        if (!months[key]) months[key] = { year: parseInt(yr), month: parseInt(mo), days: {} };
        months[key].days[dateStr] = dateValueMap[dateStr];
    });

    let html = '<div style="display:flex;flex-wrap:wrap;gap:16px 20px;">';

    Object.values(months).forEach(({ year, month, days }) => {
        const daysInMonth = new Date(year, month, 0).getDate();
        const firstDow    = new Date(year, month - 1, 1).getDay();

        html += `<div style="min-width:176px">`;
        html += `<div style="font-size:11px;font-weight:600;color:#9ca3af;margin-bottom:5px;">${MONTH_NAMES[month-1]} ${year}</div>`;
        html += `<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;">`;

        DAY_NAMES.forEach(d => {
            html += `<div style="font-size:9px;color:#4b5563;text-align:center;padding-bottom:2px;">${d}</div>`;
        });

        for (let i = 0; i < firstDow; i++) html += `<div></div>`;

        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
            const val     = days[dateStr] !== undefined ? days[dateStr] : null;
            const bg      = val !== null ? colorFn(val) : '#1f2937';
            const isDark  = bg === '#1f2937' || bg === '#ef4444' || bg === '#818cf8' || bg === '#f472b6';
            const fg      = val !== null ? (isDark ? 'rgba(255,255,255,0.55)' : '#111827') : 'rgba(255,255,255,0.2)';
            const label   = val !== null ? fmtFn(val) : '—';
            const dateBR  = formatDateBR(dateStr);
            const tipText = val !== null ? `${dateBR}: ${fmtFn(val)}${unit ? ' ' + unit : ''}` : `${dateBR}: Sem Informação`;

            html += `<div data-tip="${tipText}" style="
                background:${bg};border-radius:3px;aspect-ratio:1;
                display:flex;align-items:center;justify-content:center;
                font-size:8px;font-weight:700;color:${fg};
                min-height:22px;cursor:default;
            ">${label}</div>`;
        }

        html += '</div></div>';
    });

    html += '</div>';
    el.innerHTML = html;

    // Wire up global tooltip for data-tip cells
    el.querySelectorAll('[data-tip]').forEach(cell => {
        cell.addEventListener('mouseenter', (e) => {
            const tip = document.getElementById('global-tooltip');
            if (!tip) return;
            tip.textContent = e.currentTarget.dataset.tip;
            tip.style.display = 'block';
            const r = e.currentTarget.getBoundingClientRect();
            const tw = 200, th = 30, m = 6;
            let top = r.top - th - m;
            if (top < m) top = r.bottom + m;
            let left = r.left + r.width / 2 - tw / 2;
            left = Math.max(m, Math.min(left, window.innerWidth - tw - m));
            tip.style.top = top + 'px';
            tip.style.left = left + 'px';
        });
        cell.addEventListener('mouseleave', () => {
            const tip = document.getElementById('global-tooltip');
            if (tip) tip.style.display = 'none';
        });
    });
}

function renderGraficosCharts(data, miData) {
    const ts = data.timeseries;
    const fullDates = ts.data_sessao || [];

    if (fullDates.length === 0) return;

    // Build date→value maps filtered by selected month/year
    const refMonth = currentMonth;
    const refYear  = currentYear;

    function inSelectedMonth(dateStr) {
        if (!refMonth || !refYear) return true;
        const [yr, mo] = dateStr.split('-');
        return parseInt(yr) === refYear && parseInt(mo) === refMonth;
    }

    const cpapScoreMap = {};
    const pressureMap  = {};
    fullDates.forEach((d, i) => {
        if (!inSelectedMonth(d)) return;
        if (ts.score?.[i] != null)           cpapScoreMap[d] = ts.score[i];
        if (ts['BlowPress.95']?.[i] != null) pressureMap[d]  = ts['BlowPress.95'][i];
    });

    // Sleep score from miData filtered by selected month
    const sleepScoreMap = {};
    if (miData.sleep?.report_date) {
        miData.sleep.report_date.forEach((d, i) => {
            if (!inSelectedMonth(d)) return;
            const v = miData.sleep.sleep_score?.[i];
            if (v != null && v > 0) sleepScoreMap[d] = v;
        });
    }

    renderCalendarHeatmap('heatmap-cpap-score', cpapScoreMap,
        v => v >= 70 ? '#22c55e' : v >= 50 ? '#facc15' : '#ef4444',
        v => Math.round(v), 'pts');

    renderCalendarHeatmap('heatmap-sleep-score', sleepScoreMap,
        v => v >= 80 ? '#22c55e' : v >= 60 ? '#facc15' : '#ef4444',
        v => Math.round(v), 'pts');

    renderCalendarHeatmap('heatmap-pressure', pressureMap,
        v => v <= 12 ? '#38bdf8' : v <= 16 ? '#818cf8' : '#f472b6',
        v => v.toFixed(1), 'cmH₂O');

    // Filtered range for stacked sleep + HR charts (keep month selection)
    let monthDates = fullDates;
    if (refMonth && refYear) {
        monthDates = fullDates.filter(d => inSelectedMonth(d));
    }
    if (monthDates.length === 0) monthDates = fullDates.slice(-30);

    // Composição do sono (barras empilhadas) + Frequência Cardíaca
    if (miData.sleep && miData.sleep.report_date) {
        const miDates   = miData.sleep.report_date || [];

        // Filtra apenas datas do mês selecionado com dado na smartband
        const sharedDates = monthDates.filter(d => miDates.includes(d));
        const sharedLabels = sharedDates.map(formatDateBR);

        function miVal(field) {
            return sharedDates.map(d => {
                const i = miDates.indexOf(d);
                return i >= 0 ? (miData.sleep[field]?.[i] ?? 0) : 0;
            });
        }

        const deep  = miVal('deep_min').map(v => +(v / 60).toFixed(2));
        const rem   = miVal('rem_min').map(v => +(v / 60).toFixed(2));
        const light = miVal('light_min').map(v => +(v / 60).toFixed(2));
        const awake = miVal('awake_min').map(v => +(v / 60).toFixed(2));
        const avgHr = miVal('avg_hr');
        const minHr = miVal('min_hr');
        const maxHr = miVal('max_hr');

        const baseOpts = {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: 8 } },
            plugins: { legend: { display: false }, datalabels: { display: false } },
        };
        const stackedBase = {
            ...baseOpts,
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, grid: { color: 'rgba(255,255,255,0.05)' }, border: { dash: [4,4] }, ticks: { callback: v => v.toFixed(1) + 'h' } }
            }
        };

        if (sharedLabels.length > 0) {
            createChart('chartSleepComposition', 'bar', {
                labels: sharedLabels,
                datasets: [
                    { label: 'Profundo', data: deep,  backgroundColor: '#6366f1', borderRadius: 0, barPercentage: 0.85 },
                    { label: 'REM',      data: rem,   backgroundColor: '#22d3ee', borderRadius: 0, barPercentage: 0.85 },
                    { label: 'Leve',     data: light, backgroundColor: '#4ade80', borderRadius: 0, barPercentage: 0.85 },
                    { label: 'Acordado', data: awake, backgroundColor: '#f87171', borderRadius: 0, barPercentage: 0.85 },
                ]
            }, {
                ...stackedBase,
                plugins: {
                    legend: { display: true, position: 'bottom', labels: { color: '#9ca3af', font: { size: 10 }, boxWidth: 12, padding: 10 } },
                    datalabels: { display: false }
                }
            });

            // HR: linha avg + área min/max via fill
            const hrMax = Math.max(...maxHr.filter(v => v > 0)) + 10 || 120;
            const hrMin = Math.max(0, Math.min(...minHr.filter(v => v > 0)) - 10);
            createChart('chartSleepHR', 'line', {
                labels: sharedLabels,
                datasets: [
                    {
                        label: 'Máx',
                        data: maxHr,
                        borderColor: 'rgba(248,113,113,0.4)',
                        backgroundColor: 'rgba(248,113,113,0.15)',
                        fill: '+1',
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1,
                    },
                    {
                        label: 'Média',
                        data: avgHr,
                        borderColor: '#f87171',
                        backgroundColor: 'transparent',
                        tension: 0.3,
                        pointRadius: 3,
                        pointBackgroundColor: '#f87171',
                        borderWidth: 2,
                        fill: false,
                    },
                    {
                        label: 'Mín',
                        data: minHr,
                        borderColor: 'rgba(248,113,113,0.4)',
                        backgroundColor: 'rgba(248,113,113,0.15)',
                        fill: '-1',
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 1,
                    },
                ]
            }, {
                ...baseOpts,
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        min: hrMin, max: hrMax,
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        border: { dash: [4,4] },
                        ticks: { callback: v => v + ' bpm' }
                    }
                },
                plugins: {
                    legend: { display: true, position: 'bottom', labels: { color: '#9ca3af', font: { size: 10 }, boxWidth: 12, padding: 10 } },
                    datalabels: { display: false }
                }
            });
        } else {
            ['chartSleepComposition', 'chartSleepHR'].forEach(id => {
                if (charts[id]) { charts[id].destroy(); delete charts[id]; }
            });
        }
    }
}
