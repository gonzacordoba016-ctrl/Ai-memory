// ── AUTH HELPERS ──────────────────────────────────────────────────────────
function authFetch(url, opts = {}) {
  if (_token) {
    opts = { ...opts, headers: { 'Authorization': `Bearer ${_token}`, ...(opts.headers || {}) } };
  }
  return window.fetch(url, opts);
}

function _wsTokenParam(base) {
  const sep = base.includes('?') ? '&' : '?';
  return _token ? `${base}${sep}token=${encodeURIComponent(_token)}` : base;
}

async function doLogin() {
  const username = document.getElementById('login-user').value.trim();
  const password = document.getElementById('login-pass').value;
  const errEl    = document.getElementById('login-error');
  errEl.classList.add('hidden');
  if (!username || !password) { errEl.textContent = 'Completá usuario y contraseña.'; errEl.classList.remove('hidden'); return; }
  try {
    const r = await window.fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) { const e = await r.json(); errEl.textContent = e.detail || 'Error al iniciar sesión.'; errEl.classList.remove('hidden'); return; }
    const d = await r.json();
    _token = d.token;
    localStorage.setItem('stratum_jwt', _token);
    document.getElementById('login-modal').classList.add('hidden');
    // Reconectar WS con token
    if (ws) { ws.close(); }
    connectWS();
  } catch(e) {
    errEl.textContent = 'Error de red.'; errEl.classList.remove('hidden');
  }
}

function showLoginModal() {
  document.getElementById('login-modal').classList.remove('hidden');
  // Soportar Enter en los campos
  ['login-user','login-pass'].forEach(id => {
    document.getElementById(id).onkeydown = (e) => { if (e.key === 'Enter') doLogin(); };
  });
}

// ── AUTH STATUS ───────────────────────────────────────────────────────────
async function loadAuthStatus() {
  try {
    const r = await window.fetch(`${API}/auth/status`);
    const d = await r.json();
    const el = document.getElementById('auth-label');
    if (el) el.textContent = d.multi_user ? 'MULTI_USER_JWT_ACTIVE' : 'SINGLE_USER_MODE';

    if (d.multi_user) {
      if (!_token) {
        showLoginModal();
      } else {
        // Validar que el token almacenado sigue siendo válido
        const me = await window.fetch(`${API}/auth/me`, {
          headers: { 'Authorization': `Bearer ${_token}` }
        });
        if (!me.ok) {
          _token = null;
          localStorage.removeItem('stratum_jwt');
          showLoginModal();
        }
      }
    }
  } catch(e) {}
}
