# tests/conftest.py
import os
import sys
import tempfile
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SAMPLE_CIRCUIT = {
    "name": "TEST_LED_Blinker",
    "description": "Circuito de prueba con LED y Arduino",
    "components": [
        {"id": "U1", "name": "Arduino Uno", "type": "arduino_uno", "value": "", "unit": ""},
        {"id": "R1", "name": "Resistencia 220Ω", "type": "resistor", "value": "220", "unit": "Ω"},
        {"id": "D1", "name": "LED Rojo", "type": "led", "value": "", "unit": ""},
    ],
    "nets": [
        {"name": "VCC", "nodes": ["U1.5V", "D1.A"]},
        {"name": "GND", "nodes": ["U1.GND", "R1.2"]},
        {"name": "NET_LED", "nodes": ["U1.13", "R1.1", "D1.K"]},
    ],
    "power": "5V USB",
    "warnings": [],
}

KICAD_SCH_SAMPLE = """\
(kicad_sch (version 20230121) (generator eeschema)
  (title_block
    (title "Test Schematic")
  )
  (symbol (lib_id "Device:R") (at 100 50 0) (unit 1)
    (property "Reference" "R1" (at 102 47 0))
    (property "Value" "10k" (at 102 53 0))
  )
  (symbol (lib_id "Device:LED") (at 150 50 0) (unit 1)
    (property "Reference" "D1" (at 152 47 0))
    (property "Value" "LED" (at 152 53 0))
  )
  (net_label (at 100 50 0) "VCC")
  (net_label (at 100 70 0) "GND")
)
"""

EAGLE_SCH_SAMPLE = """\
<?xml version="1.0" encoding="utf-8"?>
<eagle version="9.6.2">
  <drawing>
    <schematic>
      <parts>
        <part name="R1" library="rcl" deviceset="R-EU" device="R0402" value="10k"/>
        <part name="C1" library="rcl" deviceset="C-EU" device="C0402" value="100nF"/>
        <part name="U1" library="atmel" deviceset="ATMEGA328" device="PU" value="ATMEGA328P"/>
      </parts>
      <sheets>
        <sheet>
          <nets>
            <net name="VCC">
              <segment>
                <pinref part="R1" gate="G$1" pin="1"/>
                <pinref part="U1" gate="G$1" pin="VCC"/>
              </segment>
            </net>
            <net name="GND">
              <segment>
                <pinref part="R1" gate="G$1" pin="2"/>
                <pinref part="C1" gate="G$1" pin="2"/>
              </segment>
            </net>
          </nets>
        </sheet>
      </sheets>
    </schematic>
  </drawing>
</eagle>
"""


@pytest.fixture
def sample_circuit():
    return dict(SAMPLE_CIRCUIT)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """CircuitDesignManager usando DB temporal (no contamina la real)."""
    db_file = str(tmp_path / "test_circuits.db")
    monkeypatch.setenv("MEMORY_DB_PATH", db_file)
    # Patch SQL_DB_PATH inside the module
    import database.circuit_design as cd_mod
    original = cd_mod.DB_PATH
    cd_mod.DB_PATH = db_file
    yield db_file
    cd_mod.DB_PATH = original


@pytest.fixture
def mgr(tmp_db):
    from database.circuit_design import CircuitDesignManager
    return CircuitDesignManager()
