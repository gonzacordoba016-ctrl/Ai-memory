# tools/state_firmware_addon.py
# Generates a C++/Arduino state-reporting addon for any firmware.
# The addon reads pins used in the circuit and sends JSON state every 500ms via Serial.
# Stratum's /ws/hardware-state WebSocket parses this stream to overlay live state
# on the circuit viewer.

from typing import Dict, Any, List, Tuple
from core.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Pin extraction from netlist
# ──────────────────────────────────────────────────────────────────────────────

def _extract_mcu_pins(circuit_data: Dict[str, Any]) -> List[Dict]:
    """
    Extract MCU pin assignments from the netlist.
    Returns list of {pin, net_name, mode, comp_type}.
    """
    mcu_types = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
                 "stm32", "rp2040", "pico", "mcu"}
    output_types = {"led", "led_rgb", "relay", "relay_module", "motor", "buzzer"}
    input_types  = {"button", "sensor", "moisture_sensor", "pir", "encoder",
                    "ultrasonic", "photoresistor"}

    # Find MCU component IDs
    mcu_ids = {c["id"] for c in circuit_data.get("components", [])
               if c.get("resolved_type", c.get("type", "")).lower() in mcu_types}

    # Build a comp_id → type map
    comp_type = {c["id"]: c.get("resolved_type", c.get("type", "generic")).lower()
                 for c in circuit_data.get("components", [])}

    pins: List[Dict] = []
    seen_pins: set = set()

    for net in circuit_data.get("nets", []):
        net_name = net.get("name", "")
        # Skip pure power nets
        if any(v in net_name.lower() for v in ("vcc", "5v", "3v3", "vin", "gnd", "ground")):
            continue

        nodes = net.get("nodes", [])
        mcu_node = None
        other_types = []

        for node in nodes:
            parts = node.split(".", 1)
            cid = parts[0]
            if cid in mcu_ids and len(parts) == 2:
                mcu_node = parts[1]  # e.g. "D13", "A0", "GPIO4"
            else:
                other_types.append(comp_type.get(cid, "generic"))

        if not mcu_node or mcu_node in seen_pins:
            continue
        seen_pins.add(mcu_node)

        # Determine mode
        is_output = any(t in output_types for t in other_types)
        is_input  = any(t in input_types for t in other_types)
        is_analog = mcu_node.upper().startswith("A") or "ADC" in mcu_node.upper()

        mode = "OUTPUT" if is_output else "INPUT"
        read_fn = "analogRead" if is_analog else "digitalRead"

        pins.append({
            "pin":      mcu_node,
            "net_name": net_name,
            "mode":     mode,
            "read_fn":  read_fn,
            "is_analog": is_analog,
            "comp_types": other_types,
        })

    return pins[:20]  # cap at 20 pins


# ──────────────────────────────────────────────────────────────────────────────
# Code generation
# ──────────────────────────────────────────────────────────────────────────────

def generate_state_addon(circuit_data: Dict[str, Any]) -> str:
    """
    Returns a C++ snippet that can be appended to any Arduino/ESP32 firmware.
    It reports pin states as JSON every 500ms via Serial.
    Example output: STATE:{"D13":1,"A0":512,"D7":0}
    """
    pins = _extract_mcu_pins(circuit_data)

    if not pins:
        return "// [Stratum] No se detectaron pines MCU en el netlist\n"

    setup_lines = []
    report_lines = []

    for p in pins:
        pin_name = p["pin"]
        # Convert friendly names to Arduino constants
        arduino_pin = _to_arduino_pin(pin_name)
        mode = p["mode"]
        read = p["read_fn"]
        net  = p["net_name"]

        if not p["is_analog"]:
            setup_lines.append(f'  pinMode({arduino_pin}, {mode});  // {net}')
        report_lines.append(
            f'  doc["{pin_name}"] = {read}({arduino_pin});  // {net}'
        )

    setup_code = "\n".join(setup_lines)
    report_code = "\n".join(report_lines)

    return f'''\
// ============================================================
// Stratum State Reporter — auto-generado por Stratum v4.2
// NO MODIFICAR — este bloque es regenerado automáticamente
// Reporta estado de pines cada 500ms via Serial (JSON)
// Usado por /ws/hardware-state para visualización en vivo
// ============================================================
#include <ArduinoJson.h>

unsigned long _stratum_last_report = 0;

void _stratumSetupPins() {{
{setup_code}
}}

void _stratumReportState() {{
  if (millis() - _stratum_last_report < 500) return;
  _stratum_last_report = millis();

  StaticJsonDocument<512> doc;
{report_code}

  Serial.print("STATE:");
  serializeJson(doc, Serial);
  Serial.println();
}}
// ============================================================
// Agregar en setup():   _stratumSetupPins();
// Agregar en loop():    _stratumReportState();
// ============================================================
'''


def generate_micropython_state_addon(circuit_data: Dict[str, Any]) -> str:
    """MicroPython version of the state reporter."""
    pins = _extract_mcu_pins(circuit_data)
    if not pins:
        return "# [Stratum] No se detectaron pines MCU\n"

    import_lines = "import json\nfrom machine import Pin, ADC\nimport time\n"
    setup_lines = []
    report_lines = []

    for p in pins:
        pin_name = p["pin"]
        var_name = f"_pin_{pin_name.lower().replace('.','_')}"
        if p["is_analog"]:
            setup_lines.append(f"{var_name} = ADC(Pin({_to_mp_pin(pin_name)}))  # {p['net_name']}")
            setup_lines.append(f"{var_name}.atten(ADC.ATTN_11DB)")
            report_lines.append(f'  state["{pin_name}"] = {var_name}.read()')
        else:
            setup_lines.append(f"{var_name} = Pin({_to_mp_pin(pin_name)}, Pin.{'OUT' if p['mode']=='OUTPUT' else 'IN'})  # {p['net_name']}")
            report_lines.append(f'  state["{pin_name}"] = {var_name}.value()')

    setup_code  = "\n".join(setup_lines)
    report_code = "\n".join(report_lines)

    return f'''\
# ============================================================
# Stratum State Reporter (MicroPython) — auto-generado
# ============================================================
{import_lines}
{setup_code}

_stratum_last = 0

def _stratum_report():
    global _stratum_last
    now = time.ticks_ms()
    if time.ticks_diff(now, _stratum_last) < 500:
        return
    _stratum_last = now
    state = {{}}
{report_code}
    print("STATE:" + json.dumps(state))
# ============================================================
# Llamar _stratum_report() en el loop principal
# ============================================================
'''


def _to_arduino_pin(name: str) -> str:
    """Map friendly pin names to Arduino constants."""
    mapping = {
        "SDA": "SDA", "SCL": "SCL", "TX": "0", "RX": "1",
        "MOSI": "MOSI", "MISO": "MISO", "SCK": "SCK", "SS": "SS",
        "RST": "RESET", "GND": "GND", "5V": "5",
        "3V3": "3", "VIN": "A0",
    }
    if name in mapping:
        return mapping[name]
    # D13 → 13
    if name.upper().startswith("D") and name[1:].isdigit():
        return name[1:]
    # GPIO4 → 4
    if name.upper().startswith("GPIO") and name[4:].isdigit():
        return name[4:]
    # A0, A1... → A0, A1...
    if name.upper().startswith("A") and name[1:].isdigit():
        return name.upper()
    return name


def _to_mp_pin(name: str) -> str:
    """Map friendly pin names to MicroPython Pin numbers."""
    if name.upper().startswith("GPIO") and name[4:].isdigit():
        return name[4:]
    if name.upper().startswith("D") and name[1:].isdigit():
        return name[1:]
    if name.upper().startswith("A") and name[1:].isdigit():
        return name.upper()
    return f'"{name}"'
