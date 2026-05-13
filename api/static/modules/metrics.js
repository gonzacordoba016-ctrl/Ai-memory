async function loadMetrics() {
  // SYSTEM no necesita metricas legacy.
}

async function loadStats() {
  try {
    const r = await authFetch(`${API}/stats`);
    if (!r.ok) return;
    const d = await r.json();
    setMetricText('h-facts', d.facts_count);
    setMetricText('h-msgs', d.messages_count);
    setMetricText('h-nodes', d.graph_nodes);
    setMetricText('s-facts', d.facts_count);
    setMetricText('s-msgs', d.messages_count);
    setMetricText('s-nodes', d.graph_nodes);
    setMetricText('s-devices', d.hw_devices || 0);
  } catch {}
}

async function loadFacts() {
  try {
    const r = await authFetch(`${API}/facts`);
    if (!r.ok) return;
    const d = await r.json();
    updateFacts(d.facts);
  } catch {}
}

function updateFacts(facts) {
  const el = document.getElementById('facts-list');
  if (!el) return;

  const entries = Object.entries(facts || {});
  if (!entries.length) {
    el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin hechos</p>';
    return;
  }

  el.innerHTML = entries.slice(0, 15).map(([k, v]) => `
    <div class="bg-[#131313] p-2 border-l-2 border-[#8eff71]/40">
      <span class="text-[8px] font-bold text-[#8eff71] block">${escHtml(k.toUpperCase())}</span>
      <span class="text-[9px] text-[#adaaaa]">${escHtml(v)}</span>
    </div>`).join('');
}

async function loadGraph() {
  const el = document.getElementById('graph-list');
  if (!el) return;

  try {
    const r = await authFetch(`${API}/graph`);
    if (!r.ok) return;
    const d = await r.json();
    if (!d.relations?.length) {
      el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin relaciones</p>';
      return;
    }

    el.innerHTML = d.relations.slice(0, 12).map(rel => `
      <div class="text-[9px] p-1.5 bg-[#131313]">
        <span class="text-primary">${escHtml(rel.subject)}</span>
        <span class="text-[#494847] mx-1">-&gt;${escHtml(rel.predicate)}-&gt;</span>
        <span class="text-secondary">${escHtml(rel.object)}</span>
      </div>`).join('');

    setMetricText('h-nodes', d.stats?.nodes);
    setMetricText('s-nodes', d.stats?.nodes);
  } catch {}
}

let _chartFirmware = null;
let _chartStock = null;

const _CHART_DEFAULTS = {
  animation: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { color: '#494847', font: { size: 8 } }, grid: { color: 'rgba(73,72,71,0.2)' } },
    y: { ticks: { color: '#494847', font: { size: 8 } }, grid: { color: 'rgba(73,72,71,0.2)' } },
  },
};

async function loadMetricsPanel() {
  try {
    const [statsR, stockSumR, decisionsR] = await Promise.all([
      authFetch(`${API}/stats`),
      authFetch(`${API}/stock/summary`),
      authFetch(`${API}/decisions?limit=10`),
    ]);

    if (statsR.ok) {
      const s = await statsR.json();
      setMetricText('kpi-devices', s.hw_devices ?? 0);
      setMetricText('kpi-firmware', s.hw_flashes ?? 0);
    }

    if (stockSumR.ok) {
      const s = await stockSumR.json();
      setMetricText('kpi-stock', s.in_stock ?? s.total_components ?? 0);
    }

    if (decisionsR.ok) {
      const decisions = await decisionsR.json();
      setMetricText('kpi-decisions', Array.isArray(decisions) ? decisions.length : 0);
    }

    await renderFirmwareChart();
    await renderStockChart();
  } catch (e) {
    console.error('[Metrics]', e);
  }
}

async function renderFirmwareChart() {
  const ctx = document.getElementById('chart-firmware');
  if (!ctx || !window.Chart) return;

  const fwR = await authFetch(`${API}/hardware/devices`);
  if (!fwR.ok) return;

  const fwData = await fwR.json();
  const devices = (fwData.registered || []).slice(0, 8);
  const labels = devices.map(d => (d.device_name || d.name || '?').slice(0, 10));
  const histories = await Promise.all(devices.map(async device => {
    const name = device.device_name || device.name;
    if (!name) return [];
    try {
      const r = await authFetch(`${API}/hardware/firmware/${encodeURIComponent(name)}`);
      if (!r.ok) return [];
      const j = await r.json();
      return j.history || [];
    } catch {
      return [];
    }
  }));

  if (_chartFirmware) _chartFirmware.destroy();
  _chartFirmware = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: histories.map(history => history.length),
        backgroundColor: 'rgba(164,255,185,0.25)',
        borderColor: '#a4ffb9',
        borderWidth: 1,
      }],
    },
    options: { ..._CHART_DEFAULTS, maintainAspectRatio: false },
  });
}

async function renderStockChart() {
  const ctx = document.getElementById('chart-stock');
  if (!ctx || !window.Chart) return;

  const stockR = await authFetch(`${API}/stock/categories`);
  if (!stockR.ok) return;

  const categories = await stockR.json();
  const labels = categories.map(c => c.category || 'Sin categoria');
  const data = categories.map(c => c.count);
  const colors = ['#a4ffb9', '#00cbfe', '#8eff71', '#ff716c', '#ffd700', '#c77dff', '#4fc3f7', '#f06292'];

  if (_chartStock) _chartStock.destroy();
  _chartStock = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors.slice(0, labels.length).map(c => c + '55'),
        borderColor: colors.slice(0, labels.length),
        borderWidth: 1,
      }],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
    },
  });

  const legend = document.getElementById('chart-stock-legend');
  if (!legend) return;
  legend.innerHTML = labels.map((label, i) => `
    <div class="flex items-center gap-1.5">
      <span style="width:8px;height:8px;background:${colors[i] || '#494847'};display:inline-block;"></span>
      <span class="opacity-70">${escHtml(label)}</span>
      <span class="text-primary ml-auto">${data[i]}</span>
    </div>`).join('');
}

function setMetricText(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined && value !== null) el.textContent = value;
}
