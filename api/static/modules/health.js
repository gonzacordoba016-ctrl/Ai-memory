function setConnected(ok) {
  const dot = document.getElementById('conn-dot');
  const label = document.getElementById('conn-label');
  const estat = document.getElementById('engine-status');

  if (dot) {
    dot.className = ok
      ? 'w-1.5 h-1.5 bg-primary rounded-full animate-pulse'
      : 'w-1.5 h-1.5 bg-gray-500 rounded-full';
  }
  if (label) {
    label.className = ok
      ? 'text-primary text-[10px] tracking-widest'
      : 'text-gray-500 text-[10px] tracking-widest';
    label.textContent = ok ? 'ACTIVE_CONNECTION' : 'DISCONNECTED';
  }
  if (estat) {
    estat.textContent = ok ? 'STATUS: OPERATIONAL' : 'STATUS: OFFLINE';
    estat.className = ok ? 'text-primary text-[9px]' : 'text-error text-[9px]';
  }
}

async function loadHealth() {
  // SYSTEM ya no muestra health/service cards.
}

async function loadBridgeStatus() {
  // Hardware bridge status no tiene panel activo en el frontend.
}

async function loadWokwiStatus() {
  // Wokwi status no tiene panel activo en el frontend.
}

async function bridgeTest() {
  // Mantiene compatibilidad con handlers antiguos si quedan cargados.
}
