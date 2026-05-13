async function loadHardware() {
  const list = document.getElementById('devices-list');
  if (!list) return;

  list.innerHTML = `
    <div class="col-span-12 panel panel-cnr px-4 py-8 text-center label label-dim">
      Escaneando hardware...
    </div>`;

  try {
    const r = await authFetch(`${API}/hardware/devices`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const connected = d.connected || [];
    const countEl = document.getElementById('s-devices');
    if (countEl) countEl.textContent = connected.length;

    if (!connected.length) {
      list.innerHTML = `
        <div class="col-span-12 panel panel-cnr px-4 py-8 text-center label label-dim">
          Sin dispositivos detectados
        </div>`;
      return;
    }

    list.innerHTML = connected.map(device => {
      const name = device.name || device.device_name || device.port || 'Dispositivo';
      const platform = device.platform || device.type || 'USB/Serial';
      const port = device.port || device.path || 'puerto no informado';
      const icon = String(platform).toLowerCase().includes('esp32') ? 'wifi' : 'usb';
      const badge = device.micropython
        ? '<span class="chip chip-ok">MicroPython</span>'
        : '';

      return `
        <div class="col-span-12 md:col-span-6 lg:col-span-4 panel panel-cnr p-3">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined" style="font-size:16px">${icon}</span>
            <span class="mono" style="font-size:12px; color:var(--fg)">${escHtml(name)}</span>
            <span class="ml-auto chip chip-ok"><span class="dot"></span>ONLINE</span>
          </div>
          <div class="mt-2 label label-dim" style="font-size:10px">${escHtml(port)}</div>
          <div class="mt-1 flex items-center gap-2 label label-dim" style="font-size:10px">
            <span>${escHtml(platform)}</span>
            ${badge}
          </div>
        </div>`;
    }).join('');
  } catch {
    list.innerHTML = `
      <div class="col-span-12 panel panel-cnr px-4 py-8 text-center label text-error">
        Error conectando con detector de hardware
      </div>`;
  }
}

async function loadJobs() {
  // Jobs no tiene panel activo en el frontend.
}

function renderIdleOscilloscope() {
  // Osciloscopio removido del frontend.
}

function connectSignalWS() {
  // Stream de osciloscopio removido del frontend.
}
