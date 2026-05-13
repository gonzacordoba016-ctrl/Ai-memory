async function webLoadStockSummary() {
  const summary = document.getElementById('stock-summary');
  if (!summary) return;

  try {
    const d = await authFetch(`${API}/stock/summary`).then(r => r.json());
    summary.textContent = `${d.total_components ?? 0} componentes | ${d.in_stock ?? 0} en stock | ${d.categories ?? 0} categorias`;
  } catch {
    summary.textContent = 'No se pudo cargar el stock';
  }
}

async function webSearchStock() {
  // Compatibilidad con app.js: el panel SYSTEM ahora solo muestra resumen.
}
