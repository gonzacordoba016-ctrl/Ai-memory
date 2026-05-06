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
