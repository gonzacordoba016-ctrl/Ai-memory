# tools/electrical_formulas.py
#
# Re-export module — agrupa todas las fórmulas eléctricas en FORMULA_REGISTRY.
# Las implementaciones viven en los módulos de categoría:
#   formulas_basic.py      — ohms_law, resistor_*
#   formulas_rc.py         — capacitor_*, rc_time_constant, low/high_pass_rc, lc_filter
#   formulas_power.py      — power_dissipation, heat_sink_required, efficiency, fuse_rating
#   formulas_converters.py — buck_converter, boost_converter, transformer_turns_ratio
#   formulas_opamp.py      — inverting_amp, non_inverting_amp, voltage_follower
#   formulas_drives.py     — battery_autonomy, charge_time, motor_*, vfd_frequency_for_rpm

from tools.formulas_basic import (
    ohms_law,
    resistor_for_led,
    resistor_voltage_divider,
    resistor_power,
    _E24, _FUSE_STD, _nearest_e24, _nearest_fuse, _result,
)
from tools.formulas_rc import (
    capacitor_filter,
    rc_time_constant,
    capacitor_energy,
    low_pass_rc,
    high_pass_rc,
    lc_filter,
)
from tools.formulas_power import (
    power_dissipation,
    heat_sink_required,
    efficiency,
    fuse_rating,
)
from tools.formulas_converters import (
    buck_converter,
    boost_converter,
    transformer_turns_ratio,
)
from tools.formulas_opamp import (
    inverting_amp,
    non_inverting_amp,
    voltage_follower,
)
from tools.formulas_drives import (
    battery_autonomy,
    charge_time,
    motor_power,
    vfd_frequency_for_rpm,
    motor_torque,
)

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
