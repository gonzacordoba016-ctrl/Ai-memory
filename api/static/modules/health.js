// ── CONNECTION STATUS ─────────────────────────────────────────────────────
function setConnected(ok) {
  const dot   = document.getElementById('conn-dot');
  const label = document.getElementById('conn-label');
  const estat = document.getElementById('engine-status');
  if (ok) {
    dot.className   = 'w-1.5 h-1.5 bg-primary rounded-full animate-pulse';
    label.className = 'text-primary text-[10px] tracking-widest';
    label.textContent = 'ACTIVE_CONNECTION';
    estat.textContent = 'STATUS: OPERATIONAL';
    estat.className   = 'text-primary text-[9px]';
  } else {
    dot.className   = 'w-1.5 h-1.5 bg-gray-500 rounded-full';
    label.className = 'text-gray-500 text-[10px] tracking-widest';
    label.textContent = 'DISCONNECTED';
    estat.textContent = 'STATUS: OFFLINE';
    estat.className   = 'text-error text-[9px]';
  }
}

// ── HEALTH CHECK ─────────────────────────────────────────────────────────
async function loadHealth() {
  try {
    const r = await authFetch(`${API}/health`);
    const d = await r.json();
    const svc = d.services || {};
    setServiceDot('sqlite', svc.sqlite === 'ok');
    setServiceDot('qdrant', svc.qdrant === 'ok' || svc.qdrant === 'not_initialized');
    setServiceDot('ollama', svc.ollama === 'ok' || !!svc.llm_provider);
  } catch(e) {
    ['sqlite','qdrant','ollama'].forEach(s => setServiceDot(s, false));
  }
  // Cache stats
  try {
    const c = await authFetch(`${API}/cache/stats`).then(r => r.json());
    const el = document.getElementById('svc-cache');
    if (el) el.textContent = `Cache: ${c.entries ?? '?'}`;
  } catch(e) {}
}

function setServiceDot(name, ok) {
  const dot  = document.getElementById(`svc-${name}-dot`);
  const span = document.getElementById(`svc-${name}`);
  if (dot)  dot.className = `w-1.5 h-1.5 rounded-full ${ok ? 'bg-primary' : 'bg-error'}`;
  if (span) {
    const label = name === 'ollama' ? 'LLM' : name.charAt(0).toUpperCase() + name.slice(1);
    span.textContent = `${label} ${ok ? '●' : '○'}`;
    span.style.color = ok ? '#a4ffb9' : '#ff716c';
  }
}

// ── BRIDGE STATUS ─────────────────────────────────────────────────────────
async function loadBridgeStatus() {
  const dot    = document.getElementById('bridge-dot-web');
  const icon   = document.getElementById('bridge-icon-web');
  const txt    = document.getElementById('bridge-status-web');
  const since  = document.getElementById('bridge-since-web');
  const card   = document.getElementById('bridge-card-web');
  try {
    const d = await authFetch(`${API}/hardware/bridge/status`).then(r => r.json());
    const ok = d.connected === true;
    if (dot)  dot.className  = ok ? 'w-2 h-2 bg-[#8eff71] rounded-full animate-pulse inline-block' : 'w-2 h-2 bg-[#494847] rounded-full inline-block';
    if (icon) icon.className = `material-symbols-outlined text-sm ${ok ? 'text-[#8eff71]' : 'text-[#494847]'}`;
    if (txt)  { txt.textContent = ok ? 'CONNECTED' : 'DISCONNECTED'; txt.className = `text-[9px] font-mono ${ok ? 'text-[#8eff71]' : 'text-[#494847]'}`; }
    if (card) card.style.borderLeftColor = ok ? '#8eff71' : '#494847';
    if (since && d.connected_at && ok) {
      const mins = Math.round((Date.now() - new Date(d.connected_at).getTime()) / 60000);
      since.textContent = `${mins}m`;
    } else if (since) {
      since.textContent = d.pending_jobs > 0 ? `${d.pending_jobs} pending` : '';
    }
  } catch(e) {
    if (txt) { txt.textContent = 'UNREACHABLE'; txt.className = 'text-[9px] font-mono text-error'; }
  }
}

// ── WOKWI CLI STATUS ─────────────────────────────────────────────────────
async function loadWokwiStatus() {
  const card = document.getElementById('wokwi-status-card');
  if (!card) return;
  try {
    const d = await authFetch(`${API}/circuits/wokwi/status`).then(r => r.json());
    const cliOk    = d.cli_available;
    const tokenOk  = d.token_set;
    const ready    = d.ready;
    const dot = (ok) => `<span class="inline-block w-1.5 h-1.5 rounded-full mr-1 ${ok ? 'bg-primary' : 'bg-[#494847]'}"></span>`;
    card.innerHTML = `
      <div class="flex items-center gap-2">${dot(cliOk)}<span class="${cliOk ? 'text-primary' : 'text-[#494847]'}">wokwi-cli ${cliOk ? 'INSTALADO' : 'NO INSTALADO'}</span></div>
      <div class="flex items-center gap-2">${dot(tokenOk)}<span class="${tokenOk ? 'text-primary' : 'text-[#494847]'}">WOKWI_CLI_TOKEN ${tokenOk ? 'CONFIGURADO' : 'NO CONFIGURADO'}</span></div>
      ${!cliOk ? `<div class="text-[#494847] mt-1">Instalar: <span class="text-[#adaaaa]">${escHtml(d.install_hint)}</span></div>` : ''}
      ${!tokenOk ? `<div class="text-[#494847]">Token: <span class="text-[#adaaaa]">wokwi.com/dashboard/ci → API Token → WOKWI_CLI_TOKEN en .env</span></div>` : ''}
      ${ready ? '<div class="text-primary mt-1">Simulación headless disponible ✓</div>' : ''}
    `;
  } catch(e) {
    card.innerHTML = `<div class="text-error text-[9px]">Error: ${escHtml(String(e))}</div>`;
  }
}

// ── HARDWARE BRIDGE TEST ─────────────────────────────────────────────────
async function bridgeTest() {
  const el = document.getElementById('bridge-test-result');
  if (!el) return;
  el.innerHTML = '<div class="text-[#adaaaa]">Enviando job "detect" al bridge...</div>';
  try {
    const r = await authFetch(`${API}/hardware/bridge/test`, { method: 'POST' });
    const d = await r.json();
    if (!d.success) {
      el.innerHTML = `<div class="text-error">Error: ${escHtml(d.error || 'Sin respuesta')}</div>`;
      return;
    }
    const devices = d.devices || [];
    if (devices.length === 0) {
      el.innerHTML = '<div class="text-[#adaaaa]">Bridge respondió — sin dispositivos detectados.</div>';
      return;
    }
    el.innerHTML = `<div class="text-primary mb-1">Bridge OK — ${devices.length} dispositivo(s):</div>` +
      devices.map(dv => `<div class="text-[#adaaaa] pl-2">▸ ${escHtml(dv.device_name || dv.port || JSON.stringify(dv))}</div>`).join('');
  } catch(e) {
    el.innerHTML = `<div class="text-error">Error: ${escHtml(String(e))}</div>`;
  }
}
