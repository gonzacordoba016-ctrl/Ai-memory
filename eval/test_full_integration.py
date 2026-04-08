# eval/test_full_integration.py

import os
import sys
import json
from pathlib import Path

# Añadir el directorio raíz al path
project_root = os.path.dirname(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_complete_integration():
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

if __name__ == "__main__":
    success = test_complete_integration()
    sys.exit(0 if success else 1)
