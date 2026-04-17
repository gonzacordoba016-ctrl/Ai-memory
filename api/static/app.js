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

// ── NAVIGATION ──────────────────────────────────────────────────────────
function switchView(name) {
  _activeView = name;

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
}
_promptEl.addEventListener('input', _autoResizePrompt);
_promptEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
document.getElementById('search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

renderIdleOscilloscope();
switchView('chat');   // start in chat view
loadSessions();       // load session list
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

// Limpiar cualquier queue residual de versiones anteriores que usaban localStorage
localStorage.removeItem('stratum_web_offline_queue');

// Cargar al iniciar
webLoadDecisions();
webLoadStockSummary();
