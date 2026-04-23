# tools/bom_generator.py
#
# Generador de BOM (Bill of Materials) con costos para Stratum.
# Mapea los componentes de un circuito contra el stock del ingeniero.

from __future__ import annotations
import csv
import io
import re
from typing import Any


# ── Footprint defaults por tipo de componente ─────────────────────────────────

_TYPE_TO_FOOTPRINT: dict[str, str] = {
    "resistor":              "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
    "capacitor":             "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
    "capacitor_electrolytic":"Capacitor_THT:CP_Radial_D8.0mm_P3.50mm",
    "led":                   "LED_THT:LED_D5.0mm",
    "led_rgb":               "LED_THT:LED_D5.0mm_RGB",
    "diode":                 "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    "1n4007":                "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    "1n5819":                "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
    "zener":                 "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal",
    "transistor":            "Package_TO_SOT_THT:TO-92_Inline",
    "mosfet":                "Package_TO_SOT_THT:TO-220-3_Vertical",
    "mosfet_n":              "Package_TO_SOT_THT:TO-220-3_Vertical",
    "button":                "Button_Switch_THT:SW_PUSH_6mm",
    "switch":                "Button_Switch_THT:SW_SPDT_PCB",
    "relay_module":          "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
    "relay":                 "Relay_THT:Relay_SPDT_Omron_G5LE-1",
    "fuse":                  "Fuseholder_Holder_3AG",
    "inductor":              "Inductor_THT:L_Axial_L5.3mm_D2.2mm_P10.16mm_Horizontal",
    "crystal":               "Crystal:Crystal_HC49-4H_Vertical",
    "arduino_uno":           "Module:Arduino_UNO_SMD",
    "arduino_nano":          "Module:Arduino_Nano",
    "arduino_mega":          "Module:Arduino_Mega2560_THT",
    "arduino_micro":         "Module:Arduino_Micro",
    "esp32":                 "Module:ESP32-WROOM-32",
    "esp8266":               "Module:NodeMCU-v1.0",
    "raspberry_pi_pico":     "Module:RPi_Pico",
    "stm32":                 "Module:STM32_DevBoard",
    "voltage_regulator":     "Package_TO_SOT_THT:TO-220-3_Vertical",
    "lm7805":                "Package_TO_SOT_THT:TO-220-3_Vertical",
    "lm317":                 "Package_TO_SOT_THT:TO-220-3_Vertical",
    "ams1117":               "Package_TO_SOT_THT:SOT-223-3_TabPin2",
    "buck_converter":        "Module:DC-DC_Converter",
    "boost_converter":       "Module:DC-DC_Converter",
    "oled":                  "Display:OLED_SSD1306_128x64",
    "lcd":                   "Display:LCD_16x2_I2C",
    "hc_sr04":               "Sensor:HC-SR04",
    "dht22":                 "Sensor:DHT22",
    "dht11":                 "Sensor:DHT11",
    "bmp280":                "Sensor:BMP280",
    "mpu6050":               "Sensor:MPU-6050",
    "ds18b20":               "Package_TO_SOT_THT:TO-92_Inline",
    "l298n":                 "Module:L298N",
    "drv8825":               "Module:DRV8825",
    "a4988":                 "Module:A4988",
    "servo":                 "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "motor":                 "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "buzzer":                "Buzzer_Beeper:Buzzer_12x9.5RM7.6",
    "connector":             "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
}


# ── Mapeo de tipos de circuito → categorías de stock ─────────────────────────

_TYPE_TO_CATEGORY = {
    "resistor":            "resistencia",
    "resistencia":         "resistencia",
    "capacitor":           "capacitor",
    "led":                 "led",
    "transistor":          "transistor",
    "mosfet":              "transistor",
    "diode":               "diodo",
    "diodo":               "diodo",
    "inductor":            "inductor",
    "relay":               "relay",
    "button":              "pulsador",
    "switch":              "switch",
    "crystal":             "cristal",
    "fuse":                "fusible",
    "arduino_uno":         "microcontrolador",
    "arduino_nano":        "microcontrolador",
    "arduino_mega":        "microcontrolador",
    "esp32":               "microcontrolador",
    "esp8266":             "microcontrolador",
    "raspberry_pi_pico":   "microcontrolador",
    "stm32":               "microcontrolador",
    "voltage_regulator":   "regulador",
    "lm317":               "regulador",
    "7805":                "regulador",
    "opamp":               "opamp",
    "ne555":               "ic",
    "555_timer":           "ic",
    "oled":                "display",
    "lcd":                 "display",
    "servo":               "actuador",
    "motor":               "motor",
    "buzzer":              "buzzer",
    "sensor":              "sensor",
    "ds18b20":             "sensor",
    "bmp280":              "sensor",
    "mpu6050":             "sensor",
}


def _normalize(s: str) -> str:
    return (s or "").lower().strip()


def _parse_value(s: str) -> float:
    """Intenta parsear un string de valor (ej: '220Ω', '100nF', '10k') a float."""
    s = _normalize(s).replace("ω","").replace("ohm","").replace("Ω","")
    multipliers = {"k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12}
    m = re.search(r'([\d.]+)\s*([kmunp]?)', s)
    if not m:
        return 0.0
    num = float(m.group(1))
    mult = multipliers.get(m.group(2), 1.0)
    return num * mult


def _find_stock_match(comp: dict, stock_items: list[dict]) -> dict | None:
    """
    Busca el componente más cercano en el stock.
    Estrategia: primero por nombre exacto, luego por categoría+valor, luego por categoría.
    """
    cname   = _normalize(comp.get("name", ""))
    ctype   = _normalize(comp.get("resolved_type") or comp.get("type") or "")
    cvalue  = _normalize(comp.get("value") or "")
    cat     = _normalize(_TYPE_TO_CATEGORY.get(ctype, ctype))

    # 1. Nombre exacto
    for item in stock_items:
        if _normalize(item.get("name", "")) == cname:
            return item

    # 2. Nombre parcial
    for item in stock_items:
        if cname and cname in _normalize(item.get("name", "")):
            return item

    # 3. Categoría + valor
    if cat and cvalue:
        for item in stock_items:
            if _normalize(item.get("category","")) == cat:
                if cvalue in _normalize(item.get("value","")) or \
                   _normalize(item.get("value","")) in cvalue:
                    return item

    # 4. Categoría + valor numérico más cercano
    if cat and cvalue:
        target_val = _parse_value(cvalue)
        candidates = [i for i in stock_items
                      if _normalize(i.get("category","")) == cat]
        if candidates and target_val > 0:
            closest = min(candidates,
                          key=lambda i: abs(_parse_value(i.get("value","")) - target_val))
            return closest

    # 5. Solo categoría
    if cat:
        for item in stock_items:
            if _normalize(item.get("category","")) == cat:
                return item

    return None


def _group_key(comp: dict) -> tuple:
    """
    Key used to collapse identical components into one BOM line.
    Passives (R/C/L/D/LED) group by (type, normalized_value).
    Everything else groups by (type, name) so each module stays separate.
    """
    ctype = _normalize(comp.get("resolved_type") or comp.get("type") or "")
    cval  = _normalize(comp.get("value") or "")
    _PASSIVES = {"resistor", "resistencia", "res", "capacitor", "cap",
                 "capacitor_electrolytic", "inductor", "led", "led_rgb",
                 "diode", "diodo", "1n4007", "1n5819", "zener"}
    if ctype in _PASSIVES:
        return (ctype, cval)
    return (ctype, _normalize(comp.get("name") or ""))


def _resolve_footprint(comp: dict) -> str:
    """Return footprint string: component field → type map → empty."""
    fp = (comp.get("footprint") or "").strip()
    if fp:
        return fp
    ctype = _normalize(comp.get("resolved_type") or comp.get("type") or "")
    return _TYPE_TO_FOOTPRINT.get(ctype, "")


def generate_bom(circuit: dict, stock_items: list[dict]) -> dict:
    """
    Genera el BOM completo de un circuito.
    Componentes idénticos (mismo tipo + valor) se agrupan en una sola línea
    con qty_needed sumado y line_total = unit_cost × qty.

    Args:
        circuit:     dict con 'name', 'components' (list), 'description'
        stock_items: list de componentes del stock (con unit_cost)

    Returns:
        dict con lines, total_cost, missing_components, by_supplier, summary
    """
    components   = circuit.get("components") or []
    circuit_name = circuit.get("name") or "Circuito sin nombre"

    # ── Group identical components ────────────────────────────────────────────
    groups: dict[tuple, list[dict]] = {}
    for comp in components:
        key = _group_key(comp)
        groups.setdefault(key, []).append(comp)

    lines:       list[dict]        = []
    missing:     list[str]         = []
    by_supplier: dict[str, float]  = {}

    for key, group_comps in groups.items():
        qty    = len(group_comps)
        comp   = group_comps[0]  # representative for stock lookup
        refs   = ", ".join(c.get("id") or c.get("ref") or "?" for c in group_comps)
        cname  = comp.get("name") or comp.get("type") or refs
        cvalue = comp.get("value") or ""
        fp     = _resolve_footprint(comp)

        match = _find_stock_match(comp, stock_items)

        if match:
            unit_cost  = float(match.get("unit_cost") or 0.0)
            line_total = round(unit_cost * qty, 4)
            supplier   = match.get("supplier") or "Sin proveedor"

            lines.append({
                "refs":         refs,
                "name":         cname,
                "value":        cvalue,
                "footprint":    fp or match.get("package") or "",
                "qty_needed":   qty,
                "in_stock":     (match.get("quantity") or 0) >= qty,
                "stock_qty":    match.get("quantity") or 0,
                "stock_name":   match.get("name"),
                "supplier":     supplier,
                "supplier_ref": match.get("supplier_ref") or "",
                "unit_cost":    unit_cost,
                "line_total":   line_total,
                "datasheet":    match.get("datasheet") or "",
            })
            if unit_cost > 0:
                by_supplier[supplier] = by_supplier.get(supplier, 0.0) + line_total
        else:
            label = f"{refs} ({cname}{' ' + cvalue if cvalue else ''})"
            missing.append(label)
            lines.append({
                "refs":         refs,
                "name":         cname,
                "value":        cvalue,
                "footprint":    fp,
                "qty_needed":   qty,
                "in_stock":     False,
                "stock_qty":    0,
                "stock_name":   None,
                "supplier":     None,
                "supplier_ref": "",
                "unit_cost":    0.0,
                "line_total":   0.0,
                "datasheet":    "",
            })

    total_cost  = round(sum(l["line_total"] for l in lines), 4)
    by_supplier = {k: round(v, 4) for k, v in by_supplier.items()}

    n_found   = len(lines) - len(missing)
    n_missing = len(missing)
    n_total   = sum(l["qty_needed"] for l in lines)

    summary = (f"BOM: {n_total} componentes ({len(lines)} líneas) — "
               f"{n_found} líneas en stock, {n_missing} faltantes — "
               f"Costo total: ${total_cost:.2f} USD")

    return {
        "circuit_name":       circuit_name,
        "lines":              lines,
        "total_cost":         total_cost,
        "total_components":   n_total,
        "missing_components": missing,
        "by_supplier":        by_supplier,
        "summary":            summary,
    }


def bom_to_csv(bom: dict) -> str:
    """Convierte un BOM generado a formato CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Refs", "Nombre", "Valor", "Footprint",
        "Qty", "En Stock", "Stock Qty",
        "Proveedor", "Ref Proveedor",
        "Costo Unit (USD)", "Total (USD)", "Datasheet"
    ])

    for line in bom.get("lines", []):
        # Support both old (ref) and new (refs) key names
        refs = line.get("refs") or line.get("ref") or ""
        writer.writerow([
            refs,
            line["name"],
            line.get("value", ""),
            line.get("footprint") or line.get("package") or "",
            line["qty_needed"],
            "Si" if line["in_stock"] else "No",
            line["stock_qty"],
            line.get("supplier") or "",
            line.get("supplier_ref") or "",
            f"{line['unit_cost']:.4f}",
            f"{line['line_total']:.4f}",
            line.get("datasheet") or "",
        ])

    writer.writerow([])
    writer.writerow(["", "", "", "", "", "", "", "", "TOTAL USD",
                     "", f"{bom['total_cost']:.4f}", ""])

    if bom.get("missing_components"):
        writer.writerow([])
        writer.writerow(["FALTANTES:", ", ".join(bom["missing_components"])])

    return output.getvalue()
