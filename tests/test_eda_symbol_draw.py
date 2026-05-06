"""Tests for tools.eda.symbol_draw — verifies SchematicRenderer parity with the
original schematic_renderer.SchematicRenderer.

The two implementations must produce byte-equivalent SVG for the same input.
"""

import pytest


def test_symbol_draw_imports_cleanly():
    from tools.eda import symbol_draw  # noqa: F401
    from tools.eda.symbol_draw import SchematicRenderer
    assert SchematicRenderer is not None


def test_render_returns_svg_string():
    from tools.eda.symbol_draw import SchematicRenderer
    circuit = {
        "name": "Test",
        "components": [
            {"id": "U1", "type": "esp32", "name": "MCU"},
            {"id": "R1", "type": "resistor", "value": "10k"},
            {"id": "LED1", "type": "led", "color": "red"},
        ],
        "nets": [
            {"name": "VCC", "nodes": ["U1.1", "R1.1"]},
            {"name": "GND", "nodes": ["U1.2", "LED1.2"]},
        ],
    }
    svg = SchematicRenderer().render_schematic_svg(circuit)
    assert isinstance(svg, str)
    assert svg.startswith("<")
    assert "svg" in svg.lower()


@pytest.mark.parametrize("circuit", [
    {
        "name": "Empty",
        "components": [],
        "nets": [],
    },
    {
        "name": "MCU only",
        "components": [{"id": "U1", "type": "esp32", "name": "MCU"}],
        "nets": [],
    },
    {
        "name": "Relay group",
        "components": [
            {"id": "RL1", "type": "relay"},
            {"id": "D_fly1", "type": "diode"},
            {"id": "R1", "type": "resistor", "value": "1k"},
            {"id": "U1", "type": "esp32"},
        ],
        "nets": [
            {"name": "VCC", "nodes": ["U1.1", "RL1.1"]},
            {"name": "GND", "nodes": ["U1.2", "RL1.2"]},
            {"name": "CTRL", "nodes": ["U1.3", "R1.1"]},
        ],
    },
    {
        "name": "AC + LV",
        "components": [
            {"id": "T1", "type": "transformer"},
            {"id": "BR1", "type": "bridge_rectifier"},
            {"id": "U1", "type": "esp32"},
            {"id": "S1", "type": "bmp280"},
            {"id": "J_OUT", "type": "connector", "name": "Salida"},
        ],
        "nets": [
            {"name": "AC_L", "nodes": ["T1.1", "BR1.1"]},
            {"name": "VCC", "nodes": ["U1.1", "S1.1"]},
        ],
    },
])
def test_parity_with_original(circuit):
    """SchematicRenderer in symbol_draw must produce same SVG as the original."""
    from tools.eda.symbol_draw import SchematicRenderer as NewR
    from tools.schematic_renderer import SchematicRenderer as OldR

    svg_new = NewR().render_schematic_svg(circuit)
    svg_old = OldR().render_schematic_svg(circuit)

    assert svg_new == svg_old, (
        f"SVG mismatch for circuit '{circuit.get('name')}':\n"
        f"  new len={len(svg_new)}, old len={len(svg_old)}"
    )
