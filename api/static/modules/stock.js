// ── WEB: COMPONENT STOCK ─────────────────────────────────────────────────────

async function webLoadStockSummary() {
  try {
    const d = await authFetch(`${API}/stock/summary`).then(r => r.json());
    document.getElementById('web-stock-total').textContent = d.total_components ?? 0;
    document.getElementById('web-stock-in').textContent    = d.in_stock ?? 0;
    document.getElementById('web-stock-cats').textContent  = d.categories ?? 0;
  } catch {}
}

async function webSearchStock(q) {
  const list = document.getElementById('web-stock-list');
  if (!list) return;
  try {
    const url = q ? `${API}/stock?q=${encodeURIComponent(q)}` : `${API}/stock?in_stock_only=true`;
    const items = await authFetch(url).then(r => r.json());
    if (!items.length) { list.innerHTML = '<p class="text-[9px] text-[#494847]">Sin resultados</p>'; return; }
    list.innerHTML = items.slice(0, 15).map(c => `
      <div class="flex justify-between text-[9px] py-0.5 border-b border-[#494847]/20">
        <span class="text-white">${esc(c.name)} <span class="text-[#494847]">${esc(c.value||'')}</span></span>
        <span class="text-secondary">×${c.quantity}</span>
      </div>
    `).join('');
  } catch {}
}

function webToggleStockForm() {
  const f = document.getElementById('web-stock-form');
  f.classList.toggle('hidden');
  if (!f.classList.contains('hidden')) document.getElementById('wsf-name').focus();
}

async function webSaveComponent() {
  const name     = document.getElementById('wsf-name').value.trim();
  if (!name) { addLog('El nombre es obligatorio', 'warn'); return; }
  const qty      = parseInt(document.getElementById('wsf-qty').value) || 1;
  const value    = document.getElementById('wsf-value').value.trim() || null;
  const category = document.getElementById('wsf-category').value.trim() || null;
  const supplier = document.getElementById('wsf-supplier').value.trim() || null;
  try {
    await authFetch(`${API}/stock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, quantity: qty, category, value, supplier }),
    });
    addLog(`Stock: ${name} ×${qty} agregado`, 'info');
    // Limpiar form y cerrar
    ['wsf-name','wsf-value','wsf-category','wsf-supplier'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('wsf-qty').value = '1';
    document.getElementById('web-stock-form').classList.add('hidden');
    webLoadStockSummary();
    webSearchStock('');
  } catch(e) { addLog('Error agregando componente: ' + e.message, 'error'); }
}

// ── WEB: SCHEMATIC IMPORT ────────────────────────────────────────────────────
async function webImportSchematic(input) {
  const file = input.files[0];
  if (!file) return;
  const statusEl = document.getElementById('web-schematic-status');
  statusEl.className = 'text-[9px] text-[#adaaaa]';
  statusEl.textContent = `Importando ${file.name}...`;
  statusEl.classList.remove('hidden');
  const formData = new FormData();
  formData.append('file', file);
  const name = file.name.replace(/\.[^.]+$/, '');
  try {
    const d = await authFetch(
      `${API}/schematics/import?project_name=${encodeURIComponent(name)}&save_to_memory=true`,
      { method: 'POST', body: formData }
    ).then(r => r.json());
    if (d.ok) {
      statusEl.className = 'text-[9px] text-secondary';
      statusEl.textContent = `✓ ${d.component_count} componentes, ${d.net_count} redes — ID ${d.circuit_id}`;
      addLog(`Esquemático importado: ${file.name} (${d.component_count} comp.)`, 'info');
    } else {
      statusEl.className = 'text-[9px] text-error';
      statusEl.textContent = `Error: ${d.detail || 'desconocido'}`;
    }
  } catch(e) {
    statusEl.className = 'text-[9px] text-error';
    statusEl.textContent = `Error: ${e.message}`;
  }
  input.value = '';
}

// ── WEB: PLC PARSER ──────────────────────────────────────────────────────────
async function webParsePLC() {
  const text = document.getElementById('web-plc-input').value.trim();
  const name = document.getElementById('web-plc-name').value.trim() || 'PLC Program';
  const resultEl = document.getElementById('web-plc-result');
  if (!text) { addLog('Ingresá la lógica ladder', 'warn'); return; }
  resultEl.classList.remove('hidden');
  resultEl.textContent = 'Parseando...';
  try {
    const d = await authFetch(`${API}/schematics/plc/parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, name }),
    }).then(r => r.json());
    resultEl.textContent = [
      `Rungs: ${d.rung_count} | Vars: ${(d.variables||[]).join(', ')||'ninguna'}`,
      d.circuit_id ? `Guardado — ID ${d.circuit_id}` : '',
      '─── Structured Text ───',
      d.structured_text || '',
    ].filter(Boolean).join('\n');
    if (d.circuit_id) addLog(`PLC guardado — ID ${d.circuit_id}`, 'info');
  } catch(e) {
    resultEl.textContent = `Error: ${e.message}`;
  }
}
