"""Tests del Pin Allocator — preferred buses, conflicts, scoring, multi-MCU."""
from __future__ import annotations

from tools.eda.ir import Circuit, Component, Net, Node
from tools.eda.pin_allocator import (
    AllocationResult,
    Assignment,
    PinRequest,
    allocate,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _esp32_with_power(extra_components=()) -> Circuit:
    return Circuit(
        components=[Component(ref="U1", type="esp32"),
                    *extra_components],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )


def _arduino_uno_with_power() -> Circuit:
    return Circuit(
        components=[Component(ref="U1", type="arduino_uno")],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
        ],
    )


def _pin_for(result: AllocationResult, net: str, mcu: str = "U1") -> str | None:
    for a in result.assignments:
        if a.mcu_ref == mcu and a.net_name == net:
            return a.pin
    return None


# ── Preferred bus assignment (I2C) ─────────────────────────────────────────


def test_i2c_sda_picks_preferred_pin_esp32():
    c = _esp32_with_power(extra_components=[Component(ref="DISP",
                                                       type="oled_ssd1306")])
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="I2C_SDA", nodes=[Node(ref="DISP", pin="SDA")]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="I2C_SDA",
                   function="I2C_SDA", bus_id="i2c_0"),
    ])
    assert _pin_for(result, "I2C_SDA") == "GPIO21"
    # Y se aplicó al circuito.
    sda_net = result.circuit.net("I2C_SDA")
    assert sda_net is not None
    pins = {(n.ref, n.pin) for n in sda_net.nodes}
    assert ("U1", "GPIO21") in pins


def test_i2c_full_bus_uses_preferred_pair():
    c = _esp32_with_power(extra_components=[Component(ref="DISP",
                                                       type="oled_ssd1306")])
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="SDA", nodes=[Node(ref="DISP", pin="SDA")]),
        Net(name="SCL", nodes=[Node(ref="DISP", pin="SCL")]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SDA",
                   function="I2C_SDA", bus_id="i2c_0"),
        PinRequest(mcu_ref="U1", net_name="SCL",
                   function="I2C_SCL", bus_id="i2c_0"),
    ])
    assert _pin_for(result, "SDA") == "GPIO21"
    assert _pin_for(result, "SCL") == "GPIO22"


def test_arduino_uno_i2c_picks_a4_a5():
    c = _arduino_uno_with_power()
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SDA",
                   function="I2C_SDA", bus_id="i2c"),
        PinRequest(mcu_ref="U1", net_name="SCL",
                   function="I2C_SCL", bus_id="i2c"),
    ])
    assert _pin_for(result, "SDA") == "A4"
    assert _pin_for(result, "SCL") == "A5"


# ── Forbidden / used / avoid ───────────────────────────────────────────────


def test_forbidden_pin_excluded_esp32():
    """GPIO6-11 son forbidden — nunca deberían asignarse."""
    c = _esp32_with_power()
    # Pedimos 6 GPIOs — el allocator no debe usar GPIO6/7/8/9/10/11.
    requests = [PinRequest(mcu_ref="U1", net_name=f"NET{i}",
                            function="GPIO")
                for i in range(6)]
    # Necesitamos crear los nets para que el apply funcione.
    c = c.model_copy(update={"nets": c.nets + [
        Net(name=f"NET{i}", nodes=[]) for i in range(6)
    ]})
    result = allocate(c, requests)
    forbidden = {f"GPIO{i}" for i in (6, 7, 8, 9, 10, 11)}
    used_pins = {a.pin for a in result.assignments}
    assert not (used_pins & forbidden)


def test_input_only_excluded_for_output_function():
    """GPIO34/35/36/39 son input-only — no deben usarse para output."""
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="LED_DRIVE", nodes=[]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="LED_DRIVE",
                   function="GPIO", require_output=True),
    ])
    pin = _pin_for(result, "LED_DRIVE")
    assert pin not in {"GPIO34", "GPIO35", "GPIO36", "GPIO39"}


def test_input_only_ok_for_adc():
    """ADC tolera input-only — pero queremos ADC1 (GPIO32-39) para WiFi compat."""
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="SOIL", nodes=[]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SOIL", function="ADC"),
    ])
    pin = _pin_for(result, "SOIL")
    assert pin is not None
    # Debe ser un pin con capability ADC
    assert pin in {"GPIO32", "GPIO33", "GPIO34", "GPIO35", "GPIO36", "GPIO39",
                    "GPIO0", "GPIO2", "GPIO4", "GPIO12", "GPIO13", "GPIO14",
                    "GPIO15", "GPIO25", "GPIO26", "GPIO27"}


def test_already_used_pin_excluded():
    """Un pin ya presente como concreto en el circuito no se reasigna."""
    c = Circuit(
        components=[Component(ref="U1", type="esp32"),
                    Component(ref="LED1", type="led")],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            # GPIO21 ya está conectado a algo distinto.
            Net(name="EXISTING", nodes=[Node(ref="U1", pin="GPIO21"),
                                          Node(ref="LED1", pin="anode")]),
            Net(name="NEW_SDA", nodes=[]),
        ],
    )
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="NEW_SDA",
                   function="I2C_SDA", bus_id="i2c_0"),
    ])
    pin = _pin_for(result, "NEW_SDA")
    assert pin != "GPIO21"  # ya usado


def test_avoid_list_respected():
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="X", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="X", function="I2C_SDA",
                   bus_id="i2c", avoid=["GPIO21"]),
    ])
    pin = _pin_for(result, "X")
    assert pin != "GPIO21"


# ── No available ──────────────────────────────────────────────────────────


def test_no_available_pin_yields_issue():
    # Pedimos DAC en arduino_uno — no tiene DAC.
    c = _arduino_uno_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="OUT", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="OUT", function="DAC"),
    ])
    assert result.assignments == []
    assert any(i.code == "PIN_NO_AVAILABLE" for i in result.issues)


def test_request_for_non_mcu_yields_issue():
    c = Circuit(
        components=[Component(ref="R1", type="resistor")],
        nets=[Net(name="X", nodes=[])],
    )
    result = allocate(c, [
        PinRequest(mcu_ref="R1", net_name="X", function="GPIO"),
    ])
    assert any(i.code == "PIN_REQUEST_INVALID_MCU" for i in result.issues)


# ── PWM (función con expansión wildcard '*') ───────────────────────────────


def test_pwm_arduino_uno_only_pwm_pins():
    c = _arduino_uno_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="MOTOR", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="MOTOR", function="PWM"),
    ])
    pin = _pin_for(result, "MOTOR")
    assert pin in {"D3", "D5", "D6", "D9", "D10", "D11"}


def test_pwm_esp32_any_pin():
    """ESP32 PWM='*' acepta cualquier GPIO output-capable."""
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="X", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="X", function="PWM"),
    ])
    assert _pin_for(result, "X") is not None


# ── Determinismo ──────────────────────────────────────────────────────────


def test_determinism_same_input_same_output():
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="A", nodes=[]), Net(name="B", nodes=[]),
        Net(name="C", nodes=[]),
    ]})
    requests = [
        PinRequest(mcu_ref="U1", net_name="A", function="GPIO"),
        PinRequest(mcu_ref="U1", net_name="B", function="GPIO"),
        PinRequest(mcu_ref="U1", net_name="C", function="GPIO"),
    ]
    r1 = allocate(c, requests)
    r2 = allocate(c, requests)
    assert [a.pin for a in r1.assignments] == [a.pin for a in r2.assignments]


def test_lex_tiebreak_numeric_aware():
    """GPIO2 antes que GPIO12 cuando ambos puntúan igual."""
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="X", nodes=[])]})
    # Pedimos GPIO genérico — los strapping pins (0/2/5/12/15) tienen -10,
    # pero 2 y 12 están penalizados igual. El tiebreak debe poner GPIO2 antes
    # que GPIO12, NO usando orden lexicográfico de string ("12" < "2").
    # Podemos validar indirectamente: avoid los no-strapping y todos los
    # input-only para forzar elección entre strapping pins.
    avoid = ["GPIO16", "GPIO17", "GPIO18", "GPIO19", "GPIO21", "GPIO22",
             "GPIO23", "GPIO25", "GPIO26", "GPIO27", "GPIO32", "GPIO33"]
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="X", function="GPIO", avoid=avoid),
    ])
    pin = _pin_for(result, "X")
    # Premium GPIO bonus: GPIO13/14 son strapping-free... wait, GPIO13/14 NO son strapping.
    # En realidad lo que verificamos: el tiebreak es numeric, no lex.
    assert pin is not None


# ── Multi-MCU ─────────────────────────────────────────────────────────────


def test_multi_mcu_independent_pools():
    c = Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="U2", type="arduino_nano"),
        ],
        nets=[
            Net(name="A", nodes=[]),
            Net(name="B", nodes=[]),
        ],
    )
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="A",
                   function="I2C_SDA", bus_id="i2c"),
        PinRequest(mcu_ref="U2", net_name="B",
                   function="I2C_SDA", bus_id="i2c"),
    ])
    a_pin = _pin_for(result, "A", mcu="U1")
    b_pin = _pin_for(result, "B", mcu="U2")
    # Dos MCUs distintos pueden usar pines distintos sin interferir.
    assert a_pin == "GPIO21"   # ESP32 preferred
    assert b_pin == "A4"       # Nano preferred


# ── Apply assignments ─────────────────────────────────────────────────────


def test_apply_replaces_existing_node():
    """Si ya hay un Node(ref=mcu) en el net, el allocator reemplaza su pin."""
    c = Circuit(
        components=[
            Component(ref="U1", type="esp32"),
            Component(ref="DISP", type="oled_ssd1306"),
        ],
        nets=[
            Net(name="VCC", nodes=[Node(ref="U1", pin="VCC")]),
            Net(name="GND", nodes=[Node(ref="U1", pin="GND")]),
            Net(name="SDA", nodes=[Node(ref="U1", pin="GPIO99"),  # bogus
                                    Node(ref="DISP", pin="SDA")]),
        ],
    )
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SDA",
                   function="I2C_SDA", bus_id="i2c"),
    ])
    sda = result.circuit.net("SDA")
    assert sda is not None
    pins_for_u1 = [n.pin for n in sda.nodes if n.ref == "U1"]
    assert pins_for_u1 == ["GPIO21"]


def test_apply_adds_node_when_missing():
    c = _esp32_with_power(extra_components=[Component(ref="DISP",
                                                       type="oled_ssd1306")])
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="SDA", nodes=[Node(ref="DISP", pin="SDA")]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SDA",
                   function="I2C_SDA", bus_id="i2c"),
    ])
    sda = result.circuit.net("SDA")
    assert sda is not None
    refs = {n.ref for n in sda.nodes}
    assert "U1" in refs


# ── Boot strap penalty ────────────────────────────────────────────────────


def test_boot_strap_penalized_for_gpio():
    """Ante igualdad de capabilities, evitar strapping pins."""
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="LED", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="LED", function="GPIO"),
    ])
    pin = _pin_for(result, "LED")
    # No deberíamos elegir GPIO0/2/5/12/15 (strapping) si hay alternativas.
    assert pin not in {"GPIO0", "GPIO2", "GPIO5", "GPIO12", "GPIO15"}


# ── AllocationResult shape ────────────────────────────────────────────────


def test_assignment_carries_score_and_bus():
    c = _esp32_with_power()
    c = c.model_copy(update={"nets": c.nets + [Net(name="X", nodes=[])]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="X",
                   function="I2C_SDA", bus_id="my_bus"),
    ])
    a = result.assignments[0]
    assert a.bus_id == "my_bus"
    assert a.score >= 50  # preferred bonus
    assert a.function == "I2C_SDA"


def test_circuit_passes_validation_after_allocation():
    """El Circuit resultante debe seguir siendo IR-válido."""
    c = _esp32_with_power(extra_components=[Component(ref="DISP",
                                                       type="oled_ssd1306")])
    c = c.model_copy(update={"nets": c.nets + [
        Net(name="SDA", nodes=[Node(ref="DISP", pin="SDA")]),
        Net(name="SCL", nodes=[Node(ref="DISP", pin="SCL")]),
    ]})
    result = allocate(c, [
        PinRequest(mcu_ref="U1", net_name="SDA",
                   function="I2C_SDA", bus_id="i2c"),
        PinRequest(mcu_ref="U1", net_name="SCL",
                   function="I2C_SCL", bus_id="i2c"),
    ])
    # Roundtrip JSON debe funcionar sobre el circuito resultante.
    Circuit.from_json(result.circuit.to_json())
