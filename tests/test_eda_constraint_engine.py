"""Tests del Constraint Engine — cada regla con caso pass + fail."""
from __future__ import annotations

import pytest

from tools.eda.constraint_engine import (
    ValidationContext,
    rule_registry,
    run_drc,
    validate,
)
from tools.eda.ir import (
    Circuit,
    Component,
    Net,
    Node,
    Severity,
    ValidationIssue,
)


# ── Helpers de construcción ────────────────────────────────────────────────


def _circuit(components, nets):
    return Circuit(components=components, nets=nets)


def _has_code(issues, code):
    return any(i.code == code for i in issues)


def _codes(issues):
    return [i.code for i in issues]


# ── Engine plumbing ────────────────────────────────────────────────────────


def test_engine_loads_rules():
    # Forzar import de las reglas.
    validate(Circuit())
    names = {r.name for r in rule_registry.all()}
    # Algunas reglas críticas deben estar registradas.
    for n in ("NO_POWER_NET", "LED_WITHOUT_RESISTOR", "MCU_MISSING_POWER",
              "PIN_INVALID", "PIN_FORBIDDEN", "RELAY_FLYBACK",
              "AC_CONNECTOR_NO_FUSE"):
        assert n in names, f"Regla faltante: {n}"


def test_validation_context_indexing():
    c = _circuit(
        [Component(ref="U1", type="esp32"), Component(ref="R1", type="resistor")],
        [Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                 Node(ref="R1", pin="1")])],
    )
    ctx = ValidationContext.build(c)
    assert ctx.refs_in_net["VCC"] == {"U1", "R1"}
    assert ctx.nets_of_ref["U1"] == {"VCC"}
    assert "U1" in ctx.refs_by_category["mcu"]


# ── 1. NO_POWER_NET ────────────────────────────────────────────────────────


def test_no_power_net_fails_without_vcc():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [Net(name="GND", nodes=[Node(ref="U1", pin="GND")])],
    )
    issues = validate(c, rules=["NO_POWER_NET"])
    assert _has_code(issues, "NO_POWER_NET")


def test_no_power_net_passes_with_both():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["NO_POWER_NET"])
    assert not _has_code(issues, "NO_POWER_NET")


# ── 3. LED_WITHOUT_RESISTOR ────────────────────────────────────────────────


def test_led_without_resistor_fails():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="LED1", type="led"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="LED1", pin="cathode")]),
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                          Node(ref="LED1", pin="anode")]),
        ],
    )
    issues = validate(c, rules=["LED_WITHOUT_RESISTOR"])
    assert _has_code(issues, "LED_WITHOUT_RESISTOR")


def test_led_with_resistor_passes():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="LED1", type="led"),
            Component(ref="R1", type="resistor"),
        ],
        [
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO2"),
                                          Node(ref="R1", pin="1")]),
            Net(name="LED_K", nodes=[Node(ref="R1", pin="2"),
                                      Node(ref="LED1", pin="anode")]),
            Net(name="GND", nodes=[Node(ref="LED1", pin="cathode")]),
        ],
    )
    issues = validate(c, rules=["LED_WITHOUT_RESISTOR"])
    assert not _has_code(issues, "LED_WITHOUT_RESISTOR")


# ── 5. DUPLICATE_NET_NODE ──────────────────────────────────────────────────


def test_duplicate_net_node_fails():
    c = Circuit(
        components=[Component(ref="U1", type="esp32"),
                    Component(ref="R1", type="resistor")],
        nets=[
            Net(name="A", nodes=[Node(ref="R1", pin="1")]),
            Net(name="B", nodes=[Node(ref="R1", pin="1")]),
        ],
    )
    issues = validate(c, rules=["DUPLICATE_NET_NODE"])
    assert _has_code(issues, "DUPLICATE_NET_NODE")


# ── 7. NO_I2C_PULLUP ───────────────────────────────────────────────────────


def test_i2c_pullup_fails():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="DISP", type="oled_ssd1306"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="DISP", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="DISP", pin="GND")]),
            Net(name="SDA", nodes=[Node(ref="U1", pin="GPIO21"),
                                    Node(ref="DISP", pin="SDA")]),
            Net(name="SCL", nodes=[Node(ref="U1", pin="GPIO22"),
                                    Node(ref="DISP", pin="SCL")]),
        ],
    )
    issues = validate(c, rules=["NO_I2C_PULLUP"])
    assert _has_code(issues, "NO_I2C_PULLUP")


def test_i2c_pullup_passes_with_resistors():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="DISP", type="oled_ssd1306"),
            Component(ref="R1", type="resistor"),
            Component(ref="R2", type="resistor"),
        ],
        [
            Net(name="SDA", nodes=[Node(ref="U1", pin="GPIO21"),
                                    Node(ref="DISP", pin="SDA"),
                                    Node(ref="R1", pin="1")]),
            Net(name="SCL", nodes=[Node(ref="U1", pin="GPIO22"),
                                    Node(ref="DISP", pin="SCL"),
                                    Node(ref="R2", pin="1")]),
            Net(name="VCC", nodes=[Node(ref="R1", pin="2"),
                                    Node(ref="R2", pin="2"),
                                    Node(ref="U1", pin="VCC"),
                                    Node(ref="DISP", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["NO_I2C_PULLUP"])
    assert not _has_code(issues, "NO_I2C_PULLUP")


# ── 13. SIGNAL_5V_ON_3V3_GPIO ──────────────────────────────────────────────


def test_5v_on_3v3_fails():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="S1", type="hc_sr04"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="S1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="S1", pin="GND")]),
            # ECHO de HC-SR04 directo a GPIO ESP32 = problema
            Net(name="ECHO", nodes=[Node(ref="S1", pin="ECHO"),
                                     Node(ref="U1", pin="GPIO16")]),
        ],
    )
    issues = validate(c, rules=["SIGNAL_5V_ON_3V3_GPIO"])
    assert _has_code(issues, "SIGNAL_5V_ON_3V3_GPIO")


def test_5v_sensor_on_5v_mcu_passes():
    c = _circuit(
        [
            Component(ref="U1", type="arduino_uno"),
            Component(ref="S1", type="hc_sr04"),
        ],
        [
            Net(name="ECHO", nodes=[Node(ref="S1", pin="ECHO"),
                                     Node(ref="U1", pin="D2")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["SIGNAL_5V_ON_3V3_GPIO"])
    assert not _has_code(issues, "SIGNAL_5V_ON_3V3_GPIO")


# ── 14. MOTOR_DIRECT_TO_MCU ────────────────────────────────────────────────


def test_motor_direct_fails():
    c = _circuit(
        [
            Component(ref="U1", type="arduino_uno"),
            Component(ref="M1", type="motor"),
        ],
        [
            Net(name="DRIVE", nodes=[Node(ref="U1", pin="D5"),
                                      Node(ref="M1", pin="1")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="M1", pin="2")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
        ],
    )
    issues = validate(c, rules=["MOTOR_DIRECT_TO_MCU"])
    assert _has_code(issues, "MOTOR_DIRECT_TO_MCU")


def test_motor_with_driver_passes():
    c = _circuit(
        [
            Component(ref="U1", type="arduino_uno"),
            Component(ref="DRV", type="l298n"),
            Component(ref="M1", type="motor"),
        ],
        [
            Net(name="IN1", nodes=[Node(ref="U1", pin="D5"),
                                    Node(ref="DRV", pin="IN1")]),
            Net(name="MOTOR_OUT", nodes=[Node(ref="DRV", pin="OUT1"),
                                          Node(ref="M1", pin="1")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["MOTOR_DIRECT_TO_MCU"])
    assert not _has_code(issues, "MOTOR_DIRECT_TO_MCU")


# ── 15. ESP_WIFI_NO_BULK_CAP ───────────────────────────────────────────────


def test_esp_no_bulk_cap_fails():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["ESP_WIFI_NO_BULK_CAP"])
    assert _has_code(issues, "ESP_WIFI_NO_BULK_CAP")


def test_esp_with_bulk_cap_passes():
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="C1", type="capacitor_electrolytic", value="100uF"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="C1", pin="+")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="C1", pin="-")]),
        ],
    )
    issues = validate(c, rules=["ESP_WIFI_NO_BULK_CAP"])
    assert not _has_code(issues, "ESP_WIFI_NO_BULK_CAP")


# ── 16. MCU_MISSING_POWER ──────────────────────────────────────────────────


def test_mcu_missing_vcc_fails():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [Net(name="GND", nodes=[Node(ref="U1", pin="GND")])],
    )
    issues = validate(c, rules=["MCU_MISSING_POWER"])
    assert _has_code(issues, "MCU_MISSING_VCC")
    assert not _has_code(issues, "MCU_MISSING_GND")


def test_mcu_missing_gnd_fails():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")])],
    )
    issues = validate(c, rules=["MCU_MISSING_POWER"])
    assert _has_code(issues, "MCU_MISSING_GND")


# ── 17. RELAY_FLYBACK ──────────────────────────────────────────────────────


def test_relay_flyback_module_passes():
    # relay_module trae flyback integrado — no debe alertar.
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="RL1", type="relay_module"),
        ],
        [
            Net(name="CTRL", nodes=[Node(ref="U1", pin="GPIO5"),
                                     Node(ref="RL1", pin="IN")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="RL1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="RL1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["RELAY_FLYBACK"])
    assert not _has_code(issues, "RELAY_NO_FLYBACK")


def test_pure_relay_without_flyback_fails():
    c = _circuit(
        [
            Component(ref="U1", type="arduino_uno"),
            Component(ref="RL1", type="relay"),
        ],
        [
            Net(name="CTRL", nodes=[Node(ref="U1", pin="D5"),
                                     Node(ref="RL1", pin="IN")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["RELAY_FLYBACK"])
    assert _has_code(issues, "RELAY_NO_FLYBACK")


def test_relay_flyback_bad_polarity_fails():
    c = _circuit(
        [
            Component(ref="U1", type="arduino_uno"),
            Component(ref="RL1", type="relay"),
            Component(ref="D1", type="diode"),
        ],
        [
            # CTRL: el ánodo del diodo en el control (incorrecto) y el cátodo a GND.
            Net(name="CTRL", nodes=[Node(ref="U1", pin="D5"),
                                     Node(ref="RL1", pin="IN"),
                                     Node(ref="D1", pin="anode")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="D1", pin="cathode")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
        ],
    )
    issues = validate(c, rules=["RELAY_FLYBACK"])
    assert _has_code(issues, "RELAY_FLYBACK_BAD_POLARITY")


# ── 18. AC_CONNECTOR_NO_FUSE ───────────────────────────────────────────────


def test_ac_connector_no_fuse_fails():
    c = _circuit(
        [
            Component(ref="J1", type="connector", value="220VAC mains"),
            Component(ref="U1", type="esp32"),
        ],
        [
            Net(name="L", nodes=[Node(ref="J1", pin="1")]),
            Net(name="N", nodes=[Node(ref="J1", pin="2")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["AC_CONNECTOR_NO_FUSE"])
    assert _has_code(issues, "AC_CONNECTOR_NO_FUSE")


def test_ac_connector_with_fuse_inline_passes():
    c = _circuit(
        [
            Component(ref="J1", type="connector", value="220VAC mains"),
            Component(ref="F1", type="fuse"),
            Component(ref="U1", type="esp32"),
        ],
        [
            Net(name="L", nodes=[Node(ref="J1", pin="1"),
                                  Node(ref="F1", pin="1")]),
            Net(name="L_FUSED", nodes=[Node(ref="F1", pin="2")]),
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )
    issues = validate(c, rules=["AC_CONNECTOR_NO_FUSE"])
    assert not _has_code(issues, "AC_CONNECTOR_NO_FUSE")
    assert not _has_code(issues, "AC_CONNECTOR_FUSE_NOT_INLINE")


# ── 19. PIN validation (vía registry) ──────────────────────────────────────


def test_pin_invalid_arduino_nano():
    # D14 no existe en Nano (D0-D13).
    c = _circuit(
        [Component(ref="U1", type="arduino_nano")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="X", nodes=[Node(ref="U1", pin="D14")]),
        ],
    )
    issues = validate(c, rules=["PIN_INVALID"])
    assert _has_code(issues, "PIN_INVALID")


def test_pin_invalid_esp32_gpio40():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="X", nodes=[Node(ref="U1", pin="GPIO40")]),
        ],
    )
    issues = validate(c, rules=["PIN_INVALID"])
    assert _has_code(issues, "PIN_INVALID")


def test_pin_forbidden_esp32_gpio6():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="LED_DRIVE", nodes=[Node(ref="U1", pin="GPIO6")]),
        ],
    )
    issues = validate(c, rules=["PIN_FORBIDDEN"])
    assert _has_code(issues, "PIN_FORBIDDEN")


def test_pin_input_only_misuse():
    # GPIO34 en ESP32 es input-only → usarlo como CTRL es error.
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="RL1", type="relay_module"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="RELAY_CTRL", nodes=[Node(ref="U1", pin="GPIO34"),
                                            Node(ref="RL1", pin="IN")]),
        ],
    )
    issues = validate(c, rules=["PIN_INPUT_ONLY_MISUSE"])
    assert _has_code(issues, "PIN_INPUT_ONLY_MISUSE")


def test_arduino_mega_pin_range_accepted():
    # D40 existe en Mega aunque no esté listado pin a pin.
    c = _circuit(
        [Component(ref="U1", type="arduino_mega")],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="X", nodes=[Node(ref="U1", pin="D40")]),
        ],
    )
    issues = validate(c, rules=["PIN_INVALID"])
    assert not _has_code(issues, "PIN_INVALID")


# ── run_drc API compat ─────────────────────────────────────────────────────


def test_run_drc_returns_dict_shape():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [Net(name="GND", nodes=[Node(ref="U1", pin="GND")])],
    )
    out = run_drc(c)
    assert "issues" in out
    assert "errors" in out
    assert "warnings" in out
    assert "summary" in out
    assert any(i["code"] == "MCU_MISSING_VCC" for i in out["errors"])


def test_run_drc_clean_circuit():
    # ESP32 con VCC, GND, bulk cap, todo OK → debería ser "DRC OK"
    c = _circuit(
        [
            Component(ref="U1", type="esp32"),
            Component(ref="C1", type="capacitor_electrolytic", value="100uF"),
            Component(ref="C2", type="capacitor", value="100nF"),
        ],
        [
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC"),
                                    Node(ref="C1", pin="+"),
                                    Node(ref="C2", pin="1")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND"),
                                    Node(ref="C1", pin="-"),
                                    Node(ref="C2", pin="2")]),
        ],
    )
    out = run_drc(c)
    # No deberían haber errores estructurales.
    error_codes = {i["code"] for i in out["errors"]}
    for crit in ("NO_POWER_NET", "MCU_MISSING_VCC", "MCU_MISSING_GND",
                 "ESP_WIFI_NO_BULK_CAP", "PIN_INVALID", "PIN_FORBIDDEN"):
        assert crit not in error_codes


# ── ValidationIssue stamping de rule ───────────────────────────────────────


def test_issue_carries_rule_name():
    c = _circuit(
        [Component(ref="U1", type="esp32")],
        [Net(name="GND", nodes=[Node(ref="U1", pin="GND")])],
    )
    issues = validate(c, rules=["NO_POWER_NET"])
    assert any(i.rule == "NO_POWER_NET" for i in issues)
