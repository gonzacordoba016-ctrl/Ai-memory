// ── GLOBAL STATE ──────────────────────────────────────────────────────────
const _isSecure    = location.protocol === 'https:';
const _isLocal     = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
const _apiBase     = _isLocal ? `http://${location.hostname}:8000` : `${location.protocol}//${location.host}`;
const _wsProto     = _isSecure ? 'wss' : 'ws';
const _wsHost      = _isLocal ? `${location.hostname}:8000` : location.host;
const API          = `${_apiBase}/api`;
const WS_URL       = `${_wsProto}://${_wsHost}/ws/chat`;
const WS_SIGNAL    = `${_wsProto}://${_wsHost}/ws/signal`;
const WS_PROACTIVE = `${_wsProto}://${_wsHost}/ws/proactive`;

let ws, wsSignal, wsProactive;
let isStreaming = false;
let currentAgentEl = null;
let signalBuffer = [];
let _session_id   = localStorage.getItem('stratum_session_id') || null;
let _token        = localStorage.getItem('stratum_jwt') || null;
let _wsRetryDelay = 2000;
let _offlineQueue = [];  // solo en memoria — no persiste entre reloads
let _sessions     = [];   // list of session objects from API
let _activeView   = 'chat';

// ── VOICE INPUT ───────────────────────────────────────────────────────────
let _voiceRec = null, _voiceOn = false;
function _initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert('Tu navegador no soporta reconocimiento de voz.'); return false; }
  _voiceRec = new SR();
  _voiceRec.lang = 'es-AR';
  _voiceRec.continuous = false;
  _voiceRec.interimResults = false;
  _voiceRec.onstart = () => {
    _voiceOn = true;
    const b = document.getElementById('voice-btn');
    if (b) b.classList.add('voice-active');
  };
  _voiceRec.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    const inp = document.getElementById('prompt');
    if (inp) { inp.value = transcript; inp.focus(); }
  };
  _voiceRec.onend = () => {
    _voiceOn = false;
    const b = document.getElementById('voice-btn');
    if (b) b.classList.remove('voice-active');
  };
  _voiceRec.onerror = (e) => {
    _voiceOn = false;
    const b = document.getElementById('voice-btn');
    if (b) b.classList.remove('voice-active');
    if (e.error !== 'no-speech') console.warn('Voice error:', e.error);
  };
  return true;
}
function toggleVoice() {
  if (!_voiceRec && !_initVoice()) return;
  _voiceOn ? _voiceRec.stop() : _voiceRec.start();
}

// ── MOBILE SIDEBAR ──────────────────────────────────────────────────────
function toggleMobileSidebar() {
  const sidebar = document.getElementById('left-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  const isOpen = sidebar.classList.contains('mobile-open');
  if (isOpen) { closeMobileSidebar(); } else {
    sidebar.classList.add('mobile-open');
    backdrop.classList.add('visible');
  }
}
function closeMobileSidebar() {
  document.getElementById('left-sidebar')?.classList.remove('mobile-open');
  document.getElementById('sidebar-backdrop')?.classList.remove('visible');
}

// ── NAVIGATION ──────────────────────────────────────────────────────────
function switchView(name) {
  _activeView = name;
  closeMobileSidebar();

  // Hide all views
  document.querySelectorAll('[id^="view-"]').forEach(el => {
    el.classList.add('hidden');
    el.classList.remove('flex');
  });

  // Show selected view
  const view = document.getElementById(`view-${name}`);
  if (view) { view.classList.remove('hidden'); view.classList.add('flex'); }

  // Update module nav active state
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.remove('active');
    el.classList.add('text-[#adaaaa]');
  });
  const navEl = document.getElementById(`nav-${name}`);
  if (navEl) { navEl.classList.add('active'); navEl.classList.remove('text-[#adaaaa]'); }

  // On first activation, reparent panel into its view slot
  const slot = document.querySelector(`[data-panel="${name}"]`);
  if (slot && slot.children.length === 0) {
    const panel = document.getElementById(`panel-${name}`);
    if (panel) {
      slot.appendChild(panel);
      panel.classList.remove('tab-content', 'hidden');
      panel.style.display = '';
    }
  }

  // Trigger data loads
  if (name === 'devices')  loadHardware();
  if (name === 'system')   { loadMetrics(); webLoadStockSummary(); webSearchStock(''); loadWokwiStatus(); }
  if (name === 'intel')    { loadIntelligence(); webLoadDecisions(); }
  if (name === 'metrics')  loadMetricsPanel();
  if (name === 'calc')     calcSwitchForm(document.getElementById('calc-selector')?.value || 'resistor_for_led');
  if (name === 'chat')     document.getElementById('prompt')?.focus();
  if (name === 'kb')       kbLoadDocuments();
}

// Legacy alias used in some places
function switchNav(tab) { switchView(tab); }

// ── SIDEBAR COLLAPSE ──────────────────────────────────────────────────────

let _chatsOpen   = true;
let _modulesOpen = true;

function toggleChatsSection() {
  _chatsOpen = !_chatsOpen;
  const wrap    = document.getElementById('sessions-list-wrap');
  const chevron = document.getElementById('chats-chevron');
  const section = document.getElementById('chats-section');

  if (_chatsOpen) {
    wrap.classList.remove('hidden');
    section.classList.add('flex-1');
    section.classList.remove('flex-shrink-0');
    if (chevron) chevron.style.transform = 'rotate(0deg)';
  } else {
    wrap.classList.add('hidden');
    section.classList.remove('flex-1');
    section.classList.add('flex-shrink-0');
    if (chevron) chevron.style.transform = 'rotate(-90deg)';
  }
}

function toggleModulesSection() {
  _modulesOpen = !_modulesOpen;
  const nav     = document.getElementById('modules-nav');
  const chevron = document.getElementById('modules-chevron');

  if (_modulesOpen) {
    nav.classList.remove('hidden');
    if (chevron) chevron.style.transform = 'rotate(0deg)';
  } else {
    nav.classList.add('hidden');
    if (chevron) chevron.style.transform = 'rotate(-180deg)';
  }
}

// ── INIT ──────────────────────────────────────────────────────────────────
document.getElementById('session-time').textContent =
  'SESSION_INIT :: ' + new Date().toISOString().replace('T', '_').slice(0, 19);

const _promptEl = document.getElementById('prompt');
function _autoResizePrompt() {
  _promptEl.style.height = 'auto';
  _promptEl.style.height = Math.min(_promptEl.scrollHeight, 220) + 'px';
  const counter = document.getElementById('prompt-counter');
  if (counter) {
    const len = _promptEl.value.length;
    counter.textContent = len > 50 ? `${len} chars` : '';
    counter.className = `text-[8px] font-mono ${len > 3000 ? 'text-error' : 'text-[#494847]'}`;
  }
}
_promptEl.addEventListener('input', _autoResizePrompt);
_promptEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    if (_snippetsVisible) { e.preventDefault(); _selectSnippet(_snippetIdx); return; }
    e.preventDefault(); sendMessage();
  }
  if (e.key === 'Escape') {
    if (_snippetsVisible) { _hideSnippets(); return; }
    _promptEl.value = ''; _autoResizePrompt();
  }
  if (e.key === 'ArrowUp'   && _snippetsVisible) { e.preventDefault(); _snippetIdx = Math.max(0, _snippetIdx-1); _renderSnippets(); }
  if (e.key === 'ArrowDown' && _snippetsVisible) { e.preventDefault(); _snippetIdx = Math.min(_filteredSnippets.length-1, _snippetIdx+1); _renderSnippets(); }
});

// ── SNIPPETS ──────────────────────────────────────────────────────────────
const _SNIPPETS = [
  { cmd: '/fw',      label: 'Firmware para dispositivo',   full: 'Escribí firmware en C++ para ' },
  { cmd: '/debug',   label: 'Debuguear código',            full: 'Debugueá este código y encontrá los bugs:\n\n' },
  { cmd: '/schema',  label: 'Diseñar esquemático',         full: 'Diseñá el esquemático para ' },
  { cmd: '/bom',     label: 'Lista de materiales (BOM)',   full: 'Generá la BOM completa para ' },
  { cmd: '/plc',     label: 'Lógica PLC Ladder',           full: 'Escribí lógica Ladder IEC 61131-3 para ' },
  { cmd: '/i2c',     label: 'Comunicación I2C',            full: 'Implementá comunicación I2C entre MCU y ' },
  { cmd: '/pid',     label: 'Control PID',                 full: 'Diseñá un controlador PID para ' },
  { cmd: '/power',   label: 'Fuente de alimentación',      full: 'Diseñá la fuente de alimentación para ' },
  { cmd: '/calc',    label: 'Calcular parámetros',         full: 'Calculá ' },
  { cmd: '/explain', label: 'Explicar componente',         full: 'Explicá el funcionamiento y uso de ' },
  { cmd: '/pinout',  label: 'Pinout de microcontrolador',  full: 'Describí el pinout y funciones de cada pin de ' },
  { cmd: '/spi',     label: 'Comunicación SPI',            full: 'Implementá comunicación SPI con ' },
  { cmd: '/uart',    label: 'Comunicación UART',           full: 'Configurá UART en ' },
  { cmd: '/isr',     label: 'Interrupción (ISR)',          full: 'Escribí una ISR para manejar ' },
  { cmd: '/pwm',     label: 'Control PWM',                 full: 'Implementá control PWM para ' },
];

let _snippetsVisible  = false;
let _filteredSnippets = [];
let _snippetIdx       = 0;

_promptEl.addEventListener('input', () => {
  const val = _promptEl.value;
  if (val.startsWith('/') && val.length >= 1) {
    const q = val.toLowerCase();
    _filteredSnippets = _SNIPPETS.filter(s => s.cmd.startsWith(q) || (q === '/' ));
    if (val === '/') _filteredSnippets = _SNIPPETS;
    if (_filteredSnippets.length) { _snippetIdx = 0; _showSnippets(); return; }
  }
  _hideSnippets();
});

function _showSnippets() {
  _snippetsVisible = true;
  _renderSnippets();
  document.getElementById('snippet-menu')?.classList.remove('hidden');
}

function _hideSnippets() {
  _snippetsVisible = false;
  document.getElementById('snippet-menu')?.classList.add('hidden');
}

function _renderSnippets() {
  const menu = document.getElementById('snippet-menu');
  if (!menu) return;
  menu.innerHTML = _filteredSnippets.map((s, i) => `
    <div class="snippet-item px-3 py-1.5 cursor-pointer font-mono text-[9px] flex items-center gap-3
      ${i === _snippetIdx ? 'bg-[#131313] text-primary' : 'text-[#adaaaa] hover:bg-[#131313] hover:text-primary'}"
      onclick="_selectSnippet(${i})">
      <span class="text-[#00cbfe] w-16 flex-shrink-0">${escHtml(s.cmd)}</span>
      <span>${escHtml(s.label)}</span>
    </div>`).join('');
}

function _selectSnippet(idx) {
  const s = _filteredSnippets[idx];
  if (!s) return;
  _promptEl.value = s.full;
  _autoResizePrompt();
  _hideSnippets();
  _promptEl.focus();
  _promptEl.setSelectionRange(_promptEl.value.length, _promptEl.value.length);
}

// ── FILE UPLOAD ───────────────────────────────────────────────────────────
function triggerFileUpload() {
  document.getElementById('file-upload-input')?.click();
}

document.getElementById('file-upload-input')?.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const MAX = 50_000;
  try {
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = () => {
        const prompt = _promptEl;
        prompt.value = (prompt.value ? prompt.value + '\n\n' : '') + `[Imagen adjunta: ${file.name}]`;
        _autoResizePrompt();
        // Store base64 for vision if needed
        _pendingImageB64 = reader.result.split(',')[1];
        addLog(`Imagen cargada: ${file.name}`, 'info');
      };
      reader.readAsDataURL(file);
    } else {
      const text = await file.text();
      const snippet = text.length > MAX ? text.slice(0, MAX) + '\n[... truncado]' : text;
      _promptEl.value = (_promptEl.value ? _promptEl.value + '\n\n' : '') +
        `\`\`\`\n// ${file.name}\n${snippet}\n\`\`\``;
      _autoResizePrompt();
      addLog(`Archivo cargado: ${file.name} (${text.length} chars)`, 'info');
    }
  } catch(err) {
    addLog(`Error leyendo archivo: ${err.message}`, 'error');
  }
  e.target.value = '';
});

let _pendingImageB64 = null;

// ── CTRL+K SEARCH ─────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    toggleSearchModal();
  }
  if (e.key === 'Escape') {
    const modal = document.getElementById('search-modal');
    if (modal && !modal.classList.contains('hidden')) closeSearchModal();
  }
});

function toggleSearchModal() {
  const modal = document.getElementById('search-modal');
  if (!modal) return;
  if (modal.classList.contains('hidden')) {
    modal.classList.remove('hidden');
    document.getElementById('search-modal-input')?.focus();
  } else {
    closeSearchModal();
  }
}

function closeSearchModal() {
  document.getElementById('search-modal')?.classList.add('hidden');
  const res = document.getElementById('search-modal-results');
  if (res) res.innerHTML = '';
  const inp = document.getElementById('search-modal-input');
  if (inp) inp.value = '';
}

let _searchDebounce = null;
document.getElementById('search-modal-input')?.addEventListener('input', (e) => {
  clearTimeout(_searchDebounce);
  _searchDebounce = setTimeout(() => _runModalSearch(e.target.value), 300);
});

async function _runModalSearch(q) {
  if (!q || q.length < 2) { document.getElementById('search-modal-results').innerHTML = ''; return; }
  try {
    const r = await authFetch(`${API}/search?q=${encodeURIComponent(q)}&top_k=8`);
    const d = await r.json();
    const results = d.results || [];
    const el = document.getElementById('search-modal-results');
    if (!results.length) {
      el.innerHTML = '<div class="text-[9px] text-[#494847] px-4 py-3">Sin resultados</div>';
      return;
    }
    el.innerHTML = results.map(r => `
      <div class="px-4 py-2.5 hover:bg-[#131313] cursor-pointer border-b border-[#494847]/20 transition-colors"
        onclick="_useSearchResult('${escHtml(r.text || r.content || '')}')">
        <div class="text-[9px] text-[#adaaaa] leading-relaxed line-clamp-2">${escHtml((r.text || r.content || '').slice(0,120))}</div>
        <div class="text-[7px] text-[#494847] mt-0.5">score: ${(r.score || 0).toFixed(2)}</div>
      </div>`).join('');
  } catch(e) {}
}

function _useSearchResult(text) {
  closeSearchModal();
  _promptEl.value = text.slice(0, 500);
  _autoResizePrompt();
  _promptEl.focus();
  switchView('chat');
}
document.getElementById('search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

renderIdleOscilloscope();
switchView('chat');   // start in chat view
loadSessions();       // load session list
loadProjects();       // load active project
connectWS();
connectSignalWS();
connectProactiveWS();
loadHealth();
loadAuthStatus();
loadBridgeStatus();
setInterval(loadStats,        30000);
setInterval(loadJobs,         30000);
setInterval(loadHealth,       30000);
setInterval(loadBridgeStatus, 60000);
setInterval(loadSessions,     30000);
setInterval(loadProjects,     60000);

// Limpiar cualquier queue residual de versiones anteriores que usaban localStorage
localStorage.removeItem('stratum_web_offline_queue');

// Cargar al iniciar
webLoadDecisions();
webLoadStockSummary();
