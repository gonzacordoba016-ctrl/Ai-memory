"""
Design rules shared between schematic and PCB renderers.
Mirrors KiCad's internal separation of layout data from drawing.
"""

MARGIN_MM = 10.0
TITLE_BLOCK_H = 32.0  # height of title block strip excluded from drawing area

# Engineering frame (ISO 7200 / ANSI Y14.1 inspired)
BORDER_MM        = 5.0    # gap between paper edge and outer frame
ZONE_REF_MM      = 6.0    # zone reference band (between outer and inner frame)
TITLE_BLOCK_W_MM = 180.0  # title block width (corner-anchored, bottom-right)
TITLE_BLOCK_H_MM = 32.0   # title block height
ZONE_COLS        = 8      # 1..8 columns
ZONE_ROWS        = 4      # A..D rows


def usable_drawing_area(sheet: dict) -> tuple:
    """Returns (x_mm, y_mm, w_mm, h_mm) of the drawing area inside the inner frame.

    Excludes outer border, zone reference band, and the bottom title-block strip.
    """
    inset = BORDER_MM + ZONE_REF_MM
    return (
        inset,
        inset,
        sheet["w"] - 2 * inset,
        sheet["h"] - 2 * inset - TITLE_BLOCK_H_MM,
    )


PCB_CLEARANCE = {
    "signal":  0.2,   # mm between signal traces
    "power":   0.5,   # mm between power traces
    "pad_pad": 0.3,   # mm between pads
}

ZONE_ORDER = ["ac", "power", "mcu", "sensor", "other", "relay", "output"]


def get_sheet_size(n_components: int) -> dict:
    """Return sheet dimensions based on component count."""
    if n_components <= 8:
        return {"name": "A4", "w": 297, "h": 210, "grid": 2.54}
    elif n_components <= 20:
        return {"name": "A3", "w": 420, "h": 297, "grid": 2.54}
    elif n_components <= 40:
        return {"name": "A2", "w": 594, "h": 420, "grid": 2.54}
    else:
        return {"name": "A1", "w": 841, "h": 594, "grid": 2.54}


def snap_to_grid(x: float, y: float, grid: float) -> tuple:
    """Snap coordinates to the nearest grid point."""
    return (round(x / grid) * grid, round(y / grid) * grid)
