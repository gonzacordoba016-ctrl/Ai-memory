"""Routing — wire/trace path computation. No drawing.

Schematic side (Option B port):
  - route_orthogonal: 2-segment ortho path between two points.
  - Full schematic net routing currently lives in SchematicRenderer._draw_connections;
    it stays there until extracted in a follow-up.

PCB side:
  - compute_pcb_routing / route_traces: Manhattan 2-layer trace routing.
  - trace_color: per-net stroke color.
"""

from typing import Dict, List, Tuple


def route_orthogonal(p1: Tuple[int, int], p2: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Returns 4-point orthogonal path: (x1,y1) -> (mid,y1) -> (mid,y2) -> (x2,y2)."""
    x1, y1 = p1
    x2, y2 = p2
    mid_x = (x1 + x2) // 2
    return [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]


def route_schematic(
    nets: List[Dict],
    positions: Dict[str, Tuple[float, float]],
) -> List[Dict]:
    """Return schematic wire segments, junctions and directional labels.

    Nets with more than three positioned nodes use a shared vertical bus.
    Smaller nets keep simple orthogonal point-to-point routing.
    """
    routed: List[Dict] = []
    for net in nets:
        name = net.get("name", "")
        coords = [
            positions[node.split(".")[0]]
            for node in net.get("nodes", [])
            if node.split(".")[0] in positions
        ]
        if len(coords) < 2:
            continue

        cx = sum(p[0] for p in coords) / len(coords)
        cy = sum(p[1] for p in coords) / len(coords)

        if len(coords) > 3:
            bus_x = cx
            y_min = min(p[1] for p in coords)
            y_max = max(p[1] for p in coords)
            routed.append({
                "kind": "wire", "net": name,
                "points": [(bus_x, y_min), (bus_x, y_max)],
            })
            for x, y in coords:
                routed.append({
                    "kind": "wire", "net": name,
                    "points": [(x, y), (bus_x, y)],
                })
                routed.append({
                    "kind": "junction", "net": name,
                    "point": (bus_x, y),
                })
                direction = "right" if x <= cx else "left"
                routed.append({
                    "kind": "label", "net": name,
                    "point": (x, y), "direction": direction,
                })
        else:
            anchor = coords[0]
            for x, y in coords[1:]:
                routed.append({
                    "kind": "wire", "net": name,
                    "points": route_orthogonal(anchor, (x, y)),
                })
            if len(coords) == 3:
                routed.append({"kind": "junction", "net": name, "point": anchor})
            for x, y in coords:
                direction = "right" if x <= cx else "left"
                routed.append({
                    "kind": "label", "net": name,
                    "point": (x, y), "direction": direction,
                })
    return routed


def route_traces(nets: List[Dict],
                 positions: Dict[str, Tuple[float, float]]) -> List[Dict]:
    """Returns PCB trace segments: {x1,y1,x2,y2,net,layer,width}.

    Manhattan routing. Trace width by electrical role:
      GND=1.0mm, VCC/PWR=0.5mm, I2C/SPI/UART=0.3mm, signal=0.25mm.
    Power nets on bottom copper; signals on top copper.
    """
    traces = []
    for net in nets:
        name = net.get("name", "")
        nl   = name.lower()
        nodes = net.get("nodes", [])

        if any(v in nl for v in ("gnd", "ground")):
            width, layer = 1.0, "bottom"
        elif any(v in nl for v in ("vcc", "5v", "3v3", "vin", "vdd", "power", "vbat")):
            width, layer = 0.5, "bottom"
        elif any(v in nl for v in ("i2c", "sda", "scl", "spi", "mosi", "miso", "sck",
                                   "uart", "tx", "rx")):
            width, layer = 0.3, "top"
        else:
            width, layer = 0.25, "top"

        coords = [positions[n.split(".")[0]]
                  for n in nodes if n.split(".")[0] in positions]

        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            mid_x = (x1 + x2) / 2
            alt = "bottom" if layer == "top" else "top"
            if abs(mid_x - x1) >= 0.001:
                traces.append({"x1": x1,    "y1": y1, "x2": mid_x, "y2": y1,
                               "net": name, "layer": layer, "width": width})
            if abs(y2 - y1) >= 0.001:
                traces.append({"x1": mid_x, "y1": y1, "x2": mid_x, "y2": y2,
                               "net": name, "layer": alt,   "width": width})
            if abs(x2 - mid_x) >= 0.001:
                traces.append({"x1": mid_x, "y1": y2, "x2": x2,    "y2": y2,
                               "net": name, "layer": layer, "width": width})
    return traces


def compute_pcb_routing(
    components: List[Dict], nets: List[Dict],
    placement: Dict[str, Tuple[float, float]], sheet: Dict
) -> List[Dict]:
    """Returns PCB trace segments (length > 0.001mm). Pure routing, no drawing."""
    return route_traces(nets, placement)


def trace_color(layer: str, net_name: str) -> str:
    """SVG stroke color for a trace."""
    nl = net_name.lower()
    if any(v in nl for v in ("gnd", "ground")):
        return "#b87333"
    if any(v in nl for v in ("vcc", "5v", "3v3", "vin", "vdd")):
        return "#cc3333" if layer == "top" else "#b87333"
    return "#daa520" if layer == "top" else "#c09030"
