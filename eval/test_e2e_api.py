#!/usr/bin/env python3
"""
eval/test_e2e_api.py
Suite de tests E2E para Stratum — prueba todos los endpoints contra el servidor local.

Uso:
    python eval/test_e2e_api.py
    python eval/test_e2e_api.py --url http://localhost:8000
    python eval/test_e2e_api.py --url https://ai-memory-production-d6b1.up.railway.app
"""

import argparse
import json
import sys
import time
import asyncio
import websockets
import requests

BASE = "http://localhost:8000"

# ── colores ────────────────────────────────────────────────────────────────────
_WIN = sys.platform == "win32"
def _c(t, c): return t if _WIN else f"\033[{c}m{t}\033[0m"
def ok(m):   print(f"  {_c('✓', 92)} {m}")
def fail(m): print(f"  {_c('✗', 91)} {m}")
def info(m): print(f"  {_c('→', 96)} {m}")
def hdr(m):  print(f"\n{_c(m, 1)}")

# ── helpers ────────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        ok(label)
    else:
        _failed += 1
        fail(f"{label}" + (f" — {detail}" if detail else ""))

def get(path: str, **kw):
    try:
        return requests.get(f"{BASE}{path}", timeout=10, **kw)
    except Exception as e:
        return None

def post(path: str, **kw):
    try:
        return requests.post(f"{BASE}{path}", timeout=15, **kw)
    except Exception as e:
        return None

def delete(path: str, **kw):
    try:
        return requests.delete(f"{BASE}{path}", timeout=10, **kw)
    except Exception as e:
        return None

def put(path: str, **kw):
    try:
        return requests.put(f"{BASE}{path}", timeout=10, **kw)
    except Exception as e:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_health():
    hdr("1. Health Check")
    r = get("/api/health")
    check("GET /api/health responde", r is not None and r.status_code == 200)
    if r and r.status_code == 200:
        d = r.json()
        check("status presente", "status" in d)
        check("sqlite ok", d.get("services", {}).get("sqlite") == "ok",
              d.get("services", {}).get("sqlite", "ausente"))
        errors = d.get("startup_errors", [])
        if errors:
            fail(f"startup_errors: {errors}")
        else:
            ok("sin startup_errors")
        failed_routers = d.get("routers_failed", [])
        if failed_routers:
            fail(f"routers fallidos: {failed_routers}")
        else:
            ok(f"todos los routers cargados: {d.get('routers_ok', [])}")


def test_stats():
    hdr("2. Stats y Facts")
    r = get("/api/stats")
    check("GET /api/stats 200", r is not None and r.status_code == 200)

    r = get("/api/facts")
    check("GET /api/facts 200", r is not None and r.status_code == 200)

    r = get("/api/profile")
    check("GET /api/profile 200", r is not None and r.status_code == 200)

    r = get("/api/agents/status")
    check("GET /api/agents/status 200", r is not None and r.status_code == 200)


def test_hardware():
    hdr("3. Hardware")
    r = get("/api/hardware/devices")
    check("GET /api/hardware/devices 200", r is not None and r.status_code == 200)
    if r and r.status_code == 200:
        d = r.json()
        check("tiene 'connected' y 'registered'",
              "connected" in d and "registered" in d)

    r = get("/api/hardware/circuits")
    check("GET /api/hardware/circuits 200", r is not None and r.status_code == 200)

    r = get("/api/hardware/library")
    check("GET /api/hardware/library 200", r is not None and r.status_code == 200)

    r = get("/api/hardware/stats")
    check("GET /api/hardware/stats 200", r is not None and r.status_code == 200)

    r = get("/api/hardware/vision/status")
    check("GET /api/hardware/vision/status 200", r is not None and r.status_code == 200)


def test_stock():
    hdr("4. Component Stock")
    # Crear componente
    payload = {
        "name": "TEST_resistencia_10k",
        "category": "Resistencias",
        "value": "10kΩ",
        "package": "0805",
        "quantity": 50,
        "supplier": "LCSC",
    }
    r = post("/api/stock", json=payload)
    check("POST /api/stock 201", r is not None and r.status_code == 201)
    comp_id = r.json().get("id") if r and r.status_code == 201 else None

    # Listar
    r = get("/api/stock")
    check("GET /api/stock 200", r is not None and r.status_code == 200)
    if r and r.status_code == 200:
        items = r.json()
        check("lista tiene al menos 1 item", isinstance(items, list) and len(items) >= 1)

    # Summary y categories
    r = get("/api/stock/summary")
    check("GET /api/stock/summary 200", r is not None and r.status_code == 200)

    r = get("/api/stock/categories")
    check("GET /api/stock/categories 200", r is not None and r.status_code == 200)

    # Buscar
    r = get("/api/stock/search?q=resistencia")
    check("GET /api/stock/search 200", r is not None and r.status_code == 200)

    # Ajustar cantidad
    if comp_id:
        r = post(f"/api/stock/{comp_id}/adjust?delta=5")
        check("POST /api/stock/{id}/adjust 200", r is not None and r.status_code == 200)

    # Eliminar
    if comp_id:
        r = delete(f"/api/stock/{comp_id}")
        check("DELETE /api/stock/{id} 200", r is not None and r.status_code == 200)


def test_decisions():
    hdr("5. Design Decisions")
    payload = {
        "project": "test_project_e2e",
        "decision": "Usar LM317 como regulador de tensión",
        "reasoning": "Disponible en stock, probado, bajo costo",
        "component": "LM317",
        "tags": ["regulador", "5V"],
    }
    r = post("/api/decisions", json=payload)
    check("POST /api/decisions 201", r is not None and r.status_code == 201)
    dec_id = r.json().get("id") if r and r.status_code == 201 else None

    r = get("/api/decisions")
    check("GET /api/decisions 200", r is not None and r.status_code == 200)

    r = get("/api/decisions?project=test_project_e2e")
    check("GET /api/decisions?project= 200", r is not None and r.status_code == 200)

    if dec_id:
        r = delete(f"/api/decisions/{dec_id}")
        check("DELETE /api/decisions/{id} 200", r is not None and r.status_code == 200)


def test_circuits():
    hdr("6. Circuits")
    r = get("/api/circuits/viewer")
    check("GET /api/circuits/viewer 200", r is not None and r.status_code == 200)

    # Parse async
    r = post("/api/circuits/parse-async",
             params={"description": "LED con resistencia 220 ohm en pin 13", "mcu": "Arduino Uno"})
    check("POST /api/circuits/parse-async 202",
          r is not None and r.status_code in (200, 201, 202))
    job_id = None
    if r and r.status_code in (200, 201, 202):
        job_id = r.json().get("job_id")
        check("retorna job_id", bool(job_id))

    # Poll job (espera max 30s)
    if job_id:
        for _ in range(10):
            time.sleep(3)
            jr = get(f"/api/jobs/{job_id}")
            if jr and jr.status_code == 200:
                status = jr.json().get("status")
                if status in ("done", "error"):
                    check(f"parse-async completó (status={status})", status == "done")
                    break
        else:
            info("parse-async: timeout esperando resultado (job sigue corriendo)")


def test_schematics():
    hdr("7. Schematics")
    r = get("/api/schematics/supported")
    check("GET /api/schematics/supported 200", r is not None and r.status_code == 200)

    # Import KiCad mínimo
    kicad_content = b"""(kicad_sch (version 20211123) (generator eeschema)
  (symbol (lib_id "Device:R") (at 100 100 0) (reference "R1") (value "10k"))
)"""
    files = {"file": ("test_circuit.kicad_sch", kicad_content, "application/octet-stream")}
    r = requests.post(f"{BASE}/api/schematics/import", files=files, timeout=10)
    check("POST /api/schematics/import 200",
          r is not None and r.status_code in (200, 201))

    # PLC parse
    r = post("/api/schematics/plc/parse",
             json={"ladder_text": "START NO --[ ]-- MOTOR --( )--"})
    check("POST /api/schematics/plc/parse 200", r is not None and r.status_code == 200)


def test_intelligence():
    hdr("8. AI Intelligence")
    r = get("/api/intelligence/profiles")
    check("GET /api/intelligence/profiles 200", r is not None and r.status_code == 200)
    if r and r.status_code == 200:
        profiles = r.json()
        check("hay perfiles cargados", len(profiles) > 0)

    r = get("/api/intelligence/sources")
    check("GET /api/intelligence/sources 200", r is not None and r.status_code == 200)

    r = get("/api/intelligence/active")
    check("GET /api/intelligence/active 200", r is not None and r.status_code == 200)


def test_memory_search():
    hdr("9. Búsqueda semántica")
    r = get("/api/search?q=arduino+led&top_k=3")
    check("GET /api/search 200", r is not None and r.status_code == 200)

    r = get("/api/graph")
    check("GET /api/graph 200", r is not None and r.status_code == 200)

    r = get("/api/history")
    check("GET /api/history 200", r is not None and r.status_code == 200)


async def test_websocket_chat():
    hdr("10. WebSocket Chat")
    uri = BASE.replace("http", "ws") + "/ws/chat"
    try:
        async with websockets.connect(uri, open_timeout=5) as ws:
            # Primer mensaje debe ser session info
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            check("WS /ws/chat: recibe session init", msg.get("type") == "session")
            session_id = msg.get("session_id", "")
            check("session_id presente", bool(session_id))

            # Enviar ping simple
            await ws.send(json.dumps({"text": "hola, test e2e"}))
            # Esperar respuesta (puede ser thinking + response)
            got_response = False
            for _ in range(10):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                    m = json.loads(raw)
                    if m.get("type") in ("response", "chunk", "done"):
                        got_response = True
                        break
                except asyncio.TimeoutError:
                    break
            check("WS chat: recibe respuesta del agente", got_response)
    except Exception as e:
        fail(f"WS /ws/chat: {e}")


def test_platformio_export():
    hdr("11. PlatformIO Export")
    # Primero guardar un firmware de prueba
    circuit_payload = {
        "project_name": "test_e2e_pio",
        "description": "LED blink test",
        "components": [{"name": "LED", "type": "led", "pin": "13"}],
        "connections": [],
    }
    requests.post(f"{BASE}/api/hardware/circuit/test_e2e_device", json=circuit_payload, timeout=5)

    # Guardar firmware manualmente via SQL (o verificar que no hay firmware = 404 esperado)
    r = get("/api/hardware/firmware/test_e2e_device/platformio.zip")
    # Sin firmware guardado → 404 es correcto
    check("GET /platformio.zip responde (200 o 404)",
          r is not None and r.status_code in (200, 404))
    if r and r.status_code == 200:
        check("Content-Type es ZIP", "zip" in r.headers.get("content-type", ""))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global BASE
    parser = argparse.ArgumentParser(description="Stratum E2E Test Suite")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="URL base del servidor (default: http://localhost:8000)")
    args = parser.parse_args()
    BASE = args.url.rstrip("/")

    print(f"\n{_c('STRATUM — Suite E2E', 96)}")
    print(f"  Servidor: {_c(BASE, 93)}\n")

    # Verificar que el servidor está arriba
    try:
        requests.get(f"{BASE}/api/health", timeout=5)
    except Exception:
        print(_c(f"\n✗ No se puede conectar a {BASE}. ¿Está corriendo el servidor?\n", 91))
        print("  Iniciá el servidor con: python run.py\n")
        sys.exit(1)

    test_health()
    test_stats()
    test_hardware()
    test_stock()
    test_decisions()
    test_circuits()
    test_schematics()
    test_intelligence()
    test_memory_search()
    asyncio.run(test_websocket_chat())
    test_platformio_export()

    # Resumen
    total = _passed + _failed
    print(f"\n{'─'*50}")
    print(f"  Resultado: {_c(str(_passed), 92)} pasaron  {_c(str(_failed), 91)} fallaron  / {total} total")
    if _failed == 0:
        print(f"  {_c('✓ Todo OK', 92)}\n")
    else:
        print(f"  {_c('✗ Hay fallos — revisá los endpoints marcados', 91)}\n")

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
