// ── WEB: DESIGN DECISIONS ────────────────────────────────────────────────────
function webToggleDecisionForm() {
  const f = document.getElementById('web-decision-form');
  f.classList.toggle('hidden');
  if (!f.classList.contains('hidden')) document.getElementById('wdf-decision').focus();
}

async function webSaveDecision() {
  const decision  = document.getElementById('wdf-decision').value.trim();
  const reasoning = document.getElementById('wdf-reasoning').value.trim();
  if (!decision || !reasoning) { addLog('Decisión y razonamiento son obligatorios', 'warn'); return; }
  const project   = document.getElementById('wdf-project').value.trim()   || 'general';
  const component = document.getElementById('wdf-component').value.trim() || null;
  try {
    await authFetch(`${API}/decisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, decision, reasoning, component }),
    });
    addLog(`Decisión guardada: ${decision.slice(0,40)}`, 'info');
    ['wdf-project','wdf-component','wdf-decision','wdf-reasoning'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('web-decision-form').classList.add('hidden');
    webLoadDecisions();
  } catch(e) { addLog('Error guardando decisión: ' + e.message, 'error'); }
}

async function webDeleteDecision(id) {
  try {
    await authFetch(`${API}/decisions/${id}`, { method: 'DELETE' });
    webLoadDecisions();
  } catch(e) { addLog('Error eliminando decisión: ' + e.message, 'error'); }
}

async function webLoadDecisions(query = '') {
  const container = document.getElementById('web-intel-decisions');
  if (!container) return;
  try {
    const url = query
      ? `${API}/decisions?q=${encodeURIComponent(query)}&limit=20`
      : `${API}/decisions?limit=20`;
    const list = await authFetch(url).then(r => r.json());
    if (!list.length) {
      container.innerHTML = '<p class="text-[10px] text-[#adaaaa]">Sin decisiones guardadas</p>';
      return;
    }
    container.innerHTML = list.map(d => `
      <div class="bg-[#131313] border-l-2 border-secondary/40 p-2 text-[9px] relative">
        <button onclick="webDeleteDecision(${d.id})" class="absolute top-1 right-1 text-[#494847] hover:text-error text-[10px] leading-none">×</button>
        <div class="text-secondary font-mono pr-4">${esc(d.project)}${d.component ? ' — ' + esc(d.component) : ''}</div>
        <div class="text-white mt-1 opacity-80">${esc(d.decision||'')}</div>
        <div class="text-[#adaaaa] mt-0.5">${esc((d.reasoning||'').slice(0,120))}${(d.reasoning||'').length>120?'…':''}</div>
        <div class="text-[#494847] mt-0.5">${(d.created_at||'').slice(0,10)}</div>
      </div>
    `).join('');
  } catch(e) {
    if (container) container.innerHTML = `<p class="text-[10px] text-error">Error: ${e.message}</p>`;
  }
}

function webSearchDecisions(q) {
  clearTimeout(window._webDecisionsTimeout);
  window._webDecisionsTimeout = setTimeout(() => webLoadDecisions(q), 400);
}
