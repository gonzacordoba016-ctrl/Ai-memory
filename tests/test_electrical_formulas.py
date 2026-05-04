import math
import pytest

from tools.formulas_basic import ohms_law, resistor_for_led, resistor_voltage_divider, resistor_power
from tools.formulas_rc import capacitor_filter, rc_time_constant, capacitor_energy, low_pass_rc, high_pass_rc, lc_filter
from tools.formulas_power import power_dissipation, heat_sink_required, efficiency, fuse_rating
from tools.formulas_converters import buck_converter, boost_converter, transformer_turns_ratio
from tools.formulas_opamp import inverting_amp, non_inverting_amp, voltage_follower
from tools.formulas_drives import battery_autonomy, charge_time, motor_power, vfd_frequency_for_rpm, motor_torque


# ── Helpers ───────────────────────────────────────────────────────────────────

def _val(result):
    return result["value"]


# ── formulas_basic ────────────────────────────────────────────────────────────

def test_ohms_law_voltage():
    r = ohms_law(i_ma=10, r=1000)
    assert abs(_val(r) - 10.0) < 0.01
    assert r["unit"] == "V"

def test_ohms_law_current():
    r = ohms_law(v=5, r=500)
    assert abs(_val(r) - 10.0) < 0.01
    assert r["unit"] == "mA"

def test_ohms_law_resistance():
    r = ohms_law(v=5, i_ma=10)
    assert abs(_val(r) - 500.0) < 0.1
    assert r["unit"] == "Ω"

def test_resistor_for_led():
    r = resistor_for_led(vcc=5.0, vled=2.0, iled_ma=20)
    assert abs(_val(r) - 150.0) < 1.0
    assert r["unit"] == "Ω"

def test_resistor_voltage_divider():
    r = resistor_voltage_divider(vin=10.0, vout=5.0, r1=1000)
    assert abs(_val(r) - 1000.0) < 1.0

def test_resistor_power_from_current():
    r = resistor_power(r=100, i_ma=100)
    assert abs(_val(r) - 1.0) < 0.001
    assert r["unit"] == "W"

def test_resistor_power_from_voltage():
    r = resistor_power(r=100, v=10)
    assert abs(_val(r) - 1.0) < 0.001


# ── formulas_rc ───────────────────────────────────────────────────────────────

def test_capacitor_filter():
    r = capacitor_filter(freq_hz=1000, resistance=1000)
    expected = 1e6 / (2 * math.pi * 1000 * 1000)
    assert abs(_val(r) - expected) < 0.001

def test_rc_time_constant():
    r = rc_time_constant(r=1000, c_uf=100)
    assert abs(_val(r) - 100.0) < 0.01
    assert r["unit"] == "ms"

def test_capacitor_energy():
    r = capacitor_energy(c_uf=1000, v=10)
    assert abs(_val(r) - 50.0) < 0.01
    assert r["unit"] == "mJ"

def test_low_pass_rc():
    r = low_pass_rc(cutoff_hz=1000, r=1000)
    assert _val(r) > 0
    assert r["unit"] == "µF"

def test_high_pass_rc():
    r = high_pass_rc(cutoff_hz=1000, c_uf=0.159)
    assert _val(r) > 0
    assert r["unit"] == "Ω"

def test_lc_filter():
    r = lc_filter(cutoff_hz=1000)
    assert _val(r) > 0
    assert r["unit"] == "µH"


# ── formulas_power ────────────────────────────────────────────────────────────

def test_power_dissipation():
    r = power_dissipation(v=5.0, i_ma=200)
    assert abs(_val(r) - 1.0) < 0.001
    assert r["unit"] == "W"

def test_heat_sink_required():
    r = heat_sink_required(p_w=10)
    assert _val(r) >= 0
    assert r["unit"] == "°C/W"

def test_efficiency():
    r = efficiency(p_out=80, p_in=100)
    assert abs(_val(r) - 80.0) < 0.01
    assert r["unit"] == "%"

def test_efficiency_zero_input():
    r = efficiency(p_out=10, p_in=0)
    assert _val(r) == 0

def test_fuse_rating():
    r = fuse_rating(i_max=8.0)
    assert _val(r) == pytest.approx(10.0, rel=0.01)
    assert r["unit"] == "A"


# ── formulas_converters ───────────────────────────────────────────────────────

def test_buck_converter():
    r = buck_converter(vin=12, vout=5, iout=1, freq_khz=100)
    assert "inductor_uh" in r["extra"]
    assert r["extra"]["duty_cycle"] == pytest.approx(5 / 12, rel=0.01)

def test_boost_converter():
    r = boost_converter(vin=5, vout=12, iout=0.5, freq_khz=100)
    assert "inductor_uh" in r["extra"]

def test_transformer_turns_ratio():
    r = transformer_turns_ratio(vp=220, vs=12)
    assert abs(_val(r) - (220 / 12)) < 0.1


# ── formulas_opamp ────────────────────────────────────────────────────────────

def test_inverting_amp():
    r = inverting_amp(r_in=1000, r_feedback=10000)
    assert abs(_val(r) - (-10.0)) < 0.01

def test_non_inverting_amp():
    r = non_inverting_amp(r1=1000, r2=9000)
    assert abs(_val(r) - 10.0) < 0.01

def test_voltage_follower():
    r = voltage_follower()
    assert _val(r) == 1


# ── formulas_drives ───────────────────────────────────────────────────────────

def test_battery_autonomy():
    r = battery_autonomy(capacity_mah=2000, current_ma=200)
    assert abs(_val(r) - 10.0) < 0.1
    assert r["unit"] == "h"

def test_charge_time():
    r = charge_time(capacity_mah=2000, charge_current_ma=500)
    assert _val(r) > 0

def test_motor_power():
    r = motor_power(voltage=24, current=5)
    assert _val(r) > 0
    assert r["unit"] == "W"

def test_vfd_frequency_for_rpm():
    r = vfd_frequency_for_rpm(rpm=1500, poles=4)
    assert abs(_val(r) - 50.0) < 0.1
    assert r["unit"] == "Hz"

def test_motor_torque():
    r = motor_torque(power_w=1000, rpm=1000)
    assert _val(r) > 0
    assert r["unit"] == "N·m"
