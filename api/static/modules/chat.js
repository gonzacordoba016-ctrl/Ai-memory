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
      loadStats();
      loadSessions();
    } else if (data.type === 'error') {
      finishStreaming(null);
      addMessage('agent', `Error: ${data.content}`, []);
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

// ── CHAT ─────────────────────────────────────────────────────────────────
function sendMessage() {
  const input = document.getElementById('prompt');
  const text  = input.value.trim();
  if (!text || isStreaming) return;
  input.value = '';

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

function addMessage(role, content, agents = [], streaming = false) {
  const msgs = document.getElementById('messages');
  const ts   = new Date().toLocaleTimeString('es', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const div  = document.createElement('div');

  if (role === 'user') {
    div.className = 'flex flex-col items-end';
    div.innerHTML = `
      <div class="bg-[#201f1f] border-r-2 border-secondary p-4 max-w-xl font-mono text-sm tracking-tight text-secondary">
        <div class="text-[9px] mb-2 opacity-50">OPERATOR_OVERRIDE // ${ts}</div>
        ${escHtml(content)}
      </div>`;
  } else {
    const badges = (agents || []).map(a => {
      const colors = { memory:'text-primary', hardware:'text-secondary', research:'text-[#adaaaa]', code:'text-[#8eff71]', proactive:'text-[#ffaa00]', direct:'text-[#adaaaa]' };
      const c = colors[a] || 'text-[#adaaaa]';
      return `<span class="px-1 py-0.5 bg-[#131313] ${c} text-[8px] font-bold uppercase border border-current/20">AGNT_${a.toUpperCase()}</span>`;
    }).join('');

    div.className = 'flex flex-col items-start';
    div.innerHTML = `
      <div class="bg-[#131313] border-l-2 border-primary p-4 max-w-2xl font-mono text-sm tracking-tight">
        <div class="flex items-center gap-2 mb-2 flex-wrap">
          <span class="text-[9px] text-primary opacity-50">STRATUM_ENGINE // AI_CORE // ${ts}</span>
          <div class="flex gap-1 agent-badges">${badges}</div>
        </div>
        <div class="agent-content prose-stratum leading-relaxed${streaming ? ' blinking-cursor' : ''}">${streaming ? escHtml(content) : renderMarkdown(content)}</div>
      </div>`;
  }

  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return role === 'agent' ? div.querySelector('.agent-content') : null;
}

function appendToken(token) {
  if (!currentAgentEl) return;
  currentAgentEl.classList.remove('blinking-cursor');
  currentAgentEl.textContent += token;
  currentAgentEl.classList.add('blinking-cursor');
  document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
}

function finishStreaming(data) {
  if (currentAgentEl) {
    currentAgentEl.classList.remove('blinking-cursor');

    const rawText = currentAgentEl.textContent || '';

    if (!rawText.trim()) {
      // Burbuja vacía (timeout sin tokens) — eliminarla del DOM
      const bubble = currentAgentEl.closest('.flex.flex-col.items-start');
      if (bubble) bubble.remove();
    } else {
      // Re-renderizar el texto acumulado como markdown
      currentAgentEl.innerHTML = renderMarkdown(rawText);

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
  isStreaming    = false;
  currentAgentEl = null;
  document.getElementById('send-btn').classList.remove('opacity-40', 'pointer-events-none');
  updateStatusText('READY_FOR_INPUT', true);
  addLog('Response complete', 'info');
}

function updateStatusText(text, ok) {
  const dot  = document.getElementById('status-dot');
  const span = document.getElementById('status-text');
  if (dot)  dot.className  = `w-1 h-1 ${ok ? 'bg-primary' : 'bg-[#494847]'}`;
  if (span) span.textContent = text;
}
