# eval/test_circuit_integration.py

import os
import sys
import json
from pathlib import Path

# Añadir el directorio raíz al path
project_root = os.path.dirname(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.config import SQL_DB_PATH

# Colores para output
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
results = []

def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    results.append(True if condition else False)

def cleanup_test_data():
    """Limpia datos de test anteriores."""
    try:
        db_path = SQL_DB_PATH
        if os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            # Solo borrar si las tablas existen
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            
            if 'circuit_context' in tables:
                conn.execute("DELETE FROM circuit_context WHERE device_name LIKE 'TEST_%'")
            if 'circuit_designs' in tables:
                conn.execute("DELETE FROM circuit_designs WHERE name LIKE 'TEST_%'")
            if 'firmware_history' in tables:
                conn.execute("DELETE FROM firmware_history WHERE device_name LIKE 'TEST_%'")
            
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error en cleanup: {e}")

def run_circuit_integration_tests():
    print("\n=== TEST INTEGRACIÓN: Circuito → Firmware ===\n")
    
    cleanup_test_data()
    
    # ── Test 1: Importaciones ──────────────────────────────────────────
    print("1. Verificando importaciones base")
    
    agent_exists = False
    try:
        from agent.agents.circuit_agent import CircuitAgent
        from database.circuit_design import CircuitDesignManager
        agent_exists = True
        check("Importación de CircuitAgent y Manager", True)
    except ImportError as e:
        check("Importación de CircuitAgent y Manager", False, f"error={str(e)}")
    
    if agent_exists:
        agent = CircuitAgent()
        
        # Datos de prueba
        circuit_data = {
            "name": "TEST_LED_Project",
            "description": "Circuito de prueba para integración",
            "components": [
                {"id": "U1", "name": "Arduino Uno", "type": "arduino_uno"},
                {"id": "R1", "name": "Resistencia 220Ω", "type": "resistor", "value": "220", "unit": "ohm"},
                {"id": "D1", "name": "LED Rojo", "type": "led", "color": "red"}
            ],
            "nets": [
                {"name": "VCC", "nodes": ["U1.5V", "D1.A"]},
                {"name": "GND", "nodes": ["U1.GND", "R1.2", "D1.K"]},
                {"name": "NET_LED", "nodes": ["U1.13", "R1.1"]}
            ],
            "power": "5V USB"
        }
        
        # ── Test 2: Guardado ─────────────────────────────────────────────
        print("\n2. Guardado de diseño")
        try:
            design_id = agent.circuit_manager.save_design(circuit_data)
            check("Guardado de diseño en DB", design_id > 0, f"id={design_id}")
            
            if design_id > 0:
                # ── Test 3: Recuperación ─────────────────────────────────────
                print("\n3. Recuperación de diseño")
                retrieved = agent.get_circuit_by_id(design_id)
                check("Recuperación por ID", retrieved is not None and retrieved['name'] == circuit_data['name'])
                
                # ── Test 4: Listado ──────────────────────────────────────────
                print("\n4. Listado de diseños")
                all_designs = agent.list_all_circuits()
                check("Listado contiene el diseño", any(d['id'] == design_id for d in all_designs))
        except Exception as e:
            check("Operaciones de DB", False, f"error={str(e)}")
            
    # ── Test 5: Renderizado ─────────────────────────────────────────────
    print("\n5. Renderizado de esquemático")
    try:
        from tools.schematic_renderer import SchematicRenderer
        renderer = SchematicRenderer()
        svg = renderer.render_schematic_svg(circuit_data)
        check("Generación de SVG", isinstance(svg, str) and "<svg" in svg)
    except Exception as e:
        check("Renderizado SVG", False, f"error={str(e)}")
        
    # ── Resumen final ───────────────────────────────────────────────────
    print(f"\n{'='*50}")
    passed = sum(1 for r in results if r is True)
    total = len(results)
    print(f"RESULTADO INTEGRACIÓN: {passed}/{total} tests pasaron")
    
    if passed == total and total > 0:
        print("✅ INTEGRACIÓN EXITOSA")
    else:
        print(f"❌ {total - passed} tests fallaron")
    
    print(f"{'='*50}")
    
    cleanup_test_data()
    return passed == total and total > 0

if __name__ == "__main__":
    success = run_circuit_integration_tests()
    sys.exit(0 if success else 1)
