#!/usr/bin/env python3
"""
guide-test.py
Script maestro de testing para Stratum.
Corre todos los tests definidos en el GUIDE.md (sección 4 y 5).

Uso:
    python guide-test.py
    python guide-test.py --url http://localhost:8000
    python guide-test.py --skip-slow       (omite tests con LLM / websocket)
    python guide-test.py --only smoke      (solo smoke test)
    python guide-test.py --only sessions   (solo tests de sesiones)
"""

import argparse
import asyncio
import json
import sys
import subprocess
import os
import time
import requests
import uuid

# Forzar UTF-8 en stdout/stderr para que ━ y otros Unicode no revienten en Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────
BASE        = "http://localhost:8000"
API         = f"{BASE}/api"
SKIP_SLOW   = False

# ── Colores (no ANSI en Windows cmd, sí en Windows Terminal / PowerShell) ────
def _c(t, c):
    if sys.platform == "win32" and "WT_SESSION" not in os.environ and "TERM_PROGRAM" not in os.environ:
        return t
    return f"\033[{c}m{t}\033[0m"

def ok(m):    print(f"  {_c('✓', 92)} {m}")
def fail(m):  print(f"  {_c('✗', 91)} {m}")
def info(m):  print(f"  {_c('→', 96)} {m}")
def warn(m):  print(f"  {_c('⚠', 93)} {m}")
def hdr(m):   print(f"\n{_c('━━ ' + m, 1)}")
def subhdr(m):print(f"  {_c(m, 36)}")

_passed = _failed = _skipped = 0

def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        ok(label)
    else:
        _failed += 1
        fail(f"{label}" + (f"  [{detail}]" if detail else ""))

def skip(label):
    global _skipped
    _skipped += 1
    warn(f"SKIP  {label}")

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def get(path, **kw):
    try:    return requests.get(f"{BASE}{path}", timeout=15, **kw)
    except: return None

def post(path, **kw):
    try:    return requests.post(f"{BASE}{path}", timeout=20, **kw)
    except: return None

def patch(path, **kw):
    try:    return requests.patch(f"{BASE}{path}", timeout=10, **kw)
    except: return None

def delete(path, **kw):
    try:    return requests.delete(f"{BASE}{path}", timeout=10, **kw)
    except: return None

def j(r):
    try:    return r.json() if r else {}
    except: return {}

# ══════════════════════════════════════════════════════════════════════════════
# 1. SMOKE TEST — servidor y rutas básicas
# ══════════════════════════════════════════════════════════════════════════════
def test_smoke():
    hdr("SMOKE — Servidor y rutas básicas")

    r = get("/api/health")
    check("/api/health responde 200", r is not None and r.status_code == 200)
    if r and r.ok:
        d = j(r)
        check("status ok",         d.get("status") == "ok", d.get("status"))
        check("routers sin fallos", d.get("routers_failed", []) == [],
              str(d.get("routers_failed", [])))
        svc = d.get("services", {})
        check("SQLite ok", svc.get("sqlite") == "ok")

    check("/api/stats 200",       get("/api/stats")    is not None and get("/api/stats").status_code    == 200)
    check("/api/facts 200",       get("/api/facts")    is not None and get("/api/facts").status_code    == 200)
    check("/api/sessions 200",    get("/api/sessions") is not None and get("/api/sessions").status_code == 200)
    check("/api/calc/formulas 200", get("/api/calc/formulas") is not None and
          get("/api/calc/formulas").status_code == 200)

    r = get("/api/calc/formulas")
    if r and r.ok:
        formulas = j(r).get("formulas", [])
        check(f"25 fórmulas disponibles", len(formulas) == 25, f"encontradas: {len(formulas)}")

# ══════════════════════════════════════════════════════════════════════════════
# 2. SESSIONS — CRUD de sesiones de chat
# ══════════════════════════════════════════════════════════════════════════════
def test_sessions():
    hdr("SESSIONS — CRUD de sesiones de chat")
    _id = None

    # Crear sesión
    r = post("/api/sessions", json={"title": "Test sesión guide-test"})
    check("POST /api/sessions 201", r is not None and r.status_code == 201)
    if r and r.ok:
        d = j(r)
        _id = d.get("id")
        check("session.id presente",    bool(_id))
        check("session.title correcto", d.get("title") == "Test sesión guide-test")

    if not _id:
        fail("No se pudo crear sesión — saltando tests dependientes")
        return

    # Listar — debe aparecer
    r = get("/api/sessions")
    check("GET /api/sessions incluye la nueva", r is not None and r.ok and
          any(s["id"] == _id for s in j(r).get("sessions", [])))

    # Renombrar
    r = patch(f"/api/sessions/{_id}/title", json={"title": "Renombrada por guide-test"})
    check("PATCH /api/sessions/{id}/title 200", r is not None and r.ok)

    # Verificar título actualizado
    sessions = j(get("/api/sessions")).get("sessions", [])
    match = next((s for s in sessions if s["id"] == _id), None)
    check("Título actualizado en lista", match is not None and
          match.get("title") == "Renombrada por guide-test",
          match.get("title") if match else "no encontrada")

    # Historial vacío
    r = get(f"/api/history?session_id={_id}&limit=10")
    check("GET /api/history con session_id 200", r is not None and r.ok)
    check("Historial vacío para sesión nueva", len(j(r).get("messages", [])) == 0)

    # Borrar
    r = delete(f"/api/sessions/{_id}")
    check("DELETE /api/sessions/{id} 200", r is not None and r.ok)

    # Verificar borrado
    sessions = j(get("/api/sessions")).get("sessions", [])
    check("Sesión eliminada de la lista", not any(s["id"] == _id for s in sessions))

# ══════════════════════════════════════════════════════════════════════════════
# 3. STOCK — componentes en inventario
# ══════════════════════════════════════════════════════════════════════════════
def test_stock():
    hdr("STOCK — Componentes en inventario")
    cid = None

    # Crear componente con unit_cost
    r = post("/api/stock", json={
        "name": "R 220Ω guide-test", "category": "resistencia",
        "value": "220", "package": "0.25W",
        "quantity": 100, "unit_cost": 0.05
    })
    check("POST /api/stock 201", r is not None and r.status_code == 201)
    if r and r.ok:
        cid = j(r).get("id")
        check("id presente en respuesta", bool(cid))

    # Listar (incluye unit_cost)
    r = get("/api/stock")
    check("GET /api/stock 200", r is not None and r.ok)
    if r and r.ok:
        raw = j(r)
        items = raw if isinstance(raw, list) else (raw.get("components") or raw.get("items") or [])
        if isinstance(items, list) and items:
            sample = next((i for i in items if "guide-test" in str(i.get("name",""))), items[0])
            check("unit_cost presente en item", "unit_cost" in sample,
                  f"claves: {list(sample.keys())}")

    # Resumen + categorías
    check("GET /api/stock/summary 200",    get("/api/stock/summary")    is not None and get("/api/stock/summary").ok)
    check("GET /api/stock/categories 200", get("/api/stock/categories") is not None and get("/api/stock/categories").ok)

    # Búsqueda
    r = get("/api/stock/search?q=220")
    check("GET /api/stock/search 200", r is not None and r.ok)

    # Ajustar stock — delta es query param
    if cid:
        r = post(f"/api/stock/{cid}/adjust?delta=-5")
        check("POST /api/stock/{id}/adjust 200", r is not None and r.ok)

    # Limpiar
    if cid:
        delete(f"/api/stock/{cid}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. CALC — calculadoras de ingeniería
# ══════════════════════════════════════════════════════════════════════════════
def test_calc():
    hdr("CALC — Calculadoras de ingeniería")

    cases = [
        ("resistor_for_led",  {"vcc": 5.0, "vled": 2.1, "iled_ma": 20},                          "value", lambda v: 100 < v < 200),
        ("ohms_law",          {"v": 12.0, "r": 220.0},                                            "value", lambda v: 50 < v < 60),
        ("buck_converter",    {"vin": 12, "vout": 5, "iout": 1, "freq_khz": 100},                 "value", lambda v: v > 0),
        ("battery_autonomy",  {"capacity_mah": 2000, "current_ma": 50},                           "value", lambda v: v > 20),
        ("capacitor_filter",  {"freq_hz": 100, "resistance": 10},                                  "value", lambda v: v > 0),
        ("heat_sink_required",{"p_w": 5, "t_ambient": 25},                                        "value", lambda v: v > 0),
        ("low_pass_rc",       {"cutoff_hz": 1000, "r": 1000},                                     "value", lambda v: v > 0),
    ]

    for formula, params, field, validator in cases:
        r = post("/api/calc/compute", json={"formula": formula, "params": params})
        ok_status = r is not None and r.ok
        check(f"POST /api/calc/compute [{formula}] 200", ok_status)
        if ok_status:
            res = j(r).get("result", {})
            val = res.get(field)
            check(f"  resultado numérico válido", val is not None and validator(float(val)),
                  f"valor={val}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. DECISIONS — decisiones de diseño
# ══════════════════════════════════════════════════════════════════════════════
def test_decisions():
    hdr("DECISIONS — Decisiones de diseño")
    did = None

    r = post("/api/decisions", json={
        "project":   "guide-test",
        "component": "U1",
        "decision":  "Usar Arduino Uno",
        "reasoning": "más familiar para el test"
    })
    check("POST /api/decisions 201", r is not None and r.status_code == 201)
    if r and r.ok:
        did = j(r).get("id")

    check("GET /api/decisions 200",                  get("/api/decisions") is not None and get("/api/decisions").ok)
    check("GET /api/decisions?project= 200",         get("/api/decisions?project=guide-test") is not None and
          get("/api/decisions?project=guide-test").ok)

    if did:
        delete(f"/api/decisions/{did}")

# ══════════════════════════════════════════════════════════════════════════════
# 6. CIRCUITS — parseo, DRC, BOM, PDF
# ══════════════════════════════════════════════════════════════════════════════
def test_circuits():
    hdr("CIRCUITS — Parseo, DRC, BOM, PDF")

    # Circuit Viewer HTML
    r = get("/api/circuits/viewer")
    check("GET /api/circuits/viewer 200", r is not None and r.ok)

    # parse-async (no espera LLM — solo verifica que el job se crea)
    r = post("/api/circuits/parse-async?description=LED+rojo+con+Arduino+Uno&mcu=Arduino+Uno")
    check("POST /api/circuits/parse-async retorna job_id",
          r is not None and (r.status_code in (200, 202)) and bool(j(r).get("job_id")))

    # DRC en circuito 1 (puede no existir → 404 también aceptado)
    r = get("/api/circuits/1/drc")
    check("GET /api/circuits/1/drc responde (200 o 404)",
          r is not None and r.status_code in (200, 404))
    if r and r.status_code == 200:
        d = j(r)
        check("DRC tiene campo 'passed'",   "passed"  in d)
        check("DRC tiene campo 'summary'",  "summary" in d)
        check("DRC tiene campo 'errors'",   "errors"  in d)

    # BOM en circuito 1
    r = get("/api/circuits/1/bom")
    check("GET /api/circuits/1/bom responde (200 o 404)",
          r is not None and r.status_code in (200, 404))
    if r and r.status_code == 200:
        d = j(r)
        check("BOM tiene campo 'lines'",         "lines"       in d)
        check("BOM tiene campo 'total_cost'",    "total_cost"  in d)
        check("BOM tiene campo 'summary'",       "summary"     in d)

    # BOM CSV
    r = get("/api/circuits/1/bom.csv")
    check("GET /api/circuits/1/bom.csv responde (200 o 404)",
          r is not None and r.status_code in (200, 404))
    if r and r.status_code == 200:
        check("Content-Type es text/csv", "csv" in r.headers.get("content-type","").lower())
        check("CSV tiene encabezado Ref", "Ref" in r.text)

    # PDF (requiere reportlab)
    r = get("/api/circuits/1/report.pdf")
    if r and r.status_code == 503:
        warn("PDF: reportlab no instalado (pip install reportlab)")
    elif r and r.status_code == 404:
        info("PDF: circuito 1 no existe — create uno primero para probar PDF")
    elif r and r.ok:
        check("PDF: Content-Type es application/pdf",
              "pdf" in r.headers.get("content-type","").lower())
        check("PDF: tamaño > 1KB", len(r.content) > 1024, f"{len(r.content)} bytes")

# ══════════════════════════════════════════════════════════════════════════════
# 7. SCHEMATICS — import de esquemáticos
# ══════════════════════════════════════════════════════════════════════════════
def test_schematics():
    hdr("SCHEMATICS — Import y parseo")

    r = get("/api/schematics/supported")
    check("GET /api/schematics/supported 200", r is not None and r.ok)
    if r and r.ok:
        formats = j(r).get("formats", [])
        # formats es lista de dicts con clave "tool"; buscar por substring case-insensitive
        tool_names = " ".join(f.get("tool", "").lower() for f in formats)
        for fmt, keyword in [("kicad", "kicad"), ("eagle", "eagle"), ("ltspice", "ltspice")]:
            check(f"  formato '{fmt}' soportado", keyword in tool_names)

    # Import via file upload (multipart) — enviar un .kicad_sch mínimo
    minimal_kicad = b"(kicad_sch (version 20211123) (generator eeschema))"
    import io
    r = post("/api/schematics/import",
             files={"file": ("test.kicad_sch", io.BytesIO(minimal_kicad), "application/octet-stream")})
    check("POST /api/schematics/import (kicad_sch) 200 o 400",
          r is not None and r.status_code in (200, 400))  # 400 si el contenido es inválido, igual es un OK funcional

    # PLC parse — body espera {"text": "..."}
    r = post("/api/schematics/plc/parse", json={"text": "Si sensor S1 activo, activar motor M1"})
    check("POST /api/schematics/plc/parse 200", r is not None and r.ok)

# ══════════════════════════════════════════════════════════════════════════════
# 8. HARDWARE — devices y bridge
# ══════════════════════════════════════════════════════════════════════════════
def test_hardware():
    hdr("HARDWARE — Devices y bridge")

    check("GET /api/hardware/devices 200",    get("/api/hardware/devices")    is not None and get("/api/hardware/devices").ok)
    check("GET /api/hardware/circuits 200",   get("/api/hardware/circuits")   is not None and get("/api/hardware/circuits").ok)
    check("GET /api/hardware/library 200",    get("/api/hardware/library")    is not None and get("/api/hardware/library").ok)
    check("GET /api/hardware/stats 200",      get("/api/hardware/stats")      is not None and get("/api/hardware/stats").ok)
    check("GET /api/hardware/bridge/status 200", get("/api/hardware/bridge/status") is not None and
          get("/api/hardware/bridge/status").ok)

# ══════════════════════════════════════════════════════════════════════════════
# 9. INTELLIGENCE — perfiles y fuentes
# ══════════════════════════════════════════════════════════════════════════════
def test_intelligence():
    hdr("INTELLIGENCE — Perfiles y fuentes")

    check("GET /api/intelligence/profiles 200", get("/api/intelligence/profiles") is not None and
          get("/api/intelligence/profiles").ok)
    check("GET /api/intelligence/sources 200",  get("/api/intelligence/sources")  is not None and
          get("/api/intelligence/sources").ok)
    check("GET /api/intelligence/active 200",   get("/api/intelligence/active")   is not None and
          get("/api/intelligence/active").ok)

# ══════════════════════════════════════════════════════════════════════════════
# 10. MEMORIA — búsqueda semántica, historial, grafo
# ══════════════════════════════════════════════════════════════════════════════
def test_memory():
    hdr("MEMORY — Búsqueda, historial y grafo")

    check("GET /api/search?q=arduino 200", get("/api/search?q=arduino") is not None and
          get("/api/search?q=arduino").ok)
    check("GET /api/graph 200",            get("/api/graph") is not None and get("/api/graph").ok)
    check("GET /api/history 200",          get("/api/history") is not None and get("/api/history").ok)
    check("GET /api/profile 200",          get("/api/profile") is not None and get("/api/profile").ok)
    check("GET /api/jobs 200",             get("/api/jobs") is not None and get("/api/jobs").ok)

# ══════════════════════════════════════════════════════════════════════════════
# 11. WEBSOCKET CHAT (slow)
# ══════════════════════════════════════════════════════════════════════════════
async def _ws_test():
    import websockets
    WS = f"ws://{BASE.split('//')[1]}/ws/chat"
    got_session = got_done = False
    try:
        async with websockets.connect(WS, open_timeout=5) as ws:
            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            got_session = data.get("type") == "session"
            sid = data.get("session_id", "")
            await ws.send(json.dumps({"type": "message", "content": "Hola Stratum, test guide"}))
            for _ in range(30):
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                d = json.loads(raw)
                if d.get("type") == "done":
                    got_done = True
                    break
    except Exception as e:
        warn(f"WS error: {e}")
    return got_session, got_done

def test_websocket():
    hdr("WEBSOCKET — Chat en tiempo real")
    if SKIP_SLOW:
        skip("WebSocket chat (--skip-slow)")
        return
    try:
        got_session, got_done = asyncio.run(_ws_test())
        check("WS: handshake session recibido", got_session)
        check("WS: mensaje procesado (done event)", got_done)
    except Exception as e:
        fail(f"WS: excepción — {e}")

# ══════════════════════════════════════════════════════════════════════════════
# 12. SUITE COMPLETA (pytest wrapper)
# ══════════════════════════════════════════════════════════════════════════════
def run_pytest_suite():
    hdr("PYTEST — Suite de tests unitarios y de integración")
    eval_dir = os.path.join(os.path.dirname(__file__), "eval")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", eval_dir, "-v", "--tb=short", "-q"],
        capture_output=True, text=True
    )
    lines = (result.stdout + result.stderr).splitlines()
    for line in lines[-20:]:  # últimas 20 líneas
        print(f"  {line}")
    check("pytest eval/ exitcode 0", result.returncode == 0,
          f"exit={result.returncode}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
SUITES = {
    "smoke":        test_smoke,
    "sessions":     test_sessions,
    "stock":        test_stock,
    "calc":         test_calc,
    "decisions":    test_decisions,
    "circuits":     test_circuits,
    "schematics":   test_schematics,
    "hardware":     test_hardware,
    "intelligence": test_intelligence,
    "memory":       test_memory,
    "websocket":    test_websocket,
    "pytest":       run_pytest_suite,
}

def main():
    global BASE, API, SKIP_SLOW

    parser = argparse.ArgumentParser(description="Stratum Guide Test Runner")
    parser.add_argument("--url",        default="http://localhost:8000", help="URL base del servidor")
    parser.add_argument("--skip-slow",  action="store_true",             help="Omitir tests lentos (WS, LLM)")
    parser.add_argument("--only",       default=None,
                        help=f"Correr solo una suite: {', '.join(SUITES.keys())}")
    args = parser.parse_args()

    BASE      = args.url.rstrip("/")
    API       = f"{BASE}/api"
    SKIP_SLOW = args.skip_slow

    print(f"\n{_c('━'*54, 36)}")
    print(f"  {_c('STRATUM — Guide Test Runner', 1)}")
    print(f"  Servidor : {_c(BASE, 93)}")
    print(f"  Slow     : {'omitidos (--skip-slow)' if SKIP_SLOW else 'incluidos'}")
    print(f"{_c('━'*54, 36)}")

    # Verificar servidor
    try:
        r = requests.get(f"{BASE}/api/health", timeout=5)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
    except Exception as e:
        print(_c(f"\n✗  Servidor no responde en {BASE}\n   Error: {e}", 91))
        print("   Iniciá el servidor con:  python run.py\n")
        sys.exit(1)

    # Ejecutar suites
    if args.only:
        name = args.only.lower()
        if name not in SUITES:
            print(f"Suite desconocida: '{name}'. Opciones: {', '.join(SUITES)}")
            sys.exit(1)
        SUITES[name]()
    else:
        for suite in SUITES.values():
            suite()

    # Resumen
    total = _passed + _failed + _skipped
    print(f"\n{_c('━'*54, 36)}")
    print(f"  {_c(f'✓ {_passed} pasaron', 92)}  "
          f"{_c(f'✗ {_failed} fallaron', 91) if _failed else _c(f'✗ 0 fallaron', 90)}  "
          f"{_c(f'⚠ {_skipped} omitidos', 93) if _skipped else ''}  / {total} total")
    if _failed == 0:
        print(f"  {_c('Todo OK ✓', 92)}")
    else:
        print(f"  {_c('Revisar los checks marcados con ✗', 91)}")
    print(f"{_c('━'*54, 36)}\n")

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
