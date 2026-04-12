# tools/electrical_formulas.py
#
# Librería de fórmulas de ingeniería eléctrica/electrónica para Stratum.
# Funciones puras — sin LLM, sin I/O, sin efectos secundarios.
# Cada función retorna un dict con: result, unit, formula, warnings, std_value.

import math
from typing import Any

# ─── Valores estándar E24 ────────────────────────────────────────────────────

_E24 = [
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
]

_FUSE_STD = [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.63, 0.8, 1.0, 1.25,
             1.6, 2.0, 2.5, 3.15, 4.0, 5.0, 6.3, 8.0, 10.0, 12.5, 16.0, 20.0]


def _nearest_e24(value: float) -> float:
    """Retorna el valor E24 más cercano al valor dado."""
    if value <= 0:
        return value
    decade = 10 ** math.floor(math.log10(value))
    normalized = value / decade
    nearest = min(_E24, key=lambda x: abs(x - normalized))
    return round(nearest * decade, 6)


def _nearest_fuse(value: float) -> float:
    """Retorna el fusible estándar más cercano por arriba."""
    for f in sorted(_FUSE_STD):
        if f >= value:
            return f
    return _FUSE_STD[-1]


def _result(value: Any, unit: str, formula: str,
            warnings: list[str] = None, std_value: Any = None,
            extra: dict = None) -> dict:
    out = {
        "value":     round(value, 6) if isinstance(value, float) else value,
        "unit":      unit,
        "formula":   formula,
        "warnings":  warnings or [],
        "std_value": std_value,
    }
    if extra:
        out.update(extra)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# RESISTENCIAS
# ─────────────────────────────────────────────────────────────────────────────

def resistor_for_led(vcc: float, vled: float, iled_ma: float) -> dict:
    """
    Calcula la resistencia limitadora de corriente para un LED.
    R = (Vcc - Vled) / Iled
    """
    warnings = []
    if iled_ma <= 0:
        return _result(0, "Ω", "R = (Vcc - Vled) / Iled", ["Corriente debe ser > 0"])
    if vcc <= vled:
        return _result(0, "Ω", "R = (Vcc - Vled) / Iled", ["Vcc debe ser mayor que Vled"])

    iled_a = iled_ma / 1000
    r = (vcc - vled) / iled_a
    p_mw = (vcc - vled) * iled_ma

    std = _nearest_e24(r)
    if p_mw > 250:
        warnings.append(f"Potencia en resistencia: {p_mw:.0f}mW — usá resistencia de 0.5W o más")
    if iled_ma > 30:
        warnings.append(f"Corriente alta ({iled_ma}mA) — verificar rating máximo del LED")

    return _result(r, "Ω", f"R = ({vcc}V - {vled}V) / {iled_ma}mA",
                   warnings, std_value=std,
                   extra={"power_mw": round(p_mw, 2), "std_resistor_ohm": std})


def resistor_voltage_divider(vin: float, vout: float, r1: float) -> dict:
    """
    Calcula R2 de un divisor de tensión resistivo.
    Vout = Vin × R2 / (R1 + R2)  →  R2 = R1 × Vout / (Vin - Vout)
    """
    warnings = []
    if vin <= vout:
        return _result(0, "Ω", "R2 = R1 × Vout / (Vin - Vout)", ["Vin debe ser mayor que Vout"])

    r2 = r1 * vout / (vin - vout)
    current_ma = (vin / (r1 + r2)) * 1000
    std = _nearest_e24(r2)

    if current_ma > 10:
        warnings.append(f"Corriente de polarización alta: {current_ma:.2f}mA — considerar valores más altos")
    if current_ma < 0.01:
        warnings.append("Corriente muy baja — divisor susceptible a ruido")

    return _result(r2, "Ω", f"R2 = {r1}Ω × {vout}V / ({vin}V - {vout}V)",
                   warnings, std_value=std,
                   extra={"current_ma": round(current_ma, 3), "std_r2_ohm": std})


def resistor_power(r: float, i_ma: float = None, v: float = None) -> dict:
    """
    Calcula la potencia disipada en una resistencia.
    P = I²R  o  P = V²/R
    """
    if i_ma is not None:
        i_a = i_ma / 1000
        p = i_a ** 2 * r
        formula = f"P = I² × R = ({i_ma}mA)² × {r}Ω"
    elif v is not None:
        p = v ** 2 / r
        formula = f"P = V² / R = ({v}V)² / {r}Ω"
    else:
        return _result(0, "W", "P = I²R o P = V²/R", ["Proveer corriente (i_ma) o tensión (v)"])

    warnings = []
    ratings = [0.125, 0.25, 0.5, 1.0, 2.0, 5.0]
    recommended = next((r_ for r_ in ratings if r_ >= p * 2), ratings[-1])
    warnings.append(f"Rating recomendado: {recommended}W (margen ×2)")

    return _result(p, "W", formula, warnings,
                   extra={"recommended_rating_w": recommended})


# ─────────────────────────────────────────────────────────────────────────────
# CAPACITORES
# ─────────────────────────────────────────────────────────────────────────────

def capacitor_filter(freq_hz: float, resistance: float) -> dict:
    """
    Calcula el capacitor para un filtro RC paso bajo.
    C = 1 / (2π × f × R)
    """
    if freq_hz <= 0 or resistance <= 0:
        return _result(0, "F", "C = 1/(2π·f·R)", ["Frecuencia y resistencia deben ser > 0"])

    c = 1 / (2 * math.pi * freq_hz * resistance)
    c_uf = c * 1e6
    std = _nearest_e24(c_uf)

    return _result(c_uf, "µF", f"C = 1/(2π × {freq_hz}Hz × {resistance}Ω)",
                   std_value=std,
                   extra={"std_capacitor_uf": std, "cutoff_hz": freq_hz})


def rc_time_constant(r: float, c_uf: float) -> dict:
    """
    Calcula la constante de tiempo RC.
    τ = R × C
    """
    tau_ms = r * (c_uf * 1e-6) * 1000
    return _result(tau_ms, "ms", f"τ = {r}Ω × {c_uf}µF",
                   extra={"tau_5x_ms": round(tau_ms * 5, 4),
                          "note": "5τ = tiempo de carga completa (~99.3%)"})


def capacitor_energy(c_uf: float, v: float) -> dict:
    """
    Calcula la energía almacenada en un capacitor.
    E = ½ × C × V²
    """
    e_j = 0.5 * (c_uf * 1e-6) * v ** 2
    e_mj = e_j * 1000
    warnings = []
    if e_j > 1:
        warnings.append(f"Energía alta ({e_j:.2f}J) — riesgo de quemadura si se descarga bruscamente")
    return _result(e_mj, "mJ", f"E = ½ × {c_uf}µF × ({v}V)²", warnings)


# ─────────────────────────────────────────────────────────────────────────────
# POTENCIA Y DISIPACIÓN TÉRMICA
# ─────────────────────────────────────────────────────────────────────────────

def power_dissipation(v: float, i_ma: float) -> dict:
    """
    Calcula potencia disipada. P = V × I
    """
    p = v * (i_ma / 1000)
    warnings = []
    if p > 1:
        warnings.append(f"Potencia alta ({p:.2f}W) — verificar disipación térmica")
    return _result(p, "W", f"P = {v}V × {i_ma}mA", warnings)


def heat_sink_required(p_w: float, t_ambient: float = 25,
                       theta_jc: float = 5, t_junction_max: float = 125) -> dict:
    """
    Calcula la resistencia térmica máxima del disipador necesario.
    θsa = (Tj_max - Ta) / P - θjc
    """
    warnings = []
    theta_total = (t_junction_max - t_ambient) / p_w
    theta_sa = theta_total - theta_jc

    if theta_sa <= 0:
        warnings.append("Imposible sin disipador externo — considerar otro transistor/MOSFET")
    if p_w > 50:
        warnings.append("Potencia alta — considerar refrigeración activa")

    return _result(max(theta_sa, 0), "°C/W",
                   f"θsa = ({t_junction_max}°C - {t_ambient}°C) / {p_w}W - {theta_jc}°C/W",
                   warnings,
                   extra={"theta_total_cw": round(theta_total, 3),
                          "note": f"Disipador debe tener θsa ≤ {max(theta_sa,0):.2f}°C/W"})


def efficiency(p_out: float, p_in: float) -> dict:
    """Calcula eficiencia energética. η = Pout/Pin × 100"""
    if p_in <= 0:
        return _result(0, "%", "η = Pout/Pin × 100", ["Pin debe ser > 0"])
    eta = (p_out / p_in) * 100
    p_loss = p_in - p_out
    warnings = []
    if eta < 80:
        warnings.append(f"Eficiencia baja ({eta:.1f}%) — {p_loss:.2f}W se disipan como calor")
    return _result(eta, "%", f"η = {p_out}W / {p_in}W × 100",
                   warnings, extra={"loss_w": round(p_loss, 3)})


def fuse_rating(i_max: float, safety_factor: float = 1.25) -> dict:
    """
    Recomienda el fusible estándar para una corriente máxima.
    I_fuse = I_max × factor_seguridad
    """
    i_fuse = i_max * safety_factor
    std = _nearest_fuse(i_fuse)
    warnings = []
    if std > i_max * 3:
        warnings.append("Fusible muy sobredimensionado — considerar protección adicional")
    return _result(i_fuse, "A",
                   f"I_fuse = {i_max}A × {safety_factor} (factor de seguridad)",
                   warnings, std_value=std,
                   extra={"std_fuse_a": std,
                          "note": f"Fusible estándar recomendado: {std}A"})


# ─────────────────────────────────────────────────────────────────────────────
# FUENTES CONMUTADAS
# ─────────────────────────────────────────────────────────────────────────────

def buck_converter(vin: float, vout: float, iout: float,
                   freq_khz: float, ripple_ratio: float = 0.3) -> dict:
    """
    Calcula inductor y capacitor para un convertidor BUCK.
    L = (Vin - Vout) × D / (f × ΔIL)
    C = ΔIL / (8 × f × ΔVout)
    """
    warnings = []
    if vin <= vout:
        return _result(0, "H", "BUCK: Vin debe ser > Vout", ["Vin debe ser mayor que Vout"])

    freq = freq_khz * 1000
    duty = vout / vin
    delta_il = ripple_ratio * iout
    l_h = (vin - vout) * duty / (freq * delta_il)
    l_uh = l_h * 1e6

    ripple_v = 0.01 * vout  # 1% ripple de salida
    c_f = delta_il / (8 * freq * ripple_v)
    c_uf = c_f * 1e6

    if duty > 0.9:
        warnings.append("Duty cycle > 90% — límite práctico de la mayoría de controladores")
    if l_uh < 1:
        warnings.append("Inductor < 1µH — considerar aumentar frecuencia o reducir ripple")

    return _result(l_uh, "µH",
                   f"L = (Vin-Vout)×D / (f×ΔIL) | C = ΔIL/(8×f×ΔVout)",
                   warnings,
                   extra={
                       "inductor_uh": round(l_uh, 3),
                       "capacitor_uf": round(c_uf, 3),
                       "duty_cycle": round(duty, 4),
                       "delta_il_a": round(delta_il, 4),
                       "std_inductor_uh": _nearest_e24(l_uh),
                       "std_capacitor_uf": _nearest_e24(c_uf),
                   })


def boost_converter(vin: float, vout: float, iout: float,
                    freq_khz: float, ripple_ratio: float = 0.3) -> dict:
    """
    Calcula inductor y capacitor para un convertidor BOOST.
    D = 1 - Vin/Vout
    L = Vin × D / (f × ΔIL)
    """
    warnings = []
    if vout <= vin:
        return _result(0, "H", "BOOST: Vout debe ser > Vin", ["Vout debe ser mayor que Vin"])

    freq = freq_khz * 1000
    duty = 1 - (vin / vout)
    iin = iout / (1 - duty)  # corriente de entrada
    delta_il = ripple_ratio * iin
    l_h = vin * duty / (freq * delta_il)
    l_uh = l_h * 1e6

    ripple_v = 0.01 * vout
    c_f = iout * duty / (freq * ripple_v)
    c_uf = c_f * 1e6

    if duty > 0.85:
        warnings.append("Duty cycle > 85% — boost de alta relación, considerar topología alternativa")

    return _result(l_uh, "µH",
                   f"D = 1 - Vin/Vout | L = Vin×D/(f×ΔIL)",
                   warnings,
                   extra={
                       "inductor_uh": round(l_uh, 3),
                       "capacitor_uf": round(c_uf, 3),
                       "duty_cycle": round(duty, 4),
                       "input_current_a": round(iin, 4),
                       "std_inductor_uh": _nearest_e24(l_uh),
                       "std_capacitor_uf": _nearest_e24(c_uf),
                   })


def transformer_turns_ratio(vp: float, vs: float,
                             ip: float = None, is_: float = None) -> dict:
    """
    Calcula la relación de transformación de un transformador.
    n = Vp/Vs  →  Is = Ip × n (ideal)
    """
    n = vp / vs
    extra = {"turns_ratio": round(n, 4)}
    if ip is not None:
        extra["secondary_current_a"] = round(ip / n, 4)
    if is_ is not None:
        extra["primary_current_a"] = round(is_ * n, 4)

    return _result(n, "n:1",
                   f"n = Vp/Vs = {vp}V / {vs}V",
                   extra=extra)


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS
# ─────────────────────────────────────────────────────────────────────────────

def low_pass_rc(cutoff_hz: float, r: float) -> dict:
    """Calcula C para filtro RC paso bajo. fc = 1/(2π×R×C)"""
    c_f = 1 / (2 * math.pi * cutoff_hz * r)
    c_uf = c_f * 1e6
    std = _nearest_e24(c_uf)
    return _result(c_uf, "µF", f"C = 1/(2π×{cutoff_hz}Hz×{r}Ω)",
                   std_value=std,
                   extra={"std_capacitor_uf": std, "attenuation_db_per_decade": -20})


def high_pass_rc(cutoff_hz: float, c_uf: float) -> dict:
    """Calcula R para filtro RC paso alto. fc = 1/(2π×R×C)"""
    r = 1 / (2 * math.pi * cutoff_hz * (c_uf * 1e-6))
    std = _nearest_e24(r)
    return _result(r, "Ω", f"R = 1/(2π×{cutoff_hz}Hz×{c_uf}µF)",
                   std_value=std,
                   extra={"std_resistor_ohm": std, "attenuation_db_per_decade": -20})


def lc_filter(cutoff_hz: float, impedance: float = 50) -> dict:
    """
    Calcula L y C para un filtro LC (segundo orden).
    f0 = 1/(2π√(LC))  →  L = Z/(2π×f),  C = 1/(2π×f×Z)
    """
    l_h = impedance / (2 * math.pi * cutoff_hz)
    c_f = 1 / (2 * math.pi * cutoff_hz * impedance)
    l_uh = l_h * 1e6
    c_uf = c_f * 1e6
    return _result(l_uh, "µH",
                   f"L = Z/(2π×f) | C = 1/(2π×f×Z) con Z={impedance}Ω",
                   extra={
                       "inductor_uh": round(l_uh, 4),
                       "capacitor_uf": round(c_uf, 6),
                       "attenuation_db_per_decade": -40,
                   })


# ─────────────────────────────────────────────────────────────────────────────
# AMPLIFICADORES OPERACIONALES
# ─────────────────────────────────────────────────────────────────────────────

def inverting_amp(r_in: float, r_feedback: float) -> dict:
    """Ganancia de amplificador inversor. G = -Rf/Rin"""
    gain = -(r_feedback / r_in)
    warnings = []
    if abs(gain) > 100:
        warnings.append("Ganancia > 100 — considerar dos etapas para mejor estabilidad")
    return _result(gain, "V/V", f"G = -Rf/Rin = -{r_feedback}Ω/{r_in}Ω",
                   warnings, extra={"gain_db": round(20 * math.log10(abs(gain)), 2)})


def non_inverting_amp(r1: float, r2: float) -> dict:
    """Ganancia de amplificador no inversor. G = 1 + R2/R1"""
    gain = 1 + (r2 / r1)
    warnings = []
    if gain > 100:
        warnings.append("Ganancia > 100 — considerar dos etapas")
    return _result(gain, "V/V", f"G = 1 + R2/R1 = 1 + {r2}Ω/{r1}Ω",
                   warnings, extra={"gain_db": round(20 * math.log10(gain), 2)})


def voltage_follower() -> dict:
    """Buffer / seguidor de tensión. G = 1"""
    return _result(1, "V/V", "G = 1 (buffer — alta impedancia entrada, baja salida)",
                   extra={"gain_db": 0, "note": "Ideal para aislamiento de etapas"})


# ─────────────────────────────────────────────────────────────────────────────
# BATERÍAS
# ─────────────────────────────────────────────────────────────────────────────

def battery_autonomy(capacity_mah: float, current_ma: float,
                     efficiency: float = 0.85) -> dict:
    """
    Calcula autonomía de una batería.
    t = (C × η) / I
    """
    warnings = []
    if current_ma <= 0:
        return _result(0, "h", "t = (C × η) / I", ["Corriente debe ser > 0"])
    hours = (capacity_mah * efficiency) / current_ma
    if hours < 1:
        warnings.append("Autonomía menor a 1 hora — considerar batería de mayor capacidad")
    if efficiency < 0.7:
        warnings.append("Eficiencia baja — revisar regulador de tensión")

    return _result(hours, "h",
                   f"t = ({capacity_mah}mAh × {efficiency}) / {current_ma}mA",
                   warnings,
                   extra={"hours": round(hours, 2),
                          "minutes": round(hours * 60, 1),
                          "days": round(hours / 24, 2)})


def charge_time(capacity_mah: float, charge_current_ma: float,
                efficiency: float = 0.9) -> dict:
    """
    Calcula tiempo de carga de una batería.
    t = C / (I × η)
    """
    if charge_current_ma <= 0:
        return _result(0, "h", "t = C / (I × η)", ["Corriente de carga debe ser > 0"])
    hours = capacity_mah / (charge_current_ma * efficiency)
    warnings = []
    if charge_current_ma > capacity_mah:
        warnings.append(f"Corriente de carga > capacidad/h (C-rate > 1) — riesgo de sobrecalentamiento")
    return _result(hours, "h",
                   f"t = {capacity_mah}mAh / ({charge_current_ma}mA × {efficiency})",
                   warnings,
                   extra={"hours": round(hours, 2), "minutes": round(hours * 60, 1)})


# ─────────────────────────────────────────────────────────────────────────────
# MOTORES
# ─────────────────────────────────────────────────────────────────────────────

def motor_power(voltage: float, current: float, efficiency: float = 0.85) -> dict:
    """
    Calcula potencia mecánica de un motor.
    P_mec = V × I × η
    """
    p_elec = voltage * current
    p_mec = p_elec * efficiency
    p_loss = p_elec - p_mec
    warnings = []
    if efficiency < 0.7:
        warnings.append("Eficiencia < 70% — pérdidas altas, revisar punto de operación")
    return _result(p_mec, "W",
                   f"P_mec = {voltage}V × {current}A × {efficiency}",
                   warnings,
                   extra={"electric_power_w": round(p_elec, 3),
                          "loss_w": round(p_loss, 3)})


def vfd_frequency_for_rpm(rpm: float, poles: int = 4) -> dict:
    """
    Calcula la frecuencia del VFD para una velocidad de motor AC.
    f = RPM × P / 120
    """
    freq = rpm * poles / 120
    warnings = []
    if freq > 60:
        warnings.append(f"Frecuencia {freq:.1f}Hz supera 60Hz — verificar motor para operación a sobre-velocidad")
    if freq < 5:
        warnings.append("Frecuencia muy baja — torque reducido, posibles problemas de refrigeración")
    return _result(freq, "Hz",
                   f"f = RPM × P / 120 = {rpm} × {poles} / 120",
                   warnings,
                   extra={"synchronous_rpm_at_50hz": round(50 * 120 / poles, 1),
                          "synchronous_rpm_at_60hz": round(60 * 120 / poles, 1)})


def motor_torque(power_w: float, rpm: float) -> dict:
    """
    Calcula el torque de un motor.
    T = P / ω = P × 60 / (2π × RPM)
    """
    if rpm <= 0:
        return _result(0, "N·m", "T = P×60/(2π×RPM)", ["RPM debe ser > 0"])
    torque = power_w * 60 / (2 * math.pi * rpm)
    return _result(torque, "N·m",
                   f"T = {power_w}W × 60 / (2π × {rpm}RPM)",
                   extra={"torque_kgcm": round(torque * 10.197, 3)})


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def ohms_law(v: float = None, i_ma: float = None, r: float = None) -> dict:
    """
    Ley de Ohm — calcula el parámetro faltante dado los otros dos.
    V = I × R
    """
    given = sum(x is not None for x in [v, i_ma, r])
    if given < 2:
        return _result(0, "", "V = I × R", ["Proveer al menos 2 de los 3 parámetros"])
    if v is None:
        i_a = i_ma / 1000
        res = i_a * r
        return _result(res, "V", f"V = {i_ma}mA × {r}Ω")
    elif i_ma is None:
        i_a = v / r
        return _result(i_a * 1000, "mA", f"I = {v}V / {r}Ω")
    else:
        i_a = i_ma / 1000
        res = v / i_a
        return _result(res, "Ω", f"R = {v}V / {i_ma}mA")


# ─── Registry público ─────────────────────────────────────────────────────────

FORMULA_REGISTRY = {
    "resistor_for_led":        resistor_for_led,
    "resistor_voltage_divider": resistor_voltage_divider,
    "resistor_power":          resistor_power,
    "capacitor_filter":        capacitor_filter,
    "rc_time_constant":        rc_time_constant,
    "capacitor_energy":        capacitor_energy,
    "power_dissipation":       power_dissipation,
    "heat_sink_required":      heat_sink_required,
    "efficiency":              efficiency,
    "fuse_rating":             fuse_rating,
    "buck_converter":          buck_converter,
    "boost_converter":         boost_converter,
    "transformer_turns_ratio": transformer_turns_ratio,
    "low_pass_rc":             low_pass_rc,
    "high_pass_rc":            high_pass_rc,
    "lc_filter":               lc_filter,
    "inverting_amp":           inverting_amp,
    "non_inverting_amp":       non_inverting_amp,
    "voltage_follower":        voltage_follower,
    "battery_autonomy":        battery_autonomy,
    "charge_time":             charge_time,
    "motor_power":             motor_power,
    "vfd_frequency_for_rpm":   vfd_frequency_for_rpm,
    "motor_torque":            motor_torque,
    "ohms_law":                ohms_law,
}
