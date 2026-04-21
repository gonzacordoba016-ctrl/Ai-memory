# tools/kicad_exporter.py
# Generates valid KiCad v6 schematic files (.kicad_sch) from the internal netlist format.
# Connection strategy: net labels placed at computed pin positions.
# Users can open the file directly in KiCad 6/7/8.

import uuid as _uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Symbol library definitions (embedded, IEC/IEEE style)
# ──────────────────────────────────────────────────────────────────────────────

_LIB_R = '''\
  (symbol "Device:R"
    (pin_numbers (hide yes))
    (pin_names (offset 0))
    (property "Reference" "R" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
    (property "Value" "R" (at 0 0 90) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at -1.778 0 90) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "R_0_1"
      (rectangle (start -1.016 -2.032) (end 1.016 2.032)
        (stroke (width 0.254) (type default)) (fill (type none)))
    )
    (symbol "R_1_1"
      (pin passive line (at 0 3.81 270) (length 1.778)
        (name "~" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 0 -3.81 90) (length 1.778)
        (name "~" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_C = '''\
  (symbol "Device:C"
    (pin_numbers (hide yes))
    (pin_names (offset 0.254))
    (property "Reference" "C" (at 1.778 0 0) (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "C" (at 1.778 -2.032 0) (effects (font (size 1.27 1.27)) (justify left)))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "C_0_1"
      (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
        (stroke (width 0.508) (type default)) (fill (type none)))
      (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))
        (stroke (width 0.508) (type default)) (fill (type none)))
    )
    (symbol "C_1_1"
      (pin passive line (at 0 3.81 270) (length 3.048)
        (name "~" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 0 -3.81 90) (length 3.048)
        (name "~" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_LED = '''\
  (symbol "Device:LED"
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
    (property "Value" "LED" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "LED_0_1"
      (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.27 0) (xy 1.27 0))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy 1.016 -0.508) (xy 1.524 0) (xy 1.016 0.508))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy 1.778 -0.508) (xy 2.286 0) (xy 1.778 0.508))
        (stroke (width 0.254) (type default)) (fill (type none)))
    )
    (symbol "LED_1_1"
      (pin passive line (at -3.81 0 0) (length 2.54)
        (name "K" (effects (font (size 1.27 1.27))))
        (number "K" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 3.81 0 180) (length 2.54)
        (name "A" (effects (font (size 1.27 1.27))))
        (number "A" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_D = '''\
  (symbol "Device:D"
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
    (property "Value" "D" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "D_0_1"
      (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
      (polyline (pts (xy -1.27 0) (xy 1.27 0))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27))
        (stroke (width 0.254) (type default)) (fill (type none)))
    )
    (symbol "D_1_1"
      (pin passive line (at -3.81 0 0) (length 2.54)
        (name "K" (effects (font (size 1.27 1.27))))
        (number "K" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 3.81 0 180) (length 2.54)
        (name "A" (effects (font (size 1.27 1.27))))
        (number "A" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_SW = '''\
  (symbol "Device:SW_Push"
    (pin_numbers (hide yes))
    (pin_names (offset 1.016) (hide yes))
    (property "Reference" "SW" (at 1.27 2.032 0) (effects (font (size 1.27 1.27))))
    (property "Value" "SW_Push" (at 1.27 -2.286 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "SW_Push_0_1"
      (circle (center 0 1.27) (radius 0.508)
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy -1.524 0) (xy 1.524 0))
        (stroke (width 0) (type default)) (fill (type none)))
    )
    (symbol "SW_Push_1_1"
      (pin passive line (at -2.54 0 0) (length 1.016)
        (name "1" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin passive line (at 2.54 0 180) (length 1.016)
        (name "2" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_IC = '''\
  (symbol "Device:IC_Generic"
    (in_bom yes) (on_board yes)
    (property "Reference" "U" (at 0 -6.35 0) (effects (font (size 1.27 1.27))))
    (property "Value" "IC_Generic" (at 0 6.35 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "IC_Generic_0_1"
      (rectangle (start -5.08 -5.08) (end 5.08 5.08)
        (stroke (width 0.254) (type default)) (fill (type background)))
    )
    (symbol "IC_Generic_1_1"
      (pin bidirectional line (at -7.62 2.54 0) (length 2.54)
        (name "IN1" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin bidirectional line (at -7.62 -2.54 0) (length 2.54)
        (name "IN2" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
      (pin bidirectional line (at 7.62 2.54 180) (length 2.54)
        (name "OUT1" (effects (font (size 1.27 1.27))))
        (number "3" (effects (font (size 1.27 1.27)))))
      (pin bidirectional line (at 7.62 -2.54 180) (length 2.54)
        (name "OUT2" (effects (font (size 1.27 1.27))))
        (number "4" (effects (font (size 1.27 1.27)))))
      (pin power_in line (at 0 7.62 270) (length 2.54)
        (name "VCC" (effects (font (size 1.27 1.27))))
        (number "5" (effects (font (size 1.27 1.27)))))
      (pin power_in line (at 0 -7.62 90) (length 2.54)
        (name "GND" (effects (font (size 1.27 1.27))))
        (number "6" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_PWR_VCC = '''\
  (symbol "power:VCC"
    (power) (pin_names (offset 0) (hide yes)) (in_bom no) (on_board no)
    (property "Reference" "#PWR" (at 0 -1.27 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "VCC" (at 0 1.905 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "VCC_0_1"
      (polyline (pts (xy -0.762 0.508) (xy 0 1.016) (xy 0.762 0.508))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy 0 0) (xy 0 1.016))
        (stroke (width 0) (type default)) (fill (type none)))
    )
    (symbol "VCC_1_1"
      (pin power_in line (at 0 0 270) (length 0)
        (name "VCC" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
    )
  )'''

_LIB_PWR_GND = '''\
  (symbol "power:GND"
    (power) (pin_names (offset 0) (hide yes)) (in_bom no) (on_board no)
    (property "Reference" "#PWR" (at 0 -1.27 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Value" "GND" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
    (symbol "GND_0_1"
      (polyline (pts (xy 0 0) (xy 0 -1.016))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy -0.762 -1.016) (xy 0.762 -1.016))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy -0.508 -1.524) (xy 0.508 -1.524))
        (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy -0.254 -2.032) (xy 0.254 -2.032))
        (stroke (width 0) (type default)) (fill (type none)))
    )
    (symbol "GND_1_1"
      (pin power_in line (at 0 0 90) (length 0)
        (name "GND" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
    )
  )'''


# ──────────────────────────────────────────────────────────────────────────────
# Component type → KiCad lib_id mapping
# ──────────────────────────────────────────────────────────────────────────────

_TYPE_TO_LIB = {
    "resistor":       "Device:R",
    "capacitor":      "Device:C",
    "led":            "Device:LED",
    "led_rgb":        "Device:LED",
    "diode":          "Device:D",
    "1n4007":         "Device:D",
    "1n5819":         "Device:D",
    "button":         "Device:SW_Push",
    "switch":         "Device:SW_Push",
}

# Everything not in the map above uses Device:IC_Generic

def _lib_id(comp: Dict) -> str:
    t = comp.get("resolved_type", comp.get("type", "generic")).lower()
    return _TYPE_TO_LIB.get(t, "Device:IC_Generic")


# ──────────────────────────────────────────────────────────────────────────────
# Pin connection-point offsets from component center (in mm)
# These match the `(at x y angle)` position in the symbol definitions above.
# Format: pin_label → (dx_mm, dy_mm)
# ──────────────────────────────────────────────────────────────────────────────

_PIN_OFFSETS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "Device:R": {
        "1": (0.0, 3.81),    # bottom (positive Y = down in KiCad)
        "2": (0.0, -3.81),   # top
    },
    "Device:C": {
        "1": (0.0, 3.81),
        "2": (0.0, -3.81),
    },
    "Device:LED": {
        "K": (-3.81, 0.0),   # left
        "A": (3.81,  0.0),   # right
    },
    "Device:D": {
        "K": (-3.81, 0.0),
        "A": (3.81,  0.0),
    },
    "Device:SW_Push": {
        "1": (-2.54, 0.0),
        "2": (2.54,  0.0),
    },
    "Device:IC_Generic": {
        # Standard pins from the generic IC definition
        "1": (-7.62, 2.54),
        "2": (-7.62, -2.54),
        "3": (7.62,  2.54),
        "4": (7.62,  -2.54),
        "5": (0.0,   7.62),
        "6": (0.0,   -7.62),
    },
}

# For MCU/complex chips, auto-generate pin offsets based on the node references
_MCU_PIN_SPACING = 2.54  # mm between pins
_MCU_HALF_WIDTH  = 10.16  # mm (box half-width)


def _mcu_pin_offsets(pin_names: List[str]) -> Dict[str, Tuple[float, float]]:
    """Generate left/right column pin offsets for an MCU box."""
    left_pins  = [p for p in pin_names if p in ("GND", "5V", "3V3", "VIN", "RST", "AREF",
                                                  "SDA", "SCL", "TX", "RX", "MOSI", "MISO", "SCK")
                  or p.startswith("A")]
    right_pins = [p for p in pin_names if p not in left_pins]

    offsets: Dict[str, Tuple[float, float]] = {}
    half_h_l = (len(left_pins) - 1) * _MCU_PIN_SPACING / 2
    half_h_r = (len(right_pins) - 1) * _MCU_PIN_SPACING / 2

    for i, name in enumerate(left_pins):
        offsets[name] = (-_MCU_HALF_WIDTH, -half_h_l + i * _MCU_PIN_SPACING)
    for i, name in enumerate(right_pins):
        offsets[name] = (_MCU_HALF_WIDTH, -half_h_r + i * _MCU_PIN_SPACING)

    return offsets


# ──────────────────────────────────────────────────────────────────────────────
# Grid snapping
# ──────────────────────────────────────────────────────────────────────────────

_GRID = 2.54  # KiCad 100-mil grid

def _snap(v: float) -> float:
    return round(v / _GRID) * _GRID

def _fmt(v: float) -> str:
    return f"{v:.4f}"


# ──────────────────────────────────────────────────────────────────────────────
# UUID helper
# ──────────────────────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(_uuid.uuid4())


# ──────────────────────────────────────────────────────────────────────────────
# Component placement
# ──────────────────────────────────────────────────────────────────────────────

def _place_components(components: List[Dict]) -> Dict[str, Tuple[float, float]]:
    """
    Returns {comp_id: (x_mm, y_mm)} for each component.
    MCU at center, others in a grid around it.
    """
    positions: Dict[str, Tuple[float, float]] = {}
    mcu_types = {"arduino_uno", "arduino_nano", "arduino_mega", "esp32", "esp8266",
                 "stm32", "rp2040", "pico", "attiny", "mcu"}

    mcus    = [c for c in components
               if c.get("resolved_type", c.get("type", "")).lower() in mcu_types]
    others  = [c for c in components
               if c.get("resolved_type", c.get("type", "")).lower() not in mcu_types]

    # MCU(s) at center row
    origin_x, origin_y = 120.0, 100.0
    for i, mcu in enumerate(mcus):
        positions[mcu["id"]] = (_snap(origin_x + i * 40.0), _snap(origin_y))

    # Others: fill a grid to the right and below
    col_x = origin_x + len(mcus) * 40.0 + 30.0
    col_y = origin_y - 40.0
    spacing_x, spacing_y = 25.4, 20.32  # 1" × 0.8"
    cols = max(1, min(6, len(others)))

    for i, comp in enumerate(others):
        col = i % cols
        row = i // cols
        positions[comp["id"]] = (_snap(col_x + col * spacing_x),
                                  _snap(col_y + row * spacing_y))

    return positions


# ──────────────────────────────────────────────────────────────────────────────
# Main exporter
# ──────────────────────────────────────────────────────────────────────────────

class KiCadExporter:

    def export(self, circuit_data: Dict[str, Any]) -> str:
        """Generate KiCad v6 schematic string (.kicad_sch)."""
        components = circuit_data.get("components", [])
        nets       = circuit_data.get("nets", [])
        name       = circuit_data.get("name", "Stratum Circuit")
        desc       = circuit_data.get("description", "")
        power_src  = circuit_data.get("power", "5V USB")
        date_str   = datetime.now().strftime("%Y-%m-%d")

        positions = _place_components(components)

        # Build node → net name index
        node_to_net: Dict[str, str] = {}
        for net in nets:
            for node in net.get("nodes", []):
                node_to_net[node] = net["name"]

        # Collect which lib symbols are needed
        needed_libs = set()
        for comp in components:
            needed_libs.add(_lib_id(comp))
        # Always add power symbols
        has_vcc = any("vcc" in n["name"].lower() or "5v" in n["name"].lower()
                      or "3v3" in n["name"].lower() or "vdd" in n["name"].lower()
                      for n in nets)
        has_gnd = any("gnd" in n["name"].lower() for n in nets)
        if has_vcc:
            needed_libs.add("power:VCC")
        if has_gnd:
            needed_libs.add("power:GND")

        lib_map = {
            "Device:R":          _LIB_R,
            "Device:C":          _LIB_C,
            "Device:LED":        _LIB_LED,
            "Device:D":          _LIB_D,
            "Device:SW_Push":    _LIB_SW,
            "Device:IC_Generic": _LIB_IC,
            "power:VCC":         _LIB_PWR_VCC,
            "power:GND":         _LIB_PWR_GND,
        }

        lines: List[str] = []
        lines.append(f'(kicad_sch (version 20211123) (generator "stratum_v4")')
        lines.append(f'  (paper "A3")')
        lines.append(f'  (title_block')
        lines.append(f'    (title "{_esc(name)}")')
        lines.append(f'    (date "{date_str}")')
        lines.append(f'    (rev "1")')
        lines.append(f'    (company "Stratum AI")')
        lines.append(f'    (comment 1 "{_esc(desc)}")')
        lines.append(f'    (comment 2 "Power: {_esc(power_src)}")')
        lines.append(f'  )')
        lines.append(f'')
        lines.append(f'  (lib_symbols')
        for lib_id_key in sorted(needed_libs):
            if lib_id_key in lib_map:
                lines.append(lib_map[lib_id_key])
        lines.append(f'  )')
        lines.append(f'')

        # ── Component instances ──────────────────────────────────────────────
        pwr_index = 1
        for comp in components:
            lid     = _lib_id(comp)
            cx, cy  = positions.get(comp["id"], (100.0, 100.0))
            ref     = comp.get("id", "U?")
            val     = comp.get("value", comp.get("name", lid.split(":")[-1]))
            unit_s  = comp.get("unit", "")
            comp_uid = _uid()

            lines.append(f'  (symbol (lib_id "{lid}") (at {_fmt(cx)} {_fmt(cy)} 0) (unit 1)')
            lines.append(f'    (in_bom yes) (on_board yes)')
            lines.append(f'    (uuid "{comp_uid}")')
            lines.append(f'    (property "Reference" "{ref}" (at {_fmt(cx+2.54)} {_fmt(cy-2.54)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27))))')
            val_str = f"{val}{unit_s}" if unit_s else val
            lines.append(f'    (property "Value" "{_esc(val_str)}" (at {_fmt(cx+2.54)} {_fmt(cy+2.54)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27))))')
            lines.append(f'    (property "Footprint" "" (at 0 0 0)')
            lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')
            lines.append(f'  )')

        lines.append(f'')

        # ── Net labels at each pin ───────────────────────────────────────────
        label_uid_index = 0
        placed_labels: set = set()  # avoid duplicating label at same position

        for comp in components:
            lid    = _lib_id(comp)
            cx, cy = positions.get(comp["id"], (100.0, 100.0))
            cid    = comp["id"]

            # Collect all pin names referenced in nets for this component
            comp_pins: Dict[str, str] = {}  # pin_name → net_name
            for net in nets:
                for node in net.get("nodes", []):
                    parts = node.split(".", 1)
                    if len(parts) == 2 and parts[0] == cid:
                        comp_pins[parts[1]] = net["name"]

            if not comp_pins:
                continue

            # Get pin offsets
            is_mcu = lid == "Device:IC_Generic"
            if is_mcu:
                pin_offs = _mcu_pin_offsets(list(comp_pins.keys()))
            else:
                pin_offs = _PIN_OFFSETS.get(lid, {})

            for pin_name, net_name in comp_pins.items():
                if pin_name in pin_offs:
                    dx, dy = pin_offs[pin_name]
                else:
                    # Fallback: place label slightly to the right of center
                    dx, dy = 10.0 + label_uid_index * 2.54, 0.0

                px = _snap(cx + dx)
                py = _snap(cy + dy)

                # Determine label angle based on which side
                if dx < -0.5:
                    angle = 0    # pin on left → label points left
                elif dx > 0.5:
                    angle = 180  # pin on right → label points right
                elif dy > 0.5:
                    angle = 90   # pin below center
                else:
                    angle = 270  # pin above center

                pos_key = (px, py, net_name)
                if pos_key not in placed_labels:
                    placed_labels.add(pos_key)
                    lines.append(
                        f'  (label "{_esc(net_name)}" (at {_fmt(px)} {_fmt(py)} {angle})'
                    )
                    lines.append(
                        f'    (effects (font (size 1.27 1.27)))'
                    )
                    lines.append(f'    (uuid "{_uid()}")')
                    lines.append(f'  )')
                label_uid_index += 1

        lines.append(f'')

        # ── Power symbols for VCC and GND nets ──────────────────────────────
        vcc_nets = [n["name"] for n in nets
                    if any(v in n["name"].lower()
                           for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd"))]
        gnd_nets = [n["name"] for n in nets
                    if "gnd" in n["name"].lower() or "ground" in n["name"].lower()]

        pwr_x, pwr_y = 20.0, 20.0
        for net_name in set(vcc_nets):
            lines.append(f'  (symbol (lib_id "power:VCC") (at {_fmt(pwr_x)} {_fmt(pwr_y)} 0) (unit 1)')
            lines.append(f'    (in_bom yes) (on_board yes)')
            lines.append(f'    (uuid "{_uid()}")')
            lines.append(f'    (property "Reference" "#PWR0{pwr_index:02d}" (at {_fmt(pwr_x)} {_fmt(pwr_y-3)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')
            lines.append(f'    (property "Value" "{_esc(net_name)}" (at {_fmt(pwr_x)} {_fmt(pwr_y+2)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27))))')
            lines.append(f'  )')
            pwr_index += 1
            pwr_x += 10.0

        pwr_x = 20.0
        pwr_y = 30.0
        for net_name in set(gnd_nets):
            lines.append(f'  (symbol (lib_id "power:GND") (at {_fmt(pwr_x)} {_fmt(pwr_y)} 0) (unit 1)')
            lines.append(f'    (in_bom yes) (on_board yes)')
            lines.append(f'    (uuid "{_uid()}")')
            lines.append(f'    (property "Reference" "#PWR0{pwr_index:02d}" (at {_fmt(pwr_x)} {_fmt(pwr_y+3)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')
            lines.append(f'    (property "Value" "{_esc(net_name)}" (at {_fmt(pwr_x)} {_fmt(pwr_y-2)} 0)')
            lines.append(f'      (effects (font (size 1.27 1.27))))')
            lines.append(f'  )')
            pwr_index += 1
            pwr_x += 10.0

        lines.append(f'')
        lines.append(f'  (sheet_instances')
        lines.append(f'    (path "/" (page "1"))')
        lines.append(f'  )')
        lines.append(f')')

        return "\n".join(lines)


def _esc(s: str) -> str:
    """Escape double quotes for KiCad S-expression strings."""
    return str(s).replace('"', '\\"')


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

_exporter_instance: Optional[KiCadExporter] = None


def export_kicad_schematic(circuit_data: Dict[str, Any]) -> str:
    """Generate a KiCad v6 .kicad_sch string from a Stratum circuit dict."""
    global _exporter_instance
    if _exporter_instance is None:
        _exporter_instance = KiCadExporter()
    return _exporter_instance.export(circuit_data)
