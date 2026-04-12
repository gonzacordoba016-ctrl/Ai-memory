# tools/bom_generator.py
#
# Generador de BOM (Bill of Materials) con costos para Stratum.
# Mapea los componentes de un circuito contra el stock del ingeniero.

from __future__ import annotations
import csv
import io
import re
from typing import Any


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


def generate_bom(circuit: dict, stock_items: list[dict]) -> dict:
    """
    Genera el BOM completo de un circuito.

    Args:
        circuit:     dict con 'name', 'components' (list), 'description'
        stock_items: list de componentes del stock (con unit_cost)

    Returns:
        dict con lines, total_cost, missing_components, by_supplier, summary
    """
    components  = circuit.get("components") or []
    circuit_name = circuit.get("name") or "Circuito sin nombre"

    lines:    list[dict] = []
    missing:  list[str]  = []
    by_supplier: dict[str, float] = {}

    for comp in components:
        cid    = comp.get("id") or comp.get("ref") or "?"
        cname  = comp.get("name") or comp.get("type") or cid
        cvalue = comp.get("value") or ""
        ctype  = comp.get("resolved_type") or comp.get("type") or ""
        cpkg   = comp.get("footprint") or ""

        match = _find_stock_match(comp, stock_items)

        if match:
            unit_cost  = float(match.get("unit_cost") or 0.0)
            line_total = unit_cost  # qty_needed = 1 por componente
            supplier   = match.get("supplier") or "Sin proveedor"

            lines.append({
                "ref":          cid,
                "name":         cname,
                "value":        cvalue,
                "package":      cpkg or match.get("package") or "",
                "qty_needed":   1,
                "in_stock":     (match.get("quantity") or 0) > 0,
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
            missing.append(f"{cid} ({cname}{' '+cvalue if cvalue else ''})")
            lines.append({
                "ref":          cid,
                "name":         cname,
                "value":        cvalue,
                "package":      cpkg,
                "qty_needed":   1,
                "in_stock":     False,
                "stock_qty":    0,
                "stock_name":   None,
                "supplier":     None,
                "supplier_ref": "",
                "unit_cost":    0.0,
                "line_total":   0.0,
                "datasheet":    "",
            })

    total_cost = sum(l["line_total"] for l in lines)
    total_cost = round(total_cost, 4)
    by_supplier = {k: round(v, 4) for k, v in by_supplier.items()}

    n_found   = len(lines) - len(missing)
    n_missing = len(missing)

    summary = (f"BOM: {len(lines)} componentes — "
               f"{n_found} en stock, {n_missing} faltantes — "
               f"Costo total: ${total_cost:.2f} USD")

    return {
        "circuit_name":       circuit_name,
        "lines":              lines,
        "total_cost":         total_cost,
        "total_components":   len(lines),
        "missing_components": missing,
        "by_supplier":        by_supplier,
        "summary":            summary,
    }


def bom_to_csv(bom: dict) -> str:
    """Convierte un BOM generado a formato CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Ref", "Nombre", "Valor", "Package",
        "Qty", "En Stock", "Stock Qty",
        "Proveedor", "Ref Proveedor",
        "Costo Unit (USD)", "Total (USD)", "Datasheet"
    ])

    for line in bom.get("lines", []):
        writer.writerow([
            line["ref"],
            line["name"],
            line.get("value", ""),
            line.get("package", ""),
            line["qty_needed"],
            "Si" if line["in_stock"] else "No",
            line["stock_qty"],
            line.get("supplier") or "",
            line.get("supplier_ref") or "",
            f"{line['unit_cost']:.4f}",
            f"{line['line_total']:.4f}",
            line.get("datasheet") or "",
        ])

    # Totales
    writer.writerow([])
    writer.writerow(["", "", "", "", "", "", "", "", "TOTAL USD",
                     "", f"{bom['total_cost']:.4f}", ""])

    if bom.get("missing_components"):
        writer.writerow([])
        writer.writerow(["FALTANTES:", ", ".join(bom["missing_components"])])

    return output.getvalue()
