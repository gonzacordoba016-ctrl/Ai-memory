# tools/formulas_drives.py
# Fórmulas de baterías y motores.

import math
from tools.formulas_basic import _result


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
