// ── PANEL CALC ────────────────────────────────────────────────────────────────

function calcSwitchForm(formula) {
  document.querySelectorAll('.calc-form').forEach(el => el.classList.add('hidden'));
  const f = document.getElementById(`calcf-${formula}`);
  if (f) f.classList.remove('hidden');
  document.getElementById('calc-result')?.classList.add('hidden');
}

function v(id) { return document.getElementById(id)?.value || ''; }

const _CALC_PARAMS = {
  resistor_for_led:         () => ({ vcc: +v('cf-vcc'), vled: +v('cf-vled'), iled_ma: +v('cf-iled') }),
  resistor_voltage_divider: () => ({ vin: +v('cf-vin'), vout: +v('cf-vout'), r1: +v('cf-r1') }),
  buck_converter:           () => ({ vin: +v('cf-bvin'), vout: +v('cf-bvout'), iout: +v('cf-biout'), freq_khz: +v('cf-bfreq') }),
  boost_converter:          () => ({ vin: +v('cf-bovin'), vout: +v('cf-bovout'), iout: +v('cf-boiout'), freq_khz: +v('cf-bofreq') }),
  battery_autonomy:         () => ({ capacity_mah: +v('cf-cap'), current_ma: +v('cf-ima'), efficiency: +v('cf-eta') }),
  fuse_rating:              () => ({ i_max: +v('cf-imax'), safety_factor: +v('cf-fsaf') }),
  heat_sink_required:       () => ({ p_w: +v('cf-pw'), t_ambient: +v('cf-tamb'), theta_jc: +v('cf-tjc'), t_junction_max: +v('cf-tjmax') }),
  transformer_turns_ratio:  () => ({ vp: +v('cf-vp'), vs: +v('cf-vs') }),
  low_pass_rc:              () => ({ cutoff_hz: +v('cf-fcl'), r: +v('cf-rl') }),
  high_pass_rc:             () => ({ cutoff_hz: +v('cf-fch'), c_uf: +v('cf-ch') }),
  inverting_amp:            () => ({ r_in: +v('cf-rin'), r_feedback: +v('cf-rf') }),
  non_inverting_amp:        () => ({ r1: +v('cf-nir1'), r2: +v('cf-nir2') }),
  motor_power:              () => ({ voltage: +v('cf-mv'), current: +v('cf-mi'), efficiency: +v('cf-meta') }),
  vfd_frequency_for_rpm:    () => ({ rpm: +v('cf-rpm'), poles: +v('cf-poles') }),
  ohms_law: () => {
    const ohv = v('cf-ohv'), ohi = v('cf-ohi'), ohr = v('cf-ohr');
    const p = {};
    if (ohv) p.v = +ohv;
    if (ohi) p.i_ma = +ohi;
    if (ohr) p.r = +ohr;
    return p;
  },
  resistor_power: () => {
    const p = { r: +v('cf-rpr') };
    const ima = v('cf-rpima'), rpv = v('cf-rpv');
    if (ima) p.i_ma = +ima;
    if (rpv) p.v = +rpv;
    return p;
  },
  capacitor_filter:   () => ({ freq_hz: +v('cf-cff'), resistance: +v('cf-cfr') }),
  rc_time_constant:   () => ({ r: +v('cf-rcr'), c_uf: +v('cf-rcc') }),
  capacitor_energy:   () => ({ c_uf: +v('cf-cec'), v: +v('cf-cev') }),
  power_dissipation:  () => ({ v: +v('cf-pdv'), i_ma: +v('cf-pdi') }),
  efficiency:         () => ({ p_out: +v('cf-effout'), p_in: +v('cf-effin') }),
  lc_filter:          () => ({ cutoff_hz: +v('cf-lcf'), impedance: +v('cf-lcz') }),
  voltage_follower:   () => ({}),
  charge_time:        () => ({ capacity_mah: +v('cf-ctcap'), charge_current_ma: +v('cf-ctic'), efficiency: +v('cf-cteta') }),
  motor_torque:       () => ({ power_w: +v('cf-mtpw'), rpm: +v('cf-mtrpm') }),
};

async function calcCompute() {
  const formula = document.getElementById('calc-selector')?.value;
  if (!formula) return;
  const paramsFn = _CALC_PARAMS[formula];
  if (!paramsFn) return;
  const params = paramsFn();

  const btn = document.querySelector('#panel-calc button[onclick="calcCompute()"]');
  if (btn) btn.textContent = '⏳ CALCULANDO...';

  try {
    const r = await authFetch(`${API}/calc/compute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ formula, params }),
    });
    if (!r.ok) {
      const err = await r.json();
      calcShowError(err.detail || 'Error de cálculo');
      return;
    }
    const data = await r.json();
    calcShowResult(data);
  } catch (e) {
    calcShowError(String(e));
  } finally {
    if (btn) btn.textContent = '⚡ CALCULAR';
  }
}

function calcShowResult(data) {
  const res = data.result;
  const el = document.getElementById('calc-result-body');
  if (!el) return;

  const SKIP = ['formula', 'warnings', 'std_value'];
  let html = '';

  // Valor principal
  html += `<div class="calc-kv"><span>RESULTADO</span><span>${res.value} ${res.unit}</span></div>`;
  if (res.std_value != null) {
    html += `<div class="calc-kv"><span>VALOR ESTÁNDAR</span><span>${res.std_value} ${res.unit}</span></div>`;
  }
  // Fórmula
  html += `<div class="text-[7px] opacity-40 mt-1">${escHtml(res.formula || '')}</div>`;

  // Campos extra
  if (res.extra) {
    Object.entries(res.extra).forEach(([k, val]) => {
      if (k === 'note') {
        html += `<div class="text-[7px] opacity-50 mt-1">${escHtml(String(val))}</div>`;
      } else {
        html += `<div class="calc-kv"><span>${k.toUpperCase().replace(/_/g,' ')}</span><span>${val}</span></div>`;
      }
    });
  }

  // Advertencias
  (res.warnings || []).forEach(w => {
    html += `<div class="calc-warn">⚠ ${escHtml(w)}</div>`;
  });

  // Stock match
  if (data.stock_match) {
    const s = data.stock_match;
    html += `<div class="calc-stock">📦 EN STOCK: ${escHtml(s.name)} — ${escHtml(s.value || '')} ${escHtml(s.package || '')} (qty: ${s.quantity})</div>`;
  }

  el.innerHTML = html;
  document.getElementById('calc-result')?.classList.remove('hidden');
}

function calcShowError(msg) {
  const el = document.getElementById('calc-result-body');
  if (el) el.innerHTML = `<div class="text-[#ff716c] text-[9px]">❌ ${escHtml(msg)}</div>`;
  document.getElementById('calc-result')?.classList.remove('hidden');
}
