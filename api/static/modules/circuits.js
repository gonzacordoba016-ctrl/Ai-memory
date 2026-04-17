// ── Circuit DRC + BOM ─────────────────────────────────────────────────────────

function _getCircuitId() {
  const val = document.getElementById('circuit-id-input')?.value;
  if (!val || isNaN(val) || parseInt(val) < 1) {
    alert('Ingresá un Circuit ID válido.');
    return null;
  }
  return parseInt(val);
}

function _showCircuitResult(html) {
  const panel = document.getElementById('circuit-result-panel');
  if (!panel) return;
  panel.innerHTML = html;
  panel.classList.remove('hidden');
}

async function runCircuitDRC() {
  const id = _getCircuitId();
  if (!id) return;
  _showCircuitResult('<div class="text-[#adaaaa]">⏳ Ejecutando DRC...</div>');
  try {
    const r = await authFetch(`/api/circuits/${id}/drc`);
    const data = await r.json();
    if (!r.ok) { _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(data.detail || 'Error')}</div>`); return; }

    const passedColor = data.passed ? '#a4ffb9' : '#ff716c';
    const passedIcon  = data.passed ? '✓' : '✗';
    let html = `<div class="font-bold mb-1" style="color:${passedColor}">${passedIcon} DRC: ${escHtml(data.summary)}</div>`;

    const allIssues = [...(data.errors||[]), ...(data.warnings||[]), ...(data.info||[])];
    if (allIssues.length === 0) {
      html += `<div class="text-[#a4ffb9] text-[8px]">Sin problemas detectados.</div>`;
    } else {
      for (const issue of allIssues) {
        const color = issue.severity === 'error' ? '#ff716c' : issue.severity === 'warning' ? '#ffd700' : '#adaaaa';
        html += `<div class="text-[8px]" style="color:${color}">
          [${escHtml(issue.severity?.toUpperCase())}] <b>${escHtml(issue.code)}</b>
          ${issue.component ? `<span class="text-[#adaaaa]">(${escHtml(issue.component)})</span>` : ''}
          — ${escHtml(issue.message)}
        </div>`;
      }
    }
    _showCircuitResult(html);
  } catch(e) {
    _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(String(e))}</div>`);
  }
}

async function runCircuitBOM() {
  const id = _getCircuitId();
  if (!id) return;
  _showCircuitResult('<div class="text-[#adaaaa]">⏳ Generando BOM...</div>');
  try {
    const r = await authFetch(`/api/circuits/${id}/bom`);
    const data = await r.json();
    if (!r.ok) { _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(data.detail || 'Error')}</div>`); return; }

    let html = `<div class="text-[#00cbfe] font-bold mb-1">BOM — ${escHtml(data.summary)}</div>`;
    html += `<table class="w-full text-[8px] border-collapse">
      <thead><tr class="text-[#494847]">
        <th class="text-left pr-2">REF</th>
        <th class="text-left pr-2">NOMBRE</th>
        <th class="text-right pr-2">STOCK</th>
        <th class="text-right pr-2">PROVEEDOR</th>
        <th class="text-right">COSTO</th>
      </tr></thead><tbody>`;
    for (const line of (data.lines || [])) {
      const stockColor = line.in_stock ? '#a4ffb9' : '#ff716c';
      html += `<tr class="border-t border-[#494847]/20">
        <td class="pr-2 text-[#adaaaa]">${escHtml(line.ref)}</td>
        <td class="pr-2 text-[#adaaaa]">${escHtml((line.name||'').slice(0,22))}</td>
        <td class="pr-2 text-right" style="color:${stockColor}">${line.stock_qty}</td>
        <td class="pr-2 text-right text-[#adaaaa]">${escHtml((line.supplier||'—').slice(0,12))}</td>
        <td class="text-right text-[#adaaaa]">${line.unit_cost ? '$'+line.unit_cost.toFixed(2) : '—'}</td>
      </tr>`;
    }
    html += `</tbody><tfoot><tr class="border-t border-[#494847]/40">
      <td colspan="4" class="text-right text-[#adaaaa] pt-1">TOTAL:</td>
      <td class="text-right text-[#a4ffb9] font-bold pt-1">$${(data.total_cost||0).toFixed(2)}</td>
    </tr></tfoot></table>`;

    if ((data.missing_components||[]).length > 0) {
      html += `<div class="text-[#ffd700] text-[8px] mt-1">⚠ Faltantes: ${escHtml(data.missing_components.join(', '))}</div>`;
    }
    _showCircuitResult(html);
  } catch(e) {
    _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(String(e))}</div>`);
  }
}

function downloadCircuitBOMcsv() {
  const id = _getCircuitId();
  if (!id) return;
  window.open(`/api/circuits/${id}/bom.csv`, '_blank');
}

async function simulateCircuitWokwi() {
  const id = _getCircuitId();
  if (!id) return;
  _showCircuitResult('<div class="text-[#adaaaa]">⏳ Generando diagram.json Wokwi...</div>');
  try {
    const r = await authFetch(`/api/circuits/${id}/simulate`, { method: 'POST' });
    const data = await r.json();
    if (!r.ok) {
      _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(data.detail || 'Error')}</div>`);
      return;
    }
    const parts = data.diagram_json?.parts?.length ?? 0;
    const conns = data.diagram_json?.connections?.length ?? 0;
    let html = `<div class="text-[#a855f7] font-bold mb-1">Wokwi — ${escHtml(data.circuit_name)}</div>`;
    html += `<div class="text-[#adaaaa]">📦 ${parts} partes · 🔗 ${conns} conexiones</div>`;
    if (data.status === 'unavailable') {
      html += `<div class="text-[#f5c518] mt-1">${escHtml(data.message)}</div>`;
      html += `<div class="flex gap-2 mt-2">`;
      html += `<a href="/api/circuits/${id}/diagram.json" download class="text-[9px] font-mono bg-[#131313] border border-[#a855f7]/50 text-[#a855f7] px-2 py-1 hover:border-[#a855f7]">⬇ Descargar diagram.json</a>`;
      html += `<a href="${escHtml(data.simulation_url)}" target="_blank" class="text-[9px] font-mono bg-[#131313] border border-[#a855f7]/50 text-[#a855f7] px-2 py-1 hover:border-[#a855f7]">🌐 Abrir Wokwi</a>`;
      html += `</div>`;
    } else if (data.status === 'ok') {
      html += `<div class="text-[#a4ffb9] mt-1">✅ Simulación completada</div>`;
      if (data.output) html += `<pre class="text-[8px] text-[#adaaaa] mt-1 max-h-24 overflow-y-auto">${escHtml(data.output)}</pre>`;
    } else {
      html += `<div class="text-[#ff716c] mt-1">⚠ ${escHtml(data.output || data.message || 'Error')}</div>`;
      html += `<a href="/api/circuits/${id}/diagram.json" download class="text-[9px] font-mono text-[#a855f7] mt-1 block">⬇ Descargar diagram.json</a>`;
    }
    _showCircuitResult(html);
  } catch(e) {
    _showCircuitResult(`<div class="text-[#ff716c]">❌ ${escHtml(String(e))}</div>`);
  }
}
