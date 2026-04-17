# tools/formulas_power.py
# Fórmulas de potencia y disipación térmica.

from tools.formulas_basic import _nearest_fuse, _result


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
