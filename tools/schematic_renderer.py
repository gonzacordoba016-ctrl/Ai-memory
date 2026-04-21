# tools/schematic_renderer.py

import svgwrite
from typing import Dict, Any, List, Tuple, Optional
import math
from core.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Net color palette
# ──────────────────────────────────────────────────────────────────────────────

def _net_color(net_name: str) -> str:
    name = net_name.lower()
    if any(v in name for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd", "power")):
        return "#ff4444"
    if any(v in name for v in ("gnd", "ground", "0v", "agnd", "dgnd")):
        return "#888888"
    if any(v in name for v in ("sda", "scl", "i2c")):
        return "#44ff88"
    if any(v in name for v in ("spi", "mosi", "miso", "sck", "cs")):
        return "#ff88ff"
    if any(v in name for v in ("tx", "rx", "uart", "serial")):
        return "#ffaa44"
    if any(v in name for v in ("pwm", "motor", "servo")):
        return "#ff8833"
    if any(v in name for v in ("data", "dat", "sig", "out", "in")):
        return "#44aaff"
    # Rotate through pleasant colors for the rest
    palette = ["#55ccff", "#ffcc55", "#cc55ff", "#55ffcc", "#ff55cc", "#ccff55"]
    return palette[hash(net_name) % len(palette)]


# ──────────────────────────────────────────────────────────────────────────────
# Component functional groups — for layout
# ──────────────────────────────────────────────────────────────────────────────

_MCU_TYPES = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
              "stm32", "rp2040", "pico", "attiny", "mcu"}
_POWER_TYPES = {"capacitor", "regulator", "ldo", "dc_dc", "battery", "fuse", "diode",
                "1n4007", "1n5819", "zener"}
_INPUT_TYPES = {"button", "sensor", "moisture_sensor", "temperature_sensor",
                "dht22", "dht11", "bmp280", "ultrasonic", "pir", "encoder",
                "potentiometer", "photoresistor", "microphone"}
_OUTPUT_TYPES = {"led", "led_rgb", "relay", "relay_module", "motor", "servo",
                 "buzzer", "display", "oled", "lcd", "neopixel", "motor_driver"}
_COMM_TYPES = {"wifi_module", "bluetooth", "lora", "zigbee", "can_transceiver",
               "rs485", "ethernet"}


def _comp_group(comp: Dict) -> str:
    t = comp.get("resolved_type", comp.get("type", "generic")).lower()
    if t in _MCU_TYPES:    return "mcu"
    if t in _POWER_TYPES:  return "power"
    if t in _INPUT_TYPES:  return "input"
    if t in _OUTPUT_TYPES: return "output"
    if t in _COMM_TYPES:   return "comm"
    return "misc"


# ──────────────────────────────────────────────────────────────────────────────
# Functional layout algorithm
# ──────────────────────────────────────────────────────────────────────────────

def _layout_components(components: List[Dict], width: int, height: int,
                       saved: Dict[str, Dict]) -> Dict[str, Tuple[int, int]]:
    """
    Assigns (x, y) to each component using functional grouping:
    - MCU: center
    - Inputs: left column
    - Outputs: right column
    - Power/decoupling: top strip
    - Comm modules: top-right
    - Misc: bottom row
    Returns dict {comp_id: (x, y)}.
    Respects saved positions for any component that already has one.
    """
    positions: Dict[str, Tuple[int, int]] = {}

    # Apply saved positions first
    for comp_id, pos in saved.items():
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            positions[comp_id] = (int(pos["x"]), int(pos["y"]))

    # Group remaining
    groups: Dict[str, List[Dict]] = {g: [] for g in ("mcu", "input", "output", "power", "comm", "misc")}
    for comp in components:
        if comp["id"] not in positions:
            groups[_comp_group(comp)].append(comp)

    cx, cy = width // 2, height // 2
    spacing_x, spacing_y = 120, 80

    # MCU — center
    for i, comp in enumerate(groups["mcu"]):
        positions[comp["id"]] = (cx + i * spacing_x, cy)

    # Inputs — left column
    start_y = cy - (len(groups["input"]) - 1) * spacing_y // 2
    for i, comp in enumerate(groups["input"]):
        positions[comp["id"]] = (max(90, cx - 220 - (i % 2) * 60), start_y + i * spacing_y)

    # Outputs — right column
    start_y = cy - (len(groups["output"]) - 1) * spacing_y // 2
    for i, comp in enumerate(groups["output"]):
        positions[comp["id"]] = (min(width - 90, cx + 220 + (i % 2) * 60), start_y + i * spacing_y)

    # Power/decoupling — top strip
    for i, comp in enumerate(groups["power"]):
        positions[comp["id"]] = (100 + i * 90, 70)

    # Comm modules — top right
    for i, comp in enumerate(groups["comm"]):
        positions[comp["id"]] = (width - 100 - i * 100, 70)

    # Misc — bottom row
    for i, comp in enumerate(groups["misc"]):
        positions[comp["id"]] = (100 + i * 90, height - 70)

    return positions


# ──────────────────────────────────────────────────────────────────────────────
# Orthogonal wire routing
# ──────────────────────────────────────────────────────────────────────────────

def _route_orthogonal(p1: Tuple[int, int], p2: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Returns a 3-point L-shaped path from p1 to p2 (horizontal first, then vertical)."""
    x1, y1 = p1
    x2, y2 = p2
    mid_x = (x1 + x2) // 2
    return [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]


# ──────────────────────────────────────────────────────────────────────────────
# Component symbol drawers
# ──────────────────────────────────────────────────────────────────────────────

class SchematicRenderer:
    def __init__(self):
        pass

    def render_schematic_svg(self, circuit_data: Dict[str, Any],
                              width: int = 1000, height: int = 700) -> str:
        try:
            dwg = svgwrite.Drawing(size=(width, height),
                                   viewBox=f"0 0 {width} {height}")

            # Background grid
            self._draw_background(dwg, width, height)

            # Title block
            self._draw_title_block(dwg, circuit_data, width, height)

            # Compute positions
            saved = circuit_data.get("positions", {})
            components = circuit_data.get("components", [])
            positions = _layout_components(components, width, height - 80, saved)

            # Draw connections first (behind components)
            nets = circuit_data.get("nets", [])
            drawn_nets = self._draw_connections(dwg, nets, positions)

            # Draw components
            for comp in components:
                pos = positions.get(comp["id"], (width // 2, height // 2))
                self._draw_component(dwg, comp, pos)

            # Net legend
            self._draw_legend(dwg, nets, width, height)

            # Power / DRC annotations
            self._draw_annotations(dwg, circuit_data, width, height)

            return dwg.tostring()

        except Exception as e:
            logger.error(f"Error renderizando esquemático: {e}")
            err = svgwrite.Drawing(size=(800, 100))
            err.add(err.rect(insert=(0, 0), size=(800, 100), fill="#1e1e1e"))
            err.add(err.text(f"Error: {e}", insert=(10, 50), fill="red",
                             font_size=16, font_family="monospace"))
            return err.tostring()

    # ──────────────────────────────────────────────────────────────────────────
    # Background
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_background(self, dwg, width: int, height: int):
        dwg.add(dwg.rect(insert=(0, 0), size=(width, height), fill="#0d1117"))
        # Subtle grid dots
        for gx in range(0, width, 20):
            for gy in range(0, height - 80, 20):
                dwg.add(dwg.circle(center=(gx, gy), r=0.8, fill="#1c2333"))

    # ──────────────────────────────────────────────────────────────────────────
    # Title block
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_title_block(self, dwg, circuit_data: Dict, width: int, height: int):
        y_base = height - 75
        dwg.add(dwg.rect(insert=(0, y_base), size=(width, 75),
                         fill="#161b22", stroke="#30363d", stroke_width=1))
        dwg.add(dwg.line(start=(0, y_base), end=(width, y_base),
                         stroke="#00d4ff", stroke_width=1.5))

        name = circuit_data.get("name", "Sin nombre")
        desc = circuit_data.get("description", "")
        power = circuit_data.get("power", "")
        domain = circuit_data.get("detected_domain", "")
        mcu = circuit_data.get("selected_mcu", "")
        warnings = circuit_data.get("warnings", [])

        dwg.add(dwg.text(name, insert=(20, y_base + 22),
                         font_size=16, fill="#e6edf3", font_family="Arial",
                         font_weight="bold"))
        dwg.add(dwg.text(desc[:120], insert=(20, y_base + 42),
                         font_size=11, fill="#8b949e", font_family="Arial"))

        meta = f"MCU: {mcu}  |  Power: {power}  |  Dominio: {domain}"
        dwg.add(dwg.text(meta, insert=(20, y_base + 60),
                         font_size=10, fill="#58a6ff", font_family="monospace"))

        # Warning badge
        if warnings:
            badge_x = width - 220
            dwg.add(dwg.rect(insert=(badge_x, y_base + 8), size=(200, 24),
                             fill="#3d1f00", stroke="#ff8c00", stroke_width=1, rx=4))
            dwg.add(dwg.text(f"⚠ {len(warnings)} advertencia(s)",
                             insert=(badge_x + 10, y_base + 24),
                             font_size=11, fill="#ff8c00", font_family="Arial"))

        # DRC badge
        drc = circuit_data.get("drc", {})
        if drc:
            passed = drc.get("passed", True)
            badge_x = width - 220
            badge_y = y_base + 38
            color = "#1f3d1f" if passed else "#3d1f1f"
            border = "#3fb950" if passed else "#f85149"
            label = "✓ DRC OK" if passed else f"✗ DRC: {drc.get('counts', {}).get('errors', '?')} errores"
            dwg.add(dwg.rect(insert=(badge_x, badge_y), size=(200, 24),
                             fill=color, stroke=border, stroke_width=1, rx=4))
            dwg.add(dwg.text(label, insert=(badge_x + 10, badge_y + 16),
                             font_size=11, fill=border, font_family="Arial"))

    # ──────────────────────────────────────────────────────────────────────────
    # Connection routing
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_connections(self, dwg, nets: List[Dict],
                          positions: Dict[str, Tuple[int, int]]) -> int:
        drawn = 0
        for net in nets:
            color = _net_color(net["name"])
            nodes = net.get("nodes", [])
            coords = []
            for node in nodes:
                comp_id = node.split(".")[0]
                if comp_id in positions:
                    coords.append(positions[comp_id])

            if len(coords) < 2:
                continue

            # Draw orthogonal segments between consecutive connected points
            for i in range(len(coords) - 1):
                path = _route_orthogonal(coords[i], coords[i + 1])
                for j in range(len(path) - 1):
                    dwg.add(dwg.line(start=path[j], end=path[j + 1],
                                     stroke=color, stroke_width=1.5,
                                     stroke_opacity=0.7))

            # Junction dots
            for pt in coords:
                dwg.add(dwg.circle(center=pt, r=3, fill=color, fill_opacity=0.8))

            # Net label at midpoint of first segment
            if coords:
                lx = (coords[0][0] + coords[-1][0]) // 2
                ly = min(c[1] for c in coords) - 10
                bg = dwg.rect(insert=(lx - 2, ly - 12),
                              size=(len(net["name"]) * 6 + 4, 14),
                              fill="#161b22", fill_opacity=0.85, rx=2)
                dwg.add(bg)
                dwg.add(dwg.text(net["name"], insert=(lx, ly),
                                 font_size=9, fill=color, font_family="monospace"))
            drawn += 1
        return drawn

    # ──────────────────────────────────────────────────────────────────────────
    # Component drawing dispatcher
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_component(self, dwg, comp: Dict, pos: Tuple[int, int]):
        x, y = pos
        t = comp.get("resolved_type", comp.get("type", "generic")).lower()

        dispatch = {
            "resistor":         self._sym_resistor,
            "led":              self._sym_led,
            "led_rgb":          self._sym_led,
            "capacitor":        self._sym_capacitor,
            "button":           self._sym_button,
            "arduino_uno":      self._sym_mcu,
            "arduino_nano":     self._sym_mcu,
            "arduino_mega":     self._sym_mcu,
            "esp32":            self._sym_mcu,
            "esp8266":          self._sym_mcu,
            "stm32":            self._sym_mcu,
            "pico":             self._sym_mcu,
            "relay":            self._sym_relay,
            "relay_module":     self._sym_relay,
            "mosfet":           self._sym_mosfet,
            "mosfet_n":         self._sym_mosfet,
            "transistor":       self._sym_transistor,
            "diode":            self._sym_diode,
            "motor":            self._sym_motor,
            "motor_driver":     self._sym_ic_generic,
            "buzzer":           self._sym_buzzer,
            "sensor":           self._sym_sensor,
            "display":          self._sym_display,
            "oled":             self._sym_display,
            "lcd":              self._sym_display,
        }
        draw_fn = dispatch.get(t, self._sym_generic)
        draw_fn(dwg, x, y, comp)

        # Reference label below component
        ref = comp.get("id", "?")
        val = comp.get("value", "")
        unit = comp.get("unit", "")
        label = f"{ref}" + (f" {val}{unit}" if val else "")
        dwg.add(dwg.text(label, insert=(x, y + 42),
                         font_size=9, fill="#c9d1d9",
                         font_family="monospace", text_anchor="middle"))

        # Component name (small, below ref)
        name = comp.get("name", "")
        if name and name != ref:
            dwg.add(dwg.text(name[:22], insert=(x, y + 54),
                             font_size=8, fill="#58a6ff",
                             font_family="Arial", text_anchor="middle"))

    # ──────────────────────────────────────────────────────────────────────────
    # Symbol primitives
    # ──────────────────────────────────────────────────────────────────────────

    def _sym_resistor(self, dwg, x, y, comp):
        """IEC rectangle resistor symbol."""
        W, H = 32, 14
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="none", stroke="#e6edf3", stroke_width=1.5))
        # Lead lines
        dwg.add(dwg.line(start=(x - W//2 - 15, y), end=(x - W//2, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + W//2, y), end=(x + W//2 + 15, y),
                         stroke="#e6edf3", stroke_width=1.5))
        # Value inside
        val = f"{comp.get('value','')}{comp.get('unit','Ω')}"
        dwg.add(dwg.text(val, insert=(x, y + 4),
                         font_size=8, fill="#ffa500",
                         font_family="monospace", text_anchor="middle"))

    def _sym_led(self, dwg, x, y, comp):
        """LED symbol — triangle with cathode bar and light arrows."""
        color = comp.get("color", "yellow")
        svg_colors = {"red": "#ff4444", "green": "#44ff44", "blue": "#4444ff",
                      "yellow": "#ffff44", "white": "#ffffff", "orange": "#ff8833",
                      "rgb": "#ff44ff"}
        fill_color = svg_colors.get(color, "#ffff44")

        # Triangle (anode left, cathode right)
        tri_pts = [(x - 14, y - 12), (x - 14, y + 12), (x + 10, y)]
        dwg.add(dwg.polygon(tri_pts, fill=fill_color, fill_opacity=0.3,
                            stroke=fill_color, stroke_width=1.5))
        # Cathode bar
        dwg.add(dwg.line(start=(x + 10, y - 13), end=(x + 10, y + 13),
                         stroke=fill_color, stroke_width=2))
        # Lead lines
        dwg.add(dwg.line(start=(x - 25, y), end=(x - 14, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 10, y), end=(x + 25, y),
                         stroke="#e6edf3", stroke_width=1.5))
        # Light arrows
        for i, (ox, oy) in enumerate([(18, -10), (22, -14)]):
            ax, ay = x + ox - 3 * i, y - oy
            dwg.add(dwg.line(start=(ax, ay), end=(ax + 8, ay - 8),
                             stroke=fill_color, stroke_width=1, stroke_opacity=0.7))

    def _sym_capacitor(self, dwg, x, y, comp):
        """Capacitor symbol — two parallel plates."""
        gap = 5
        plate_w = 20
        # Top plate (positive)
        dwg.add(dwg.line(start=(x - plate_w, y - gap), end=(x + plate_w, y - gap),
                         stroke="#e6edf3", stroke_width=2.5))
        # Bottom plate
        dwg.add(dwg.line(start=(x - plate_w, y + gap), end=(x + plate_w, y + gap),
                         stroke="#e6edf3", stroke_width=2.5))
        # Lead lines (vertical)
        dwg.add(dwg.line(start=(x, y - 20), end=(x, y - gap),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x, y + gap), end=(x, y + 20),
                         stroke="#e6edf3", stroke_width=1.5))
        # + marker
        dwg.add(dwg.text("+", insert=(x + 22, y - 3),
                         font_size=11, fill="#44ff44", font_family="Arial"))

    def _sym_button(self, dwg, x, y, comp):
        """SPST push button symbol."""
        dwg.add(dwg.line(start=(x - 22, y), end=(x - 8, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 8, y), end=(x + 22, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.circle(center=(x - 8, y), r=2.5, fill="#e6edf3"))
        dwg.add(dwg.circle(center=(x + 8, y), r=2.5, fill="#e6edf3"))
        # Actuator line (angled, showing NO state)
        dwg.add(dwg.line(start=(x - 8, y), end=(x + 6, y - 10),
                         stroke="#e6edf3", stroke_width=1.5))

    def _sym_mcu(self, dwg, x, y, comp):
        """MCU / module box with colored header."""
        W, H = 80, 50
        name = comp.get("name", comp.get("id", "MCU"))
        # Body
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="#0d2137", stroke="#00d4ff", stroke_width=1.5, rx=3))
        # Header bar
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, 16),
                         fill="#00d4ff", fill_opacity=0.25, rx=3))
        # MCU label
        short = name.replace("Arduino ", "").replace(" Uno", "").replace(" Nano", "")
        dwg.add(dwg.text(short[:10], insert=(x, y - H//2 + 11),
                         font_size=10, fill="#00d4ff",
                         font_family="monospace", text_anchor="middle"))
        # ID
        dwg.add(dwg.text(comp.get("id", "U1"), insert=(x, y + 5),
                         font_size=9, fill="#8b949e",
                         font_family="monospace", text_anchor="middle"))

    def _sym_relay(self, dwg, x, y, comp):
        """Relay symbol — coil + switch."""
        # Coil (rectangle)
        dwg.add(dwg.rect(insert=(x - 18, y - 12), size=(36, 24),
                         fill="none", stroke="#ff8c00", stroke_width=1.5))
        dwg.add(dwg.text("RL", insert=(x, y + 5),
                         font_size=9, fill="#ff8c00",
                         font_family="monospace", text_anchor="middle"))
        # Switch contacts (above coil)
        dwg.add(dwg.line(start=(x - 8, y - 22), end=(x - 8, y - 32),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 8, y - 22), end=(x + 8, y - 32),
                         stroke="#e6edf3", stroke_width=1.5))
        # Armature (open contact)
        dwg.add(dwg.line(start=(x - 8, y - 28), end=(x + 5, y - 35),
                         stroke="#e6edf3", stroke_width=1.5))
        # Lead lines for coil
        dwg.add(dwg.line(start=(x - 18, y), end=(x - 30, y),
                         stroke="#ff8c00", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 18, y), end=(x + 30, y),
                         stroke="#ff8c00", stroke_width=1.5))

    def _sym_mosfet(self, dwg, x, y, comp):
        """N-Channel MOSFET symbol."""
        # Body line
        dwg.add(dwg.line(start=(x, y - 20), end=(x, y + 20),
                         stroke="#e6edf3", stroke_width=2))
        # Gate line (horizontal)
        dwg.add(dwg.line(start=(x - 20, y), end=(x - 4, y),
                         stroke="#e6edf3", stroke_width=1.5))
        # Gate bar
        dwg.add(dwg.line(start=(x - 4, y - 16), end=(x - 4, y + 16),
                         stroke="#e6edf3", stroke_width=2))
        # Drain and Source
        dwg.add(dwg.line(start=(x + 8, y - 10), end=(x, y - 10),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 8, y + 10), end=(x, y + 10),
                         stroke="#e6edf3", stroke_width=1.5))
        # Arrow on source
        arr = [(x + 3, y + 10), (x + 10, y + 7), (x + 10, y + 13)]
        dwg.add(dwg.polygon(arr, fill="#e6edf3"))
        # Labels
        dwg.add(dwg.text("G", insert=(x - 28, y + 4),
                         font_size=8, fill="#e6edf3", font_family="Arial"))
        dwg.add(dwg.text("D", insert=(x + 12, y - 8),
                         font_size=8, fill="#e6edf3", font_family="Arial"))
        dwg.add(dwg.text("S", insert=(x + 12, y + 14),
                         font_size=8, fill="#e6edf3", font_family="Arial"))

    def _sym_transistor(self, dwg, x, y, comp):
        """NPN transistor symbol."""
        # Base
        dwg.add(dwg.line(start=(x - 20, y), end=(x, y), stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x, y - 18), end=(x, y + 18), stroke="#e6edf3", stroke_width=2.5))
        # Collector
        dwg.add(dwg.line(start=(x, y - 10), end=(x + 18, y - 20), stroke="#e6edf3", stroke_width=1.5))
        # Emitter with arrow
        dwg.add(dwg.line(start=(x, y + 10), end=(x + 18, y + 20), stroke="#e6edf3", stroke_width=1.5))
        arr = [(x + 14, y + 17), (x + 20, y + 22), (x + 10, y + 23)]
        dwg.add(dwg.polygon(arr, fill="#e6edf3"))

    def _sym_diode(self, dwg, x, y, comp):
        """Diode symbol (flyback or signal)."""
        tri = [(x - 14, y - 10), (x - 14, y + 10), (x + 10, y)]
        dwg.add(dwg.polygon(tri, fill="#555555", stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 10, y - 11), end=(x + 10, y + 11),
                         stroke="#e6edf3", stroke_width=2))
        dwg.add(dwg.line(start=(x - 25, y), end=(x - 14, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 10, y), end=(x + 25, y),
                         stroke="#e6edf3", stroke_width=1.5))

    def _sym_motor(self, dwg, x, y, comp):
        """DC Motor symbol — circle with M."""
        dwg.add(dwg.circle(center=(x, y), r=22,
                           fill="none", stroke="#ff8833", stroke_width=1.5))
        dwg.add(dwg.text("M", insert=(x, y + 6),
                         font_size=18, fill="#ff8833",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        dwg.add(dwg.line(start=(x - 22, y), end=(x - 35, y),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x + 22, y), end=(x + 35, y),
                         stroke="#e6edf3", stroke_width=1.5))

    def _sym_buzzer(self, dwg, x, y, comp):
        """Buzzer / piezo symbol."""
        dwg.add(dwg.ellipse(center=(x, y), r=(16, 12),
                            fill="#1a1a3a", stroke="#aaaaff", stroke_width=1.5))
        # Sound waves
        for r_offset in (20, 26):
            dwg.add(dwg.path(
                d=f"M {x+r_offset} {y-8} Q {x+r_offset+6} {y} {x+r_offset} {y+8}",
                fill="none", stroke="#aaaaff", stroke_width=1, stroke_opacity=0.6))
        dwg.add(dwg.text("~", insert=(x, y + 5),
                         font_size=14, fill="#aaaaff",
                         font_family="Arial", text_anchor="middle"))
        dwg.add(dwg.line(start=(x - 22, y - 6), end=(x - 16, y - 6),
                         stroke="#e6edf3", stroke_width=1.5))
        dwg.add(dwg.line(start=(x - 22, y + 6), end=(x - 16, y + 6),
                         stroke="#e6edf3", stroke_width=1.5))

    def _sym_sensor(self, dwg, x, y, comp):
        """Generic sensor — box with S and sensing lines."""
        W, H = 36, 28
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="#0d2137", stroke="#44ffaa", stroke_width=1.5, rx=4))
        dwg.add(dwg.text("S", insert=(x, y + 5),
                         font_size=14, fill="#44ffaa",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        # Sensing lines on the right
        for offset in (-8, 0, 8):
            dwg.add(dwg.line(start=(x + W//2, y + offset),
                             end=(x + W//2 + 12, y + offset),
                             stroke="#44ffaa", stroke_width=1, stroke_opacity=0.6,
                             stroke_dasharray="2,2"))

    def _sym_display(self, dwg, x, y, comp):
        """OLED/LCD display symbol."""
        W, H = 60, 36
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="#000033", stroke="#5588ff", stroke_width=1.5, rx=3))
        # Screen content simulation
        for row in range(3):
            dwg.add(dwg.rect(insert=(x - W//2 + 5, y - H//2 + 5 + row * 9),
                             size=(W - 10, 6),
                             fill="#1144aa", fill_opacity=0.5, rx=1))
        dwg.add(dwg.text("DISP", insert=(x, y + 5),
                         font_size=9, fill="#5588ff",
                         font_family="monospace", text_anchor="middle"))

    def _sym_ic_generic(self, dwg, x, y, comp):
        """Generic IC / driver box."""
        W, H = 60, 40
        name = comp.get("name", comp.get("id", "IC"))
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="#1a1a2e", stroke="#888888", stroke_width=1.5))
        short = name[:8]
        dwg.add(dwg.text(short, insert=(x, y + 4),
                         font_size=9, fill="#cccccc",
                         font_family="monospace", text_anchor="middle"))

    def _sym_generic(self, dwg, x, y, comp):
        """Fallback generic symbol."""
        W, H = 40, 28
        t = comp.get("resolved_type", comp.get("type", "?"))[:6]
        dwg.add(dwg.rect(insert=(x - W//2, y - H//2), size=(W, H),
                         fill="#111111", stroke="#666666", stroke_width=1, rx=2))
        dwg.add(dwg.text(t, insert=(x, y + 4),
                         font_size=8, fill="#aaaaaa",
                         font_family="monospace", text_anchor="middle"))

    # ──────────────────────────────────────────────────────────────────────────
    # Legend and annotations
    # ──────────────────────────────────────────────────────────────────────────

    def _draw_legend(self, dwg, nets: List[Dict], width: int, height: int):
        """Compact net legend — top-right corner."""
        if not nets:
            return
        lx, ly = width - 180, 12
        dwg.add(dwg.rect(insert=(lx - 4, ly - 2), size=(180, min(len(nets) * 16 + 8, 160)),
                         fill="#161b22", fill_opacity=0.9,
                         stroke="#30363d", stroke_width=1, rx=3))
        dwg.add(dwg.text("Redes:", insert=(lx, ly + 10),
                         font_size=9, fill="#8b949e",
                         font_family="monospace"))
        for i, net in enumerate(nets[:9]):
            yy = ly + 22 + i * 15
            color = _net_color(net["name"])
            dwg.add(dwg.line(start=(lx, yy), end=(lx + 20, yy),
                             stroke=color, stroke_width=2))
            dwg.add(dwg.text(net["name"][:20], insert=(lx + 24, yy + 4),
                             font_size=9, fill=color, font_family="monospace"))
        if len(nets) > 9:
            dwg.add(dwg.text(f"… +{len(nets)-9} más",
                             insert=(lx, ly + 22 + 9 * 15),
                             font_size=8, fill="#555555", font_family="Arial"))

    def _draw_annotations(self, dwg, circuit_data: Dict, width: int, height: int):
        """Show first 3 DRC warnings as inline annotations."""
        drc = circuit_data.get("drc", {})
        errors = drc.get("errors", [])
        for i, err in enumerate(errors[:3]):
            msg = f"⚠ {err.get('code','ERR')}: {err.get('message','')}"[:60]
            dwg.add(dwg.text(msg, insert=(8, height - 88 - i * 14),
                             font_size=9, fill="#ff8c00",
                             font_family="monospace"))
