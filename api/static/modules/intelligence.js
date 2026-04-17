// ── INTELLIGENCE ──────────────────────────────────────────────────────────
async function loadIntelligence() {
  try {
    const [profilesR, sourcesR, activeR] = await Promise.all([
      authFetch(`${API}/intelligence/profiles`).then(r => r.json()),
      authFetch(`${API}/intelligence/sources`).then(r => r.json()),
      authFetch(`${API}/intelligence/active`).then(r => r.json()),
    ]);

    const profiles = profilesR.profiles || [];
    const sources  = sourcesR.sources   || [];
    const activeId = activeR.profile?.id;

    // Header badge
    const badge = document.getElementById('h-active-profile');
    if (badge) badge.textContent = activeR.profile?.name || '—';

    // Render profiles
    const pel = document.getElementById('intel-profiles');
    pel.innerHTML = profiles.length ? profiles.map(p => {
      const isActive = p.id === activeId;
      const border   = isActive ? 'border-primary' : 'border-[#494847]/30';
      const nameClr  = isActive ? 'text-primary' : 'text-white';
      const activeLbl= isActive ? '<span class="text-[8px] text-primary font-bold">● ACTIVE</span>' : '';
      const canDel   = !p.id.startsWith('default-');
      return `
        <div class="bg-[#131313] border-l-2 ${border} p-2.5 space-y-1">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-bold ${nameClr}">${escHtml(p.name)}</span>
            <div class="flex items-center gap-2">
              ${activeLbl}
              ${canDel ? `<button onclick="deleteProfile('${p.id}')" class="text-[8px] text-error hover:opacity-80">✕</button>` : ''}
            </div>
          </div>
          ${p.description ? `<p class="text-[8px] text-[#adaaaa]">${escHtml(p.description)}</p>` : ''}
          <div class="text-[7px] text-[#494847] font-mono leading-tight line-clamp-2 mt-1">${escHtml(p.system_prompt.slice(0, 80))}...</div>
          ${!isActive ? `<button onclick="activateProfile('${p.id}')" class="mt-1 w-full py-1 text-[8px] border border-secondary/30 text-secondary hover:bg-secondary/10 transition-colors">SET ACTIVE</button>` : ''}
        </div>`;
    }).join('') : '<p class="text-[10px] text-[#adaaaa]">Sin perfiles</p>';

    // Render sources
    const sel = document.getElementById('intel-sources');
    sel.innerHTML = sources.length ? sources.map(s => {
      const indexed = s.indexed;
      const idxClr  = indexed ? 'text-primary' : 'text-[#adaaaa]';
      const idxLbl  = indexed ? 'INDEXED' : 'NOT_INDEXED';
      return `
        <div class="bg-[#131313] border-l-2 border-[#8eff71]/30 p-2.5">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-bold text-[#8eff71]">${escHtml(s.name)}</span>
            <div class="flex items-center gap-2">
              <span class="text-[7px] ${idxClr}">${idxLbl}</span>
              <button onclick="deleteSource('${s.id}')" class="text-[8px] text-error hover:opacity-80">✕</button>
            </div>
          </div>
          ${s.description ? `<p class="text-[8px] text-[#adaaaa] mt-0.5">${escHtml(s.description)}</p>` : ''}
          <div class="flex gap-1 mt-1.5">
            <span class="text-[7px] px-1 py-0.5 bg-black border border-[#494847]/30 text-[#adaaaa]">${escHtml(s.type.toUpperCase())}</span>
            ${!indexed ? `<button onclick="indexSource('${s.id}')" class="text-[7px] px-1 py-0.5 bg-[#8eff71]/10 border border-[#8eff71]/30 text-[#8eff71] hover:bg-[#8eff71]/20">INDEX NOW</button>` : ''}
          </div>
        </div>`;
    }).join('') : '<p class="text-[10px] text-[#adaaaa]">Sin fuentes</p>';

  } catch(e) { addLog('Error cargando intelligence', 'error'); }
}

async function activateProfile(id) {
  try {
    await authFetch(`${API}/intelligence/profiles/${id}/activate`, {method:'POST'});
    addLog(`Perfil activado`, 'info');
    loadIntelligence();
  } catch(e) { addLog('Error activando perfil', 'error'); }
}

async function deleteProfile(id) {
  if (!confirm('¿Eliminar este perfil?')) return;
  try {
    const r = await authFetch(`${API}/intelligence/profiles/${id}`, {method:'DELETE'});
    const d = await r.json();
    if (d.ok) { addLog('Perfil eliminado', 'info'); loadIntelligence(); }
    else addLog('No se puede eliminar este perfil', 'warn');
  } catch(e) {}
}

function showCreateProfile() {
  document.getElementById('intel-create-profile-form').classList.remove('hidden');
}
function hideCreateProfile() {
  document.getElementById('intel-create-profile-form').classList.add('hidden');
  document.getElementById('intel-pf-name').value = '';
  document.getElementById('intel-pf-prompt').value = '';
  document.getElementById('intel-pf-desc').value = '';
}
async function saveNewProfile() {
  const name   = document.getElementById('intel-pf-name').value.trim();
  const prompt = document.getElementById('intel-pf-prompt').value.trim();
  const desc   = document.getElementById('intel-pf-desc').value.trim();
  if (!name || !prompt) { addLog('Nombre y system prompt requeridos', 'warn'); return; }
  try {
    const r = await authFetch(`${API}/intelligence/profiles`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, system_prompt: prompt, description: desc}),
    });
    const d = await r.json();
    if (d.profile) { hideCreateProfile(); loadIntelligence(); addLog(`Perfil creado: ${name}`, 'info'); }
  } catch(e) { addLog('Error creando perfil', 'error'); }
}

async function indexSource(id) {
  try {
    addLog('Indexando fuente...', 'info');
    const r = await authFetch(`${API}/intelligence/sources/${id}/index`, {method:'POST'});
    const d = await r.json();
    if (d.ok) { addLog(`Fuente indexada — ${d.chunks} chunks`, 'info'); loadIntelligence(); }
    else addLog('Error indexando', 'error');
  } catch(e) { addLog('Error indexando fuente', 'error'); }
}

async function deleteSource(id) {
  if (!confirm('¿Eliminar esta fuente?')) return;
  try {
    await authFetch(`${API}/intelligence/sources/${id}`, {method:'DELETE'});
    addLog('Fuente eliminada', 'info');
    loadIntelligence();
  } catch(e) {}
}

function showCreateSource() {
  document.getElementById('intel-create-source-form').classList.remove('hidden');
}
function hideCreateSource() {
  document.getElementById('intel-create-source-form').classList.add('hidden');
  document.getElementById('intel-src-name').value = '';
  document.getElementById('intel-src-content').value = '';
  document.getElementById('intel-src-desc').value = '';
}
async function saveNewSource() {
  const name    = document.getElementById('intel-src-name').value.trim();
  const content = document.getElementById('intel-src-content').value.trim();
  const desc    = document.getElementById('intel-src-desc').value.trim();
  if (!name || !content) { addLog('Nombre y contenido requeridos', 'warn'); return; }
  try {
    const r = await authFetch(`${API}/intelligence/sources`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, type:'text', content, description: desc}),
    });
    const d = await r.json();
    if (d.source) {
      addLog(`Fuente creada: ${name} — indexando...`, 'info');
      hideCreateSource();
      await indexSource(d.source.id);
    }
  } catch(e) { addLog('Error creando fuente', 'error'); }
}
