"""
Placement Engine — asignación determinista de coordenadas a los componentes.

Reemplaza el placement implícito que hacían los renderers (`tools/eda/layout.py`
+ heurísticas dispersas en `pcb_renderer.py`) por una capa pura sin rendering
ni routing.

Pipeline:
    1. Clasificar cada componente en una zona (MCU / POWER / INPUT / OUTPUT
       / COMM / PASSIVE) usando `registry.category` + overrides por keyword.
    2. Calcular el rectángulo de cada zona dentro del board.
    3. Packing row-major en grid dentro de cada zona, con spacing constante.
    4. Detección de colisiones (defensa final si se cruzan zonas con
       configs custom).
    5. Asignar `Component.placement = PlacementInfo(position, ...)`.

Determinismo:
    - Componentes ordenados alfabéticamente por `ref` antes de packear.
    - Layout de zonas calculado a partir de las dimensiones de board.
    - Sin estado global, sin random.

API:
    place(circuit, options=None) → PlacementResult

Sin SVG. Sin nets físicas. Solo coordenadas.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from tools.eda.component_registry import ComponentSpec, get_registry
from tools.eda.ir import (
    Board,
    Circuit,
    Component,
    Layer,
    PlacementInfo,
    Severity,
    ValidationIssue,
    Vec2,
)


# ────────────────────────────────────────────────────────────────────────────
# Zonas
# ────────────────────────────────────────────────────────────────────────────


class Zone(str, Enum):
    MCU = "mcu"
    POWER = "power"
    INPUT = "input"
    OUTPUT = "output"
    COMM = "comm"
    PASSIVE = "passive"
    UNKNOWN = "unknown"


# Keyword overrides para clasificar dentro de category="ic":
# por defecto los ICs van a OUTPUT (motor drivers, relays, actuadores),
# pero los de comunicación/display caen a COMM.
_COMM_KEYWORDS = (
    "oled", "ssd1306", "lcd",
    "hc05", "hc06", "hc-05", "hc-06",
    "nrf24", "nrf51", "lora", "esp01",
    "rtc", "ds3231", "ds1307",
    "bluetooth", "ble", "wifi_module",
)
_OUTPUT_IC_KEYWORDS = (
    "l298", "drv8825", "a4988", "tb6600",
    "relay", "rele",
    "motor_driver", "h-bridge", "h_bridge",
)
_AC_KEYWORDS = (
    "220", "110", "230", "240", "ac", "mains", "vac", "red ",
)


# ────────────────────────────────────────────────────────────────────────────
# Tamaños por defecto (footprint estimado para placement)
# ────────────────────────────────────────────────────────────────────────────


_DEFAULT_SIZE_BY_CATEGORY: dict[str, Vec2] = {
    "mcu":       Vec2(x=30.0, y=22.0),
    "sensor":    Vec2(x=18.0, y=14.0),
    "display":   Vec2(x=27.0, y=27.0),
    "ic":        Vec2(x=20.0, y=12.0),
    "power":     Vec2(x=18.0, y=15.0),
    "connector": Vec2(x=15.0, y=10.0),
    "passive":   Vec2(x=8.0,  y=4.0),
    "unknown":   Vec2(x=12.0, y=8.0),
}

# Override por type específico cuando el footprint difiere mucho del default.
_SIZE_OVERRIDE_BY_TYPE: dict[str, Vec2] = {
    "arduino_uno":         Vec2(x=53.3, y=68.6),
    "arduino_nano":        Vec2(x=18.0, y=43.0),
    "arduino_mega":        Vec2(x=53.3, y=101.5),
    "esp32":               Vec2(x=27.5, y=51.5),  # DevKit V1
    "esp8266":             Vec2(x=25.0, y=48.0),  # NodeMCU
    "raspberry_pi_pico":   Vec2(x=21.0, y=51.0),
    "stm32":               Vec2(x=22.0, y=53.0),  # Blue Pill
    "lm7805":              Vec2(x=10.4, y=8.7),   # TO-220
    "lm317":               Vec2(x=10.4, y=8.7),
    "ams1117":             Vec2(x=6.5,  y=6.7),   # SOT-223
    "l298n":               Vec2(x=43.0, y=43.0),  # módulo
    "oled_ssd1306":        Vec2(x=27.0, y=27.0),
    "ds3231":              Vec2(x=38.0, y=22.0),
    "relay_module":        Vec2(x=43.0, y=17.0),
    "capacitor_electrolytic": Vec2(x=8.0, y=8.0),
    "fuse":                Vec2(x=20.0, y=8.0),
    "led":                 Vec2(x=5.0,  y=5.0),
    "resistor":            Vec2(x=10.0, y=4.0),
    "diode":               Vec2(x=10.0, y=4.0),
}


# ────────────────────────────────────────────────────────────────────────────
# Options
# ────────────────────────────────────────────────────────────────────────────


class PlacementOptions(BaseModel):
    """Configuración del placement engine.

    El engine puede crecer la board si los componentes no caben en las
    dimensiones iniciales (`auto_grow=True`).
    """
    model_config = ConfigDict(extra="forbid")

    initial_board_width_mm: float = Field(default=120.0, gt=0)
    initial_board_height_mm: float = Field(default=100.0, gt=0)
    margin_mm: float = Field(default=5.0, ge=0)
    component_spacing_mm: float = Field(default=3.0, ge=0)
    auto_grow: bool = True
    grid_mm: float = Field(default=2.54, gt=0)


# ────────────────────────────────────────────────────────────────────────────
# Result
# ────────────────────────────────────────────────────────────────────────────


class PlacementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    circuit: Circuit
    issues: list[ValidationIssue] = Field(default_factory=list)
    bbox_used: Vec2  # ancho/alto realmente ocupado (incluyendo márgenes)
    zone_assignments: dict[str, str] = Field(default_factory=dict)  # ref → zone


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────


def place(
    circuit: Circuit,
    options: PlacementOptions | None = None,
) -> PlacementResult:
    options = options or PlacementOptions()
    registry = get_registry()
    issues: list[ValidationIssue] = []

    # 1. Clasificar.
    zone_of: dict[str, Zone] = {}
    spec_of: dict[str, ComponentSpec | None] = {}
    for c in circuit.components:
        spec = registry.get(c.type)
        spec_of[c.ref] = spec
        zone_of[c.ref] = _classify_zone(c, spec)

    # 2. Tamaños.
    size_of: dict[str, Vec2] = {
        c.ref: _size_of(c, spec_of[c.ref]) for c in circuit.components
    }

    # 3. Calcular layout de zonas (rectángulos).
    board_w = options.initial_board_width_mm
    board_h = options.initial_board_height_mm

    # Si auto_grow, estimar mínimos por zona y crecer la board si hace falta.
    components_by_zone: dict[Zone, list[Component]] = {z: [] for z in Zone}
    for c in circuit.components:
        components_by_zone[zone_of[c.ref]].append(c)
    for z in components_by_zone:
        components_by_zone[z].sort(key=lambda c: c.ref)

    if options.auto_grow:
        board_w, board_h = _grow_board_for_zones(
            components_by_zone, size_of, options, board_w, board_h
        )

    layout = _compute_zone_rectangles(board_w, board_h, options)

    # 4. Pack componentes dentro de cada zona.
    placements: dict[str, Vec2] = {}
    for zone, comps in components_by_zone.items():
        if not comps:
            continue
        rect = layout.get(zone)
        if rect is None:  # Zone.UNKNOWN
            rect = layout[Zone.PASSIVE]  # fallback
            issues.append(ValidationIssue(
                code="ZONE_UNKNOWN_FALLBACK",
                severity=Severity.INFO,
                message=f"{len(comps)} componente(s) sin zona asignada — "
                        f"colocados en zona PASSIVE.",
                rule="placement_engine",
            ))
        positions, overflow = _pack_grid(
            comps, size_of, rect, options
        )
        if overflow:
            issues.append(ValidationIssue(
                code="ZONE_OVERFLOW",
                severity=Severity.WARNING,
                message=f"Zona '{zone.value}' overflow: {overflow} "
                        f"componente(s) no encajaron en el rectángulo.",
                rule="placement_engine",
            ))
        placements.update(positions)

    # 5. Validar ausencia de colisiones (paranoia — el packer no debería
    #    generar overlaps, pero zonas adyacentes podrían tocarse en bordes).
    overlaps = _detect_overlaps(placements, size_of)
    for ref_a, ref_b in overlaps:
        issues.append(ValidationIssue(
            code="PLACEMENT_OVERLAP",
            severity=Severity.WARNING,
            message=f"Overlap detectado: {ref_a} y {ref_b} se superponen.",
            rule="placement_engine",
        ))

    # 6. Snap to grid.
    grid = options.grid_mm
    for ref in placements:
        p = placements[ref]
        placements[ref] = Vec2(
            x=round(p.x / grid) * grid,
            y=round(p.y / grid) * grid,
        )

    # 7. Aplicar al circuito.
    new_components = []
    for c in circuit.components:
        if c.ref in placements:
            new_components.append(c.model_copy(update={
                "placement": PlacementInfo(position=placements[c.ref]),
            }))
        else:
            new_components.append(c)

    bbox = _compute_bbox(placements, size_of, options.margin_mm)
    new_board = circuit.board or Board(
        width_mm=max(board_w, bbox.x),
        height_mm=max(board_h, bbox.y),
        layers=[Layer.F_CU, Layer.B_CU],
    )
    new_circuit = circuit.model_copy(update={
        "components": new_components,
        "board": new_board,
    })

    return PlacementResult(
        circuit=new_circuit,
        issues=issues,
        bbox_used=bbox,
        zone_assignments={ref: z.value for ref, z in zone_of.items()},
    )


# ────────────────────────────────────────────────────────────────────────────
# Clasificación
# ────────────────────────────────────────────────────────────────────────────


def _classify_zone(component: Component, spec: ComponentSpec | None) -> Zone:
    """Asigna zona usando registry.category + overrides por keyword."""
    cat = spec.category if spec else None

    if cat == "mcu":
        return Zone.MCU
    if cat == "power":
        return Zone.POWER
    if cat == "sensor":
        return Zone.INPUT
    if cat == "display":
        return Zone.COMM

    # Búsqueda por keyword en type/value para los casos ambiguos.
    blob = (component.type + " " + (component.value or "")).lower()

    if cat == "ic":
        if any(kw in blob for kw in _OUTPUT_IC_KEYWORDS):
            return Zone.OUTPUT
        if any(kw in blob for kw in _COMM_KEYWORDS):
            return Zone.COMM
        return Zone.OUTPUT  # default ICs → output

    if cat == "connector":
        if any(kw in blob for kw in _AC_KEYWORDS):
            return Zone.POWER
        return Zone.OUTPUT

    if cat == "passive":
        return Zone.PASSIVE

    return Zone.UNKNOWN


def _size_of(component: Component, spec: ComponentSpec | None) -> Vec2:
    """Tamaño del componente para placement (mm)."""
    if component.type in _SIZE_OVERRIDE_BY_TYPE:
        return _SIZE_OVERRIDE_BY_TYPE[component.type]
    cat = spec.category if spec else "unknown"
    return _DEFAULT_SIZE_BY_CATEGORY.get(cat, _DEFAULT_SIZE_BY_CATEGORY["unknown"])


# ────────────────────────────────────────────────────────────────────────────
# Layout de zonas
# ────────────────────────────────────────────────────────────────────────────


# Layout fraccional dentro del área útil (board − margen):
#
#   ┌────────────── POWER ──────────────┬──── COMM ────┐
#   │                                    │              │
#   ├──────┬─────────────────────┬───────┴──────────────┤
#   │      │                     │                      │
#   │INPUT │      MCU            │       OUTPUT         │
#   │      │                     │                      │
#   ├──────┴─────────────────────┴──────────────────────┤
#   │                  PASSIVE                          │
#   └───────────────────────────────────────────────────┘
#
# Coords fraccionales (x, y, w, h) en [0,1].

_ZONE_FRACTIONS: dict[Zone, tuple[float, float, float, float]] = {
    Zone.POWER:   (0.00, 0.00, 0.70, 0.20),
    Zone.COMM:    (0.70, 0.00, 0.30, 0.30),
    Zone.INPUT:   (0.00, 0.20, 0.25, 0.55),
    Zone.MCU:     (0.25, 0.20, 0.45, 0.55),
    Zone.OUTPUT:  (0.70, 0.30, 0.30, 0.45),
    Zone.PASSIVE: (0.00, 0.75, 1.00, 0.25),
}


class _Rect:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h


def _compute_zone_rectangles(
    board_w: float, board_h: float, options: PlacementOptions,
) -> dict[Zone, _Rect]:
    m = options.margin_mm
    usable_w = max(0.0, board_w - 2 * m)
    usable_h = max(0.0, board_h - 2 * m)
    out: dict[Zone, _Rect] = {}
    for zone, (fx, fy, fw, fh) in _ZONE_FRACTIONS.items():
        out[zone] = _Rect(
            x=m + fx * usable_w,
            y=m + fy * usable_h,
            w=fw * usable_w,
            h=fh * usable_h,
        )
    return out


# ────────────────────────────────────────────────────────────────────────────
# Auto-grow
# ────────────────────────────────────────────────────────────────────────────


def _grow_board_for_zones(
    components_by_zone: dict[Zone, list[Component]],
    size_of: dict[str, Vec2],
    options: PlacementOptions,
    init_w: float,
    init_h: float,
) -> tuple[float, float]:
    """Crece la board hasta que todas las zonas con componentes encajen
    razonablemente. Estima el área ocupada por zona y compara contra el
    rectángulo fraccional disponible.
    """
    w, h = init_w, init_h
    spacing = options.component_spacing_mm

    # Iterar hasta convergencia (max 8 iteraciones de seguridad).
    for _ in range(8):
        rects = _compute_zone_rectangles(w, h, options)
        need_grow = False
        for zone, comps in components_by_zone.items():
            if not comps or zone == Zone.UNKNOWN:
                continue
            rect = rects[zone]
            if not _zone_fits(comps, size_of, rect, spacing):
                need_grow = True
                break
        if not need_grow:
            return w, h
        w *= 1.25
        h *= 1.25
    return w, h


def _zone_fits(
    comps: list[Component],
    size_of: dict[str, Vec2],
    rect: _Rect,
    spacing: float,
) -> bool:
    """¿Caben los componentes packeados row-major en el rect?"""
    if rect.w <= 0 or rect.h <= 0:
        return False
    cur_x = 0.0
    cur_y = 0.0
    row_h = 0.0
    for c in comps:
        s = size_of[c.ref]
        if cur_x + s.x > rect.w and cur_x > 0:
            cur_x = 0.0
            cur_y += row_h + spacing
            row_h = 0.0
        if cur_y + s.y > rect.h:
            return False
        cur_x += s.x + spacing
        if s.y > row_h:
            row_h = s.y
    return True


# ────────────────────────────────────────────────────────────────────────────
# Packing
# ────────────────────────────────────────────────────────────────────────────


def _pack_grid(
    comps: list[Component],
    size_of: dict[str, Vec2],
    rect: _Rect,
    options: PlacementOptions,
) -> tuple[dict[str, Vec2], int]:
    """Pack row-major dentro de `rect`. Componentes pre-ordenados.

    Devuelve (placements, overflow_count).
    """
    placements: dict[str, Vec2] = {}
    spacing = options.component_spacing_mm
    cur_x = 0.0
    cur_y = 0.0
    row_h = 0.0
    overflow = 0
    for c in comps:
        s = size_of[c.ref]
        if cur_x + s.x > rect.w and cur_x > 0:
            cur_x = 0.0
            cur_y += row_h + spacing
            row_h = 0.0
        if cur_y + s.y > rect.h:
            overflow += 1
            continue
        # `position` es el centro del componente — convención KiCad.
        placements[c.ref] = Vec2(
            x=rect.x + cur_x + s.x / 2.0,
            y=rect.y + cur_y + s.y / 2.0,
        )
        cur_x += s.x + spacing
        if s.y > row_h:
            row_h = s.y
    return placements, overflow


# ────────────────────────────────────────────────────────────────────────────
# Detección de colisiones
# ────────────────────────────────────────────────────────────────────────────


def _detect_overlaps(
    placements: dict[str, Vec2],
    size_of: dict[str, Vec2],
) -> list[tuple[str, str]]:
    """Pares de refs cuyos bounding boxes se superponen."""
    refs = sorted(placements.keys())
    overlaps: list[tuple[str, str]] = []
    for i, ra in enumerate(refs):
        pa = placements[ra]
        sa = size_of[ra]
        ax0, ax1 = pa.x - sa.x / 2, pa.x + sa.x / 2
        ay0, ay1 = pa.y - sa.y / 2, pa.y + sa.y / 2
        for rb in refs[i + 1:]:
            pb = placements[rb]
            sb = size_of[rb]
            bx0, bx1 = pb.x - sb.x / 2, pb.x + sb.x / 2
            by0, by1 = pb.y - sb.y / 2, pb.y + sb.y / 2
            # AABB overlap (excluye contacto exacto en el borde).
            if ax1 > bx0 and bx1 > ax0 and ay1 > by0 and by1 > ay0:
                overlaps.append((ra, rb))
    return overlaps


def _compute_bbox(
    placements: dict[str, Vec2],
    size_of: dict[str, Vec2],
    margin: float,
) -> Vec2:
    if not placements:
        return Vec2(x=margin * 2, y=margin * 2)
    max_x = 0.0
    max_y = 0.0
    for ref, pos in placements.items():
        s = size_of[ref]
        max_x = max(max_x, pos.x + s.x / 2)
        max_y = max(max_y, pos.y + s.y / 2)
    return Vec2(x=max_x + margin, y=max_y + margin)
