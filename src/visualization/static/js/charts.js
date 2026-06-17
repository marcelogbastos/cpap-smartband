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

function renderGraficosCharts(data, miData) {
    const ts = data.timeseries;
    const fullDates = ts.data_sessao || [];

    // Use the month/year selected in the dropdowns
    let refMonth = currentMonth;
    let refYear = currentYear;

    // Filter all dates that belong to the selected month/year
    let monthDates = fullDates;
    if (refMonth && refYear) {
        monthDates = fullDates.filter(d => {
            const parts = d.split('-');
            return parseInt(parts[0]) === refYear && parseInt(parts[1]) === refMonth;
        });
    }

    // If no dates for that month, fall back to last 30 days
    if (monthDates.length === 0) {
        monthDates = fullDates.slice(-30);
    }

    if (monthDates.length === 0) {
        // Clear charts if no data
        ['chartScore', 'chartSleepScore', 'chartAhi', 'chartPressure'].forEach(id => {
            if (charts[id]) { charts[id].destroy(); delete charts[id]; }
        });
        return;
    }

    const startIdx = fullDates.indexOf(monthDates[0]);
    const endIdx = fullDates.indexOf(monthDates[monthDates.length - 1]) + 1;

    const dates = monthDates.map(formatDateBR);
    const scores = (ts.score || []).slice(startIdx, endIdx);
    const ahis = (ts.AHI || []).slice(startIdx, endIdx);
    const leaks = (ts['Leak.95'] || []).slice(startIdx, endIdx);
    const pressures = (ts['BlowPress.95'] || []).slice(startIdx, endIdx);

    function scoreColor(v) { return v >= 70 ? '#27ae60' : v >= 50 ? '#f39c12' : '#e74c3c'; }
    function sleepScoreColor(v) { return v >= 70 ? '#27ae60' : v >= 50 ? '#f39c12' : '#e74c3c'; }
    function ahiColor(v) { return v < 5 ? '#27ae60' : v < 15 ? '#f39c12' : '#e74c3c'; }
    function presColor(v) { return '#27ae60'; } // Image shows all green for pressure
    // leakColor is defined but unused in original, keeping scoreColor mappings

    const commonOptions = {
        responsive: true, maintainAspectRatio: false, 
        plugins: { legend: { display: false } },
        scales: { 
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, border: { dash: [4, 4] }, beginAtZero: true }, 
            x: { grid: { display: false } } 
        },
        layout: { padding: { top: 20 } }
    };

    // Score CPAP
    createChart('chartScore', 'bar', {
        labels: dates,
        datasets: [{ data: scores, backgroundColor: scores.map(scoreColor), borderRadius: 2, barPercentage: 0.8 }]
    }, { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, max: 100 } }});

    // Sleep Score
    let sleepScores = [];
    let sleepLabels = [];
    if (miData.sleep && miData.sleep.sleep_score) {
        const miDates = miData.sleep.report_date || [];
        const chartDates = fullDates.slice(startIdx, endIdx);
        sleepScores = chartDates.map(d => {
            const idx = miDates.indexOf(d);
            return idx >= 0 ? miData.sleep.sleep_score[idx] : null;
        }).filter(v => v !== null);
        sleepLabels = chartDates.filter((_, i) => {
            const idx = miDates.indexOf(chartDates[i]);
            return idx >= 0 && miData.sleep.sleep_score[idx] != null;
        }).map(formatDateBR);
    }
    if (sleepLabels.length > 0) {
        createChart('chartSleepScore', 'bar', {
            labels: sleepLabels,
            datasets: [{ data: sleepScores, backgroundColor: sleepScores.map(sleepScoreColor), borderRadius: 2, barPercentage: 0.8 }]
        }, { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, max: 100 } }});
    } else {
        if (charts['chartSleepScore']) { charts['chartSleepScore'].destroy(); delete charts['chartSleepScore']; }
    }

    // IAH
    createChart('chartAhi', 'bar', {
        labels: dates,
        datasets: [{ data: ahis, backgroundColor: ahis.map(ahiColor), borderRadius: 2, barPercentage: 0.8 }]
    }, { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, max: 20 } }});

    // Pressão
    const presMax = pressures.length > 0 ? Math.ceil(Math.max(...pressures)) + 2 : 20;
    createChart('chartPressure', 'bar', {
        labels: dates,
        datasets: [{ data: pressures, backgroundColor: pressures.map(presColor), borderRadius: 2, barPercentage: 0.8 }]
    }, { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, max: presMax, min: 0 } } });

    // Composição do sono (barras empilhadas) + Frequência Cardíaca
    if (miData.sleep && miData.sleep.report_date) {
        const miDates   = miData.sleep.report_date || [];
        const chartDates = fullDates.slice(startIdx, endIdx);

        // Filtra apenas datas com dado na smartband
        const sharedDates = chartDates.filter(d => miDates.includes(d));
        const sharedLabels = sharedDates.map(formatDateBR);

        function miVal(field) {
            return sharedDates.map(d => {
                const i = miDates.indexOf(d);
                return i >= 0 ? (miData.sleep[field]?.[i] ?? 0) : 0;
            });
        }

        const deep  = miVal('deep_min');
        const rem   = miVal('rem_min');
        const light = miVal('light_min');
        const awake = miVal('awake_min');
        const avgHr = miVal('avg_hr');
        const minHr = miVal('min_hr');
        const maxHr = miVal('max_hr');

        const noDataLabels = { plugins: { ...commonOptions.plugins, datalabels: { display: false } } };
        const stackedBase = {
            ...commonOptions,
            ...noDataLabels,
            layout: { padding: { top: 8 } },
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, grid: { color: 'rgba(255,255,255,0.05)' }, border: { dash: [4,4] }, ticks: { callback: v => v + 'min' } }
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
                    ...stackedBase.plugins,
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
                ...commonOptions,
                ...noDataLabels,
                layout: { padding: { top: 8 } },
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
                    ...commonOptions.plugins,
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
