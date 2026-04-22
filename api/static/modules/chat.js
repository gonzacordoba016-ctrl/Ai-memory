// ── HELPERS ───────────────────────────────────────────────────────────────
function _fmtElapsed(ms) {
  if (!ms || ms <= 0) return null;
  return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
}

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
    if (isStreaming) finishStreaming(null);
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
    if (data.type === 'thinking') {
      return; // heartbeat del servidor — ignorar silenciosamente
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
    } else if (data.type === 'session_title') {
      // Evento asíncrono: el título LLM llega después del 'done'
      const sid = data.session_id || _session_id;
      const el = document.querySelector(`#sess-${sid} .text-\\[10px\\]`);
      if (el) el.textContent = data.title;
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
    document.getElementById('chat-empty')?.remove();
    msgs.forEach(m => {
      if (m.role !== 'user' && m.role !== 'assistant') return;
      addMessage(m.role === 'user' ? 'user' : 'agent', m.content, m.agents_used || [], false, m.elapsed_ms);
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
  const sp = btn.querySelector('span');
  if (sp) sp.textContent = s + 's';
  clearInterval(_rateLimitTimer);
  _rateLimitTimer = setInterval(() => {
    s--;
    if (s <= 0) {
      clearInterval(_rateLimitTimer);
      if (!isStreaming) {
        btn.classList.remove('opacity-40', 'pointer-events-none');
        if (sp) { sp.textContent = 'send'; sp.className = 'material-symbols-outlined'; }
      }
    } else {
      if (sp) sp.textContent = s + 's';
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
  const counter = document.getElementById('prompt-counter');
  if (counter) counter.textContent = '';

  // Sin conexión → encolar
  if (!ws || ws.readyState !== 1) {
    _enqueueMessage(text);
    return;
  }

  addMessage('user', text, []);
  isStreaming = true;
  const _sb = document.getElementById('send-btn');
  if (_sb) _sb.classList.add('opacity-40', 'pointer-events-none');
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

function addMessage(role, content, agents = [], streaming = false, elapsed_ms = null) {
  const msgs = document.getElementById('messages');
  if (!msgs) return null;
  const ts = new Date().toLocaleTimeString('es', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const wasAtBottom = _isNearBottom(msgs);

  // Eliminar empty state al primer mensaje
  document.getElementById('chat-empty')?.remove();

  if (role === 'user') {
    const wrap = document.createElement('div');
    wrap.className = 'msg-user-wrap';
    const div = document.createElement('div');
    div.className = 'msg-user';
    const lines = content.split('\n');
    if (lines.length > 4) {
      div.innerHTML = escHtml(lines.slice(0, 4).join('\n')) +
        `<span style="color:var(--fg-4)"> … +${lines.length - 4} líneas</span>`;
    } else {
      div.textContent = content;
    }
    const tsEl = document.createElement('div');
    tsEl.className = 'msg-user-ts';
    tsEl.textContent = ts;
    wrap.appendChild(div);
    wrap.appendChild(tsEl);
    msgs.appendChild(wrap);
    if (wasAtBottom) msgs.scrollTop = msgs.scrollHeight;
    return null;
  } else {
    const agentBadges = (agents || []).map(a =>
      `<span class="chip" style="font-size:9px;height:18px;padding:0 5px">${a.toUpperCase()}</span>`
    ).join('');

    const article = document.createElement('article');
    article.className = 'msg-agent panel-cnr';
    if (!streaming && content) article.dataset.raw = content;
    article.innerHTML = `
      <div class="msg-head">
        <span class="dot${streaming ? ' dot-pulse' : ''}" style="color:var(--accent)"></span>
        <span class="label label-accent">AGENT</span>
        <span class="panel-sub">stratum-core · ${ts}${elapsed_ms && !streaming ? ' · ' + _fmtElapsed(elapsed_ms) : ''}</span>
        <div class="ml-auto flex items-center gap-1 agent-badges">${agentBadges}</div>
        <div class="flex gap-0 ml-1">
          <button class="btn btn-ghost tts-btn" onclick="_ttsSpeak(this)" title="TTS"
            style="height:22px;padding:0 6px;border-color:transparent;background:transparent">
            <span class="material-symbols-outlined" style="font-size:12px">volume_up</span>
          </button>
          <button class="btn btn-ghost" onclick="_exportMD(this)" title="Export MD"
            style="height:22px;padding:0 6px;border-color:transparent;background:transparent">
            <span class="material-symbols-outlined" style="font-size:12px">download</span>
          </button>
        </div>
      </div>
      ${streaming ? '<div class="pulse-bar"></div>' : ''}
      <div class="msg-body agent-content${streaming ? ' blinking-cursor' : ''}">${streaming ? '' : renderMarkdown(content)}</div>
    `;
    if (!streaming) {
      _addCopyButtons(article);
      _postRender(article.querySelector('.agent-content'));
    }
    msgs.appendChild(article);
    if (wasAtBottom) msgs.scrollTop = msgs.scrollHeight;
    return article.querySelector('.agent-content');
  }
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
    const article = currentAgentEl.closest('article.msg-agent') || currentAgentEl.closest('.msg-agent');

    if (!rawText.trim()) {
      if (article) article.remove();
    } else {
      currentAgentEl.innerHTML = renderMarkdown(rawText);
      if (article) {
        article.dataset.raw = rawText;
        article.querySelector('.pulse-bar')?.remove();
        const dot = article.querySelector('.dot');
        if (dot) dot.classList.remove('dot-pulse');
        // Actualizar timestamp al momento real de respuesta
        const tsEl = article.querySelector('.panel-sub');
        if (tsEl) {
          const now = new Date().toLocaleTimeString('es', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
          const elapsed = _fmtElapsed(data?.elapsed_ms);
          tsEl.textContent = `stratum-core · ${now}${elapsed ? ' · ' + elapsed : ''}`;
        }
        _addCopyButtons(article);
        if (data?.agents_used?.length) {
          const badgeContainer = article.querySelector('.agent-badges');
          if (badgeContainer) {
            badgeContainer.innerHTML = data.agents_used.map(a =>
              `<span class="chip" style="font-size:9px;height:18px;padding:0 5px">${a.toUpperCase()}</span>`
            ).join('');
          }
        }
      }
      _postRender(currentAgentEl);
      // Circuit design card — inject after message body
      if (data?.circuit_design_id && article) {
        _appendCircuitCard(article, data.circuit_design_id, data.circuit_name || 'Circuito');
      }
    }
  }
  _streamBuffer  = '';
  isStreaming    = false;
  currentAgentEl = null;
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) {
    sendBtn.classList.remove('opacity-40', 'pointer-events-none');
    const sp = sendBtn.querySelector('span');
    if (sp) { sp.textContent = 'send'; sp.className = 'material-symbols-outlined'; }
  }
  updateStatusText('READY_FOR_INPUT', true);
  addLog('Response complete', 'info');
  _scrollToBottom(true);
}

function _appendCircuitCard(article, id, name) {
  const card = document.createElement('div');
  card.className = 'circuit-chat-card';
  card.style.cssText = [
    'margin:10px 0 4px 0', 'border:1px solid #00d4ff44', 'border-radius:6px',
    'background:#0d2137', 'overflow:hidden'
  ].join(';');

  const hdr = document.createElement('div');
  hdr.style.cssText = 'padding:6px 10px;background:#00d4ff18;display:flex;align-items:center;gap:8px;border-bottom:1px solid #00d4ff33';
  hdr.innerHTML = `
    <span style="color:#00d4ff;font-size:11px;font-family:monospace">⚡ CIRCUITO #${id}</span>
    <span style="color:#8b949e;font-size:10px;flex:1">${escHtml(name)}</span>
    <a href="/api/circuits/${id}/schematic.kicad_sch" target="_blank"
       style="color:#58a6ff;font-size:10px;text-decoration:none;padding:2px 6px;border:1px solid #58a6ff44;border-radius:3px">KiCad</a>
    <a href="/api/circuits/${id}/bom.csv" target="_blank"
       style="color:#3fb950;font-size:10px;text-decoration:none;padding:2px 6px;border:1px solid #3fb95044;border-radius:3px">BOM CSV</a>
    <a href="/api/circuits/${id}/gerber" target="_blank"
       style="color:#d29922;font-size:10px;text-decoration:none;padding:2px 6px;border:1px solid #d2992244;border-radius:3px">Gerber</a>
    <a href="/api/circuits/viewer?id=${id}" target="_blank"
       style="color:#bc8cff;font-size:10px;text-decoration:none;padding:2px 6px;border:1px solid #bc8cff44;border-radius:3px">3D Viewer</a>
  `;

  const preview = document.createElement('div');
  preview.style.cssText = 'padding:6px;text-align:center;cursor:pointer';
  preview.title = 'Click para ver esquemático completo';
  preview.onclick = () => window.open(`/api/circuits/viewer?id=${id}`, '_blank');

  const img = document.createElement('img');
  img.src = `/api/circuits/${id}/schematic.svg`;
  img.alt = 'Esquemático';
  img.style.cssText = 'max-width:100%;max-height:220px;object-fit:contain;border-radius:3px';
  img.onerror = () => { preview.style.display = 'none'; };
  preview.appendChild(img);

  card.appendChild(hdr);
  card.appendChild(preview);
  article.appendChild(card);
}

function updateStatusText(text, ok) {
  const dot  = document.getElementById('status-dot');
  const span = document.getElementById('status-text');
  if (dot)  dot.className  = `w-1 h-1 ${ok ? 'bg-primary' : 'bg-[#494847]'}`;
  if (span) span.textContent = text;
}
