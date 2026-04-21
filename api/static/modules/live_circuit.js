// api/static/modules/live_circuit.js
// Connects to /ws/hardware-state and overlays live pin state on the SVG
// circuit viewer. Shows colored indicators on each component that has a
// matching pin in the live state dict.

const LiveCircuit = (() => {
  let _ws = null;
  let _circuitId = null;
  let _overlay = null;      // <div> containing all indicator elements
  let _indicators = {};     // pin → <div> element
  let _port = 'COM3';
  let _baud = 115200;
  let _onStateChange = null;
  let _reconnectTimer = null;
  let _active = false;

  // ── Colour helpers ──────────────────────────────────────────────────

  function _pinColor(pin, value, maxAnalog = 1023) {
    const upper = pin.toUpperCase();
    if (upper.startsWith('A')) {
      // Analog: gradient from blue (0) to red (max)
      const ratio = Math.min(value / maxAnalog, 1);
      const r = Math.round(ratio * 255);
      const b = Math.round((1 - ratio) * 255);
      return `rgb(${r},60,${b})`;
    }
    // Digital: green=HIGH, grey=LOW
    return value ? '#00ff88' : '#555555';
  }

  function _pinLabel(pin, value) {
    const upper = pin.toUpperCase();
    if (upper.startsWith('A')) return `${pin}: ${value}`;
    return `${pin}: ${value ? 'HIGH' : 'LOW'}`;
  }

  // ── Overlay management ──────────────────────────────────────────────

  function _ensureOverlay(container) {
    if (_overlay && container.contains(_overlay)) return;
    _overlay = document.createElement('div');
    _overlay.id = 'lc-overlay';
    _overlay.style.cssText =
      'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:10;';
    container.style.position = 'relative';
    container.appendChild(_overlay);
    _indicators = {};
  }

  function _clearOverlay() {
    if (_overlay) _overlay.innerHTML = '';
    _indicators = {};
  }

  // Map pin name to approximate SVG position.
  // Reads data-pin attributes placed on SVG <g> elements by the renderer,
  // or falls back to a legend strip at the bottom of the overlay.
  function _pinPosition(svgEl, pin) {
    if (!svgEl) return null;
    // Preferred: renderer marks each component group with data-pins="D13,A0"
    const groups = svgEl.querySelectorAll('[data-pins]');
    for (const g of groups) {
      const pins = g.dataset.pins.split(',');
      if (pins.includes(pin)) {
        const bb = g.getBoundingClientRect();
        const parent = svgEl.getBoundingClientRect();
        return {
          x: bb.left - parent.left + bb.width / 2,
          y: bb.top  - parent.top  + bb.height / 2,
        };
      }
    }
    return null;  // will use legend instead
  }

  function _renderState(container, svgEl, pins) {
    _ensureOverlay(container);

    // Legend strip at bottom for pins without positional data
    let legend = _overlay.querySelector('#lc-legend');
    if (!legend) {
      legend = document.createElement('div');
      legend.id = 'lc-legend';
      legend.style.cssText =
        'position:absolute;bottom:4px;left:4px;right:4px;display:flex;flex-wrap:wrap;gap:4px;';
      _overlay.appendChild(legend);
    }

    const inLegend = new Set();

    for (const [pin, value] of Object.entries(pins)) {
      const color = _pinColor(pin, value);
      const label = _pinLabel(pin, value);
      const pos = _pinPosition(svgEl, pin);

      if (pos) {
        // Floating indicator on the SVG
        let dot = _indicators[pin];
        if (!dot) {
          dot = document.createElement('div');
          dot.className = 'lc-dot';
          dot.style.cssText =
            'position:absolute;width:14px;height:14px;border-radius:50%;'
            + 'border:2px solid #fff;transform:translate(-50%,-50%);'
            + 'transition:background 0.2s;cursor:default;';
          const tip = document.createElement('span');
          tip.className = 'lc-tip';
          tip.style.cssText =
            'position:absolute;bottom:18px;left:50%;transform:translateX(-50%);'
            + 'background:#111;color:#fff;font:10px monospace;padding:2px 5px;'
            + 'border-radius:3px;white-space:nowrap;pointer-events:none;opacity:0;'
            + 'transition:opacity 0.15s;';
          dot.appendChild(tip);
          dot.addEventListener('mouseenter', () => { tip.style.opacity = '1'; });
          dot.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
          _overlay.appendChild(dot);
          _indicators[pin] = dot;
        }
        dot.style.left = pos.x + 'px';
        dot.style.top  = pos.y + 'px';
        dot.style.background = color;
        dot.querySelector('.lc-tip').textContent = label;
      } else {
        inLegend.add(pin);
        let chip = _indicators['leg_' + pin];
        if (!chip) {
          chip = document.createElement('span');
          chip.style.cssText =
            'display:inline-flex;align-items:center;gap:4px;'
            + 'background:#1a1a2e;border-radius:4px;padding:2px 6px;'
            + 'font:11px monospace;color:#ddd;border:1px solid #333;';
          const dot = document.createElement('span');
          dot.style.cssText =
            'display:inline-block;width:8px;height:8px;border-radius:50%;';
          chip.appendChild(dot);
          chip.appendChild(document.createTextNode(label));
          legend.appendChild(chip);
          _indicators['leg_' + pin] = chip;
        }
        chip.querySelector('span').style.background = color;
        chip.childNodes[1].textContent = label;
      }
    }

    // Remove stale legend chips
    for (const key of Object.keys(_indicators)) {
      if (key.startsWith('leg_') && !inLegend.has(key.slice(4))) {
        _indicators[key].remove();
        delete _indicators[key];
      }
    }
  }

  // ── WebSocket ───────────────────────────────────────────────────────

  function _connect(container, svgEl) {
    if (_ws) { _ws.close(); _ws = null; }
    clearTimeout(_reconnectTimer);

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/hardware-state?port=${encodeURIComponent(_port)}&baud=${_baud}`;

    _ws = new WebSocket(url);

    _ws.onopen = () => {
      console.log('[LiveCircuit] WS conectado:', url);
    };

    _ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'state') {
          _renderState(container, svgEl, data.pins);
          if (_onStateChange) _onStateChange(data.pins);
        } else if (data.type === 'error') {
          _showBanner(container, '⚠ ' + data.message, 'error');
        } else if (data.type === 'connected') {
          _showBanner(container, '🔌 ' + data.message, 'ok');
        }
      } catch (e) {
        console.warn('[LiveCircuit] Parse error:', e);
      }
    };

    _ws.onclose = () => {
      console.log('[LiveCircuit] WS cerrado');
      if (_active) {
        _reconnectTimer = setTimeout(() => _connect(container, svgEl), 3000);
      }
    };

    _ws.onerror = (e) => {
      console.error('[LiveCircuit] WS error', e);
    };
  }

  function _showBanner(container, text, type) {
    let banner = container.querySelector('.lc-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.className = 'lc-banner';
      banner.style.cssText =
        'position:absolute;top:6px;left:50%;transform:translateX(-50%);'
        + 'padding:4px 12px;border-radius:4px;font:12px monospace;'
        + 'z-index:20;opacity:1;transition:opacity 1s;';
      container.appendChild(banner);
    }
    banner.textContent = text;
    banner.style.background = type === 'error' ? '#7a0000' : '#004d2e';
    banner.style.color = '#fff';
    banner.style.opacity = '1';
    clearTimeout(banner._hide);
    banner._hide = setTimeout(() => { banner.style.opacity = '0'; }, 3000);
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    /**
     * Start live overlay.
     * @param {HTMLElement} container  — wrapper div that contains the SVG
     * @param {SVGElement|null} svgEl  — the schematic <svg> element
     * @param {string} port            — serial port, e.g. "COM3" or "/dev/ttyUSB0"
     * @param {number} baud            — baud rate
     * @param {Function} [onState]     — optional callback(pins: object)
     */
    start(container, svgEl, port = 'COM3', baud = 115200, onState = null) {
      _port = port;
      _baud = baud;
      _active = true;
      _onStateChange = onState;
      _ensureOverlay(container);
      _connect(container, svgEl);
    },

    stop() {
      _active = false;
      clearTimeout(_reconnectTimer);
      if (_ws) { _ws.close(); _ws = null; }
      _clearOverlay();
    },

    isActive() {
      return _active;
    },

    /** Inject a simulated state (for testing without hardware). */
    simulate(container, svgEl, pins) {
      _ensureOverlay(container);
      _renderState(container, svgEl, pins);
    },
  };
})();

export default LiveCircuit;
