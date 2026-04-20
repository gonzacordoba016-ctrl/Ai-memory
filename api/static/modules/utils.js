// ── UTILS ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
const esc = escHtml;

// Render markdown seguro para mensajes del agente.
// Protege los bloques LaTeX antes de que marked.js los consuma.
function renderMarkdown(text) {
  try {
    if (typeof marked === 'undefined') return escHtml(text);
    marked.setOptions({ gfm: true, breaks: true });

    // Extraer bloques de math antes de pasar a marked para que no los rompa
    const mathStore = [];
    const placeholder = (i) => `\x02MATH${i}\x03`;
    let t = String(text);

    // display math: $$...$$ y \[...\]
    t = t.replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => { mathStore.push(`$$${m}$$`); return placeholder(mathStore.length - 1); });
    t = t.replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => { mathStore.push(`\\[${m}\\]`); return placeholder(mathStore.length - 1); });
    // inline math: \(...\) y $...$  (no multiline)
    t = t.replace(/\\\((.+?)\\\)/g, (_, m) => { mathStore.push(`\\(${m}\\)`); return placeholder(mathStore.length - 1); });
    t = t.replace(/\$([^\n$]+?)\$/g, (_, m) => { mathStore.push(`$${m}$`); return placeholder(mathStore.length - 1); });

    let html = marked.parse(t);

    // Restaurar los bloques de math
    mathStore.forEach((math, i) => {
      html = html.replace(placeholder(i), math);
    });

    return html;
  } catch(e) {
    return escHtml(text);
  }
}

// ── POST-RENDER: KaTeX + highlight.js + Bode charts ─────────────────────
function _postRender(el) {
  if (!el) return;

  // Syntax highlighting
  if (typeof hljs !== 'undefined') {
    el.querySelectorAll('pre code').forEach(block => {
      if (!block.dataset.highlighted) hljs.highlightElement(block);
    });
  }

  // Math rendering (KaTeX auto-render)
  if (typeof renderMathInElement !== 'undefined') {
    renderMathInElement(el, {
      delimiters: [
        { left: '$$',  right: '$$',  display: true  },
        { left: '\\[', right: '\\]', display: true  },
        { left: '$',   right: '$',   display: false },
        { left: '\\(', right: '\\)', display: false },
      ],
      throwOnError: false,
    });
  }

  // Bode plot charts (data-bode attribute)
  el.querySelectorAll('canvas[data-bode]').forEach(canvas => {
    try {
      const cfg = JSON.parse(canvas.dataset.bode);
      delete canvas.dataset.bode;
      _renderBode(canvas, cfg);
    } catch(e) { console.warn('Bode parse error', e); }
  });
}

function _renderBode(canvas, { type, fc }) {
  const pts = 80;
  const labels = [], gain = [], phase = [];
  for (let i = 0; i < pts; i++) {
    const f = fc * Math.pow(10, (i - pts / 2) / (pts / 4));
    const ratio = f / fc;
    const mag = type === 'lowpass'
      ? -20 * Math.log10(Math.sqrt(1 + ratio * ratio))
      : 20 * Math.log10(ratio / Math.sqrt(1 + ratio * ratio));
    const ph = type === 'lowpass'
      ? -Math.atan(ratio) * 180 / Math.PI
      : 90 - Math.atan(ratio) * 180 / Math.PI;
    labels.push(f < 1000 ? f.toFixed(1) + 'Hz' : (f / 1000).toFixed(2) + 'kHz');
    gain.push(parseFloat(mag.toFixed(2)));
    phase.push(parseFloat(ph.toFixed(1)));
  }
  // Mark fc
  const fcLabel = fc < 1000 ? fc.toFixed(1) + 'Hz' : (fc / 1000).toFixed(2) + 'kHz';
  new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Ganancia (dB)', data: gain, borderColor: '#a4ffb9', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
        { label: 'Fase (°)',      data: phase, borderColor: '#00cbfe', borderWidth: 1,   pointRadius: 0, yAxisID: 'y1', borderDash: [4,3] },
      ],
    },
    options: {
      responsive: true, animation: false,
      plugins: {
        legend: { labels: { color: '#adaaaa', font: { size: 9 } } },
        annotation: {},
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        x: { ticks: { color: '#494847', font: { size: 8 }, maxTicksLimit: 10 }, grid: { color: '#1a1a1a' } },
        y:  { ticks: { color: '#a4ffb9', font: { size: 8 } }, grid: { color: '#1a1a1a' }, title: { display: true, text: 'dB', color: '#494847', font: { size: 8 } } },
        y1: { position: 'right', ticks: { color: '#00cbfe', font: { size: 8 } }, grid: { drawOnChartArea: false }, title: { display: true, text: '°', color: '#494847', font: { size: 8 } } },
      },
    },
  });
}

// ── LOGS ──────────────────────────────────────────────────────────────────
function addLog(msg, type = 'info') {
  const el = document.getElementById('logs-list');
  const ts = new Date().toLocaleTimeString('es', {hour12: false});
  const colors = { info:'text-[#494847]', warn:'text-[#ffaa00]', error:'text-error', cmd:'text-primary' };
  const line = document.createElement('div');
  line.className  = `${colors[type] || 'text-[#494847]'} leading-relaxed`;
  line.textContent = `[${ts}] ${msg}`;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
  if (el.children.length > 200) el.removeChild(el.firstChild);
}

// ── DEV EXPORT ───────────────────────────────────────────────────────────
async function exportChat() {
  const sid = _session_id;
  if (!sid) { alert('[DEV] No hay sesión activa'); return; }
  try {
    const res  = await authFetch(`${API}/history?session_id=${encodeURIComponent(sid)}&limit=2000`);
    const data = await res.json();
    const msgs = data.messages || [];
    const out  = {
      exported_at: new Date().toISOString(),
      session_id:  sid,
      total:       msgs.length,
      messages:    msgs,
    };
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `stratum_chat_${sid.slice(0,8)}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('[DEV] Error exportando: ' + e.message);
  }
}

// ── OFFLINE QUEUE ────────────────────────────────────────────────────────
function _saveQueue() {
  // Queue es solo en memoria — no persiste en localStorage para evitar
  // que mensajes de sesiones anteriores se reenvíen en un reload.
}
function _updateQueueBadge() {
  const s = document.getElementById('status-text');
  if (!s) return;
  s.innerHTML = _offlineQueue.length > 0
    ? `ENGINE_OFFLINE <span class="queue-badge">${_offlineQueue.length} QUEUED</span>`
    : s.textContent;
}
function _enqueueMessage(text) {
  _offlineQueue.push({ text, ts: Date.now() });
  _saveQueue();
  const area = document.getElementById('chat-area');
  if (area) {
    const div = document.createElement('div');
    const ts  = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
    div.className     = 'msg-queued font-mono text-xs';
    div.dataset.queued = 'true';
    div.innerHTML = `<span class="text-[8px] text-[#494847] mr-2">${ts} QUEUED</span><span class="text-[#adaaaa]">${text.replace(/</g,'&lt;')}</span>`;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
  }
  _updateQueueBadge();
  addLog(`Mensaje encolado (sin conexión): "${text.slice(0, 40)}"`, 'warn');
}
async function drainOfflineQueue() {
  if (!_offlineQueue.length) return;
  document.querySelectorAll('[data-queued="true"]').forEach(el => el.remove());
  const queue = [..._offlineQueue];
  _offlineQueue = [];
  _saveQueue();
  for (const item of queue) {
    if (!ws || ws.readyState !== 1) break;
    addMessage('user', item.text, []);
    isStreaming = true;
    document.getElementById('send-btn').classList.add('opacity-40', 'pointer-events-none');
    currentAgentEl = null;
    addLog(`Enviando mensaje encolado: "${item.text.slice(0, 40)}"`, 'info');
    ws.send(JSON.stringify({ message: item.text }));
    await new Promise(res => {
      const handler = (e) => {
        try { const d = JSON.parse(e.data); if (d.type === 'done' || d.type === 'error') { ws.removeEventListener('message', handler); res(); } } catch(e) {}
      };
      ws.addEventListener('message', handler);
      setTimeout(res, 30000);
    });
  }
}

// ── SEARCH ────────────────────────────────────────────────────────────────
async function doSearch() {
  const q  = document.getElementById('search-input').value.trim();
  const el = document.getElementById('search-results');
  if (!q) return;
  el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Buscando...</p>';
  try {
    const r = await authFetch(`${API}/search?q=${encodeURIComponent(q)}&top_k=5`);
    const d = await r.json();
    if (!d.results?.length) { el.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin resultados</p>'; return; }
    el.innerHTML = d.results.map(res => `
      <div class="bg-[#131313] p-2 border-l-2 border-[#494847]/40 text-[9px] text-[#adaaaa] leading-relaxed">${escHtml(res)}</div>`).join('');
  } catch(e) { el.innerHTML = '<p class="text-[10px] text-error">Error</p>'; }
}
