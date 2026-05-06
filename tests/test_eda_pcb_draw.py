"""Tests for tools.eda.pcb_draw — verifies PCBRenderer parity with the original."""

import pytest


def test_pcb_draw_imports_cleanly():
    from tools.eda import pcb_draw  # noqa: F401
    from tools.eda.pcb_draw import PCBRenderer
    assert PCBRenderer is not None


def test_render_returns_svg_string():
    from tools.eda.pcb_draw import PCBRenderer
    circuit = {
        "name": "Test",
        "components": [
            {"id": "U1", "type": "esp32"},
            {"id": "R1", "type": "resistor"},
        ],
        "nets": [
            {"name": "VCC", "nodes": ["U1.1", "R1.1"]},
        ],
    }
    svg = PCBRenderer().render_pcb_svg(circuit)
    assert isinstance(svg, str)
    assert "svg" in svg.lower()


@pytest.mark.parametrize("circuit", [
    {"name": "Empty", "components": [], "nets": []},
    {"name": "MCU only",
     "components": [{"id": "U1", "type": "esp32"}],
     "nets": []},
    {"name": "Relay group",
     "components": [
         {"id": "RL1", "type": "relay"},
         {"id": "D_fly1", "type": "diode"},
         {"id": "R1", "type": "resistor", "value": "1k"},
         {"id": "U1", "type": "esp32"},
     ],
     "nets": [
         {"name": "VCC", "nodes": ["U1.1", "RL1.1"]},
         {"name": "GND", "nodes": ["U1.2", "RL1.2"]},
     ]},
    {"name": "AC + LV",
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
     ]},
])
def test_pcb_parity_with_original(circuit):
    from tools.eda.pcb_draw import PCBRenderer as NewR
    from tools.pcb_renderer import PCBRenderer as OldR

    svg_new = NewR().render_pcb_svg(circuit)
    svg_old = OldR().render_pcb_svg(circuit)

    assert svg_new == svg_old, (
        f"PCB SVG mismatch for circuit '{circuit.get('name')}':\n"
        f"  new len={len(svg_new)}, old len={len(svg_old)}"
    )
