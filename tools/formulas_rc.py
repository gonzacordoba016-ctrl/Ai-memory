# tools/formulas_rc.py
# Fórmulas de capacitores y filtros RC/LC.

import math
from tools.formulas_basic import _nearest_e24, _result


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
