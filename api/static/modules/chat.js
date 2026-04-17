// ── SCROLL INTELIGENTE ────────────────────────────────────────────────────
function _isNearBottom(el, threshold = 80) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}
function _scrollToBottom(force = false) {
  const msgs = document.getElementById('messages');
  if (msgs && (force || _isNearBottom(msgs))) msgs.scrollTop = msgs.scrollHeight;
}

// ── WEBSOCKET CHAT ───────────────────────────────────────────────────────
function connectWS() {
  const wsUrl = _wsTokenParam(WS_URL + (_session_id ? `?session=${encodeURIComponent(_session_id)}` : ''));
  ws = new WebSocket(wsUrl);
  ws.onopen  = () => {
    _wsRetryDelay = 2000;
    setConnected(true);
    addLog('WebSocket conectado', 'info');
    loadStats();
    loadFacts();
    // No drainear aquí — esperamos el session message para saber si el server reinició
  };
  ws.onclose = () => {
    setConnected(false);
    const delay = _wsRetryDelay;
    _wsRetryDelay = Math.min(_wsRetryDelay * 2, 8000); // máximo 8s, no 30s
    addLog(`WS desconectado — reintentando en ${delay/1000}s...`, 'warn');
    setTimeout(connectWS, delay);
  };
  ws.onerror = () => addLog('Error de WebSocket', 'error');
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'session') {
      _session_id = data.session_id;
      localStorage.setItem('stratum_session_id', _session_id);
      // Detectar reinicio del server por cambio de timestamp
      const prevServerStart = localStorage.getItem('stratum_server_start');
      const currServerStart = String(data.server_start || '');
      const serverRestarted = currServerStart && prevServerStart !== currServerStart;
      if (serverRestarted) {
        _offlineQueue = [];
        _saveQueue();
        document.querySelectorAll('[data-queued="true"]').forEach(el => el.remove());
        _updateQueueBadge();
        const area = document.getElementById('messages');
        if (area) area.innerHTML = '';
        addLog('Server reiniciado — chat limpiado', 'warn');
        localStorage.setItem('stratum_server_start', currServerStart);
      } else {
        if (_offlineQueue.length > 0) drainOfflineQueue();
        if (data.resumed) loadSessionHistory(_session_id);
      }
      loadSessions();
      return;
    }
    if (data.type === 'token') {
      appendToken(data.content);
    } else if (data.type === 'done') {
      finishStreaming(data);
      if (data.facts) updateFacts(data.facts);
      if (data.session_title) {
        const el = document.querySelector(`#sess-${_session_id} .text-\\[10px\\]`);
        if (el) el.textContent = data.session_title;
      }
      loadStats();
      loadSessions();
    } else if (data.type === 'error') {
      finishStreaming(null);
      // Detectar rate limit y mostrar countdown en lugar de burbuja de error
      const rlMatch = data.content && data.content.match(/Esperá (\d+)s/);
      if (rlMatch) {
        _showRateLimit(parseInt(rlMatch[1]));
      } else {
        addMessage('agent', `Error: ${data.content}`, []);
      }
    }
  };
}

async function loadSessionHistory(sid) {
  try {
    const d = await authFetch(`${API}/history?session_id=${encodeURIComponent(sid)}&limit=20`).then(r => r.json());
    const msgs = d.messages || [];
    if (!msgs.length) return;
    // Limpiar DOM antes de cargar para evitar duplicados
    const area = document.getElementById('messages');
    if (area) area.innerHTML = '';
    msgs.forEach(m => {
      if (m.role !== 'user' && m.role !== 'assistant') return;
      addMessage(m.role === 'user' ? 'user' : 'agent', m.content, m.agents_used || []);
    });
    addLog(`Historial reanudado — ${msgs.length} mensajes`, 'info');
  } catch(e) {}
}

// ── RATE LIMIT COUNTDOWN ─────────────────────────────────────────────────
let _rateLimitTimer = null;
function _showRateLimit(seconds) {
  const btn = document.getElementById('send-btn');
  if (!btn) return;
  let s = seconds;
  btn.classList.add('opacity-40', 'pointer-events-none');
  btn.querySelector('span').textContent = s + 's';
  clearInterval(_rateLimitTimer);
  _rateLimitTimer = setInterval(() => {
    s--;
    if (s <= 0) {
      clearInterval(_rateLimitTimer);
      if (!isStreaming) {
        btn.classList.remove('opacity-40', 'pointer-events-none');
        btn.querySelector('span').textContent = 'send';
        btn.querySelector('span').className = 'material-symbols-outlined';
      }
    } else {
      btn.querySelector('span').textContent = s + 's';
    }
  }, 1000);
}

// ── CHAT ─────────────────────────────────────────────────────────────────
function sendMessage() {
  const input = document.getElementById('prompt');
  const text  = input.value.trim();
  if (!text || isStreaming) return;
  input.value = '';
  input.style.height = 'auto';
  // reset char counter
  const counter = document.getElementById('prompt-counter');
  if (counter) counter.textContent = '';

  // Sin conexión → encolar
  if (!ws || ws.readyState !== 1) {
    _enqueueMessage(text);
    return;
  }

  addMessage('user', text, []);
  isStreaming   = true;
  document.getElementById('send-btn').classList.add('opacity-40', 'pointer-events-none');
  currentAgentEl = addMessage('agent', '', [], true);
  addLog(`CMD: ${text.slice(0, 60)}`, 'cmd');
  ws.send(JSON.stringify({ message: text }));
}

function _addCopyButtons(container) {
  container.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.copy-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'copy-btn absolute top-2 right-2 text-[8px] font-mono text-[#494847] hover:text-primary border border-[#494847]/40 hover:border-primary/60 px-1.5 py-0.5 transition-colors bg-[#0e0e0e]';
    btn.textContent = 'COPY';
    btn.onclick = () => {
      const code = pre.querySelector('code')?.innerText || pre.innerText;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = 'COPIED';
        btn.classList.add('text-primary');
        setTimeout(() => { btn.textContent = 'COPY'; btn.classList.remove('text-primary'); }, 1500);
      });
    };
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
}

// ── TTS ───────────────────────────────────────────────────────────────────
let _ttsActive = false;
function _ttsSpeak(btn) {
  if (!window.speechSynthesis) return;
  if (_ttsActive) {
    window.speechSynthesis.cancel();
    _ttsActive = false;
    document.querySelectorAll('.tts-btn').forEach(b => b.classList.remove('text-primary'));
    return;
  }
  const msg = btn.closest('[data-raw]');
  const text = msg ? msg.dataset.raw : btn.closest('.bg-\\[\\#131313\\]')?.querySelector('.agent-content')?.innerText || '';
  if (!text) return;
  const utt = new SpeechSynthesisUtterance(text.replace(/[#*`_~]/g, ''));
  utt.lang = 'es-AR';
  utt.rate = 1.1;
  utt.onend = () => { _ttsActive = false; btn.classList.remove('text-primary'); };
  window.speechSynthesis.speak(utt);
  _ttsActive = true;
  btn.classList.add('text-primary');
}

function _exportMD(btn) {
  const msg  = btn.closest('[data-raw]');
  const text = msg ? msg.dataset.raw : '';
  if (!text) return;
  const blob = new Blob([text], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `stratum_${new Date().toISOString().slice(0,10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function addMessage(role, content, agents = [], streaming = false) {
  const msgs = document.getElementById('messages');
  const ts   = new Date().toLocaleTimeString('es', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const div  = document.createElement('div');
  const wasAtBottom = _isNearBottom(msgs);

  if (role === 'user') {
    const lines = content.split('\n');
    const preview = lines.length > 4
      ? escHtml(lines.slice(0, 4).join('\n')) + `<span class="text-[#494847]">… +${lines.length-4} líneas</span>`
      : escHtml(content);
    div.className = 'flex flex-col items-end';
    div.innerHTML = `
      <div class="bg-[#201f1f] border-r-2 border-secondary p-4 max-w-xl font-mono text-sm tracking-tight text-secondary">
        <div class="text-[9px] mb-2 opacity-50">OPERATOR_OVERRIDE // ${ts}</div>
        <div class="whitespace-pre-wrap">${preview}</div>
      </div>`;
  } else {
    const badges = (agents || []).map(a => {
      const colors = { memory:'text-primary', hardware:'text-secondary', research:'text-[#adaaaa]', code:'text-[#8eff71]', proactive:'text-[#ffaa00]', direct:'text-[#adaaaa]' };
      const c = colors[a] || 'text-[#adaaaa]';
      return `<span class="px-1 py-0.5 bg-[#131313] ${c} text-[8px] font-bold uppercase border border-current/20">AGNT_${a.toUpperCase()}</span>`;
    }).join('');

    div.className = 'flex flex-col items-start group';
    div.innerHTML = `
      <div class="bg-[#131313] border-l-2 border-primary p-4 max-w-2xl font-mono text-sm tracking-tight">
        <div class="flex items-center gap-2 mb-2 flex-wrap">
          <span class="text-[9px] text-primary opacity-50">STRATUM_ENGINE // AI_CORE // ${ts}</span>
          <div class="flex gap-1 agent-badges">${badges}</div>
        </div>
        <div class="agent-content prose-stratum leading-relaxed${streaming ? ' blinking-cursor' : ''}">${streaming ? '' : renderMarkdown(content)}</div>
        <div class="flex items-center gap-3 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="tts-btn flex items-center gap-1 text-[8px] text-[#494847] hover:text-primary font-mono transition-colors" onclick="_ttsSpeak(this)" title="Escuchar">
            <span class="material-symbols-outlined text-[10px]">volume_up</span>TTS
          </button>
          <button class="flex items-center gap-1 text-[8px] text-[#494847] hover:text-primary font-mono transition-colors" onclick="_exportMD(this)" title="Exportar markdown">
            <span class="material-symbols-outlined text-[10px]">download</span>MD
          </button>
        </div>
      </div>`;
    if (!streaming) _addCopyButtons(div);
  }

  msgs.appendChild(div);
  if (wasAtBottom) msgs.scrollTop = msgs.scrollHeight;
  return role === 'agent' ? div.querySelector('.agent-content') : null;
}

// Streaming acumulado para render markdown progresivo
let _streamBuffer = '';
let _streamRenderTimer = null;

function appendToken(token) {
  if (!currentAgentEl) return;
  _streamBuffer += token;
  currentAgentEl.classList.add('blinking-cursor');

  // Render markdown progresivo cada 120ms para no saturar el DOM
  if (!_streamRenderTimer) {
    _streamRenderTimer = setTimeout(() => {
      _streamRenderTimer = null;
      if (!currentAgentEl) return;
      currentAgentEl.innerHTML = renderMarkdown(_streamBuffer) + '<span class="blinking-cursor-inline">▋</span>';
      _scrollToBottom();
    }, 120);
  }
}

function finishStreaming(data) {
  if (_streamRenderTimer) { clearTimeout(_streamRenderTimer); _streamRenderTimer = null; }
  if (currentAgentEl) {
    currentAgentEl.classList.remove('blinking-cursor');
    const rawText = _streamBuffer || currentAgentEl.textContent || '';

    if (!rawText.trim()) {
      const bubble = currentAgentEl.closest('.flex.flex-col.items-start');
      if (bubble) bubble.remove();
    } else {
      currentAgentEl.innerHTML = renderMarkdown(rawText);
      const outerDiv = currentAgentEl.closest('.flex.flex-col.items-start');
      if (outerDiv) outerDiv.dataset.raw = rawText;
      _addCopyButtons(outerDiv || currentAgentEl);

      if (data?.agents_used?.length) {
        const container = currentAgentEl.closest('.bg-\\[\\#131313\\]')?.querySelector('.agent-badges');
        if (container) {
          const colors = { memory:'text-primary', hardware:'text-secondary', research:'text-[#adaaaa]', code:'text-[#8eff71]', proactive:'text-[#ffaa00]', direct:'text-[#adaaaa]' };
          container.innerHTML = data.agents_used.map(a => {
            const c = colors[a] || 'text-[#adaaaa]';
            return `<span class="px-1 py-0.5 bg-[#131313] ${c} text-[8px] font-bold uppercase border border-current/20">AGNT_${a.toUpperCase()}</span>`;
          }).join('');
        }
      }
    }
  }
  _streamBuffer  = '';
  isStreaming    = false;
  currentAgentEl = null;
  document.getElementById('send-btn').classList.remove('opacity-40', 'pointer-events-none');
  document.getElementById('send-btn').querySelector('span').textContent = 'send';
  updateStatusText('READY_FOR_INPUT', true);
  addLog('Response complete', 'info');
  _scrollToBottom(true);
}

function updateStatusText(text, ok) {
  const dot  = document.getElementById('status-dot');
  const span = document.getElementById('status-text');
  if (dot)  dot.className  = `w-1 h-1 ${ok ? 'bg-primary' : 'bg-[#494847]'}`;
  if (span) span.textContent = text;
}
