# tools/formulas_basic.py
# Helpers compartidos + fórmulas básicas: ohms_law, resistor_*.

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
