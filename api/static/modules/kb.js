// ── KNOWLEDGE BASE ────────────────────────────────────────────────────────────

async function kbLoadDocuments() {
  const el = document.getElementById('kb-doc-list');
  if (!el) return;
  el.innerHTML = '<div class="text-[#494847]">Cargando...</div>';
  try {
    const r = await authFetch('/api/knowledge/documents');
    const data = await r.json();
    if (!data.documents || data.documents.length === 0) {
      el.innerHTML = '<div class="text-[#494847]">Sin documentos indexados.</div>';
      return;
    }
    el.innerHTML = data.documents.map(d => {
      const name = typeof d === 'string' ? d : (d.source || d.filename || d.name || JSON.stringify(d));
      const chunks = typeof d === 'object' && d.chunks != null ? ` <span class="text-[#494847]">${d.chunks} chunks</span>` : '';
      return `<div class="flex items-center gap-2 py-0.5 border-b border-[#494847]/10">
        <span class="material-symbols-outlined text-xs text-[#494847]">description</span>
        <span class="flex-1 truncate">${escHtml(name)}</span>${chunks}
        <button onclick="kbDeleteDoc('${escHtml(name).replace(/'/g, "\\'")}')"
                class="text-[8px] text-[#494847] hover:text-error transition-colors ml-1" title="Eliminar">
          <span class="material-symbols-outlined text-xs">delete</span>
        </button>
      </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div class="text-[#ff716c]">Error: ${escHtml(String(e))}</div>`;
  }
}

async function kbDeleteDoc(filename) {
  if (!confirm(`Eliminar "${filename}" de la Knowledge Base?`)) return;
  const status = document.getElementById('kb-upload-status');
  status.classList.remove('hidden');
  status.textContent = `Eliminando ${filename}...`;
  try {
    const r = await authFetch(`/api/knowledge/delete/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = `❌ ${data.detail || 'Error al eliminar'}`;
    } else {
      status.textContent = `✅ ${data.deleted} eliminado`;
      kbLoadDocuments();
    }
  } catch(e) {
    status.textContent = `❌ ${String(e)}`;
  }
}

async function kbUploadFile(input) {
  const file = input.files?.[0];
  if (!file) return;
  const status = document.getElementById('kb-upload-status');
  status.classList.remove('hidden');
  status.textContent = `⏳ Subiendo ${file.name}...`;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await authFetch('/api/knowledge/upload', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = `❌ ${data.detail || 'Error al subir'}`;
    } else {
      status.textContent = `✅ ${data.filename} subido e indexado`;
      input.value = '';
      kbLoadDocuments();
    }
  } catch(e) {
    status.textContent = `❌ ${String(e)}`;
  }
}

async function kbReindex() {
  const status = document.getElementById('kb-upload-status');
  status.classList.remove('hidden');
  status.textContent = '⏳ Re-indexando...';
  try {
    const r = await authFetch('/api/knowledge/index?force=true', { method: 'POST' });
    const data = await r.json();
    const idx = data.indexed || {};
    const msg = idx.files > 0 ? `${idx.files} archivos nuevos, ${idx.chunks} chunks` : 'Todo ya estaba indexado';
    status.textContent = `✅ Re-indexación completa: ${msg}`;
    kbLoadDocuments();
  } catch(e) {
    status.textContent = `❌ ${String(e)}`;
  }
}

async function kbImportFeed() {
  const status = document.getElementById('kb-upload-status');
  const btn = document.getElementById('kb-import-feed-btn');
  status.classList.remove('hidden');
  status.textContent = '⏳ Importando knowledge_feed...';
  if (btn) btn.disabled = true;
  try {
    const r = await authFetch('/api/knowledge/import-feed', { method: 'POST' });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = `❌ ${data.detail || 'Error al importar'}`;
    } else if (data.imported && data.imported.length > 0) {
      status.textContent = `✅ ${data.imported.length} archivos importados e indexados`;
      kbLoadDocuments();
    } else {
      status.textContent = `ℹ️ ${data.message || 'Sin archivos nuevos'}`;
    }
  } catch(e) {
    status.textContent = `❌ ${String(e)}`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function kbSearch() {
  const q = document.getElementById('kb-search-input')?.value?.trim();
  const el = document.getElementById('kb-search-results');
  if (!q || !el) return;
  el.innerHTML = '<div class="text-[#494847] text-[9px]">Buscando...</div>';
  try {
    const r = await authFetch(`/api/knowledge/search?q=${encodeURIComponent(q)}&top_k=5`);
    const data = await r.json();
    if (!data.results || data.results.length === 0) {
      el.innerHTML = '<div class="text-[#494847] text-[9px]">Sin resultados.</div>';
      return;
    }
    el.innerHTML = data.results.map((res, i) => {
      // results may be plain strings "[source.txt] text..." or objects
      const raw = typeof res === 'string' ? res : (res.text || JSON.stringify(res));
      const srcMatch = raw.match(/^\[([^\]]+)\]\s*/);
      const src = srcMatch ? srcMatch[1] : '';
      const text = srcMatch ? raw.slice(srcMatch[0].length) : raw;
      const score = typeof res === 'object' && res.score != null
        ? `<span class="text-[#494847] ml-1">${(res.score*100).toFixed(0)}%</span>` : '';
      return `<div class="border border-[#494847]/20 p-2 space-y-0.5">
        <div class="flex items-center gap-1 text-[8px] text-[#494847]">
          <span>#${i+1}</span>${score}${src ? `<span class="ml-1">· ${escHtml(src)}</span>` : ''}
        </div>
        <div class="text-[9px] text-[#adaaaa] leading-relaxed">${escHtml(text.slice(0,300))}</div>
      </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = `<div class="text-[#ff716c] text-[9px]">❌ ${escHtml(String(e))}</div>`;
  }
}
