// ── HARDWARE ──────────────────────────────────────────────────────────────
async function loadHardware() {
  try {
    const r = await authFetch(`${API}/hardware/devices`);
    const d = await r.json();

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('hw-devices', d.stats?.devices       || 0);
    set('hw-flashes', d.stats?.total_flashes || 0);
    set('hw-success', d.stats?.successful    || 0);
    set('hw-failed',  d.stats?.failed        || 0);
    set('s-devices',  d.stats?.devices       || 0);
    set('s-flashes',  d.stats?.total_flashes || 0);

    const el = document.getElementById('devices-list');
    const connected  = d.connected  || [];
    const registered = d.registered || [];
    const connNames  = new Set(connected.map(x => x.name));
    const all = [...connected, ...registered.filter(r => !connNames.has(r.name)).map(r => ({...r, _offline: true}))];

    if (!all.length) { el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin dispositivos</p>'; return; }

    el.innerHTML = all.map(dev => {
      const online = !dev._offline;
      const badge  = dev.micropython
        ? '<span class="text-[8px] px-1 bg-primary/10 text-primary border border-primary/20">MicroPython</span>'
        : '';
      return `
        <div class="group cursor-pointer py-1.5 hover:bg-[#131313] transition-colors px-1" onclick="loadDeviceHistory('${escHtml(dev.name)}')">
          <div class="flex items-center gap-2 text-[10px] ${online ? 'text-secondary' : 'text-[#adaaaa]'}">
            <span class="material-symbols-outlined text-[12px]">${dev.platform?.includes('esp32') ? 'wifi' : 'usb'}</span>
            ${escHtml(dev.name)}
            ${online ? '' : '<span class="text-[8px] text-error ml-auto">OFFLINE</span>'}
          </div>
          <div class="flex items-center gap-2 ml-5 mt-0.5">
            <span class="text-[9px] text-[#adaaaa]">${dev.port || '—'}</span>
            ${badge}
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('devices-list').innerHTML = '<p class="text-[10px] text-error">Error conectando</p>';
  }
}

async function loadDeviceHistory(name) {
  try {
    const r = await authFetch(`${API}/hardware/firmware/${encodeURIComponent(name)}`);
    const d = await r.json();
    const el = document.getElementById('devices-list');
    let html = `<button onclick="loadHardware()" class="text-[8px] text-secondary mb-2 hover:underline">← BACK</button>
      <div class="flex items-center justify-between mb-2">
        <div class="text-[10px] font-bold">${escHtml(name)}</div>
        <div class="flex gap-2">
          <button onclick="loadFirmwareDiff('${escHtml(name)}')"
            class="text-[7px] font-mono text-[#494847] hover:text-secondary border border-[#494847]/40 hover:border-secondary/60 px-2 py-0.5 transition-colors">
            DIFF
          </button>
          <a href="${API}/hardware/firmware/${encodeURIComponent(name)}/platformio.zip"
            class="text-[7px] font-mono text-[#494847] hover:text-primary border border-[#494847]/40 hover:border-primary/60 px-2 py-0.5 transition-colors">
            PIO.ZIP
          </a>
        </div>
      </div>`;
    if (d.current) {
      html += `<div class="bg-[#131313] p-2 border-l-2 border-primary mb-2">
        <span class="text-[8px] text-primary block mb-1">CURRENT_FIRMWARE</span>
        <p class="text-[9px] text-[#adaaaa]">${escHtml(d.current.task)}</p>
        <pre class="text-[8px] text-secondary bg-black p-1 mt-1 overflow-x-auto">${escHtml((d.current.code || '').slice(0,200))}</pre>
      </div>`;
    }
    html += `<div id="diff-panel" class="hidden mb-2"></div>`;
    (d.history || []).forEach(h => {
      html += `<div class="bg-[#131313] p-2 mb-1 border-l-2 ${h.success ? 'border-primary/40' : 'border-error/40'}">
        <p class="text-[9px] text-[#adaaaa]">${escHtml((h.task||'').slice(0,60))}</p>
        <span class="text-[8px] text-[#494847]">${h.timestamp||''}</span>
      </div>`;
    });
    el.innerHTML = html;
  } catch(e) {}
}

async function loadFirmwareDiff(name) {
  const panel = document.getElementById('diff-panel');
  if (!panel) return;
  panel.innerHTML = '<span class="text-[8px] text-[#494847]">Cargando diff...</span>';
  panel.classList.remove('hidden');
  try {
    const r = await authFetch(`${API}/hardware/firmware/${encodeURIComponent(name)}/diff`);
    const d = await r.json();
    if (!d.diff) {
      panel.innerHTML = `<div class="text-[8px] text-[#494847] p-2">${escHtml(d.message || 'Sin diff')}</div>`;
      return;
    }
    const lines = d.diff.split('\n').map(line => {
      const cls = line.startsWith('+') && !line.startsWith('+++')
        ? 'text-primary'
        : line.startsWith('-') && !line.startsWith('---')
        ? 'text-error'
        : line.startsWith('@')
        ? 'text-secondary'
        : 'text-[#adaaaa]';
      return `<div class="${cls}">${escHtml(line)}</div>`;
    }).join('');
    panel.innerHTML = `
      <div class="text-[7px] text-[#494847] mb-1">DIFF: ${escHtml(d.old_ts?.slice(0,10)||'')} → ${escHtml(d.new_ts?.slice(0,10)||'')}</div>
      <pre class="text-[8px] bg-black p-2 overflow-x-auto leading-relaxed max-h-48 overflow-y-auto border-l-2 border-[#494847]/40">${lines}</pre>`;
  } catch(e) {
    panel.innerHTML = '<div class="text-[8px] text-error p-2">Error cargando diff</div>';
  }
}

// ── JOBS ─────────────────────────────────────────────────────────────────
async function loadJobs() {
  try {
    const r = await authFetch(`${API}/jobs`);
    const d = await r.json();
    const jobs = (d.jobs || []).slice(0, 4);
    const el = document.getElementById('jobs-list');
    const countEl = document.getElementById('jobs-count');
    if (countEl) countEl.textContent = d.total || 0;
    // Floating badge
    const badge = document.getElementById('jobs-badge');
    const badgeCount = document.getElementById('jobs-badge-count');
    const activeJobs = (d.jobs || []).filter(j => j.status === 'running' || j.status === 'pending').length;
    if (badge) badge.classList.toggle('hidden', activeJobs === 0);
    if (badgeCount) badgeCount.textContent = activeJobs;

    if (!jobs.length) {
      if (el) el.innerHTML = '<div class="text-[9px] text-[#494847] opacity-40">NO_ACTIVE_JOBS</div>';
      return;
    }

    el.innerHTML = jobs.map(j => {
      const colors   = { done:'border-primary', error:'border-error', running:'border-secondary', pending:'border-[#494847]/50' };
      const pctColors= { done:'bg-primary', error:'bg-error', running:'bg-secondary animate-pulse', pending:'bg-[#494847]' };
      const border   = colors[j.status]   || 'border-[#494847]/50';
      const barColor = pctColors[j.status] || 'bg-[#494847]';
      const pct      = j.progress || (j.status === 'done' ? 100 : 0);
      return `
        <div class="bg-[#131313] border-l-2 ${border} p-3">
          <div class="flex justify-between text-[10px] mb-1.5">
            <span class="truncate max-w-[60%]">${escHtml(j.type?.toUpperCase() || 'JOB')}</span>
            <span class="${j.status === 'done' ? 'text-primary' : j.status === 'error' ? 'text-error' : 'text-secondary'}">${pct}%</span>
          </div>
          <div class="w-full h-0.5 bg-black overflow-hidden">
            <div class="h-full ${barColor}" style="width:${pct}%"></div>
          </div>
          <div class="text-[8px] text-[#adaaaa] mt-1">${j.status?.toUpperCase()}</div>
        </div>`;
    }).join('');
  } catch(e) {}
}

// ── SIGNAL OSCILLOSCOPE (Chart.js) ────────────────────────────────────────
let _oscChart = null;

function _initOscChart() {
  const canvas = document.getElementById('osc-chart');
  if (!canvas || !window.Chart) return;
  const ctx = canvas.getContext('2d');
  const labels = Array.from({length: 40}, (_, i) => i);
  const data   = Array(40).fill(null);
  _oscChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data,
        borderColor: '#00cbfe',
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 0,
        tension: 0.3,
        fill: true,
        backgroundColor: 'rgba(0,203,254,0.06)',
      }]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: {
          display: true,
          min: 0, max: 1023,
          grid: { color: 'rgba(73,72,71,0.2)', lineWidth: 0.5 },
          ticks: { display: false },
          border: { display: false },
        }
      },
    }
  });
}

function connectSignalWS() {
  wsSignal = new WebSocket(_wsTokenParam(WS_SIGNAL));
  wsSignal.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'signal' || data.a0 !== undefined) {
      const point = data.data || data;
      signalBuffer.push(point);
      if (signalBuffer.length > 40) signalBuffer.shift();
      renderOscilloscope(point);
    }
  };
  wsSignal.onclose = () => setTimeout(connectSignalWS, 3000);
}

function renderOscilloscope(latest) {
  if (!_oscChart) _initOscChart();
  if (_oscChart) {
    const vals = Array(40).fill(null);
    signalBuffer.forEach((b, i) => { vals[i + (40 - signalBuffer.length)] = b.a0 || 0; });
    _oscChart.data.datasets[0].data = vals;
    // último punto en verde
    _oscChart.data.datasets[0].pointRadius = vals.map((v, i) => (v !== null && i === 39) ? 3 : 0);
    _oscChart.data.datasets[0].pointBackgroundColor = '#a4ffb9';
    _oscChart.update('none');
  }
  if (latest) {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('osc-volt', (latest.v || 0).toFixed(2) + 'V');
    set('osc-a0', latest.a0 || 0);
    set('osc-label', 'RECEIVING [SERIAL_DATA_STREAM]...');
    const dot = document.getElementById('osc-status-dot');
    if (dot) dot.className = 'w-2 h-2 bg-secondary rounded-full animate-pulse';
  }
}

function renderIdleOscilloscope() {
  try { if (!_oscChart) _initOscChart(); } catch(e) {}
  if (!_oscChart) return;
  const idle = [30,50,70,45,20,60,90,65,40,20,55,85,50,35,75,25,60,45,70,40,
                30,50,70,45,20,60,90,65,40,20,55,85,50,35,75,25,60,45,70,40];
  _oscChart.data.datasets[0].data = idle.map(h => Math.round(h / 100 * 1023));
  _oscChart.data.datasets[0].borderColor = 'rgba(0,203,254,0.2)';
  _oscChart.update('none');
}

// ── VISION MODAL ──────────────────────────────────────────────────────────
let visionImageB64 = null;

function openVisionModal() {
  const m = document.getElementById('vision-modal');
  m.classList.remove('hidden');
  m.classList.add('flex');
  loadDevicesForVision();
}
function closeVisionModal() {
  const m = document.getElementById('vision-modal');
  m.classList.add('hidden');
  m.classList.remove('flex');
  visionImageB64 = null;
  document.getElementById('vision-preview').classList.add('hidden');
  document.getElementById('vision-preview').src = '';
  document.getElementById('vision-placeholder').classList.remove('hidden');
  document.getElementById('vision-status').classList.add('hidden');
  document.getElementById('vision-analyze-btn').disabled = true;
}
function handleVisionFile(event) {
  const file = event.target.files[0];
  if (file) loadVisionImage(file);
}
function handleVisionDrop(event) {
  event.preventDefault();
  const file = event.dataTransfer.files[0];
  if (file?.type.startsWith('image/')) loadVisionImage(file);
}
function loadVisionImage(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl  = e.target.result;
    visionImageB64 = dataUrl.split(',')[1];
    const preview  = document.getElementById('vision-preview');
    preview.src    = dataUrl;
    preview.classList.remove('hidden');
    document.getElementById('vision-placeholder').classList.add('hidden');
    document.getElementById('vision-analyze-btn').disabled = false;
  };
  reader.readAsDataURL(file);
}
async function loadDevicesForVision() {
  try {
    const r = await authFetch(`${API}/hardware/devices`);
    const d = await r.json();
    const all = [...(d.connected || []), ...(d.registered || [])];
    const el  = document.getElementById('vision-devices-list');
    el.innerHTML = all.slice(0, 5).map(dev => `
      <button onclick="document.getElementById('vision-device').value='${escHtml(dev.name)}'"
        class="text-[8px] px-2 py-1 bg-[#131313] text-[#adaaaa] hover:text-primary hover:bg-[#201f1f] transition-colors mr-1 mb-1">
        ${escHtml(dev.name)}</button>`).join('');
  } catch(e) {}
}
async function analyzeCircuit() {
  if (!visionImageB64) return;
  const deviceName = document.getElementById('vision-device').value.trim();
  const btn        = document.getElementById('vision-analyze-btn');
  const statusEl   = document.getElementById('vision-status');
  const progressEl = document.getElementById('vision-progress');
  const statusText = document.getElementById('vision-status-text');
  const statusDot  = document.getElementById('vision-status-dot');
  btn.disabled = true;
  statusEl.classList.remove('hidden');
  statusDot.className = 'w-2 h-2 bg-secondary animate-pulse';
  let progress = 0;
  const iv = setInterval(() => {
    progress = Math.min(progress + 2, 85);
    progressEl.style.width = progress + '%';
    statusText.textContent = progress < 30 ? 'Enviando imagen...' : progress < 60 ? 'Identificando componentes...' : 'Extrayendo conexiones...';
  }, 400);
  try {
    const r = await authFetch(`${API}/hardware/vision/analyze`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ image: visionImageB64, device_name: deviceName }),
    });
    const result = await r.json();
    clearInterval(iv);
    progressEl.style.width = '100%';
    if (result.success) {
      statusDot.className   = 'w-2 h-2 bg-primary';
      statusText.textContent = '✓ Análisis completado';
      addMessage('agent', result.message, ['hardware']);
      renderVisionResults(result.circuit);
      setTimeout(closeVisionModal, 1500);
    } else {
      statusDot.className   = 'w-2 h-2 bg-error';
      statusText.textContent = 'Error en el análisis';
      addMessage('agent', result.message, ['hardware']);
      btn.disabled = false;
    }
  } catch(e) {
    clearInterval(iv);
    statusDot.className   = 'w-2 h-2 bg-error';
    statusText.textContent = 'Error de conexión';
    btn.disabled = false;
  }
}
function renderVisionResults(circuit) {
  if (!circuit?.project_name) return;
  const panel   = document.getElementById('vision-results-panel');
  const content = document.getElementById('vision-results-content');
  panel.classList.remove('hidden');
  const comps = (circuit.components || []).slice(0, 6);
  content.innerHTML = `
    <div class="bg-[#131313] p-2 border-l-2 border-secondary">
      <div class="flex justify-between items-center mb-1">
        <span class="text-[9px] font-bold text-secondary">${escHtml(circuit.project_name)}</span>
        <span class="text-[8px] text-[#adaaaa]">${escHtml(circuit.confidence || '')}</span>
      </div>
      ${circuit.description ? `<p class="text-[8px] text-[#adaaaa]">${escHtml(circuit.description)}</p>` : ''}
    </div>
    ${comps.map(c => `
      <div class="flex items-center gap-2 py-1 border-b border-[#494847]/10 text-[9px]">
        <span class="px-1 bg-secondary/10 text-secondary text-[8px] uppercase">${escHtml(c.type || '?')}</span>
        <span>${escHtml(c.name || '?')}</span>
        ${c.pin ? `<span class="text-[#494847] ml-auto">pin ${escHtml(c.pin)}</span>` : ''}
      </div>`).join('')}`;
}
