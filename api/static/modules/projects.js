// ── PROYECTO ACTIVO ───────────────────────────────────────────────────────
let _projects    = [];
let _activeProject = null;

async function loadProjects() {
  try {
    const r = await authFetch(`${API}/projects`);
    const d = await r.json();
    _projects      = d.projects || [];
    _activeProject = d.active   || null;
    _renderProjects();
  } catch(e) {}
}

function _renderProjects() {
  const list = document.getElementById('projects-list');
  if (!list) return;

  if (!_projects.length) {
    list.innerHTML = '<div class="text-[9px] text-[#494847] px-3 py-2">Sin proyectos</div>';
    _updateActiveProjectBadge(null);
    return;
  }

  list.innerHTML = _projects.map(p => {
    const active = _activeProject && _activeProject.id === p.id;
    return `<div class="group flex items-center gap-2 px-3 py-1.5 hover:bg-[#131313] cursor-pointer transition-colors
        ${active ? 'border-l-2 border-primary' : 'border-l-2 border-transparent'}"
        onclick="activateProject('${escHtml(p.id)}')">
      <div class="flex-1 min-w-0">
        <div class="text-[9px] font-mono truncate ${active ? 'text-primary' : 'text-[#adaaaa]'}">${escHtml(p.name)}</div>
        ${p.mcu ? `<div class="text-[7px] text-[#494847]">${escHtml(p.mcu)}</div>` : ''}
      </div>
      ${active ? '<span class="material-symbols-outlined text-[9px] text-primary">done</span>' : ''}
      <button onclick="event.stopPropagation(); deleteProject('${escHtml(p.id)}')"
        class="hidden group-hover:block text-[7px] text-[#494847] hover:text-error ml-1 leading-none">✕</button>
    </div>`;
  }).join('');

  _updateActiveProjectBadge(_activeProject);
}

function _updateActiveProjectBadge(project) {
  const badge = document.getElementById('active-project-badge');
  if (!badge) return;
  if (project) {
    badge.textContent = project.name;
    badge.title = `MCU: ${project.mcu || '—'} | ${project.description || ''}`;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}

async function activateProject(projectId) {
  try {
    await authFetch(`${API}/projects/${projectId}/activate`, { method: 'POST' });
    await loadProjects();
  } catch(e) {}
}

async function deactivateAllProjects() {
  try {
    await authFetch(`${API}/projects/deactivate`, { method: 'POST' });
    await loadProjects();
  } catch(e) {}
}

function toggleCreateProjectForm() {
  document.getElementById('create-project-form')?.classList.toggle('hidden');
}

async function saveNewProject() {
  const name  = document.getElementById('proj-name')?.value?.trim();
  const mcu   = document.getElementById('proj-mcu')?.value?.trim()  || '';
  const desc  = document.getElementById('proj-desc')?.value?.trim() || '';
  const comps = document.getElementById('proj-comps')?.value?.trim()|| '';
  if (!name) return;

  try {
    await authFetch(`${API}/projects`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, mcu, description: desc, components: comps }),
    });
    ['proj-name','proj-mcu','proj-desc','proj-comps'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    document.getElementById('create-project-form')?.classList.add('hidden');
    await loadProjects();
  } catch(e) {}
}

async function deleteProject(projectId) {
  if (!confirm('¿Eliminar proyecto?')) return;
  try {
    await authFetch(`${API}/projects/${projectId}`, { method: 'DELETE' });
    await loadProjects();
  } catch(e) {}
}
