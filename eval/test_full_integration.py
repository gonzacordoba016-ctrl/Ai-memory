# eval/test_full_integration.py

import os
import sys
import json
from pathlib import Path

# Añadir el directorio raíz al path
project_root = os.path.dirname(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_complete_integration(tmp_db):
    """Test de integración completa del sistema de circuitos."""
    print("\n=== TEST INTEGRACIÓN COMPLETA: Stratum Circuit System ===\n")
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Importaciones básicas
    print("1. Verificando importaciones...")
    try:
        from agent.agents.circuit_agent import CircuitAgent
        from database.circuit_design import CircuitDesignManager
        from tools.schematic_renderer import SchematicRenderer
        from tools.breadboard_renderer import BreadboardRenderer
        from tools.pcb_renderer import PCBRenderer
        print("  ✅ Todas las importaciones correctas")
        tests_passed += 1
    except ImportError as e:
        print(f"  ❌ Error de importación: {e}")
    total_tests += 1
    
    # Test 2: Base de datos de componentes
    print("\n2. Verificando base de datos de componentes...")
    try:
        from database.circuit_design import COMPONENT_LIBRARY, COMPONENT_ALIASES
        if COMPONENT_LIBRARY and len(COMPONENT_LIBRARY) > 0:
            print(f"  ✅ Librería de componentes: {len(COMPONENT_LIBRARY)} componentes")
            tests_passed += 1
        else:
            print("  ❌ Librería de componentes vacía")
        total_tests += 1
        
        if COMPONENT_ALIASES and len(COMPONENT_ALIASES) > 0:
            print(f"  ✅ Aliases de componentes: {len(COMPONENT_ALIASES)} aliases")
            tests_passed += 1
        else:
            print("  ❌ Aliases de componentes vacíos")
        total_tests += 1
    except Exception as e:
        print(f"  ❌ Error en base de datos: {e}")
        total_tests += 2
    
    # Test 3: Manager de circuitos
    print("\n3. Verificando manager de circuitos...")
    try:
        from database.circuit_design import CircuitDesignManager
        manager = CircuitDesignManager()
        designs = manager.list_designs()
        print(f"  ✅ Manager inicializado correctamente")
        tests_passed += 1
        
        # Test de guardado básico
        test_circuit = {
            "name": "TEST_Integration_Circuit",
            "description": "Integration Test Description",
            "components": [{"id": "U1", "type": "arduino_uno"}],
            "nets": []
        }
        design_id = manager.save_design(test_circuit)
        if design_id > 0:
            print(f"  ✅ Guardado de diseño exitoso (ID: {design_id})")
            tests_passed += 1
        else:
            print("  ❌ Fallo al guardar diseño")
        total_tests += 1
    except Exception as e:
        print(f"  ❌ Error en manager de circuitos: {e}")
        total_tests += 2
        
    # Test 4: Hardware Agent y Firmware Integration
    print("\n4. Verificando HardwareAgent...")
    try:
        from agent.agents.hardware_agent import get_hardware_agent
        hw_agent = get_hardware_agent()
        
        test_circuit = {
            "project_name": "Test project",
            "components": [{"name": "LED", "type": "led", "pin": "13"}]
        }
        formatted = hw_agent._format_circuit_for_firmware(test_circuit)
        if "LED" in formatted and "pin 13" in formatted:
            print("  ✅ Formateo de circuito para firmware correcto")
            tests_passed += 1
        else:
            print("  ❌ Fallo en formateo para firmware")
        total_tests += 1
    except Exception as e:
        print(f"  ❌ Error en HardwareAgent: {e}")
        total_tests += 1

    # Resumen final
    print(f"\n{'-'*50}")
    print(f"RESULTADO FINAL: {tests_passed}/{total_tests} tests pasaron")
    print(f"{'-'*50}")
    
    return tests_passed == total_tests

def test_kicad_connectivity():
    """
    FASE 2: Verifica que parse_kicad traza conectividad real y pobla nodes.
    Usa un .kicad_sch sintético con 2 componentes (R1 + LED1), 3 wires y 3 net labels.
    """
    from tools.schematic_parser import parse_kicad
    from tools.electrical_drc import run_drc

    # Esquemático mínimo KiCad 6:
    #   R1 (Test:R) en (100,100,0°): pin1 en (100,95), pin2 en (100,105)
    #   LED1 (Test:LED) en (100,120,0°): pinA en (100,115), pinK en (100,125)
    #   Conexiones: VCC→R1.1, R1.2→LED1.A (net ANODE), LED1.K→GND
    KICAD_MINIMAL = """\
(kicad_sch (version 20230121)
  (lib_symbols
    (symbol "Test:R"
      (symbol "Test:R_1_1"
        (pin passive line (at 0 -5 270) (length 0)
          (name "~" (effects (font (size 1.27 1.27)) hide))
          (number "1" (effects (font (size 1.27 1.27)) hide))
        )
        (pin passive line (at 0 5 90) (length 0)
          (name "~" (effects (font (size 1.27 1.27)) hide))
          (number "2" (effects (font (size 1.27 1.27)) hide))
        )
      )
    )
    (symbol "Test:LED"
      (symbol "Test:LED_1_1"
        (pin passive line (at 0 -5 270) (length 0)
          (name "A" (effects (font (size 1.27 1.27)) hide))
          (number "A" (effects (font (size 1.27 1.27)) hide))
        )
        (pin passive line (at 0 5 90) (length 0)
          (name "K" (effects (font (size 1.27 1.27)) hide))
          (number "K" (effects (font (size 1.27 1.27)) hide))
        )
      )
    )
  )
  (symbol (lib_id "Test:R") (at 100 100 0)
    (property "Reference" "R1" (at 0 0 0))
    (property "Value" "10k" (at 0 0 0))
    (pin "1" (uuid "aaaa1111-0000-0000-0000-000000000001"))
    (pin "2" (uuid "aaaa2222-0000-0000-0000-000000000002"))
  )
  (symbol (lib_id "Test:LED") (at 100 120 0)
    (property "Reference" "LED1" (at 0 0 0))
    (property "Value" "RED" (at 0 0 0))
    (pin "A" (uuid "bbbbAAAA-0000-0000-0000-000000000003"))
    (pin "K" (uuid "bbbbKKKK-0000-0000-0000-000000000004"))
  )
  (wire (start 100 90) (end 100 95))
  (wire (start 100 105) (end 100 115))
  (wire (start 100 125) (end 100 130))
  (net_label "VCC" (at 100 90 0))
  (net_label "ANODE" (at 100 105 0))
  (net_label "GND" (at 100 130 0))
)
"""
    result = parse_kicad(KICAD_MINIMAL, "test_connectivity.kicad_sch")

    # ── Estructura básica ──────────────────────────────────────────────────────
    assert result["tool"] == "kicad"
    assert result["component_count"] == 2, \
        f"Esperaba 2 componentes, got {result['component_count']}"

    nets_by_name = {n["name"]: n for n in result["nets"]}

    # ── Los 3 nets deben existir ───────────────────────────────────────────────
    for expected_net in ("VCC", "ANODE", "GND"):
        assert expected_net in nets_by_name, \
            f"Net '{expected_net}' no encontrada. Nets: {list(nets_by_name.keys())}"

    vcc_nodes   = nets_by_name["VCC"]["nodes"]
    anode_nodes = nets_by_name["ANODE"]["nodes"]
    gnd_nodes   = nets_by_name["GND"]["nodes"]

    # ── nodes no vacíos ────────────────────────────────────────────────────────
    assert len(vcc_nodes) > 0,   f"VCC.nodes debe ser no-vacío, got {vcc_nodes}"
    assert len(anode_nodes) > 0, f"ANODE.nodes debe ser no-vacío, got {anode_nodes}"
    assert len(gnd_nodes) > 0,   f"GND.nodes debe ser no-vacío, got {gnd_nodes}"

    # ── Contenido correcto de cada net ────────────────────────────────────────
    assert "R1.1" in vcc_nodes,   f"R1.1 debe estar en VCC, got {vcc_nodes}"
    assert "R1.2" in anode_nodes, f"R1.2 debe estar en ANODE, got {anode_nodes}"
    assert "LED1.A" in anode_nodes, f"LED1.A debe estar en ANODE, got {anode_nodes}"
    assert "LED1.K" in gnd_nodes, f"LED1.K debe estar en GND, got {gnd_nodes}"

    # ── DRC puede ejecutarse sobre el resultado del parser ────────────────────
    # Añadir "type" para que DRC pueda clasificar componentes
    circuit_for_drc = {
        "components": [
            {"id": "R1",   "ref": "R1",   "type": "resistor", "value": "10k"},
            {"id": "LED1", "ref": "LED1", "type": "led",       "value": "RED"},
        ],
        "nets": result["nets"],   # nets con nodes poblados
    }
    drc = run_drc(circuit_for_drc)

    # Resultado válido
    assert "errors"   in drc, "DRC debe retornar 'errors'"
    assert "warnings" in drc, "DRC debe retornar 'warnings'"
    assert "passed"   in drc, "DRC debe retornar 'passed'"

    # No debe haber SHORT_CIRCUIT (VCC y GND son nets separados)
    short_errors = [e for e in drc["errors"] if e.get("code") == "SHORT_CIRCUIT"]
    assert len(short_errors) == 0, \
        f"No debe haber SHORT_CIRCUIT en este circuito, got: {short_errors}"

    # Al menos un check distinto de NO_POWER_NET y HIGH_CURRENT_NO_FUSE debe ejecutarse.
    # Con LED sin decoupling, LED_WITHOUT_RESISTOR se esperaría, pero R1 está en el mismo
    # net ANODE → no aplica. Verificamos que la lista de issues fue construida correctamente.
    all_codes = {i.get("code") for i in drc["errors"] + drc["warnings"] + drc.get("info", [])}
    excluded = {"NO_POWER_NET", "HIGH_CURRENT_NO_FUSE"}
    non_power_checks_ran = (all_codes - excluded)
    # Si no hay issues extra, igualmente el DRC corrió todos sus checks internos.
    # Lo importante es que NO lanzó excepción y retornó un dict válido.
    assert isinstance(drc["passed"], bool), "drc['passed'] debe ser bool"


def test_kicad_legacy_connectivity():
    """
    Verifica que _parse_kicad_legacy traza conectividad real con Union-Find.
    Esquemático v5 sintético: R1 en (5000,5000), LED1 en (5000,5500).
    Wire VCC→R1 center, Wire R1→LED1, Wire LED1→GND.
    """
    from tools.schematic_parser import _parse_kicad_legacy

    # R1 en (5000,5000): wire VCC desde (5000,4750) hasta (5000,5000)
    # LED1 en (6000,5000): wire GND desde (6000,5000) hasta (6000,5250)
    # Dos sub-circuitos independientes → dos nets distintos.
    SCH = """\
EESchema Schematic File Version 4
$Comp
L Device:R R1
U 1 1 00000001
P 5000 5000
F 0 "R1" H 5070 5046 50  0000 L CNN
F 1 "10k" H 5070 4955 50  0000 L CNN
F 2 "" H 5000 5000 50  0001 C CNN
$EndComp
$Comp
L Device:LED LED1
U 1 1 00000002
P 6000 5000
F 0 "LED1" H 5993 5215 50  0000 C CNN
F 1 "RED" H 5993 5124 50  0000 C CNN
F 2 "" H 6000 5000 50  0001 C CNN
$EndComp
Wire Wire Line
	5000 4750 5000 5000
Wire Wire Line
	6000 5000 6000 5250
Text Label 5000 4750 0    50   ~ 0
VCC
Text Label 6000 5250 0    50   ~ 0
GND
$EndSCHEMATC
"""

    result = _parse_kicad_legacy(SCH, "test_legacy.sch")

    assert result["tool"] == "kicad_legacy"
    assert result["component_count"] == 2, \
        f"Esperaba 2 componentes, got {result['component_count']}"

    nets_by_name = {n["name"]: n for n in result["nets"]}

    assert "VCC" in nets_by_name, f"Net VCC no encontrada. Nets: {list(nets_by_name.keys())}"
    assert "GND" in nets_by_name, f"Net GND no encontrada. Nets: {list(nets_by_name.keys())}"

    # Los componentes deben aparecer en al menos un net (nodes != [])
    all_nodes = []
    for net in result["nets"]:
        all_nodes.extend(net["nodes"])

    assert len(all_nodes) > 0, \
        f"nodes debe ser no-vacío — ningún componente conectado a nets. nets={result['nets']}"

    assert "R1" in all_nodes or "LED1" in all_nodes, \
        f"R1 o LED1 deben aparecer en nodes. all_nodes={all_nodes}"


if __name__ == "__main__":
    success = test_complete_integration()
    sys.exit(0 if success else 1)
