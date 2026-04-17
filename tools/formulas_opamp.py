# tools/formulas_opamp.py
# Fórmulas de amplificadores operacionales.

import math
from tools.formulas_basic import _result


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
