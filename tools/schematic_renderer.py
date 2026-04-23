# tools/schematic_renderer.py — EDA-style professional renderer (light KiCad theme)

import svgwrite
from typing import Dict, Any, List, Tuple, Optional
import math
from core.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Net color palette — dark/saturated for light EDA background
# ──────────────────────────────────────────────────────────────────────────────

def _net_color(net_name: str) -> str:
    name = net_name.lower()
    if any(v in name for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd", "power")):
        return "#cc0000"
    if any(v in name for v in ("gnd", "ground", "0v", "agnd", "dgnd")):
        return "#1a1a1a"
    if any(v in name for v in ("sda", "scl", "i2c")):
        return "#007744"
    if any(v in name for v in ("spi", "mosi", "miso", "sck", "cs")):
        return "#770077"
    if any(v in name for v in ("tx", "rx", "uart", "serial")):
        return "#885500"
    if any(v in name for v in ("pwm", "motor", "servo")):
        return "#884400"
    if any(v in name for v in ("data", "dat", "sig", "out", "in")):
        return "#003388"
    palette = ["#005599", "#995500", "#007755", "#550077", "#557700", "#005577"]
    return palette[hash(net_name) % len(palette)]


# ──────────────────────────────────────────────────────────────────────────────
# Component functional groups
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
# Layout
# ──────────────────────────────────────────────────────────────────────────────

def _layout_components(components: List[Dict], width: int, height: int,
                       saved: Dict[str, Dict]) -> Dict[str, Tuple[int, int]]:
    positions: Dict[str, Tuple[int, int]] = {}
    for comp_id, pos in saved.items():
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            positions[comp_id] = (int(pos["x"]), int(pos["y"]))
    groups: Dict[str, List[Dict]] = {g: [] for g in ("mcu","input","output","power","comm","misc")}
    for comp in components:
        if comp["id"] not in positions:
            groups[_comp_group(comp)].append(comp)
    cx, cy = width // 2, height // 2
    spacing_x, spacing_y = 130, 85
    for i, comp in enumerate(groups["mcu"]):
        positions[comp["id"]] = (cx + i * spacing_x, cy)
    start_y = cy - (len(groups["input"]) - 1) * spacing_y // 2
    for i, comp in enumerate(groups["input"]):
        positions[comp["id"]] = (max(90, cx - 230 - (i % 2) * 60), start_y + i * spacing_y)
    start_y = cy - (len(groups["output"]) - 1) * spacing_y // 2
    for i, comp in enumerate(groups["output"]):
        positions[comp["id"]] = (min(width - 90, cx + 230 + (i % 2) * 60), start_y + i * spacing_y)
    for i, comp in enumerate(groups["power"]):
        positions[comp["id"]] = (110 + i * 95, 70)
    for i, comp in enumerate(groups["comm"]):
        positions[comp["id"]] = (width - 110 - i * 100, 70)
    for i, comp in enumerate(groups["misc"]):
        positions[comp["id"]] = (110 + i * 95, height - 70)
    return positions


def _route_orthogonal(p1: Tuple[int, int], p2: Tuple[int, int]) -> List[Tuple[int, int]]:
    x1, y1 = p1
    x2, y2 = p2
    mid_x = (x1 + x2) // 2
    return [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]


# ──────────────────────────────────────────────────────────────────────────────
# SchematicRenderer
# ──────────────────────────────────────────────────────────────────────────────

class SchematicRenderer:

    # Symbol line/fill palette (EDA light theme)
    _SYM_STROKE  = "#1a1a2e"   # near-black for symbol lines
    _SYM_STROKE2 = "#333355"   # slightly lighter for secondary lines
    _PIN_COLOR   = "#1a1a2e"   # pin stub lines
    _TEXT_COLOR  = "#1a1a2e"   # general text
    _TEXT_REF    = "#111111"   # reference designator
    _TEXT_VAL    = "#555555"   # value/name
    _FILL_PASSIVE= "#ffffff"   # resistor, cap, diode body
    _FILL_MCU    = "#e8f0ff"   # MCU body fill
    _FILL_ACTIVE = "#f8f8ff"   # transistor/mosfet
    _FILL_POWER  = "#fffbe8"   # regulator/battery
    _FILL_SENSOR = "#e8fff4"   # sensor modules
    _FILL_DRIVER = "#fff0e8"   # motor drivers
    _FILL_COMM   = "#f4e8ff"   # RF/BT modules
    _FILL_DISP   = "#e8eeff"   # displays

    def render_schematic_svg(self, circuit_data: Dict[str, Any],
                              width: int = 1000, height: int = 700) -> str:
        try:
            dwg = svgwrite.Drawing(size=('100%', '100%'),
                                   viewBox=f"0 0 {width} {height}")
            self._draw_background(dwg, width, height)
            self._draw_title_block(dwg, circuit_data, width, height)
            saved      = circuit_data.get("positions", {})
            components = circuit_data.get("components", [])
            positions  = _layout_components(components, width, height - 90, saved)
            nets       = circuit_data.get("nets", [])
            self._draw_connections(dwg, nets, positions)
            # Power rail symbols
            self._draw_power_rails(dwg, nets, positions)
            for comp in components:
                pos = positions.get(comp["id"], (width // 2, height // 2))
                self._draw_component(dwg, comp, pos)
            self._draw_legend(dwg, nets, width, height)
            self._draw_annotations(dwg, circuit_data, width, height)
            return dwg.tostring()
        except Exception as e:
            logger.error(f"Error renderizando esquemático: {e}")
            err = svgwrite.Drawing(size=(800, 100))
            err.add(err.rect(insert=(0,0), size=(800,100), fill="#fafafa"))
            err.add(err.text(f"Error: {e}", insert=(10,50), fill="red",
                             font_size=16, font_family="monospace"))
            return err.tostring()

    # ── Background ──────────────────────────────────────────────────────────

    def _draw_background(self, dwg, width: int, height: int):
        # Light cream background like KiCad
        dwg.add(dwg.rect(insert=(0,0), size=(width, height), fill="#f5f6f7"))
        # Fine grid lines
        for gx in range(0, width, 20):
            dwg.add(dwg.line(start=(gx,0), end=(gx, height-90),
                             stroke="#e4e6eb", stroke_width=0.4))
        for gy in range(0, height-90, 20):
            dwg.add(dwg.line(start=(0,gy), end=(width, gy),
                             stroke="#e4e6eb", stroke_width=0.4))
        # Major grid every 100px
        for gx in range(0, width, 100):
            dwg.add(dwg.line(start=(gx,0), end=(gx, height-90),
                             stroke="#d0d2da", stroke_width=0.8))
        for gy in range(0, height-90, 100):
            dwg.add(dwg.line(start=(0,gy), end=(width,gy),
                             stroke="#d0d2da", stroke_width=0.8))
        # Schematic area border
        dwg.add(dwg.rect(insert=(2,2), size=(width-4, height-92),
                         fill="none", stroke="#999aaa", stroke_width=1.2))

    # ── Title block (EDA-style bottom frame) ────────────────────────────────

    def _draw_title_block(self, dwg, circuit_data: Dict, width: int, height: int):
        y_base = height - 88
        # Title block background
        dwg.add(dwg.rect(insert=(0, y_base), size=(width, 88),
                         fill="#eeeff4", stroke="none"))
        # Top border of title block
        dwg.add(dwg.line(start=(0, y_base), end=(width, y_base),
                         stroke="#444466", stroke_width=1.5))
        # Vertical dividers
        divs = [width * 0.45, width * 0.65, width * 0.80]
        for dx in divs:
            dwg.add(dwg.line(start=(dx, y_base), end=(dx, height),
                             stroke="#aaaacc", stroke_width=0.8))
        # Horizontal mid-line
        dwg.add(dwg.line(start=(0, y_base+44), end=(width, y_base+44),
                         stroke="#aaaacc", stroke_width=0.8))

        name  = circuit_data.get("name", "Sin nombre")
        desc  = circuit_data.get("description", "")[:80]
        power = circuit_data.get("power", "")
        mcu   = circuit_data.get("selected_mcu", "")
        domain= circuit_data.get("detected_domain", "")
        n_comp= len(circuit_data.get("components", []))

        # Title
        dwg.add(dwg.text("TITLE:", insert=(8, y_base+14),
                         font_size=8, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(name, insert=(8, y_base+32),
                         font_size=15, fill="#111133", font_family="Arial",
                         font_weight="bold"))
        dwg.add(dwg.text(desc, insert=(8, y_base+50),
                         font_size=9, fill="#555577", font_family="Arial"))

        # MCU / power info
        x2 = width * 0.46
        dwg.add(dwg.text("MCU:", insert=(x2+6, y_base+14),
                         font_size=8, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(mcu or "—", insert=(x2+6, y_base+30),
                         font_size=11, fill="#223399", font_family="monospace"))
        dwg.add(dwg.text("Power:", insert=(x2+6, y_base+48),
                         font_size=8, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(power or "—", insert=(x2+6, y_base+62),
                         font_size=10, fill="#cc3300", font_family="monospace"))

        # Domain / components
        x3 = width * 0.66
        dwg.add(dwg.text("Domain:", insert=(x3+6, y_base+14),
                         font_size=8, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(domain or "generic", insert=(x3+6, y_base+30),
                         font_size=10, fill="#117755", font_family="monospace"))
        dwg.add(dwg.text("Components:", insert=(x3+6, y_base+48),
                         font_size=8, fill="#666688", font_family="Arial"))
        dwg.add(dwg.text(str(n_comp), insert=(x3+6, y_base+64),
                         font_size=14, fill="#333355", font_family="monospace",
                         font_weight="bold"))

        # DRC / warnings badge
        x4 = width * 0.81
        warnings = circuit_data.get("warnings", [])
        drc = circuit_data.get("drc", {})
        passed = drc.get("passed", True)
        badge_color = "#1a7a1a" if passed else "#aa1111"
        label = "✓ DRC OK" if passed else f"✗ {drc.get('counts',{}).get('errors','?')} errores DRC"
        dwg.add(dwg.rect(insert=(x4+6, y_base+6), size=(width-x4-14, 30),
                         fill=badge_color, fill_opacity=0.12,
                         stroke=badge_color, stroke_width=1, rx=4))
        dwg.add(dwg.text(label, insert=(x4+12, y_base+26),
                         font_size=11, fill=badge_color, font_family="Arial",
                         font_weight="bold"))
        if warnings:
            dwg.add(dwg.text(f"⚠ {len(warnings)} advertencia(s)",
                             insert=(x4+12, y_base+52),
                             font_size=9, fill="#885500", font_family="Arial"))
        # Stratum watermark
        dwg.add(dwg.text("Stratum EDA", insert=(width-90, height-6),
                         font_size=8, fill="#9999bb", font_family="Arial",
                         font_style="italic"))

    # ── Net connections ──────────────────────────────────────────────────────

    def _draw_connections(self, dwg, nets: List[Dict],
                          positions: Dict[str, Tuple[int, int]]):
        for net in nets:
            name  = net.get("name","")
            color = _net_color(name)
            nodes = net.get("nodes", [])
            coords = [positions[n.split(".")[0]] for n in nodes
                      if n.split(".")[0] in positions]
            if len(coords) < 2:
                continue
            for i in range(len(coords)-1):
                path = _route_orthogonal(coords[i], coords[i+1])
                for j in range(len(path)-1):
                    dwg.add(dwg.line(start=path[j], end=path[j+1],
                                     stroke=color, stroke_width=1.8))
            # Junction dots
            for pt in coords:
                dwg.add(dwg.circle(center=pt, r=3.5, fill=color))
            # Net label (small, on wire)
            if coords:
                lx = (coords[0][0] + coords[-1][0]) // 2
                ly = min(c[1] for c in coords) - 10
                label_w = len(name)*5 + 8
                dwg.add(dwg.rect(insert=(lx-2, ly-11), size=(label_w, 14),
                                 fill="#ffffee", stroke=color, stroke_width=0.7, rx=2))
                dwg.add(dwg.text(name, insert=(lx+2, ly),
                                 font_size=9, fill=color, font_family="monospace"))

    # ── Power rail symbols (VCC ↑ / GND ⏚) ─────────────────────────────────

    def _draw_power_rails(self, dwg, nets: List[Dict],
                          positions: Dict[str, Tuple[int, int]]):
        for net in nets:
            name = net.get("name","")
            nl   = name.lower()
            nodes = net.get("nodes",[])
            if not nodes:
                continue
            # Get first valid component position
            pos = None
            for n in nodes:
                cid = n.split(".")[0]
                if cid in positions:
                    pos = positions[cid]
                    break
            if not pos:
                continue
            px, py = pos
            if any(v in nl for v in ("vcc","5v","3v3","vin","vdd","power")):
                # VCC: upward arrow above connection point
                ax, ay = px, py - 45
                dwg.add(dwg.line(start=(px, py-20), end=(ax, ay+18),
                                 stroke="#cc0000", stroke_width=1.5))
                # Arrow head
                dwg.add(dwg.polygon([(ax,ay), (ax-6,ay+10), (ax+6,ay+10)],
                                    fill="#cc0000"))
                # Label
                dwg.add(dwg.rect(insert=(ax-16, ay-14), size=(32,14),
                                 fill="#fff0f0", stroke="#cc0000",
                                 stroke_width=0.8, rx=2))
                dwg.add(dwg.text(name.upper(), insert=(ax, ay-3),
                                 font_size=9, fill="#cc0000", font_family="monospace",
                                 font_weight="bold", text_anchor="middle"))
            elif any(v in nl for v in ("gnd","ground","0v")):
                # GND: 3-line symbol below connection point
                gx, gy = px, py + 20
                dwg.add(dwg.line(start=(px, py+18), end=(gx, gy),
                                 stroke="#1a1a1a", stroke_width=1.5))
                for i, w in enumerate([20, 13, 6]):
                    yy = gy + i*5
                    dwg.add(dwg.line(start=(gx-w, yy), end=(gx+w, yy),
                                     stroke="#1a1a1a", stroke_width=2-i*0.3))
                dwg.add(dwg.text("GND", insert=(gx, gy+22),
                                 font_size=8, fill="#1a1a1a", font_family="monospace",
                                 text_anchor="middle"))

    # ── Component dispatcher ─────────────────────────────────────────────────

    def _draw_component(self, dwg, comp: Dict, pos: Tuple[int, int]):
        x, y = pos
        t = comp.get("resolved_type", comp.get("type", "generic")).lower()
        dispatch = {
            "resistor":              self._sym_resistor,
            "led":                   self._sym_led,
            "led_rgb":               self._sym_led,
            "capacitor":             self._sym_capacitor,
            "capacitor_electrolytic":self._sym_capacitor,
            "button":                self._sym_button,
            "arduino_uno":           self._sym_mcu,
            "arduino_nano":          self._sym_mcu,
            "arduino_mega":          self._sym_mcu,
            "arduino_micro":         self._sym_mcu,
            "esp32":                 self._sym_mcu,
            "esp8266":               self._sym_mcu,
            "stm32":                 self._sym_mcu,
            "pico":                  self._sym_mcu,
            "raspberry_pi_pico":     self._sym_mcu,
            "relay":                 self._sym_relay,
            "relay_module":          self._sym_relay,
            "mosfet":                self._sym_mosfet,
            "mosfet_n":              self._sym_mosfet,
            "transistor":            self._sym_transistor,
            "diode":                 self._sym_diode,
            "motor":                 self._sym_motor,
            "dc_motor":              self._sym_motor,
            "stepper":               self._sym_stepper,
            "stepper_motor":         self._sym_stepper,
            "servo":                 self._sym_servo,
            "motor_driver":          self._sym_l298n,
            "l298n":                 self._sym_l298n,
            "drv8825":               self._sym_stepper_driver,
            "a4988":                 self._sym_stepper_driver,
            "tb6600":                self._sym_stepper_driver,
            "uln2003":               self._sym_ic_generic,
            "buzzer":                self._sym_buzzer,
            "sensor":                self._sym_sensor,
            "moisture_sensor":       self._sym_moisture,
            "hc_sr04":               self._sym_ultrasonic,
            "ultrasonic":            self._sym_ultrasonic,
            "ultrasonic_sensor":     self._sym_ultrasonic,
            "display":               self._sym_display,
            "oled":                  self._sym_display,
            "lcd":                   self._sym_display,
            "voltage_regulator":     self._sym_regulator,
            "lm7805":                self._sym_regulator,
            "ams1117":               self._sym_regulator,
            "lm317":                 self._sym_regulator,
            "regulator":             self._sym_regulator,
            "buck_converter":        self._sym_converter,
            "boost_converter":       self._sym_converter,
            "buck_boost":            self._sym_converter,
            "wifi_module":           self._sym_rf_module,
            "bluetooth":             self._sym_rf_module,
            "hc05":                  self._sym_rf_module,
            "hc_05":                 self._sym_rf_module,
            "nrf24l01":              self._sym_rf_module,
            "rf_module":             self._sym_rf_module,
            "lora":                  self._sym_rf_module,
            "connector":             self._sym_connector,
            "header":                self._sym_connector,
            "pin_header":            self._sym_connector,
            "terminal_block":        self._sym_connector,
            "inductor":              self._sym_inductor,
            "battery":               self._sym_battery,
            "battery_18650":         self._sym_battery,
            "lipo":                  self._sym_battery,
            # RTC modules
            "rtc":                   self._sym_rtc,
            "ds3231":                self._sym_rtc,
            "ds1307":                self._sym_rtc,
            "pcf8523":               self._sym_rtc,
            # Explicit diode part numbers
            "1n4007":                self._sym_diode,
            "1n5819":                self._sym_diode,
            "1n4148":                self._sym_diode,
            "zener":                 self._sym_diode,
            # Explicit transistors
            "bc547":                 self._sym_transistor,
            "bc557":                 self._sym_transistor,
            "2n2222":                self._sym_transistor,
            # Explicit MOSFETs
            "irf520":                self._sym_mosfet,
            "irf540":                self._sym_mosfet,
            "irfz44":                self._sym_mosfet,
        }
        draw_fn = dispatch.get(t, self._sym_generic)
        draw_fn(dwg, x, y, comp)

        # Reference above component
        ref = comp.get("id","?")
        val = comp.get("value","")
        unit = comp.get("unit","")
        dwg.add(dwg.text(ref, insert=(x, y-38),
                         font_size=10, fill=self._TEXT_REF,
                         font_family="monospace", text_anchor="middle",
                         font_weight="bold"))
        # Value below reference
        if val:
            dwg.add(dwg.text(f"{val}{unit}", insert=(x, y-26),
                             font_size=9, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))
        # Name below component
        name = comp.get("name","")
        if name and name != ref:
            dwg.add(dwg.text(name[:24], insert=(x, y+50),
                             font_size=8, fill="#445588",
                             font_family="Arial", text_anchor="middle"))

    # ── Symbol primitives (EDA light theme: dark lines, light fills) ─────────

    def _sym_resistor(self, dwg, x, y, comp):
        """IEC rectangle resistor."""
        W, H = 34, 14
        # Body
        dwg.add(dwg.rect(insert=(x-W//2, y-H//2), size=(W,H),
                         fill=self._FILL_PASSIVE, stroke=self._SYM_STROKE, stroke_width=1.5))
        # Lead stubs
        for x0, x1 in [(x-W//2-14, x-W//2), (x+W//2, x+W//2+14)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Value inside
        val = f"{comp.get('value','')}{comp.get('unit','Ω')}"
        dwg.add(dwg.text(val, insert=(x, y+4),
                         font_size=8, fill="#aa6600",
                         font_family="monospace", text_anchor="middle"))

    def _sym_led(self, dwg, x, y, comp):
        """LED — triangle + cathode bar + light arrows."""
        color = comp.get("color","yellow")
        svg_colors = {"red":"#ee2222","green":"#22bb22","blue":"#2244ee",
                      "yellow":"#ddcc00","white":"#aaaaaa","orange":"#ee7700","rgb":"#884499"}
        fill_c = svg_colors.get(color,"#ddcc00")
        tri_pts = [(x-14, y-12),(x-14, y+12),(x+10, y)]
        dwg.add(dwg.polygon(tri_pts, fill=fill_c, fill_opacity=0.35,
                            stroke=fill_c, stroke_width=1.8))
        dwg.add(dwg.line(start=(x+10,y-13), end=(x+10,y+13),
                         stroke=fill_c, stroke_width=2.5))
        for x0, x1 in [(x-25,x-14),(x+10,x+26)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        # Light arrows
        for dx, dy in [(18,-10),(23,-15)]:
            dwg.add(dwg.line(start=(x+dx-4,y-dy), end=(x+dx+5,y-dy-9),
                             stroke=fill_c, stroke_width=1.2))
            # Arrow head
            ang = math.atan2(-9,9)
            dwg.add(dwg.polygon([
                (x+dx+5, y-dy-9),
                (x+dx+5-4*math.cos(ang+0.5), y-dy-9-4*math.sin(ang+0.5)),
                (x+dx+5-4*math.cos(ang-0.5), y-dy-9-4*math.sin(ang-0.5)),
            ], fill=fill_c))

    def _sym_capacitor(self, dwg, x, y, comp):
        """Capacitor — two parallel plates."""
        gap, pw = 5, 22
        dwg.add(dwg.line(start=(x-pw,y-gap), end=(x+pw,y-gap),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        dwg.add(dwg.line(start=(x-pw,y+gap), end=(x+pw,y+gap),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        for y0, y1 in [(y-20,y-gap),(y+gap,y+20)]:
            dwg.add(dwg.line(start=(x,y0), end=(x,y1),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text("+", insert=(x+25,y-2),
                         font_size=12, fill="#1a8822", font_family="Arial",
                         font_weight="bold"))

    def _sym_button(self, dwg, x, y, comp):
        """SPST push button."""
        for cx, x2 in [(x-22,x-8),(x+8,x+22)]:
            dwg.add(dwg.line(start=(cx,y), end=(x2,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.circle(center=(x-8,y), r=2.5,
                           fill=self._SYM_STROKE, stroke="none"))
        dwg.add(dwg.circle(center=(x+8,y), r=2.5,
                           fill=self._SYM_STROKE, stroke="none"))
        dwg.add(dwg.line(start=(x-8,y), end=(x+5,y-11),
                         stroke=self._SYM_STROKE, stroke_width=1.8))
        # Push indicator
        dwg.add(dwg.line(start=(x+2,y-18), end=(x+2,y-10),
                         stroke="#666688", stroke_width=1, stroke_dasharray="2,2"))

    def _sym_mcu(self, dwg, x, y, comp):
        """MCU / module — IC box with pin stubs."""
        W, H = 90, 60
        name = comp.get("name", comp.get("id","MCU"))
        # Body
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_MCU, stroke=self._SYM_STROKE, stroke_width=2, rx=2))
        # Header bar
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,18),
                         fill="#4466aa", fill_opacity=0.18, rx=2))
        short = name.replace("Arduino ","").replace(" Uno","").replace(" Nano","")[:12]
        dwg.add(dwg.text(short, insert=(x,y-H//2+13),
                         font_size=11, fill="#223388",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        dwg.add(dwg.text(comp.get("id","U1"), insert=(x,y+6),
                         font_size=9, fill="#555577",
                         font_family="monospace", text_anchor="middle"))
        # Pin stubs — left and right sides (simplified)
        n_pins = 4
        for side_sign, label_x in [(-1, x-W//2-14), (1, x+W//2+14)]:
            for i in range(n_pins):
                py_ = y - 16 + i*11
                x_body = x + side_sign * W//2
                x_tip  = x + side_sign * (W//2 + 10)
                dwg.add(dwg.line(start=(x_body,py_), end=(x_tip,py_),
                                 stroke=self._PIN_COLOR, stroke_width=1))
                # Pin number
                dwg.add(dwg.text(str(i+1 if side_sign<0 else n_pins*2-i),
                                 insert=(label_x, py_+3),
                                 font_size=6, fill="#888899",
                                 font_family="monospace", text_anchor="middle"))

    def _sym_relay(self, dwg, x, y, comp):
        """Relay — coil + contact symbol."""
        # Coil rectangle
        dwg.add(dwg.rect(insert=(x-20,y-12), size=(40,24),
                         fill=self._FILL_PASSIVE, stroke="#886600", stroke_width=1.8))
        # Coil winding lines
        for i in range(5):
            xi = x-14 + i*7
            dwg.add(dwg.line(start=(xi,y-8), end=(xi,y+8),
                             stroke="#886600", stroke_width=0.8, stroke_opacity=0.5))
        dwg.add(dwg.text("K", insert=(x,y+5),
                         font_size=10, fill="#886600",
                         font_family="monospace", text_anchor="middle"))
        # Contact symbol above coil
        dwg.add(dwg.line(start=(x-8,y-22), end=(x-8,y-32), stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x+8,y-22), end=(x+8,y-32), stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x-8,y-28), end=(x+4,y-36), stroke=self._SYM_STROKE, stroke_width=1.5))
        # Coil leads
        for x0,x1 in [(x-34,x-20),(x+20,x+34)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_mosfet(self, dwg, x, y, comp):
        """N-Channel MOSFET."""
        # Channel body line
        dwg.add(dwg.line(start=(x,y-22), end=(x,y+22),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        # Gate
        dwg.add(dwg.line(start=(x-22,y), end=(x-5,y),
                         stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.line(start=(x-5,y-18), end=(x-5,y+18),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        gap = 4
        dwg.add(dwg.line(start=(x-5+gap,y-18), end=(x-5+gap,y+18),
                         stroke=self._SYM_STROKE, stroke_width=1.5,
                         stroke_dasharray="3,2"))
        # Drain / Source
        for sign, lbl in [(-1,"D"),(1,"S")]:
            dwg.add(dwg.line(start=(x-1,y+sign*12), end=(x+20,y+sign*12),
                             stroke=self._SYM_STROKE, stroke_width=1.5))
            dwg.add(dwg.line(start=(x+20,y+sign*12), end=(x+20,y+sign*24),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+24,y+sign*14+4),
                             font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))
        # Arrow (source)
        arr = [(x+14,y+12),(x+20,y+8),(x+20,y+16)]
        dwg.add(dwg.polygon(arr, fill=self._SYM_STROKE))
        dwg.add(dwg.text("G", insert=(x-28,y+4),
                         font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_transistor(self, dwg, x, y, comp):
        """NPN transistor."""
        # Base
        dwg.add(dwg.line(start=(x-22,y), end=(x,y),
                         stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y-20), end=(x,y+20),
                         stroke=self._SYM_STROKE, stroke_width=2.5))
        # Collector / Emitter
        dwg.add(dwg.line(start=(x,y-10), end=(x+20,y-22),
                         stroke=self._SYM_STROKE, stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y+10), end=(x+20,y+22),
                         stroke=self._SYM_STROKE, stroke_width=1.5))
        # Emitter arrow
        arr = [(x+14,y+17),(x+22,y+23),(x+12,y+24)]
        dwg.add(dwg.polygon(arr, fill=self._SYM_STROKE))
        for lbl, lx, ly_ in [("B",x-28,y+4),("C",x+22,y-20),("E",x+22,y+24)]:
            dwg.add(dwg.text(lbl, insert=(lx,ly_),
                             font_size=8, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_diode(self, dwg, x, y, comp):
        """Diode (signal/flyback)."""
        tri = [(x-14,y-10),(x-14,y+10),(x+10,y)]
        dwg.add(dwg.polygon(tri, fill="#dddddd",
                            stroke=self._SYM_STROKE, stroke_width=1.8))
        dwg.add(dwg.line(start=(x+10,y-12), end=(x+10,y+12),
                         stroke=self._SYM_STROKE, stroke_width=2.2))
        for x0,x1 in [(x-26,x-14),(x+10,x+26)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        for lbl,lx in [("A",x-28),("K",x+18)]:
            dwg.add(dwg.text(lbl, insert=(lx,y+4),
                             font_size=7, fill=self._TEXT_COLOR, font_family="Arial"))

    def _sym_motor(self, dwg, x, y, comp):
        """DC Motor — circle with M."""
        dwg.add(dwg.circle(center=(x,y), r=22,
                           fill=self._FILL_PASSIVE, stroke="#884400", stroke_width=2))
        dwg.add(dwg.text("M", insert=(x,y+7),
                         font_size=20, fill="#884400",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for x0,x1 in [(x-36,x-22),(x+22,x+36)]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_buzzer(self, dwg, x, y, comp):
        """Buzzer / piezo."""
        dwg.add(dwg.ellipse(center=(x,y), r=(17,12),
                            fill="#f0f0ff", stroke="#444488", stroke_width=1.8))
        for r_off in (21,27):
            dwg.add(dwg.path(
                d=f"M {x+r_off} {y-9} Q {x+r_off+7} {y} {x+r_off} {y+9}",
                fill="none", stroke="#444488", stroke_width=1.2))
        dwg.add(dwg.text("~", insert=(x,y+6),
                         font_size=14, fill="#444488",
                         font_family="Arial", text_anchor="middle"))
        for offs in [(-6,6)]:
            dwg.add(dwg.line(start=(x-24,y+offs[0]), end=(x-17,y+offs[0]),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.line(start=(x-24,y+offs[1]), end=(x-17,y+offs[1]),
                             stroke=self._PIN_COLOR, stroke_width=1.5))

    def _sym_sensor(self, dwg, x, y, comp):
        """Generic sensor box."""
        W, H = 38, 30
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#117755", stroke_width=1.8, rx=4))
        dwg.add(dwg.text("S", insert=(x,y+6),
                         font_size=16, fill="#117755",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for off in (-8,0,8):
            dwg.add(dwg.line(start=(x+W//2,y+off), end=(x+W//2+12,y+off),
                             stroke="#117755", stroke_width=1, stroke_dasharray="2,2"))

    def _sym_display(self, dwg, x, y, comp):
        """OLED/LCD display."""
        W, H = 64, 38
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_DISP, stroke="#334499", stroke_width=2, rx=3))
        # Screen area
        dwg.add(dwg.rect(insert=(x-W//2+4,y-H//2+4), size=(W-8,H-8),
                         fill="#111133", rx=2))
        # Simulated pixels
        for row in range(3):
            dwg.add(dwg.rect(insert=(x-W//2+7, y-H//2+7+row*9),
                             size=(W-14,6), fill="#2244cc", fill_opacity=0.6, rx=1))
        dwg.add(dwg.text("DISP", insert=(x,y+6),
                         font_size=9, fill="#aabbff",
                         font_family="monospace", text_anchor="middle"))

    def _sym_ic_generic(self, dwg, x, y, comp):
        """Generic IC / driver."""
        W, H = 64, 42
        name = comp.get("name", comp.get("id","IC"))[:9]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#f0f0f8", stroke="#555566", stroke_width=1.8))
        dwg.add(dwg.text(name, insert=(x,y+4),
                         font_size=10, fill="#333355",
                         font_family="monospace", text_anchor="middle"))
        # Notch
        dwg.add(dwg.path(d=f"M {x-6} {y-H//2} Q {x} {y-H//2+6} {x+6} {y-H//2}",
                         fill="#ccccdd", stroke="#555566", stroke_width=0.8))

    def _sym_l298n(self, dwg, x, y, comp):
        """L298N dual H-bridge."""
        W, H = 74, 52
        name = comp.get("name","L298N")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_DRIVER, stroke="#885500", stroke_width=1.8))
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,16),
                         fill="#885500", fill_opacity=0.15))
        dwg.add(dwg.text(name, insert=(x,y-H//2+12),
                         font_size=10, fill="#885500",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for i,lbl in enumerate(["IN1","IN2","EN"]):
            dwg.add(dwg.text(lbl, insert=(x-W//2+4,y-6+i*13),
                             font_size=7, fill="#555566", font_family="monospace"))
        for i,lbl in enumerate(["OUT1","OUT2"]):
            dwg.add(dwg.text(lbl, insert=(x+10,y+0+i*13),
                             font_size=7, fill="#885500", font_family="monospace"))

    def _sym_stepper_driver(self, dwg, x, y, comp):
        """DRV8825/A4988 stepper driver."""
        W, H = 58, 44
        name = (comp.get("name", comp.get("id","DRV")) or "")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#116611", stroke_width=1.8))
        dwg.add(dwg.text(name, insert=(x,y-5),
                         font_size=9, fill="#116611",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for i,lbl in enumerate(["STP","DIR","EN"]):
            dwg.add(dwg.text(lbl, insert=(x-W//2+3,y-H//2+18+i*11),
                             font_size=7, fill="#555566", font_family="monospace"))
        for i,lbl in enumerate(["A1","A2","B1","B2"]):
            dwg.add(dwg.text(lbl, insert=(x+W//2-16,y-H//2+12+i*9),
                             font_size=7, fill="#116611", font_family="monospace"))

    def _sym_regulator(self, dwg, x, y, comp):
        """TO-220 voltage regulator."""
        # Body
        dwg.add(dwg.rect(insert=(x-18,y-14), size=(36,28),
                         fill=self._FILL_POWER, stroke="#776600", stroke_width=1.8))
        # Heat tab
        dwg.add(dwg.rect(insert=(x-9,y-22), size=(18,10),
                         fill="#eeeedd", stroke="#776600", stroke_width=1.2))
        # 3 pins
        for dx in (-10,0,10):
            dwg.add(dwg.line(start=(x+dx,y+14), end=(x+dx,y+24),
                             stroke=self._PIN_COLOR, stroke_width=2.2))
        for dx,lbl in [(-14,"IN"),(0,"GND"),(14,"OUT")]:
            dwg.add(dwg.text(lbl, insert=(x+dx,y+34),
                             font_size=6, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))
        name = (comp.get("name","REG") or "")[:8]
        dwg.add(dwg.text(name, insert=(x,y+5),
                         font_size=8, fill="#776600",
                         font_family="monospace", text_anchor="middle"))

    def _sym_moisture(self, dwg, x, y, comp):
        """FC-28 soil moisture sensor."""
        W, H = 30, 42
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2+10), size=(W,20),
                         fill=self._FILL_SENSOR, stroke="#117755", stroke_width=1.5, rx=2))
        dwg.add(dwg.text("FC28", insert=(x,y+8),
                         font_size=7, fill="#117755",
                         font_family="monospace", text_anchor="middle"))
        for dx in (-8,8):
            dwg.add(dwg.rect(insert=(x+dx-3,y+10), size=(6,20),
                             fill="#226633", stroke="#117755", stroke_width=1))
        for dx,lbl in [(-8,"A"),(0,"V"),(8,"G")]:
            dwg.add(dwg.line(start=(x+dx,y-H//2+10), end=(x+dx,y-H//2),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+dx,y-H//2-3),
                             font_size=6, fill="#117755",
                             font_family="monospace", text_anchor="middle"))

    def _sym_ultrasonic(self, dwg, x, y, comp):
        """HC-SR04 ultrasonic sensor."""
        dwg.add(dwg.rect(insert=(x-32,y-17), size=(64,34),
                         fill=self._FILL_SENSOR, stroke="#227799", stroke_width=1.8, rx=3))
        for cx_,lbl in [(x-16,"T"),(x+16,"E")]:
            dwg.add(dwg.circle(center=(cx_,y), r=11,
                               fill="#ddeeff", stroke="#227799", stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(cx_,y+4),
                             font_size=8, fill="#227799",
                             font_family="monospace", text_anchor="middle"))
        for r in (14,20):
            dwg.add(dwg.path(
                d=f"M {x+32} {y-r//2} Q {x+32+r//3} {y} {x+32} {y+r//2}",
                fill="none", stroke="#227799", stroke_width=1, stroke_opacity=0.6))

    def _sym_connector(self, dwg, x, y, comp):
        """Pin header / terminal block."""
        try:
            pins = int(comp.get("pins", comp.get("value", 2)) or 2)
        except (ValueError, TypeError):
            pins = 2
        pins = max(2, min(pins, 8))
        H, W = pins*11+6, 26
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#f0f0f0", stroke="#555566", stroke_width=1.5, rx=2))
        for i in range(pins):
            py_ = y-H//2+8+i*11
            dwg.add(dwg.rect(insert=(x-W//2+3,py_-4), size=(10,8),
                             fill="#cccc88", stroke="#888866", stroke_width=0.8, rx=1))
            dwg.add(dwg.circle(center=(x-W//2+8,py_), r=2.5,
                               fill="#333300", stroke="none"))
            dwg.add(dwg.line(start=(x-W//2-10,py_), end=(x-W//2,py_),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text(f"J{pins}", insert=(x+8,y+4),
                         font_size=8, fill="#555566",
                         font_family="monospace", text_anchor="middle"))

    def _sym_rf_module(self, dwg, x, y, comp):
        """HC-05 / nRF24L01 RF module."""
        W, H = 60, 40
        name = (comp.get("name","RF") or "")[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_COMM, stroke="#660099", stroke_width=1.8, rx=3))
        # Antenna
        dwg.add(dwg.line(start=(x+W//2,y-H//4), end=(x+W//2+14,y-H//4),
                         stroke="#660099", stroke_width=2))
        dwg.add(dwg.line(start=(x+W//2+14,y-H//4-7), end=(x+W//2+14,y-H//4+7),
                         stroke="#660099", stroke_width=1.5))
        for r in (5,10):
            dwg.add(dwg.path(
                d=f"M {x+W//2+16} {y-H//4-r} Q {x+W//2+22+r} {y-H//4} {x+W//2+16} {y-H//4+r}",
                fill="none", stroke="#660099", stroke_width=1.2, stroke_opacity=0.7))
        dwg.add(dwg.text(name, insert=(x,y+5),
                         font_size=9, fill="#660099",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))

    def _sym_converter(self, dwg, x, y, comp):
        """Buck/Boost DC-DC converter."""
        W, H = 62, 42
        is_boost = "boost" in (comp.get("resolved_type",comp.get("type","")) or "").lower()
        color = "#cc8800" if is_boost else "#0055aa"
        label = "BOOST↑" if is_boost else "BUCK↓"
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_POWER, stroke=color, stroke_width=1.8, rx=3))
        # Coil symbol
        cx0 = x-10
        for i in range(4):
            dwg.add(dwg.path(
                d=f"M {cx0+i*6} {y} Q {cx0+i*6+3} {y-10} {cx0+i*6+6} {y}",
                fill="none", stroke=color, stroke_width=1.8))
        dwg.add(dwg.text(label, insert=(x,y+16),
                         font_size=8, fill=color,
                         font_family="monospace", text_anchor="middle"))
        for x0,x1,lbl in [(x-W//2-10,x-W//2,"IN"),(x+W//2,x+W//2+10,"OUT")]:
            dwg.add(dwg.line(start=(x0,y), end=(x1,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x0-2 if lbl=="IN" else x1+2,y-5),
                             font_size=7, fill=color, font_family="monospace",
                             text_anchor="end" if lbl=="IN" else "start"))

    def _sym_stepper(self, dwg, x, y, comp):
        """Stepper motor — circle with 4 coil leads."""
        dwg.add(dwg.circle(center=(x,y), r=24,
                           fill=self._FILL_PASSIVE, stroke="#224488", stroke_width=2))
        dwg.add(dwg.text("STEP", insert=(x,y+6),
                         font_size=10, fill="#224488",
                         font_family="Arial", font_weight="bold", text_anchor="middle"))
        for ang_deg,lbl in [(45,"A+"),(135,"A-"),(225,"B+"),(315,"B-")]:
            rad = math.radians(ang_deg)
            ex, ey = x+24*math.cos(rad), y+24*math.sin(rad)
            lx, ly_ = x+36*math.cos(rad), y+36*math.sin(rad)
            dwg.add(dwg.line(start=(ex,ey), end=(lx,ly_),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
            dwg.add(dwg.text(lbl, insert=(x+42*math.cos(rad),y+42*math.sin(rad)+3),
                             font_size=7, fill="#224488",
                             font_family="monospace", text_anchor="middle"))

    def _sym_servo(self, dwg, x, y, comp):
        """Servo motor."""
        W, H = 48, 32
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill=self._FILL_SENSOR, stroke="#226622", stroke_width=1.8, rx=4))
        dwg.add(dwg.circle(center=(x,y-H//2-9), r=8,
                           fill=self._FILL_PASSIVE, stroke="#226622", stroke_width=1.5))
        dwg.add(dwg.line(start=(x,y-H//2-9), end=(x+8,y-H//2-9),
                         stroke="#226622", stroke_width=2.5))
        dwg.add(dwg.text("SRV", insert=(x,y+6),
                         font_size=10, fill="#226622",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        for dx,c in [(-9,"#ee2222"),(0,"#555555"),(9,"#dddd00")]:
            dwg.add(dwg.line(start=(x+dx,y+H//2), end=(x+dx,y+H//2+10),
                             stroke=c, stroke_width=2.5))

    def _sym_inductor(self, dwg, x, y, comp):
        """Inductor — 4 bumps."""
        bumps, bw = 4, 9
        total = bumps*bw
        x0 = x - total//2
        for i in range(bumps):
            cxb = x0+i*bw+bw//2
            dwg.add(dwg.path(
                d=f"M {x0+i*bw} {y} Q {cxb} {y-15} {x0+(i+1)*bw} {y}",
                fill="none", stroke=self._SYM_STROKE, stroke_width=2))
        for x0_,x1_ in [(x-total//2-15,x-total//2),(x+total//2,x+total//2+15)]:
            dwg.add(dwg.line(start=(x0_,y), end=(x1_,y),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        val = comp.get("value","")
        if val:
            dwg.add(dwg.text(val, insert=(x,y+16),
                             font_size=8, fill=self._TEXT_VAL,
                             font_family="monospace", text_anchor="middle"))

    def _sym_battery(self, dwg, x, y, comp):
        """Battery — stacked cell plates."""
        for i,(w,thick) in enumerate([(22,2.5),(14,1.5),(22,2.5),(14,1.5)]):
            py_ = y-14+i*7
            dwg.add(dwg.line(start=(x-w//2,py_), end=(x+w//2,py_),
                             stroke="#117700", stroke_width=thick))
        for y0,y1 in [(y-14,y-24),(y+14,y+24)]:
            dwg.add(dwg.line(start=(x,y0), end=(x,y1),
                             stroke=self._PIN_COLOR, stroke_width=1.5))
        dwg.add(dwg.text("+", insert=(x+16,y-18),
                         font_size=12, fill="#117700",
                         font_family="Arial", font_weight="bold"))
        val = comp.get("value","")
        if val:
            dwg.add(dwg.text(val, insert=(x,y+36),
                             font_size=8, fill="#117700",
                             font_family="monospace", text_anchor="middle"))

    def _sym_rtc(self, dwg, x, y, comp):
        """RTC module — IC box + coin cell symbol."""
        W, H = 52, 32
        name = comp.get("name", comp.get("id","RTC"))[:10]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#e8f0ff", stroke="#224488", stroke_width=1.8, rx=2))
        # Header bar
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,14),
                         fill="#224488", fill_opacity=0.15, rx=2))
        dwg.add(dwg.text("RTC", insert=(x,y-H//2+10),
                         font_size=9, fill="#224488",
                         font_family="monospace", text_anchor="middle", font_weight="bold"))
        dwg.add(dwg.text(name, insert=(x,y+8),
                         font_size=8, fill="#334455",
                         font_family="monospace", text_anchor="middle"))
        # Coin cell symbol (small circle on side)
        dwg.add(dwg.circle(center=(x+W//2+8,y), r=7,
                           fill="none", stroke="#888899", stroke_width=1.5))
        dwg.add(dwg.line(start=(x+W//2+12,y), end=(x+W//2+18,y),
                         stroke="#888899", stroke_width=1.2))
        # I2C pin stubs
        for sign, label in [(-1,"SDA"), (-1,"SCL"), (1,"VCC"), (1,"GND")]:
            yi = y - 8 + (0 if label in ("SDA","VCC") else 8)
            x_body = x + sign * W//2
            x_tip  = x + sign * (W//2 + 12)
            dwg.add(dwg.line(start=(x_body,yi), end=(x_tip,yi),
                             stroke=self._PIN_COLOR, stroke_width=1))
            dwg.add(dwg.text(label, insert=(x_tip + sign*4, yi+3),
                             font_size=6, fill="#667788",
                             font_family="monospace",
                             text_anchor="start" if sign > 0 else "end"))

    def _sym_generic(self, dwg, x, y, comp):
        """Fallback generic IC."""
        W, H = 48, 34
        name = comp.get("name", comp.get("id","?"))[:10]
        t = comp.get("resolved_type", comp.get("type","?"))[:8]
        dwg.add(dwg.rect(insert=(x-W//2,y-H//2), size=(W,H),
                         fill="#f0f0f8", stroke="#6666aa", stroke_width=1.5, rx=2))
        # Small type label at top
        dwg.add(dwg.text(t, insert=(x,y-H//2+10),
                         font_size=7, fill="#8888aa",
                         font_family="monospace", text_anchor="middle"))
        dwg.add(dwg.text(name, insert=(x,y+5),
                         font_size=8, fill="#333355",
                         font_family="monospace", text_anchor="middle"))
        # Generic pin stubs (2 each side)
        for sign in [-1, 1]:
            for i, yi in enumerate([y-8, y+4]):
                x_body = x + sign * W//2
                x_tip  = x + sign * (W//2 + 10)
                dwg.add(dwg.line(start=(x_body,yi), end=(x_tip,yi),
                                 stroke=self._PIN_COLOR, stroke_width=1))

    # ── Legend ───────────────────────────────────────────────────────────────

    def _draw_legend(self, dwg, nets: List[Dict], width: int, height: int):
        if not nets:
            return
        lx, ly = width-185, 12
        n = min(len(nets), 9)
        dwg.add(dwg.rect(insert=(lx-4,ly-2), size=(185, n*16+14),
                         fill="#fffffc", fill_opacity=0.95,
                         stroke="#aaaacc", stroke_width=1, rx=3))
        dwg.add(dwg.text("Net", insert=(lx,ly+9),
                         font_size=9, fill="#666688",
                         font_family="monospace", font_weight="bold"))
        for i, net in enumerate(nets[:n]):
            yy = ly+20+i*15
            color = _net_color(net["name"])
            dwg.add(dwg.line(start=(lx,yy), end=(lx+22,yy),
                             stroke=color, stroke_width=2.2))
            dwg.add(dwg.circle(center=(lx+11,yy), r=2, fill=color))
            dwg.add(dwg.text(net["name"][:22], insert=(lx+26,yy+4),
                             font_size=9, fill=color, font_family="monospace"))
        if len(nets) > 9:
            dwg.add(dwg.text(f"… +{len(nets)-9} redes",
                             insert=(lx, ly+22+9*15),
                             font_size=8, fill="#888899", font_family="Arial"))

    def _draw_annotations(self, dwg, circuit_data: Dict, width: int, height: int):
        drc = circuit_data.get("drc",{})
        issues = drc.get("errors",[])
        for i, err in enumerate(issues[:3]):
            msg = f"⚠ {err.get('code','ERR')}: {err.get('message','')}  "[:65]
            bw = len(msg)*5+8
            dwg.add(dwg.rect(insert=(6, height-98-i*16), size=(bw,14),
                             fill="#fff8e0", stroke="#cc8800", stroke_width=0.7, rx=2))
            dwg.add(dwg.text(msg, insert=(10, height-88-i*16),
                             font_size=9, fill="#885500", font_family="monospace"))
