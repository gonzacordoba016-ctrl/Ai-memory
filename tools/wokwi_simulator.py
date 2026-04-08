# tools/wokwi_simulator.py
#
# Generador de simulaciones Wokwi para Stratum.
#
# Convierte el netlist interno (circuit_designs) al formato diagram.json de Wokwi
# y genera una URL de simulación o guarda el archivo para usar con wokwi-cli.
#
# Uso:
#   from tools.wokwi_simulator import generate_wokwi_diagram, get_simulation_url
#
#   diagram = generate_wokwi_diagram(circuit_data)
#   result  = get_simulation_url(diagram)

import json
import subprocess
import tempfile
import os
from pathlib import Path
from core.logger import logger

# ── Mapeo componentes Stratum → tipos Wokwi ────────────────────────────────────

WOKWI_TYPE_MAP: dict[str, str] = {
    "arduino_uno":     "wokwi-arduino-uno",
    "arduino_nano":    "wokwi-arduino-nano",
    "esp32":           "wokwi-esp32-devkit-v1",
    "esp8266":         "wokwi-esp8266",
    "raspberry_pico":  "wokwi-pi-pico",
    "led":             "wokwi-led",
    "resistor":        "wokwi-resistor",
    "capacitor":       "wokwi-capacitor",
    "button":          "wokwi-pushbutton",
    "dht22":           "wokwi-dht22",
    "dht11":           "wokwi-dht22",          # fallback — Wokwi no tiene DHT11
    "lcd_16x2":        "wokwi-lcd1602",
    "oled_ssd1306":    "wokwi-ssd1306",
    "servo_sg90":      "wokwi-servo",
    "hc_sr04":         "wokwi-hc-sr04",
    "potentiometer":   "wokwi-potentiometer",
    "buzzer":          "wokwi-buzzer",
    "mpu6050":         "wokwi-mpu6050",
    "nrf24l01":        "wokwi-nrf24l01",
    "ds18b20":         "wokwi-ds18b20",
    "bme280":          "wokwi-bme280",
    "pir":             "wokwi-pir-motion-sensor",
    "relay_5v":        "wokwi-relay-module",
    "lm35":            "wokwi-ntc-temperature-sensor",  # aproximación
    "transistor_npn":  "wokwi-npn-transistor",
    "diode":           "wokwi-diode",
    "max7219":         "wokwi-max7219-matrix",
    "rtc_ds3231":      "wokwi-ds1307",          # fallback
    "sd_card":         "wokwi-microsd-card",
    "l298n":           "wokwi-l293d",           # equivalente funcional
}

# Colores de conexión según tipo de pin
_PIN_COLORS: dict[str, str] = {
    "power":    "red",
    "GND":      "black",
    "gnd":      "black",
    "digital":  "green",
    "analog":   "orange",
    "i2c":      "blue",
    "spi":      "purple",
    "uart":     "cyan",
    "pwm":      "yellow",
    "default":  "gray",
}


# ── Generador de diagram.json ──────────────────────────────────────────────────

def generate_wokwi_diagram(circuit_data: dict) -> dict:
    """
    Convierte el netlist interno de Stratum al formato diagram.json de Wokwi.

    circuit_data es el dict retornado por CircuitDesignManager.get_design() o
    CircuitAgent.parse_circuit() — campos usados: components, nets, name.

    Retorna un dict compatible con diagram.json que puede:
      - Pegarse en wokwi.com → New Project → Upload diagram.json
      - Usarse con wokwi-cli para simulación headless
    """
    parts: list[dict] = []
    connections: list[list] = []
    seen_ids: set[str] = set()

    # Posiciones de layout automáticas (grid simple)
    col_spacing = 250
    row_spacing = 200
    col, row = 0, 0

    for comp in circuit_data.get("components", []):
        comp_id   = _safe_id(comp.get("id", comp.get("name", "comp")), seen_ids)
        comp_type = comp.get("type", "")
        wokwi_type = WOKWI_TYPE_MAP.get(comp_type, "wokwi-resistor")  # fallback seguro

        attrs: dict = {}

        # Atributos especiales según tipo
        if comp_type == "resistor":
            attrs["value"] = comp.get("value", "1000")
        elif comp_type == "led":
            attrs["color"] = comp.get("color", "red")
        elif comp_type == "capacitor":
            attrs["capacitance"] = comp.get("value", "100e-6")
        elif comp_type == "potentiometer":
            attrs["value"] = comp.get("value", "10000")
        elif comp_type == "buzzer":
            attrs["volume"] = "0.1"

        parts.append({
            "type":  wokwi_type,
            "id":    comp_id,
            "top":   row * row_spacing,
            "left":  col * col_spacing,
            "rotate": 0,
            "hide":  False,
            "attrs": attrs,
        })

        col += 1
        if col > 3:
            col = 0
            row += 1

    # Convertir nets → connections Wokwi: ["from_id:pin", "to_id:pin", "color", []]
    for net in circuit_data.get("nets", []):
        nodes = net.get("nodes", [])
        if len(nodes) < 2:
            continue

        pin_type = net.get("type", "default")
        color = _PIN_COLORS.get(pin_type, _PIN_COLORS["default"])

        # Detectar si es GND o VCC por el nombre de la net
        net_name = net.get("name", "").lower()
        if "gnd" in net_name or "ground" in net_name:
            color = "black"
        elif "vcc" in net_name or "5v" in net_name or "3v3" in net_name or "power" in net_name:
            color = "red"

        # Conectar cada par consecutivo de nodos en la net
        for i in range(len(nodes) - 1):
            src = nodes[i]
            dst = nodes[i + 1]
            src_ref = f"{_comp_id_from_node(src)}:{_pin_from_node(src)}"
            dst_ref = f"{_comp_id_from_node(dst)}:{_pin_from_node(dst)}"
            connections.append([src_ref, dst_ref, color, []])

    diagram = {
        "version":     1,
        "author":      "Stratum Hardware Memory Engine",
        "editor":      "wokwi",
        "parts":       parts,
        "connections": connections,
    }

    logger.info(
        f"[WokwiSimulator] Diagram generado: {len(parts)} partes, "
        f"{len(connections)} conexiones"
    )
    return diagram


# ── Simulación headless (wokwi-cli) ───────────────────────────────────────────

def run_wokwi_cli(
    diagram: dict,
    firmware_path: str = "",
    timeout: int = 10,
) -> dict:
    """
    Intenta correr wokwi-cli con el diagram.json generado.

    Requiere `wokwi-cli` instalado y una API key en WOKWI_CLI_TOKEN.
    Si no está disponible retorna status='unavailable' sin error fatal.

    Args:
        diagram:       Dict diagram.json generado por generate_wokwi_diagram()
        firmware_path: Ruta al .elf o .hex compilado (opcional)
        timeout:       Segundos máximos de simulación

    Returns:
        {
          "status":       "ok" | "error" | "unavailable",
          "output":       str,       # salida serial de la simulación
          "diagram_json": dict,
          "cli_available": bool,
        }
    """
    # Verificar si wokwi-cli existe
    cli_available = _is_wokwi_cli_available()

    if not cli_available:
        logger.info("[WokwiSimulator] wokwi-cli no encontrado — retornando diagram.json")
        return {
            "status":        "unavailable",
            "output":        "",
            "diagram_json":  diagram,
            "cli_available": False,
            "message": (
                "wokwi-cli no está instalado. Podés cargar el diagram.json en "
                "https://wokwi.com/projects/new para simular en el navegador."
            ),
        }

    token = os.getenv("WOKWI_CLI_TOKEN", "")
    if not token:
        return {
            "status":        "unavailable",
            "output":        "",
            "diagram_json":  diagram,
            "cli_available": True,
            "message": "WOKWI_CLI_TOKEN no configurado en .env",
        }

    # Escribir diagram.json a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        diagram_path = os.path.join(tmpdir, "diagram.json")
        with open(diagram_path, "w", encoding="utf-8") as f:
            json.dump(diagram, f, ensure_ascii=False, indent=2)

        cmd = ["wokwi-cli", "--diagram-file", diagram_path, "--timeout", str(timeout * 1000)]
        if firmware_path and os.path.exists(firmware_path):
            cmd += ["--elf", firmware_path]

        env = dict(os.environ, WOKWI_CLI_TOKEN=token)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout + 5, env=env,
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
            logger.info(f"[WokwiSimulator] CLI exit={result.returncode}")
            return {
                "status":        "ok" if success else "error",
                "output":        output,
                "diagram_json":  diagram,
                "cli_available": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "status":        "error",
                "output":        "Simulación excedió el timeout",
                "diagram_json":  diagram,
                "cli_available": True,
            }
        except Exception as e:
            logger.error(f"[WokwiSimulator] Error en CLI: {e}")
            return {
                "status":        "error",
                "output":        str(e),
                "diagram_json":  diagram,
                "cli_available": True,
            }


def get_simulation_url(circuit_name: str = "stratum-circuit") -> str:
    """
    Retorna la URL base de Wokwi para crear un nuevo proyecto.
    El usuario puede cargar el diagram.json descargado desde el endpoint.
    """
    return "https://wokwi.com/projects/new"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_id(raw: str, seen: set) -> str:
    """Genera un ID único y compatible con Wokwi (sin espacios ni chars especiales)."""
    base = raw.lower().replace(" ", "_").replace("-", "_")
    cand = base
    n = 1
    while cand in seen:
        cand = f"{base}_{n}"
        n += 1
    seen.add(cand)
    return cand


def _comp_id_from_node(node: dict | str) -> str:
    """Extrae el comp_id de un nodo de net."""
    if isinstance(node, dict):
        return node.get("component", "").lower().replace(" ", "_").replace("-", "_")
    # formato "comp_id.pin"
    return str(node).split(".")[0]


def _pin_from_node(node: dict | str) -> str:
    """Extrae el pin de un nodo de net."""
    if isinstance(node, dict):
        return node.get("pin", "1")
    parts = str(node).split(".")
    return parts[1] if len(parts) > 1 else "1"


def _is_wokwi_cli_available() -> bool:
    try:
        subprocess.run(
            ["wokwi-cli", "--version"],
            capture_output=True, timeout=3,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
