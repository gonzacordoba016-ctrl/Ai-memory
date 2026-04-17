// ── SESSION MANAGEMENT ────────────────────────────────────────────────────

async function loadSessions() {
  try {
    const data = await authFetch(`${API}/sessions`).then(r => r.json());
    _sessions = data.sessions || [];
    renderSessionsList();
  } catch(e) { /* ignore */ }
}

function renderSessionsList() {
  const el = document.getElementById('sessions-list');
  if (!el) return;
  if (_sessions.length === 0) {
    el.innerHTML = '<div class="px-4 py-6 text-center text-[9px] text-[#494847]">Sin conversaciones</div>';
    return;
  }

  // Group by Today / Yesterday / Anterior
  const now   = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);

  const groups = { 'Hoy': [], 'Ayer': [], 'Anterior': [] };
  for (const s of _sessions) {
    const d = new Date(s.last_msg_at || s.created_at);
    if (d >= today) groups['Hoy'].push(s);
    else if (d >= yesterday) groups['Ayer'].push(s);
    else groups['Anterior'].push(s);
  }

  let html = '';
  for (const [label, list] of Object.entries(groups)) {
    if (list.length === 0) continue;
    html += `<div class="px-4 pt-3 pb-1 text-[8px] text-[#494847] tracking-widest uppercase">${label}</div>`;
    for (const s of list) {
      const isActive = s.id === _session_id;
      const titleSafe = escHtml(s.title || 'Nueva conversación');
      const timeAgo = _relTime(s.last_msg_at || s.created_at);
      html += `
        <div class="group flex items-center px-3 py-2 cursor-pointer transition-colors session-item ${isActive ? 'bg-[#131313] border-l-2 border-primary' : 'hover:bg-[#0f0f0f] border-l-2 border-transparent'}"
             onclick="switchSession('${escHtml(s.id)}')" id="sess-${escHtml(s.id)}">
          <div class="flex-1 min-w-0 mr-2">
            <div class="text-[10px] ${isActive ? 'text-primary' : 'text-[#adaaaa]'} truncate leading-tight">${titleSafe}</div>
            <div class="text-[8px] text-[#494847] mt-0.5">${timeAgo}</div>
          </div>
          <button onclick="deleteSession('${escHtml(s.id)}', event)"
            class="opacity-0 group-hover:opacity-100 text-[#494847] hover:text-error p-0.5 transition-all flex-shrink-0">
            <span class="material-symbols-outlined text-xs">delete</span>
          </button>
        </div>`;
    }
  }
  el.innerHTML = html;
}

function _relTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'ahora';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h`;
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
}

async function newSession() {
  try {
    const res = await authFetch(`${API}/sessions`, { method: 'POST',
      headers: {'Content-Type':'application/json'}, body: JSON.stringify({title:'Nueva conversación'}) });
    const s = await res.json();
    _session_id = s.id;
    localStorage.setItem('stratum_session_id', _session_id);
    // Reconnect WS with new session
    if (ws) ws.close();
    // Clear messages area
    const msgs = document.getElementById('messages');
    if (msgs) msgs.innerHTML = `
      <div class="flex items-center gap-4 text-[#494847] text-[9px] uppercase tracking-widest">
        <div class="h-[1px] flex-1 bg-[#494847]/30"></div>
        <span id="session-time">NUEVA SESIÓN</span>
        <div class="h-[1px] flex-1 bg-[#494847]/30"></div>
      </div>
      <div class="flex flex-col items-start">
        <div class="bg-[#131313] border-l-2 border-primary p-4 max-w-2xl">
          <div class="text-[9px] mb-2 opacity-50 text-primary">STRATUM_ENGINE // SYSTEM</div>
          <p class="text-sm font-mono tracking-tight">Sesión nueva. Engineering Memory Engine listo.</p>
        </div>
      </div>`;
    switchView('chat');
    await loadSessions();
    setTimeout(connectWS, 200);
  } catch(e) { console.error(e); }
}

async function switchSession(sessionId) {
  if (_session_id === sessionId) { switchView('chat'); return; }
  _session_id = sessionId;
  localStorage.setItem('stratum_session_id', sessionId);
  // Clear & reload messages
  const msgs = document.getElementById('messages');
  if (msgs) msgs.innerHTML = `<div class="flex items-center gap-4 text-[#494847] text-[9px] uppercase tracking-widest"><div class="h-[1px] flex-1 bg-[#494847]/30"></div><span>CARGANDO...</span><div class="h-[1px] flex-1 bg-[#494847]/30"></div></div>`;
  switchView('chat');
  if (ws) ws.close();
  setTimeout(connectWS, 200);
  renderSessionsList(); // update active indicator
}

async function deleteSession(sessionId, event) {
  event?.stopPropagation();
  if (!confirm('¿Eliminar esta conversación?')) return;
  await authFetch(`${API}/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  if (_session_id === sessionId) {
    // Switch to newest remaining session or create new
    await loadSessions();
    if (_sessions.length > 0) {
      await switchSession(_sessions[0].id);
    } else {
      await newSession();
    }
  } else {
    await loadSessions();
  }
}
