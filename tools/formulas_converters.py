# tools/formulas_converters.py
# Fórmulas de fuentes conmutadas y transformadores.

from tools.formulas_basic import _nearest_e24, _result


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
