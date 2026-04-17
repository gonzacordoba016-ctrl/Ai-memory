// ── METRICS ───────────────────────────────────────────────────────────────
async function loadMetrics() {
  try {
    const [pluginsR, profileR, proactiveR] = await Promise.all([
      authFetch(`${API}/plugins`).then(r => r.json()),
      authFetch(`${API}/profile`).then(r => r.json()),
      authFetch(`${API}/proactive/status`).then(r => r.json()),
    ]);

    // Plugins
    const pluginsEl = document.getElementById('metrics-plugins');
    const plugins   = pluginsR.plugins || [];
    pluginsEl.innerHTML = plugins.length
      ? plugins.map(p => `
          <div class="bg-[#131313] p-2 border-l-2 border-secondary/40">
            <div class="flex justify-between"><span class="text-[9px] text-secondary">${escHtml(p.name)}</span><span class="text-[8px] text-[#adaaaa]">v${escHtml(p.version)}</span></div>
            <p class="text-[8px] text-[#494847] mt-0.5">${escHtml(p.description)}</p>
          </div>`).join('')
      : '<p class="text-[10px] text-[#adaaaa]">Sin plugins</p>';

    // Perfil
    const profile  = profileR.profile || {};
    const profileEl = document.getElementById('metrics-profile');
    profileEl.innerHTML = profile.interaction_count > 0
      ? `<div class="bg-[#131313] p-2 space-y-1">
          <div class="flex justify-between text-[9px]"><span>EXPERTISE</span><span class="text-primary">${escHtml(profile.expertise || '—')}</span></div>
          <div class="flex justify-between text-[9px]"><span>INTERACTIONS</span><span class="text-primary">${profile.interaction_count}</span></div>
          ${profile.platforms?.length ? `<div class="text-[8px] text-[#adaaaa]">${profile.platforms.map(p => escHtml(p)).join(' · ')}</div>` : ''}
        </div>`
      : '<p class="text-[10px] text-[#adaaaa]">Perfil en construcción</p>';

    // Proactive
    const proactEl = document.getElementById('metrics-proactive');
    proactEl.innerHTML = `
      <div class="flex items-center gap-2 text-[9px]">
        <span class="w-2 h-2 ${proactiveR.running ? 'bg-primary animate-pulse' : 'bg-error'}"></span>
        <span class="${proactiveR.running ? 'text-primary' : 'text-error'}">${proactiveR.running ? 'RUNNING' : 'STOPPED'}</span>
        <span class="text-[#494847] ml-auto">${proactiveR.clients || 0} client(s)</span>
      </div>`;
  } catch(e) {}
}

// ── API ───────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const r = await authFetch(`${API}/stats`);
    const d = await r.json();
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('h-facts',   d.facts_count);
    set('h-msgs',    d.messages_count);
    set('h-nodes',   d.graph_nodes);
    set('s-facts',   d.facts_count);
    set('s-msgs',    d.messages_count);
    set('s-nodes',   d.graph_nodes);
    set('s-edges',   d.graph_edges);
    set('s-devices', d.hw_devices || 0);
    set('s-flashes', d.hw_flashes || 0);
    set('hw-devices',d.hw_devices || 0);
    set('hw-flashes',d.hw_flashes || 0);
    loadJobs();
  } catch(e) {}
}

async function loadFacts() {
  try {
    const r = await authFetch(`${API}/facts`);
    const d = await r.json();
    updateFacts(d.facts);
  } catch(e) {}
}

function updateFacts(facts) {
  const el      = document.getElementById('facts-list');
  const entries = Object.entries(facts || {});
  if (!entries.length) { el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin hechos</p>'; return; }
  el.innerHTML = entries.slice(0, 15).map(([k, v]) => `
    <div class="bg-[#131313] p-2 border-l-2 border-[#8eff71]/40">
      <span class="text-[8px] font-bold text-[#8eff71] block">${escHtml(k.toUpperCase())}</span>
      <span class="text-[9px] text-[#adaaaa]">${escHtml(v)}</span>
    </div>`).join('');
}

async function loadGraph() {
  try {
    const r = await authFetch(`${API}/graph`);
    const d = await r.json();
    const el = document.getElementById('graph-list');
    if (!d.relations?.length) { el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin relaciones</p>'; return; }
    el.innerHTML = d.relations.slice(0, 12).map(rel => `
      <div class="text-[9px] p-1.5 bg-[#131313]">
        <span class="text-primary">${escHtml(rel.subject)}</span>
        <span class="text-[#494847] mx-1">→${escHtml(rel.predicate)}→</span>
        <span class="text-secondary">${escHtml(rel.object)}</span>
      </div>`).join('');
    const hn = document.getElementById('h-nodes');
    const sn = document.getElementById('s-nodes');
    if (hn) hn.textContent = d.stats?.nodes ?? hn.textContent;
    if (sn) sn.textContent = d.stats?.nodes ?? sn.textContent;
    const se = document.getElementById('s-edges');
    if (se) se.textContent = d.stats?.edges ?? se.textContent;
  } catch(e) {}
}

// ── METRICS DASHBOARD ────────────────────────────────────────────────────

let _chartFirmware = null;
let _chartStock    = null;

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
    // ── KPIs ─────────────────────────────────────────────────────────────
    const [statsR, stockSumR, decisionsR, hardwareR] = await Promise.all([
      authFetch(`${API}/stats`),
      authFetch(`${API}/stock/summary`),
      authFetch(`${API}/decisions?limit=10`),
      authFetch(`${API}/hardware/stats`),
    ]);

    if (statsR.ok) {
      const s = await statsR.json();
      document.getElementById('kpi-devices').textContent   = s.hw_devices ?? 0;
      document.getElementById('kpi-firmware').textContent  = s.hw_flashes ?? 0;
    }
    if (stockSumR.ok) {
      const s = await stockSumR.json();
      document.getElementById('kpi-stock').textContent = s.in_stock ?? s.total_components ?? 0;
    }

    // Decisions count + list
    let allDecisionItems = [];
    if (decisionsR.ok) {
      const decs = await decisionsR.json();
      allDecisionItems = decs.map(d => ({
        type: 'DECISION',
        date: d.created_at || '',
        label: d.project + (d.component ? ' — ' + d.component : ''),
        text: d.decision || '',
      }));
      document.getElementById('kpi-decisions').textContent = decs.length;
      const dl = document.getElementById('metrics-decisions-list');
      if (dl) {
        if (!decs.length) {
          dl.innerHTML = '<p class="text-[8px] opacity-40">Sin decisiones guardadas</p>';
        } else {
          dl.innerHTML = decs.map(d => `
            <div class="bg-surface-container-low px-3 py-2 border-l border-secondary/20 text-[8px]">
              <span class="text-secondary font-mono">${esc(d.project)}${d.component?' — '+esc(d.component):''}</span>
              <span class="ml-2 opacity-50">${(d.created_at||'').slice(0,10)}</span>
              <div class="opacity-70 mt-0.5">${esc((d.reasoning||'').slice(0,90))}${(d.reasoning||'').length>90?'…':''}</div>
            </div>`).join('');
        }
      }
    }

    // ── Firmware chart (bar por dispositivo) ─────────────────────────────
    const fwR = await authFetch(`${API}/hardware/devices`);
    const allFirmwareItems = [];   // acumular para el timeline
    if (fwR.ok) {
      const fwData = await fwR.json();
      const devices  = (fwData.registered || []).slice(0, 8);
      const labels   = devices.map(d => d.device_name?.slice(0, 10) || '?');
      const fwHistories = await Promise.all(devices.map(async d => {
        try {
          const r = await authFetch(`${API}/hardware/firmware/${encodeURIComponent(d.device_name)}`);
          if (!r.ok) return { device: d.device_name, history: [] };
          const j = await r.json();
          return { device: d.device_name, history: j.history || [] };
        } catch { return { device: d.device_name, history: [] }; }
      }));
      const counts = fwHistories.map(h => h.history.length);
      // Recopilar items para el timeline
      fwHistories.forEach(({ device, history }) => {
        history.slice(0, 3).forEach(fw => {
          allFirmwareItems.push({
            type: 'FLASH',
            date: fw.timestamp || '',
            label: device,
            text: fw.task || 'firmware',
            success: fw.success,
          });
        });
      });

      const ctx = document.getElementById('chart-firmware');
      if (ctx) {
        if (_chartFirmware) _chartFirmware.destroy();
        _chartFirmware = new Chart(ctx, {
          type: 'bar',
          data: {
            labels,
            datasets: [{
              data:            counts,
              backgroundColor: 'rgba(164,255,185,0.25)',
              borderColor:     '#a4ffb9',
              borderWidth:     1,
            }],
          },
          options: { ..._CHART_DEFAULTS, maintainAspectRatio: false },
        });
      }
    }

    // ── Stock por categoría (doughnut) ────────────────────────────────────
    const stockR = await authFetch(`${API}/stock/categories`);
    if (stockR.ok) {
      const cats = await stockR.json();  // [{category, count}]
      const labels = cats.map(c => c.category || 'Sin categoría');
      const data   = cats.map(c => c.count);
      const COLORS = ['#a4ffb9','#00cbfe','#8eff71','#ff716c','#ffd700','#c77dff','#4fc3f7','#f06292'];

      const ctx2 = document.getElementById('chart-stock');
      if (ctx2) {
        if (_chartStock) _chartStock.destroy();
        _chartStock = new Chart(ctx2, {
          type: 'doughnut',
          data: {
            labels,
            datasets: [{
              data,
              backgroundColor: COLORS.slice(0, labels.length).map(c => c + '55'),
              borderColor:     COLORS.slice(0, labels.length),
              borderWidth: 1,
            }],
          },
          options: {
            animation: false,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
          },
        });
      }

      // Leyenda manual
      const legend = document.getElementById('chart-stock-legend');
      if (legend) {
        legend.innerHTML = labels.map((l, i) => `
          <div class="flex items-center gap-1.5">
            <span style="width:8px;height:8px;background:${COLORS[i] || '#494847'};display:inline-block;"></span>
            <span class="opacity-70">${esc(l)}</span>
            <span class="text-primary ml-auto">${data[i]}</span>
          </div>`).join('');
      }
    }

    // ── Timeline actividad reciente ───────────────────────────────────────
    const activityEl = document.getElementById('metrics-activity');
    if (activityEl) {
      const items = [
        ...allDecisionItems,
        ...allFirmwareItems,
      ].filter(i => i.date).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 12);

      if (!items.length) {
        activityEl.innerHTML = '<p class="text-[8px] opacity-40">Sin actividad registrada</p>';
      } else {
        const BADGE = {
          FLASH:    { color: '#a4ffb9', bg: 'rgba(164,255,185,0.08)' },
          DECISION: { color: '#00cbfe', bg: 'rgba(0,203,254,0.08)'   },
        };
        activityEl.innerHTML = items.map(item => {
          const { color, bg } = BADGE[item.type] || BADGE.DECISION;
          const dateStr = (item.date || '').slice(0, 16).replace('T', ' ');
          const statusDot = item.type === 'FLASH'
            ? `<span style="color:${item.success ? '#8eff71' : '#ff716c'}">●</span> `
            : '';
          return `
            <div class="flex items-start gap-2 px-2 py-1.5 text-[8px]" style="background:${bg};border-left:2px solid ${color}20">
              <span class="font-mono shrink-0" style="color:${color}">${item.type}</span>
              <span class="opacity-40 shrink-0">${dateStr}</span>
              <span class="opacity-70 truncate">${statusDot}${esc(item.label)}</span>
              <span class="opacity-50 truncate flex-1">${esc((item.text||'').slice(0,50))}</span>
            </div>`;
        }).join('');
      }
    }

  } catch (e) {
    console.error('[Metrics]', e);
  }
}
