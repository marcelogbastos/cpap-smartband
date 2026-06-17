let currentMonth = null;
let currentYear = null;
let availablePeriods = [];
let sleepData = [];
let cpapData = [];
let globalSelectedDate = null;
let globalSelectedPeriod = 7;
let currentPatientData = null;
let currentMiData = null;
let sortState = {
    sleep: { col: 'report_date', dir: 'desc' },
    cpap: { col: 'data_sessao', dir: 'desc' }
};

// Flatpickr setup
let datePickerInstance = flatpickr("#datePicker", {
    locale: "pt",
    dateFormat: "Y-m-d",
    onChange: function(selectedDates, dateStr, instance) {
        if (selectedDates.length > 0) {
            globalSelectedDate = dateStr;
            if (currentPatientData && currentMiData) {
                updateKPIs(currentPatientData, currentMiData);
                renderGraficosCharts(currentPatientData, currentMiData);
                updateAverages(currentPatientData, currentMiData);
            }
        }
    }
});

document.getElementById('btn-calendar').addEventListener('click', () => {
    if (currentPatientData && currentPatientData.timeseries && currentPatientData.timeseries.data_sessao) {
        datePickerInstance.set('enable', currentPatientData.timeseries.data_sessao);
    }
    datePickerInstance.open();
});

// Period Select
document.getElementById('periodSelect').addEventListener('change', (e) => {
    globalSelectedPeriod = parseInt(e.target.value);
    if (currentPatientData && currentMiData) {
        updateAverages(currentPatientData, currentMiData);
        renderGraficosCharts(currentPatientData, currentMiData);
    }
});

// Period buttons (7 days / 30 days)
document.getElementById('btn-7days').addEventListener('click', () => {
    globalSelectedPeriod = 7;
    document.getElementById('btn-7days').classList.add('active');
    document.getElementById('btn-30days').classList.remove('active');
    if (currentPatientData && currentMiData) {
        updateAverages(currentPatientData, currentMiData);
        renderGraficosCharts(currentPatientData, currentMiData);
    }
});

document.getElementById('btn-30days').addEventListener('click', () => {
    globalSelectedPeriod = 30;
    document.getElementById('btn-30days').classList.add('active');
    document.getElementById('btn-7days').classList.remove('active');
    if (currentPatientData && currentMiData) {
        updateAverages(currentPatientData, currentMiData);
        renderGraficosCharts(currentPatientData, currentMiData);
    }
});

// Tabs
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
});

function sortTable(table, col, dir) {
    const data = table === 'sleep' ? sleepData : cpapData;
    const isDate = col === 'report_date' || col === 'data_sessao';
    data.sort((a, b) => {
        let valA = isDate ? new Date(a[col]) : (parseFloat(a[col]) || 0);
        let valB = isDate ? new Date(b[col]) : (parseFloat(b[col]) || 0);
        if (valA < valB) return dir === 'asc' ? -1 : 1;
        if (valA > valB) return dir === 'asc' ? 1 : -1;
        return 0;
    });
    if (table === 'sleep') renderSleepTable(data);
    else renderCpapTable(data);
}

function updateSortIcons(table) {
    const state = sortState[table];
    document.querySelectorAll(`th[data-table="${table}"]`).forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.col === state.col) th.classList.add(state.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    });
}

document.addEventListener('click', (e) => {
    const th = e.target.closest('th[data-table]');
    if (!th) return;
    const table = th.dataset.table;
    const col = th.dataset.col;
    const state = sortState[table];
    if (state.col === col) state.dir = state.dir === 'asc' ? 'desc' : 'asc';
    else { state.col = col; state.dir = 'asc'; }
    updateSortIcons(table);
    sortTable(table, state.col, state.dir);
});

async function loadAvailablePeriods(patient) {
    if (!patient) return;
    try {
        const res = await fetch(`/api/available-periods?patient=${patient}`);
        if (!res.ok) return;
        const data = await res.json();
        availablePeriods = data.periods;
        updateDateSelectors();
    } catch (e) { console.error("Error loading periods", e); }
}

function updateDateSelectors() {
    const monthSelect = document.getElementById('monthSelect');
    const yearSelect = document.getElementById('yearSelect');
    monthSelect.innerHTML = '';
    yearSelect.innerHTML = '';
    if (availablePeriods.length === 0) return;
    const months = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
    const uniqueYears = [...new Set(availablePeriods.map(p => p.year))].sort((a, b) => b - a);
    const uniqueMonths = [...new Set(availablePeriods.map(p => p.month))].sort((a, b) => a - b);
    uniqueYears.forEach(y => { const opt = document.createElement('option'); opt.value = y; opt.textContent = y; yearSelect.appendChild(opt); });
    uniqueMonths.forEach(m => { const opt = document.createElement('option'); opt.value = m; opt.textContent = months[m - 1]; monthSelect.appendChild(opt); });
    const first = availablePeriods[0];
    currentYear = first.year;
    currentMonth = first.month;
    yearSelect.value = currentYear;
    monthSelect.value = currentMonth;
    loadMonthlySleep();
    loadMonthlyCpap();
    
    // Add Event Listeners if not already added
    if (!monthSelect.dataset.hasListener) {
        monthSelect.dataset.hasListener = "true";
        monthSelect.addEventListener('change', (e) => { 
            currentMonth = parseInt(e.target.value); 
            loadMonthlySleep(); 
            loadMonthlyCpap(); 
            if (currentPatientData && currentMiData) renderGraficosCharts(currentPatientData, currentMiData); 
        });
    }
    if (!yearSelect.dataset.hasListener) {
        yearSelect.dataset.hasListener = "true";
        yearSelect.addEventListener('change', (e) => { 
            currentYear = parseInt(e.target.value); 
            loadMonthlySleep(); 
            loadMonthlyCpap(); 
            if (currentPatientData && currentMiData) renderGraficosCharts(currentPatientData, currentMiData); 
        });
    }
}

function formatHoursMinutes(mins) {
    if (!mins) return "0h 0m";
    const h = Math.floor(mins / 60);
    const m = Math.floor(mins % 60);
    return `${h}h ${m}m`;
}

function formatHoursDecimal(mins) {
    if (!mins) return "0.0h";
    return (mins / 60).toFixed(1) + 'h';
}

async function fetchPatients() {
    try {
        const res = await fetch('/api/patients');
        if (!res.ok) throw new Error("API error");
        const patients = await res.json();
        const select = document.getElementById('patientSelect');
        select.innerHTML = '';
        if (patients.length === 0) {
            select.innerHTML = '<option value="">Sem pacientes</option>';
            return;
        }
        patients.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            select.appendChild(opt);
        });
        loadPatientData(patients[0]);
        loadAvailablePeriods(patients[0]);
    } catch (e) {
        console.error("Error loading patients", e);
        document.getElementById('patientSelect').innerHTML = '<option value="">Erro ao carregar</option>';
    }
}

async function loadMonthlySleep(patient) {
    if (!patient) patient = document.getElementById('patientSelect').value;
    if (!patient || !currentMonth || !currentYear) return;
    try {
        const res = await fetch(`/api/smartband/${patient}/monthly-sleep?year=${currentYear}&month=${currentMonth}`);
        if (!res.ok) return;
        const data = await res.json();
        sleepData = data.rows.map(row => {
            const total = row.total_duration_min || 0;
            const rem = row.rem_min || 0;
            return { ...row, rem_pct: total > 0 ? ((rem / total) * 100) : 0 };
        });
        sortState.sleep = { col: 'report_date', dir: 'desc' };
        updateSortIcons('sleep');
        sortTable('sleep', 'report_date', 'desc');
    } catch (e) { console.error("Error loading monthly sleep", e); }
}

async function loadMonthlyCpap(patient) {
    if (!patient) patient = document.getElementById('patientSelect').value;
    if (!patient || !currentMonth || !currentYear) return;
    try {
        const res = await fetch(`/api/cpap/${patient}/monthly?year=${currentYear}&month=${currentMonth}`);
        if (!res.ok) return;
        const data = await res.json();
        cpapData = data.rows;
        sortState.cpap = { col: 'data_sessao', dir: 'desc' };
        updateSortIcons('cpap');
        sortTable('cpap', 'data_sessao', 'desc');
    } catch (e) { console.error("Error loading monthly CPAP", e); }
}

function renderCpapTable(rows) {
    const tbody = document.getElementById('cpapTableBody');
    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="px-2 py-2 text-center text-gray-500">Sem dados de CPAP para este período</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(row => {
        const score = row.score || 0;
        const scoreColor = score >= 70 ? 'text-green-500' : score >= 50 ? 'text-yellow-500' : 'text-red-500';
        const usageColor = (row.usage_mins || 0) >= 240 ? 'text-green-400' : 'text-red-400';
        const ahiColor = (row.ahi || 0) < 5 ? 'text-green-400' : (row.ahi || 0) < 15 ? 'text-yellow-400' : 'text-red-400';
        const leakColor = (row.leak_95 || 0) <= 24 ? 'text-green-400' : 'text-red-400';
        return `<tr class="border-b border-gray-800 hover:bg-[#1a1f2e] transition-colors">
            <td class="px-2 py-2 text-gray-400 whitespace-nowrap">${row.data_sessao}</td>
            <td class="px-2 py-2 ${usageColor} whitespace-nowrap">${formatHoursMinutes(row.usage_mins)}</td>
            <td class="px-2 py-2 ${ahiColor} whitespace-nowrap">${(row.ahi||0).toFixed(1)}</td>
            <td class="px-2 py-2 whitespace-nowrap">${(row.p95_pressure || 0).toFixed(1)}</td>
            <td class="px-2 py-2 ${leakColor} whitespace-nowrap">${(row.leak_95 || 0).toFixed(1)}</td>
            <td class="px-2 py-2 ${scoreColor} whitespace-nowrap">${score}</td>
        </tr>`;
    }).join('');
}

function renderSleepTable(rows) {
    const tbody = document.getElementById('sleepTableBody');
    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-2 py-2 text-center text-gray-500">Sem dados de sono para este período</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(row => {
        const total = row.total_duration_min || 0;
        const rem = row.rem_min || 0;
        const remPct = row.rem_pct ? row.rem_pct.toFixed(1) : '0.0';
        return `<tr class="border-b border-gray-800 hover:bg-[#1a1f2e] transition-colors">
            <td class="px-2 py-2 text-gray-400 whitespace-nowrap">${row.report_date}</td>
            <td class="px-2 py-2 whitespace-nowrap">${formatHoursMinutes(total)}</td>
            <td class="px-2 py-2 text-yellow-500 whitespace-nowrap">${formatHoursDecimal(rem)}</td>
            <td class="px-2 py-2 text-blue-500 whitespace-nowrap">${formatHoursDecimal(row.deep_min || 0)}</td>
            <td class="px-2 py-2 text-orange-400 whitespace-nowrap">${formatHoursDecimal(row.light_min || 0)}</td>
            <td class="px-2 py-2 text-purple-400 whitespace-nowrap">${formatHoursDecimal(row.awake_min || 0)}</td>
            <td class="px-2 py-2 whitespace-nowrap">${remPct}%</td>
        </tr>`;
    }).join('');
}

async function loadPatientData(patient) {
    if (!patient) return;
    showSpinner(true);
    try {
        const res = await fetch(`/api/data/${patient}`);
        if (!res.ok) throw new Error(`API retornou ${res.status}`);
        const data = await res.json();
        let miData = { sleep: {}, activity: {} };
        try {
            const resMi = await fetch(`/api/smartband/${patient}/daily`);
            if (resMi.ok) miData = await resMi.json();
        } catch (e) { console.error("Error loading MiFitness", e); }
        currentPatientData = data;
        currentMiData = miData;
        
        if (data.timeseries && data.timeseries.data_sessao && data.timeseries.data_sessao.length > 0) {
            const dates = data.timeseries.data_sessao;
            if (!globalSelectedDate || !dates.includes(globalSelectedDate)) {
                globalSelectedDate = dates[dates.length - 1];
            }
            datePickerInstance.setDate(globalSelectedDate);
        } else {
            globalSelectedDate = null;
        }
        
        updateKPIs(data, miData);
        renderGraficosCharts(data, miData);
        updateAverages(data, miData);
        hideError();
    } catch (e) {
        console.error("Error loading patient data", e);
        showError('Erro ao carregar dados do paciente. Verifique se o servidor está ativo e os dados processados.');
    } finally {
        showSpinner(false);
    }
}

function updateKPIs(data, miData) {
    const ts = data.timeseries;
    const dates = ts.data_sessao || [];
    
    let idx = dates.length > 0 ? dates.length - 1 : -1;
    if (globalSelectedDate) {
        const foundIdx = dates.indexOf(globalSelectedDate);
        if (foundIdx !== -1) idx = foundIdx;
    }
    
    const lastDate = idx >= 0 ? dates[idx] : null;
    document.getElementById('resumo-noite-title').textContent = `Noite - ${formatDateBR(lastDate)}`;

    let cScore = 0, usageMins = 0, ahi = 0, leak = 0, maskEvents = 0, pressure = 0;
    if (idx >= 0) {
        cScore = ts.score && ts.score[idx] ? ts.score[idx] : 0;
        usageMins = ts.usage_mins && ts.usage_mins[idx] ? ts.usage_mins[idx] : 0;
        ahi = ts.AHI && ts.AHI[idx] ? ts.AHI[idx] : 0;
        leak = ts['Leak.95'] && ts['Leak.95'][idx] ? ts['Leak.95'][idx] : 0;
        maskEvents = ts.mask_events && ts.mask_events[idx] ? ts.mask_events[idx] : 0;
        pressure = ts['BlowPress.95'] && ts['BlowPress.95'][idx] ? ts['BlowPress.95'][idx] : 0;
    }
    
    const usageH = Math.floor(usageMins / 60);
    const usageM = Math.floor(usageMins % 60);
    
    // CPAP Score Logic
    let cIcon = cScore >= 70 ? '⭐' : cScore >= 50 ? '👍' : '⚠️';
    let cColor = cScore >= 70 ? 'text-green-500' : cScore >= 50 ? 'text-yellow-500' : 'text-red-500';
    let cBorder = cScore >= 70 ? 'border-green-500' : cScore >= 50 ? 'border-yellow-500' : 'border-red-500';
    
    document.getElementById('kpi-score-text').textContent = idx >= 0 ? cScore : '--';
    document.getElementById('kpi-score-text').className = `font-bold text-sm ${cColor}`;
    document.getElementById('kpi-score-circle').textContent = idx >= 0 ? cIcon : '⚙️';
    document.getElementById('kpi-score-circle').className = `w-9 h-9 rounded-full border-4 flex items-center justify-center text-sm mx-auto mb-1 ${cBorder}`;

    document.getElementById('kpi-usage-top').textContent = idx >= 0 ? `${usageH}h ${usageM}m` : '--';
    document.getElementById('kpi-usage-top').className = `font-bold text-sm ${usageMins >= 240 ? 'text-green-400' : 'text-red-400'}`;
    document.getElementById('kpi-ahi-top').textContent = idx >= 0 ? ahi.toFixed(1) : '--';
    document.getElementById('kpi-ahi-top').className = `font-bold text-sm ${ahi < 5 ? 'text-green-400' : ahi < 15 ? 'text-yellow-400' : 'text-red-400'}`;
    document.getElementById('kpi-leak-top').textContent = idx >= 0 ? leak.toFixed(1) : '--';
    document.getElementById('kpi-leak-top').className = `font-bold text-sm ${leak <= 24 ? 'text-green-400' : 'text-red-400'}`;
    document.getElementById('kpi-mask-top').textContent = idx >= 0 ? Math.round(maskEvents) : '--';
    document.getElementById('kpi-pressure-top').textContent = idx >= 0 ? pressure.toFixed(1) : '--';

    // Reset smartband fields in case there is no data
    document.getElementById('kpi-mif-score-text').textContent = '--';
    document.getElementById('kpi-mif-score-circle').textContent = '😴';
    document.getElementById('kpi-mif-score-circle').className = 'w-9 h-9 rounded-full border-4 border-gray-600 flex items-center justify-center text-sm mx-auto mb-1';
    document.getElementById('kpi-mif-total').textContent = '--';
    document.getElementById('kpi-mif-rem').textContent = '--';
    document.getElementById('kpi-mif-deep').textContent = '--';
    document.getElementById('kpi-mif-light').textContent = '--';
    document.getElementById('kpi-mif-awake').textContent = '--';

    if (miData.sleep && miData.sleep.total_duration_min && miData.sleep.total_duration_min.length > 0) {
        const miDates = miData.sleep.report_date || [];
        let miIdx = miDates.length > 0 ? miDates.length - 1 : -1;
        if (globalSelectedDate) {
            const foundMiIdx = miDates.indexOf(globalSelectedDate);
            if (foundMiIdx !== -1) miIdx = foundMiIdx;
            else miIdx = -1; // No miData for this date
        }
        
        if (miIdx >= 0) {
            const total = miData.sleep.total_duration_min[miIdx] || 0;
            const rem = miData.sleep.rem_min ? miData.sleep.rem_min[miIdx] || 0 : 0;
            const deep = miData.sleep.deep_min ? miData.sleep.deep_min[miIdx] || 0 : 0;
            const light = miData.sleep.light_min ? miData.sleep.light_min[miIdx] || 0 : 0;
            const awake = miData.sleep.awake_min ? miData.sleep.awake_min[miIdx] || 0 : 0;
            const sleepScore = miData.sleep.sleep_score ? Math.round(miData.sleep.sleep_score[miIdx]) : 0;
            
            let sIcon = sleepScore >= 80 ? '⭐' : sleepScore >= 60 ? '👍' : '⚠️';
            let sColor = sleepScore >= 80 ? 'text-green-500' : sleepScore >= 60 ? 'text-yellow-500' : 'text-red-500';
            let sBorder = sleepScore >= 80 ? 'border-green-500' : sleepScore >= 60 ? 'border-yellow-500' : 'border-red-500';
            
            document.getElementById('kpi-mif-score-text').textContent = sleepScore;
            document.getElementById('kpi-mif-score-text').className = `font-bold text-sm ${sColor}`;
            document.getElementById('kpi-mif-score-circle').textContent = sIcon;
            document.getElementById('kpi-mif-score-circle').className = `w-9 h-9 rounded-full border-4 flex items-center justify-center text-sm mx-auto mb-1 ${sBorder}`;
            
            document.getElementById('kpi-mif-total').textContent = formatHoursMinutes(total);
            document.getElementById('kpi-mif-rem').textContent = formatHoursMinutes(rem);
            document.getElementById('kpi-mif-deep').textContent = formatHoursMinutes(deep);
            document.getElementById('kpi-mif-light').textContent = formatHoursMinutes(light);
            document.getElementById('kpi-mif-awake').textContent = formatHoursMinutes(awake);
        }
    }
}

function updateAverages(data, miData) {
    const ts = data.timeseries;
    const dates = ts.data_sessao || [];
    
    let endIdx = dates.length;
    if (globalSelectedDate) {
        const foundIdx = dates.indexOf(globalSelectedDate);
        if (foundIdx !== -1) endIdx = foundIdx + 1;
    }
    
    let startIdx;
    if (globalSelectedPeriod === 0) {
        startIdx = 0;
    } else {
        startIdx = Math.max(0, endIdx - globalSelectedPeriod);
    }
    const periodDates = dates.slice(startIdx, endIdx);
    
    const firstD = periodDates.length > 0 ? periodDates[0] : null;
    const lastD = periodDates.length > 0 ? periodDates[periodDates.length - 1] : null;
    if (firstD && lastD) {
        document.getElementById('resumo-dias-title').textContent = ` - ${formatDateBR(firstD)} a ${formatDateBR(lastD)}`;
    } else {
        document.getElementById('resumo-dias-title').textContent = ' - Sem período selecionado';
    }
    
    const usage = (ts.usage_mins || []).slice(startIdx, endIdx);
    const scores = (ts.score || []).slice(startIdx, endIdx);
    const ahis = (ts.AHI || []).slice(startIdx, endIdx);
    const leaks = (ts['Leak.95'] || []).slice(startIdx, endIdx);
    const press = (ts['BlowPress.95'] || []).slice(startIdx, endIdx);
    const masks = (ts.mask_events || []).slice(startIdx, endIdx);

    const avgUsage = usage.length ? usage.reduce((a, b) => a + b, 0) / usage.length / 60 : 0;
    const avgAhi = ahis.length ? ahis.reduce((a, b) => a + b, 0) / ahis.length : 0;
    const avgScore = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
    const avgLeak = leaks.length ? leaks.reduce((a, b) => a + b, 0) / leaks.length : 0;
    const avgPress = press.length ? press.reduce((a, b) => a + b, 0) / press.length : 0;
    const avgMask = masks.length ? masks.reduce((a, b) => a + b, 0) / masks.length : 0;

    document.getElementById('avg-usage').textContent = avgUsage.toFixed(1);
    document.getElementById('avg-ahi').textContent = avgAhi.toFixed(1);
    document.getElementById('avg-leak').textContent = avgLeak.toFixed(1);
    document.getElementById('avg-pressure').textContent = avgPress.toFixed(1);
    document.getElementById('avg-mask').textContent = Math.round(avgMask);

    // CPAP Score circle
    const avgScoreRounded = Math.round(avgScore);
    const hasScoreData = scores.length > 0;
    const ascIcon = avgScoreRounded >= 70 ? '⭐' : avgScoreRounded >= 50 ? '👍' : '⚠️';
    const ascColor = avgScoreRounded >= 70 ? 'text-green-500' : avgScoreRounded >= 50 ? 'text-yellow-500' : 'text-red-500';
    const ascBorder = avgScoreRounded >= 70 ? 'border-green-500' : avgScoreRounded >= 50 ? 'border-yellow-500' : 'border-red-500';
    document.getElementById('avg-score-text').textContent = hasScoreData ? avgScoreRounded : '--';
    document.getElementById('avg-score-text').className = `font-bold text-sm ${ascColor}`;
    document.getElementById('avg-score-circle').textContent = hasScoreData ? ascIcon : '⚙️';
    document.getElementById('avg-score-circle').className = `w-9 h-9 rounded-full border-4 flex items-center justify-center text-sm mx-auto mb-1 ${hasScoreData ? ascBorder : 'border-gray-600'}`;

    // Reset smartband averages
    document.getElementById('avg-sleep').textContent = '--';
    document.getElementById('avg-sleepscore-text').textContent = '--';
    document.getElementById('avg-sleepscore-circle').textContent = '😴';
    document.getElementById('avg-sleepscore-circle').className = 'w-9 h-9 rounded-full border-4 border-gray-600 flex items-center justify-center text-sm mx-auto mb-1';
    document.getElementById('avg-rem').textContent = '--';
    document.getElementById('avg-deep').textContent = '--';
    document.getElementById('avg-light').textContent = '--';
    document.getElementById('avg-awake').textContent = '--';

    if (miData.sleep && miData.sleep.total_duration_min) {
        const miDates = miData.sleep.report_date || [];
        let miEndIdx = miDates.length;
        if (globalSelectedDate) {
            const foundMiIdx = miDates.indexOf(globalSelectedDate);
            if (foundMiIdx !== -1) miEndIdx = foundMiIdx + 1;
            else {
                // find closest date before selected
                let closest = -1;
                for(let i=0; i<miDates.length; i++) {
                    if (miDates[i] <= globalSelectedDate) closest = i;
                }
                miEndIdx = closest !== -1 ? closest + 1 : 0;
            }
        }
        let miStartIdx;
        if (globalSelectedPeriod === 0) {
            miStartIdx = 0;
        } else {
            miStartIdx = Math.max(0, miEndIdx - globalSelectedPeriod);
        }
        
        const sleepVals = miData.sleep.total_duration_min.slice(miStartIdx, miEndIdx);
        const sleepScores = miData.sleep.sleep_score ? miData.sleep.sleep_score.slice(miStartIdx, miEndIdx) : [];
        const rems = (miData.sleep.rem_min || []).slice(miStartIdx, miEndIdx);
        const deeps = (miData.sleep.deep_min || []).slice(miStartIdx, miEndIdx);
        const lights = (miData.sleep.light_min || []).slice(miStartIdx, miEndIdx);
        const awakes = (miData.sleep.awake_min || []).slice(miStartIdx, miEndIdx);

        const avgSleep = sleepVals.length ? sleepVals.reduce((a, b) => a + b, 0) / sleepVals.length / 60 : 0;
        const avgSleepScore = sleepScores.length ? sleepScores.reduce((a, b) => a + b, 0) / sleepScores.length : 0;
        const avgRem = rems.length ? rems.reduce((a, b) => a + b, 0) / rems.length / 60 : 0;
        const avgDeep = deeps.length ? deeps.reduce((a, b) => a + b, 0) / deeps.length / 60 : 0;
        const avgLight = lights.length ? lights.reduce((a, b) => a + b, 0) / lights.length / 60 : 0;
        const avgAwake = awakes.length ? awakes.reduce((a, b) => a + b, 0) / awakes.length / 60 : 0;

        document.getElementById('avg-sleep').textContent = sleepVals.length ? avgSleep.toFixed(1) : '--';

        // Smartband Score circle
        const avgSleepScoreRounded = Math.round(avgSleepScore);
        const sscIcon = avgSleepScoreRounded >= 80 ? '⭐' : avgSleepScoreRounded >= 60 ? '👍' : '⚠️';
        const sscColor = avgSleepScoreRounded >= 80 ? 'text-green-500' : avgSleepScoreRounded >= 60 ? 'text-yellow-500' : 'text-red-500';
        const sscBorder = avgSleepScoreRounded >= 80 ? 'border-green-500' : avgSleepScoreRounded >= 60 ? 'border-yellow-500' : 'border-red-500';
        document.getElementById('avg-sleepscore-text').textContent = sleepScores.length ? avgSleepScoreRounded : '--';
        document.getElementById('avg-sleepscore-text').className = `font-bold text-sm ${sscColor}`;
        document.getElementById('avg-sleepscore-circle').textContent = sleepScores.length ? sscIcon : '😴';
        document.getElementById('avg-sleepscore-circle').className = `w-9 h-9 rounded-full border-4 flex items-center justify-center text-sm mx-auto mb-1 ${sscBorder}`;

        document.getElementById('avg-rem').textContent = rems.length ? avgRem.toFixed(1) : '--';
        document.getElementById('avg-deep').textContent = deeps.length ? avgDeep.toFixed(1) : '--';
        document.getElementById('avg-light').textContent = lights.length ? avgLight.toFixed(1) : '--';
        document.getElementById('avg-awake').textContent = awakes.length ? avgAwake.toFixed(1) : '--';
    }
}

document.getElementById('patientSelect').addEventListener('change', (e) => {
    loadPatientData(e.target.value);
    loadAvailablePeriods(e.target.value);
});

function showSpinner(visible) {
    const el = document.getElementById('global-spinner');
    if (el) el.style.display = visible ? 'flex' : 'none';
}

function showError(msg) {
    const el = document.getElementById('global-error');
    if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function hideError() {
    const el = document.getElementById('global-error');
    if (el) el.style.display = 'none';
}

fetchPatients();
