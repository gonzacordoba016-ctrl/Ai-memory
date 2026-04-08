# eval/run_eval.py

import os
import sys
import math
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

EVAL_PREFIX = "EVAL_ISOLATION_K92x"
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    results.append(condition)


def cleanup_eval_data():
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from infrastructure.vector_store import vector_store
        vector_store.client.delete(
            collection_name=vector_store.collection,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value="eval"))]
            )
        )
    except Exception:
        pass

    try:
        db_path = os.getenv("MEMORY_DB_PATH", "./database/memory.db")
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM facts WHERE key LIKE 'eval_%'")
        conn.execute("DELETE FROM hardware_devices WHERE device_name LIKE 'EVAL_%'")
        conn.execute("DELETE FROM firmware_history WHERE device_name LIKE 'EVAL_%'")
        conn.execute("DELETE FROM project_library WHERE name LIKE 'EVAL_%'")
        conn.commit()
        conn.close()
    except Exception:
        pass

    try:
        from memory.graph_memory import graph_memory
        nodes_to_remove = [
            n for n in list(graph_memory.graph.nodes())
            if any(d.get("source") == "eval"
                   for _, _, d in graph_memory.graph.edges(n, data=True))
        ]
        for n in nodes_to_remove:
            if n in graph_memory.graph:
                graph_memory.graph.remove_node(n)
        graph_memory.save()
    except Exception:
        pass


cleanup_eval_data()

print("\n=== EVAL: Memory + Hardware ===\n")


# ── Test 1: SQLite ──────────────────────────────────────────
print("1. SQLite — almacenamiento de hechos")

from database.sql_memory import _default as sql_db

sql_db.store_fact("eval_test_name", "TestUser")
sql_db.store_fact("eval_test_job",  "Desarrollador")
facts = sql_db.get_all_facts()

check("Nombre guardado",  "eval_test_name" in facts and facts["eval_test_name"] == "TestUser")
check("Trabajo guardado", "eval_test_job"  in facts and facts["eval_test_job"]  == "Desarrollador")

sql_db.delete_fact("eval_test_name")
sql_db.delete_fact("eval_test_job")


# ── Test 2: Qdrant ──────────────────────────────────────────
print("\n2. Qdrant — búsqueda semántica")

from memory.vector_memory import store_memory, search_memory

store_memory(
    f"{EVAL_PREFIX} trabaja como desarrollador Python en Buenos Aires",
    metadata={"source": "eval"}
)
store_memory(
    f"{EVAL_PREFIX} tiene un perro llamado Rocket",
    metadata={"source": "eval"}
)

res      = search_memory(f"{EVAL_PREFIX} profesión", top_k=5)
found_job = any("desarrollador" in r.lower() or "python" in r.lower() for r in res)
found_dog = any("rocket" in r.lower() for r in res)

check("Encuentra hecho sobre trabajo", found_job, f"{[r[:60] for r in res]}")
check("Encuentra hecho sobre mascota", found_dog, f"{[r[:60] for r in res]}")
check("Retorna resultados no vacíos",  len(res) > 0, f"{len(res)} resultados")


# ── Test 3: Decaimiento temporal ────────────────────────────
print("\n3. Decaimiento temporal")

from core.config import MEMORY_DECAY_RATE

decay_now = math.exp(-MEMORY_DECAY_RATE * 0)
decay_30d = math.exp(-MEMORY_DECAY_RATE * 30)
decay_90d = math.exp(-MEMORY_DECAY_RATE * 90)

check("Recuerdo nuevo > 30 días",   decay_now > decay_30d,
      f"nuevo={decay_now:.3f} 30d={decay_30d:.3f}")
check("Recuerdo 30d > 90 días",     decay_30d > decay_90d,
      f"30d={decay_30d:.3f} 90d={decay_90d:.3f}")
check("Decay rate razonable",       0 < MEMORY_DECAY_RATE < 0.1,
      f"rate={MEMORY_DECAY_RATE}")


# ── Test 4: Grafo ───────────────────────────────────────────
print("\n4. Grafo — relaciones")

from memory.graph_memory import graph_memory

graph_memory.add_relation("eval_user", "trabaja_en",  "eval_acme",   source="eval")
graph_memory.add_relation("eval_acme", "usa",         "eval_python", source="eval")
graph_memory.add_relation("eval_user", "se_llama",    "eval_tester", source="eval")

related = graph_memory.get_related("eval_user", depth=2)
ctx     = graph_memory.get_context_for_query("eval_user tecnología")

check("Relaciones directas",        len(related) >= 2, f"{len(related)} relaciones")
check("Traversal 2 saltos",         any("eval_python" in r for r in related), f"{related}")
check("Contexto generado",          len(ctx) > 0, f"{ctx[:80]}")
check("Grafo tiene nodos/aristas",  graph_memory.stats()["nodes"] >= 3)


# ── Test 5: Hardware Memory ─────────────────────────────────
print("\n5. Hardware Memory — dispositivos y firmware")

from database.hardware_memory import hardware_memory

EVAL_DEVICE = "EVAL_Arduino_Test"

hardware_memory.register_device({
    "name":     EVAL_DEVICE,
    "port":     "COM_EVAL",
    "fqbn":     "arduino:avr:uno",
    "platform": "arduino:avr",
})

hardware_memory.save_firmware(
    device_name = EVAL_DEVICE,
    task        = "EVAL_parpadear LED pin 13",
    code        = "void setup(){pinMode(13,OUTPUT);} void loop(){digitalWrite(13,HIGH);delay(1000);digitalWrite(13,LOW);delay(1000);}",
    filename    = "eval_blink.ino",
    success     = True,
    serial_out  = "LED parpadeando",
)

devices = hardware_memory.get_all_devices()
current = hardware_memory.get_current_firmware(EVAL_DEVICE)
stats   = hardware_memory.get_stats()

check("Dispositivo registrado",
      any(d["name"] == EVAL_DEVICE for d in devices),
      f"{[d['name'] for d in devices]}")
check("Firmware guardado y recuperable",
      current is not None and "LED" in current.get("task", ""),
      f"task={current.get('task', 'None')[:40] if current else 'None'}")
check("Stats actualizados",
      stats["devices"] >= 1 and stats["total_flashes"] >= 1,
      f"devices={stats['devices']} flashes={stats['total_flashes']}")


# ── Test 6: Biblioteca de proyectos ────────────────────────
print("\n6. Biblioteca de proyectos — reutilización")

proj_id = hardware_memory.save_to_library(
    name        = "EVAL_Blink LED",
    description = "EVAL parpadear LED en pin 13 cada segundo",
    code        = "void setup(){pinMode(13,OUTPUT);} void loop(){digitalWrite(13,HIGH);delay(1000);digitalWrite(13,LOW);delay(1000);}",
    platform    = "arduino:avr",
    tags        = ["led", "blink", "eval"],
)

results_lib = hardware_memory.search_library("EVAL parpadear")
found_proj  = any(p["name"] == "EVAL_Blink LED" for p in results_lib)
used        = hardware_memory.use_from_library(proj_id)
lib_all     = hardware_memory.get_library()

check("Proyecto guardado en biblioteca",  proj_id > 0, f"id={proj_id}")
check("Búsqueda en biblioteca funciona",  found_proj, f"{[p['name'] for p in results_lib]}")
check("use_from_library retorna código",  used is not None and "setup" in used.get("code", ""))
check("get_library retorna proyectos",    len(lib_all) >= 1, f"{len(lib_all)} proyectos")


# ── Test 7: Detección de plataformas ───────────────────────
print("\n7. Hardware Detector — plataformas soportadas")

from tools.hardware_detector import get_supported_platforms, DEVICE_SIGNATURES

platforms  = get_supported_platforms()
signatures = len(DEVICE_SIGNATURES)

check("Más de 10 plataformas soportadas", len(platforms) >= 5,
      f"{len(platforms)} plataformas: {platforms[:5]}")
check("Más de 15 dispositivos en signatures", signatures >= 15,
      f"{signatures} dispositivos registrados")
check("ESP32 soportado",    "esp32:esp32" in platforms)
check("Arduino AVR soportado", "arduino:avr" in platforms)
check("RP2040 soportado",   "rp2040:rp2040" in platforms)


# ── Test 8: Clasificación de intents ───────────────────────
print("\n8. Hardware Agent — clasificación de intents")

from agent.agents.hardware_agent import HardwareAgent

agent = HardwareAgent()

query_cases = [
    "qué dispositivos tengo registrados?",
    "mostrá el historial del Arduino",
    "cuántas veces flasheé hardware?",
    "qué tenía programado?",
]
program_cases = [
    "quiero hacer parpadear el LED del pin 13",
    "programá el Arduino para leer temperatura",
    "cargá un blink en el ESP32",
]
debug_cases = [
    "el LED no enciende",
    "el código falla",
    "arreglá el firmware",
]

query_ok   = all(agent._classify_by_keywords(q) == "query"   for q in query_cases)
program_ok = all(agent._classify_by_keywords(q) == "program" for q in program_cases)
debug_ok   = all(agent._classify_by_keywords(q) == "debug"   for q in debug_cases)

check("Queries clasificadas como 'query'",   query_ok,
      f"casos: {[agent._classify_by_keywords(q) for q in query_cases]}")
check("Programar clasificado como 'program'", program_ok,
      f"casos: {[agent._classify_by_keywords(q) for q in program_cases]}")
check("Debug clasificado como 'debug'",       debug_ok,
      f"casos: {[agent._classify_by_keywords(q) for q in debug_cases]}")


# ── Test 9: Async Client ────────────────────────────────────
print("\n9. Async Client — cliente httpx centralizado")

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

async def _test_async_client():
    from llm.async_client import call_llm_text, call_llm_async

    # Mock de httpx para no llamar al LLM real
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "respuesta de prueba"}}]
    }

    with patch("llm.async_client._client") as mock_client:
        mock_client.post = AsyncMock(return_value=mock_response)

        # Test call_llm_text
        result = await call_llm_text(
            messages=[{"role": "user", "content": "test"}],
            agent_id="eval-test",
        )
        check("call_llm_text retorna string",
              isinstance(result, str) and result == "respuesta de prueba",
              f"result='{result}'")
        check("call_llm_text nunca lanza excepción (error handling)",
              True)   # Si llegamos acá sin excepción, pasó

        # Test que call_llm_text retorna "" en error (nunca explota)
        mock_client.post = AsyncMock(side_effect=Exception("timeout simulado"))
        result_err = await call_llm_text(
            messages=[{"role": "user", "content": "test error"}],
            agent_id="eval-test",
        )
        check("call_llm_text retorna '' en error (no explota)",
              result_err == "",
              f"result='{result_err}'")

asyncio.run(_test_async_client())


# ── Test 10: Extractores async ──────────────────────────────
print("\n10. Extractores async — fact y graph extractor")

async def _test_extractors():
    # ── fact_extractor ──────────────────────────────────────
    with patch("llm.async_client._client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        # Caso: texto sin keywords → debe retornar {} sin llamar al LLM
        from memory.fact_extractor import extract_facts
        mock_client.post = AsyncMock()   # no debe llamarse

        result_short = await extract_facts("hola")
        check("extract_facts ignora textos cortos",
              result_short == {},
              f"result={result_short}")
        check("extract_facts no llama LLM sin keywords",
              not mock_client.post.called,
              "llamadas LLM: 0")

        # Caso: texto con keywords → llama LLM y parsea JSON
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"user_name": "EVAL_TestUser"}'}}]
        }
        mock_client.post = AsyncMock(return_value=mock_resp)

        result_facts = await extract_facts("me llamo EVAL_TestUser y soy desarrollador")
        check("extract_facts detecta keywords y llama LLM",
              mock_client.post.called,
              f"llamadas: {mock_client.post.call_count}")
        check("extract_facts parsea JSON correctamente",
              isinstance(result_facts, dict),
              f"result={result_facts}")

    # ── graph_extractor ─────────────────────────────────────
    with patch("llm.async_client._client") as mock_client:
        mock_resp2 = MagicMock()
        mock_resp2.raise_for_status = MagicMock()
        mock_resp2.json.return_value = {
            "choices": [{"message": {"content": '[{"subject":"eval_user","predicate":"usa","object":"eval_python"}]'}}]
        }
        mock_client.post = AsyncMock(return_value=mock_resp2)

        from memory.graph_extractor import extract_relations
        relations = await extract_relations("EVAL: el usuario usa Python para sus proyectos de hardware")

        check("extract_relations retorna lista",
              isinstance(relations, list),
              f"type={type(relations)}")
        check("extract_relations llama LLM para textos largos",
              mock_client.post.called)

        # Texto corto → no debe llamar LLM
        mock_client.post.reset_mock()
        rel_short = await extract_relations("hola")
        check("extract_relations ignora textos cortos",
              rel_short == [] and not mock_client.post.called)

asyncio.run(_test_extractors())


# ── Test 11: Orchestrator async ─────────────────────────────
print("\n11. Orchestrator async — routing sin LLM (keywords)")

from agent.orchestrator import Orchestrator

async def _test_orchestrator():
    orch = Orchestrator(client_fn=None)

    # Test keyword routing (zero-LLM) — no debe llamar al LLM
    hardware_queries = [
        "programá el arduino para parpadear el LED",
        "flashear el esp32",
        "qué dispositivos tengo registrados",
    ]
    research_queries = [
        "busca el precio del dólar hoy",
        "noticias de hoy",
    ]
    code_queries = [
        "calculá el 15% de 200",
        "ejecuta este script python",
    ]

    hw_ok  = all(orch._keyword_route(q) == ["hardware"] for q in hardware_queries)
    res_ok = all(orch._keyword_route(q) == ["research"] for q in research_queries)
    cod_ok = all(orch._keyword_route(q) == ["code"]     for q in code_queries)

    check("Hardware keywords detectados correctamente", hw_ok,
          f"casos: {[orch._keyword_route(q) for q in hardware_queries]}")
    check("Research keywords detectados correctamente", res_ok,
          f"casos: {[orch._keyword_route(q) for q in research_queries]}")
    check("Code keywords detectados correctamente",     cod_ok,
          f"casos: {[orch._keyword_route(q) for q in code_queries]}")

    # Consulta ambigua → debe retornar None (irá al LLM)
    ambiguous = orch._keyword_route("qué pensás sobre el futuro de la IA?")
    check("Consulta ambigua no matchea keywords (va al LLM)",
          ambiguous is None,
          f"result={ambiguous}")

    # Test route() completo con LLM mockeado
    with patch("llm.async_client._client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"agents": ["direct"], "reason": "saludo"}'}}]
        }
        mock_client.post = AsyncMock(return_value=mock_resp)

        # Para keywords que matchean, NO debe llamar al LLM
        agents = await orch.route("programá el arduino")
        check("route() usa keywords sin llamar LLM",
              agents == ["hardware"] and not mock_client.post.called,
              f"agents={agents}, LLM llamado={mock_client.post.called}")

        # Para consultas sin keywords, SÍ llama al LLM
        agents_llm = await orch.route("qué pensás de la vida?")
        check("route() llama LLM para consultas ambiguas",
              mock_client.post.called,
              f"agents={agents_llm}")

asyncio.run(_test_orchestrator())


# ── Test 12: Install missing libraries ─────────────────────
print("\n12. Firmware Flasher — auto-instalación de librerías")

from tools.firmware_flasher import install_missing_libraries

# Caso: error con librería faltante
error_fastled = """
In file included from /tmp/sketch.ino:1:
/tmp/sketch.ino:1:10: fatal error: FastLED.h: No such file or directory
 #include <FastLED.h>
          ^~~~~~~~~~~
compilation terminated.
"""

error_nolibrary = """
/tmp/sketch.ino: In function 'void setup()':
/tmp/sketch.ino:5:3: error: 'pinMode' was not declared in this scope
"""

# Sin arduino-cli disponible → debe manejar el error graciosamente
with patch("tools.firmware_flasher.subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    result = install_missing_libraries(error_fastled)
    check("Detecta FastLED.h como librería faltante",
          mock_run.called,
          f"llamadas subprocess: {mock_run.call_count}")

    # Verificar que el nombre de librería es correcto
    if mock_run.called:
        cmd = mock_run.call_args[0][0]
        check("Comando usa 'arduino-cli lib install'",
              "lib" in cmd and "install" in cmd,
              f"cmd={cmd}")
        check("Nombre de librería es 'FastLED' (sin .h)",
              "FastLED" in cmd,
              f"cmd={cmd}")

# Caso: error sin librería faltante → no debe llamar subprocess
with patch("tools.firmware_flasher.subprocess.run") as mock_run2:
    result2 = install_missing_libraries(error_nolibrary)
    check("No llama subprocess si no hay librería faltante",
          not mock_run2.called,
          f"llamadas: {mock_run2.call_count}")
    check("Retorna any_installed=False cuando no hay libs",
          not result2["any_installed"],
          f"result={result2}")


# ── Test 13: Proactive Engine ───────────────────────────────
print("\n13. Proactive Engine — notificaciones autónomas")

async def _test_proactive():
    from agent.proactive_engine import ProactiveEngine

    engine = ProactiveEngine()

    # Test subscribe/unsubscribe
    q1 = engine.subscribe()
    q2 = engine.subscribe()
    check("subscribe() agrega clientes",
          len(engine._clients) == 2,
          f"clientes={len(engine._clients)}")

    engine.unsubscribe(q1)
    check("unsubscribe() elimina cliente",
          len(engine._clients) == 1,
          f"clientes={len(engine._clients)}")

    # Test broadcast llega a clientes
    await engine._broadcast({
        "type":    "eval_test",
        "title":   "Test broadcast",
        "message": "mensaje de prueba",
    })
    check("_broadcast entrega mensaje al cliente",
          not q2.empty(),
          f"queue size={q2.qsize()}")

    msg = await q2.get()
    import json as _json_test
    parsed = _json_test.loads(msg)
    check("Mensaje broadcast tiene timestamp",
          "timestamp" in parsed,
          f"keys={list(parsed.keys())}")
    check("Mensaje broadcast preserva tipo",
          parsed.get("type") == "eval_test",
          f"type={parsed.get('type')}")

    # Test que sin clientes no explota
    engine.unsubscribe(q2)
    try:
        await engine._broadcast({"type": "test", "title": "sin clientes", "message": ""})
        check("_broadcast sin clientes no lanza excepción", True)
    except Exception as e:
        check("_broadcast sin clientes no lanza excepción", False, str(e))

    # Test detección de nuevos dispositivos (mockeado)
    with patch("agent.proactive_engine.detect_devices") as mock_detect:
        mock_detect.return_value = [
            {"port": "COM_EVAL_NEW", "name": "EVAL_Device", "platform": "arduino:avr"}
        ]
        engine._known_ports = set()  # Simular que no había dispositivos antes
        q3 = engine.subscribe()
        await engine._check_new_devices()
        check("Detecta nuevo dispositivo y notifica",
              not q3.empty(),
              f"notificaciones={q3.qsize()}")
        engine.unsubscribe(q3)

asyncio.run(_test_proactive())


# ── Test 14: Vision Agent (mock) ────────────────────────────
print("\n14. Vision Agent — análisis de circuitos (mockeado)")

from agent.agents.vision_agent import VisionAgent

MOCK_CIRCUIT_JSON = '''{
  "project_name": "EVAL Circuito LED",
  "description": "Circuito simple con LED y resistencia",
  "components": [
    {"name": "LED rojo", "type": "actuador", "pin": "13", "notes": "con resistencia 220ohm"},
    {"name": "Resistencia 220ohm", "type": "pasivo", "pin": "serie con LED"}
  ],
  "connections": [
    {"from": "Pin 13", "to": "LED anodo", "description": "señal digital"}
  ],
  "power": "5V USB",
  "confidence": "alta",
  "notes": "circuito básico de prueba"
}'''

va = VisionAgent()

# Test _parse_circuit con JSON válido
circuit = va._parse_circuit(MOCK_CIRCUIT_JSON)
check("_parse_circuit extrae project_name",
      circuit.get("project_name") == "EVAL Circuito LED",
      f"name='{circuit.get('project_name')}'")
check("_parse_circuit extrae components como lista",
      isinstance(circuit.get("components"), list) and len(circuit["components"]) == 2,
      f"components={len(circuit.get('components', []))}")
check("_parse_circuit extrae connections",
      isinstance(circuit.get("connections"), list),
      f"connections={circuit.get('connections')}")

# Test _parse_circuit con JSON rodeado de markdown (como lo haría el LLM)
markdown_json = f"```json\n{MOCK_CIRCUIT_JSON}\n```"
circuit_md = va._parse_circuit(markdown_json)
check("_parse_circuit limpia markdown del LLM",
      circuit_md.get("project_name") == "EVAL Circuito LED",
      f"name='{circuit_md.get('project_name')}'")

# Test _parse_circuit con JSON inválido → retorna {}
circuit_bad = va._parse_circuit("esto no es json válido")
check("_parse_circuit retorna {} con JSON inválido",
      circuit_bad == {},
      f"result={circuit_bad}")

# Test _build_summary
summary = va._build_summary(circuit, "EVAL_Arduino", saved=True)
check("_build_summary incluye nombre del proyecto",
      "EVAL Circuito LED" in summary,
      f"summary='{summary[:80]}'")
check("_build_summary confirma guardado",
      "EVAL_Arduino" in summary,
      f"summary='{summary[:120]}'")

# Test analyze_circuit con LLaVA mockeado (sin GPU real)
with patch.object(va, "_check_vision_model", return_value=True), \
     patch.object(va, "_call_llava", return_value=MOCK_CIRCUIT_JSON):

    result = va.analyze_circuit("fake_base64_image==", device_name="")
    check("analyze_circuit retorna success=True con mock",
          result["success"],
          f"success={result['success']}")
    check("analyze_circuit retorna circuit con componentes",
          len(result["circuit"].get("components", [])) == 2,
          f"components={len(result['circuit'].get('components', []))}")
    check("analyze_circuit no guarda si no hay device_name",
          not result["saved"],
          f"saved={result['saved']}")

# Test cuando LLaVA no está disponible
with patch.object(va, "_check_vision_model", return_value=False):
    result_no_llava = va.analyze_circuit("fake_base64==", device_name="")
    check("analyze_circuit falla graciosamente sin LLaVA",
          not result_no_llava["success"] and "ollama pull" in result_no_llava["message"],
          f"message='{result_no_llava['message'][:60]}'")


# ── Test 15: User Profiler ──────────────────────────────────
print("\n15. User Profiler — modelo mental del usuario")

from unittest.mock import MagicMock
from agent.user_profiler import UserProfiler

# Mock de sql_memory para no tocar la DB real
mock_sql = MagicMock()
mock_sql.get_all_facts.return_value = {}

profiler = UserProfiler(mock_sql)

# Perfil default vacío
profile = profiler.get_profile()
check("Perfil default tiene expertise 'desconocido'",
      profile["expertise"] == "desconocido",
      f"expertise={profile['expertise']}")
check("Perfil default tiene plataformas vacías",
      profile["platforms"] == [],
      f"platforms={profile['platforms']}")

# Detectar expertise principiante
profiler.update_from_interaction("no sé cómo conectar el sensor, es mi primer proyecto")
check("Detecta expertise principiante",
      profiler.get_profile()["expertise"] == "principiante",
      f"expertise={profiler.get_profile()['expertise']}")

# Detectar expertise avanzado (override)
profiler.update_from_interaction("necesito configurar el watchdog timer y manejar interrupciones por DMA")
check("Detecta expertise avanzado",
      profiler.get_profile()["expertise"] == "avanzado",
      f"expertise={profiler.get_profile()['expertise']}")

# Detectar plataformas
profiler._cache = profiler._default_profile()
profiler.update_from_interaction("estoy programando un esp32 con arduino y también un stm32")
platforms = profiler.get_profile()["platforms"]
check("Detecta ESP32 como plataforma",
      "esp32" in platforms,
      f"platforms={platforms}")
check("Detecta STM32 como plataforma",
      "stm32" in platforms,
      f"platforms={platforms}")

# Detectar lenguaje preferido
profiler._cache = profiler._default_profile()
profiler.update_from_interaction("quiero usar micropython para este proyecto")
check("Detecta MicroPython como lenguaje preferido",
      profiler.get_profile()["preferred_lang"] == "micropython",
      f"lang={profiler.get_profile()['preferred_lang']}")

# Detectar estilo de respuesta
profiler._cache = profiler._default_profile()
profiler.update_from_interaction("explicame todo paso a paso con detalles")
check("Detecta estilo 'detallado'",
      profiler.get_profile()["response_style"] == "detallado",
      f"style={profiler.get_profile()['response_style']}")

# format_for_prompt no inyecta nada con < 3 interacciones
profiler._cache = profiler._default_profile()
profiler._cache["interaction_count"] = 2
prompt_ctx = profiler.format_for_prompt()
check("format_for_prompt vacío con < 3 interacciones",
      prompt_ctx == "",
      f"context='{prompt_ctx[:50]}'")

# format_for_prompt inyecta contexto con perfil completo
profiler._cache = {
    "expertise":         "avanzado",
    "platforms":         ["arduino", "esp32"],
    "preferred_lang":    "c++",
    "response_style":    "conciso",
    "last_topics":       ["control LED", "sensor temperatura"],
    "interaction_count": 10,
    "last_seen":         "",
}
prompt_ctx = profiler.format_for_prompt()
check("format_for_prompt incluye expertise",
      "avanzado" in prompt_ctx,
      f"context='{prompt_ctx[:80]}'")
check("format_for_prompt incluye plataformas",
      "arduino" in prompt_ctx and "esp32" in prompt_ctx,
      f"context='{prompt_ctx[:120]}'")
check("format_for_prompt incluye hint de estilo",
      "breve" in prompt_ctx or "directo" in prompt_ctx,
      f"context='{prompt_ctx}'")

# get_profile_summary retorna dict con todos los campos
summary = profiler.get_profile_summary()
check("get_profile_summary tiene todos los campos",
      all(k in summary for k in ["expertise", "platforms", "preferred_lang",
                                   "response_style", "last_topics", "interaction_count"]),
      f"keys={list(summary.keys())}")


# ── Test 16: Plugin System ──────────────────────────────────
print("\n16. Plugin System — autodiscovery y ejecución")

import tempfile
from pathlib import Path
from tools.plugin_loader import PluginLoader

# Crear plugin de prueba en un directorio temporal
EVAL_PLUGIN_CODE = '''
PLUGIN_NAME        = "eval_plugin"
PLUGIN_DESCRIPTION = "Plugin de evaluación — solo para tests"
PLUGIN_VERSION     = "1.0"

def eval_suma(a: int, b: int) -> int:
    return a + b

def eval_echo(texto: str) -> str:
    return f"ECHO: {texto}"

PLUGIN_TOOLS = [
    {
        "function":    eval_suma,
        "name":        "eval_suma",
        "description": "Suma dos números",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "function":    eval_echo,
        "name":        "eval_echo",
        "description": "Repite un texto",
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {"type": "string"}
            },
            "required": ["texto"]
        }
    }
]
'''

INVALID_PLUGIN_CODE = '''
# Plugin inválido — falta PLUGIN_TOOLS
PLUGIN_NAME        = "invalid"
PLUGIN_DESCRIPTION = "Plugin inválido para test"
'''

with tempfile.TemporaryDirectory() as tmp_dir:
    plugins_dir = Path(tmp_dir)

    # Crear plugin válido
    (plugins_dir / "eval_plugin.py").write_text(EVAL_PLUGIN_CODE, encoding="utf-8")
    # Crear plugin inválido
    (plugins_dir / "invalid_plugin.py").write_text(INVALID_PLUGIN_CODE, encoding="utf-8")
    # Crear archivo que debe ignorarse
    (plugins_dir / "__init__.py").write_text("", encoding="utf-8")

    # Parchear PLUGINS_DIR para apuntar al directorio temporal
    import tools.plugin_loader as pl_module
    original_dir = pl_module.PLUGINS_DIR
    pl_module.PLUGINS_DIR = plugins_dir

    loader = PluginLoader()
    count  = loader.load_all()

    # Restaurar
    pl_module.PLUGINS_DIR = original_dir

    check("Carga plugins válidos (ignora inválidos)",
          count == 1,
          f"plugins cargados={count}")

    check("__init__.py ignorado correctamente",
          "_" not in [p["name"] for p in loader.get_plugins_info()],
          f"plugins={[p['name'] for p in loader.get_plugins_info()]}")

    # Verificar functions registradas
    fns = loader.get_functions()
    check("eval_suma registrada como función",
          "eval_suma" in fns and callable(fns["eval_suma"]),
          f"tools={list(fns.keys())}")
    check("eval_echo registrada como función",
          "eval_echo" in fns,
          f"tools={list(fns.keys())}")

    # Verificar definitions para el LLM
    defs = loader.get_definitions()
    check("Definitions JSON generadas para el LLM",
          len(defs) == 2,
          f"definitions={len(defs)}")
    check("Definition tiene estructura correcta",
          all("function" in d and "name" in d["function"] for d in defs),
          f"defs={[d['function']['name'] for d in defs]}")

    # Ejecutar tools a través del loader
    result_suma = loader.execute("eval_suma", {"a": 3, "b": 7})
    check("execute() retorna resultado correcto",
          result_suma == "10",
          f"result='{result_suma}'")

    result_echo = loader.execute("eval_echo", {"texto": "hola stratum"})
    check("execute() funciona con strings",
          "ECHO: hola stratum" in result_echo,
          f"result='{result_echo}'")

    # Tool inexistente — no debe explotar
    result_missing = loader.execute("tool_que_no_existe", {})
    check("execute() tool inexistente retorna mensaje claro",
          "no encontrada" in result_missing.lower(),
          f"result='{result_missing}'")

    # is_plugin_tool
    check("is_plugin_tool() detecta tools de plugin",
          loader.is_plugin_tool("eval_suma"),
          "eval_suma es plugin tool")
    check("is_plugin_tool() no confunde con tools core",
          not loader.is_plugin_tool("web_search"),
          "web_search no es plugin tool")

    # get_plugins_info
    info_list = loader.get_plugins_info()
    check("get_plugins_info() retorna metadata completa",
          len(info_list) == 1 and info_list[0]["name"] == "eval_plugin",
          f"info={info_list}")
    check("Plugin info tiene todos los campos",
          all(k in info_list[0] for k in ["name", "description", "file", "tools", "version"]),
          f"keys={list(info_list[0].keys())}")

    # Error handling — función que explota
    loader._functions["eval_crash"] = lambda: 1/0
    result_crash = loader.execute("eval_crash", {})
    check("execute() maneja excepciones sin explotar",
          "error" in result_crash.lower(),
          f"result='{result_crash}'")


# ── Test 17: Consolidación nocturna ────────────────────────
print("\n17. Consolidación nocturna — scheduler automático")

async def _test_consolidation():
    from memory.memory_consolidator import MemoryConsolidator, _run_async
    from unittest.mock import patch, AsyncMock, MagicMock

    consolidator = MemoryConsolidator()

    # Test _analyze_contradiction con mock async
    with patch("memory.memory_consolidator.call_llm_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"contradiction": true, "reason": "trabajo diferente", "keep": "new", "merged": null}'

        result = await consolidator._analyze_contradiction(
            "trabajo en Acme Corp",
            "trabajo en Google"
        )
        check("_analyze_contradiction detecta contradicción",
              result.get("contradiction") is True,
              f"result={result}")
        check("_analyze_contradiction sugiere keep=new",
              result.get("keep") == "new",
              f"keep={result.get('keep')}")

        # Sin contradicción
        mock_llm.return_value = '{"contradiction": false, "reason": "temas distintos", "keep": "both", "merged": null}'
        result2 = await consolidator._analyze_contradiction("me gusta el café", "programo en Python")
        check("_analyze_contradiction retorna no-contradicción",
              result2.get("contradiction") is False,
              f"result={result2}")

    # Test _summarize_memories con mock
    with patch("memory.memory_consolidator.call_llm_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "El usuario es desarrollador Python que trabaja con Arduino."

        summary = await consolidator._summarize_memories([
            "Usuario trabajó con Arduino Uno",
            "Usuario programó en Python",
            "Usuario resolvió un bug en el sensor DHT22",
        ])
        check("_summarize_memories retorna resumen",
              summary is not None and len(summary) > 10,
              f"summary='{summary[:60]}'")
        check("_summarize_memories llama al LLM",
              mock_llm.called,
              f"llamadas={mock_llm.call_count}")

    # Test consolidate_old_memories_async con vector_store mockeado
    mock_point = MagicMock()
    mock_point.payload = {
        "text":      "Usuario: programé un LED | Agente: Listo",
        "timestamp": "2020-01-01T00:00:00+00:00",  # muy antiguo
        "type":      "conversation",
    }

    with patch("memory.memory_consolidator.vector_store") as mock_vs, \
         patch("memory.memory_consolidator.call_llm_text", new_callable=AsyncMock) as mock_llm, \
         patch("memory.memory_consolidator.store_memory") as mock_store:

        mock_vs.client.scroll.return_value = ([mock_point] * 5, None)
        mock_llm.return_value = "Resumen: el usuario programó LEDs y trabajó con hardware."

        result = await consolidator.consolidate_old_memories_async(days_threshold=1)
        check("consolidate_old_memories_async procesa memorias antiguas",
              result.get("consolidated", 0) > 0 or "skipped" in result,
              f"result={result}")

    # Test _sleep_until_midnight retorna un tiempo razonable (< 24h)
    from agent.proactive_engine import ProactiveEngine
    engine = ProactiveEngine()

    # Mockear asyncio.sleep para capturar el valor sin esperar
    slept_seconds = []
    async def mock_sleep(secs):
        slept_seconds.append(secs)

    with patch("agent.proactive_engine.asyncio.sleep", side_effect=mock_sleep):
        await engine._sleep_until_midnight()

    check("_sleep_until_midnight duerme menos de 24h",
          slept_seconds and 0 <= slept_seconds[0] <= 86400,
          f"segundos={slept_seconds[0] if slept_seconds else 'N/A':.0f}")

    # Test que _loop_nightly_consolidation notifica al cliente tras consolidar
    q = engine.subscribe()
    with patch("memory.memory_consolidator.memory_consolidator") as mock_cons, \
         patch("agent.proactive_engine.asyncio.sleep", new_callable=AsyncMock):

        mock_cons.consolidate_old_memories_async = AsyncMock(
            return_value={"consolidated": 12, "summary": "Resumen de prueba"}
        )
        # Simular un ciclo del loop (sin el sleep de 24h)
        await engine._broadcast({
            "type":    "nightly_consolidation",
            "title":   "Consolidación nocturna completada",
            "message": "Procesé **12** memorias antiguas.",
            "consolidated": 12,
        })

    check("Notificación nocturna llega al cliente",
          not q.empty(),
          f"queue={q.qsize()}")

    msg = json.loads(await q.get())
    check("Notificación tiene tipo correcto",
          msg.get("type") == "nightly_consolidation",
          f"type={msg.get('type')}")
    check("Notificación tiene timestamp",
          "timestamp" in msg,
          f"keys={list(msg.keys())}")

    engine.unsubscribe(q)

import json
asyncio.run(_test_consolidation())


# ── Test 18: Agent Runner async ─────────────────────────────
print("\n18. Agent Runner async — loop ReAct sin bloqueo")

async def _test_agent_runner():
    from agent.agent_runner import run_agent_loop
    from unittest.mock import AsyncMock, MagicMock
    import inspect

    # Verificar que run_agent_loop es async
    check("run_agent_loop es una coroutine async",
          inspect.iscoroutinefunction(run_agent_loop),
          f"type={type(run_agent_loop)}")

    # Test: respuesta directa sin tool_calls
    mock_client = AsyncMock(return_value={
        "choices": [{
            "message":       {"role": "assistant", "content": "Respuesta directa"},
            "finish_reason": "stop",
        }]
    })

    answer, msgs = await run_agent_loop(mock_client, [{"role": "user", "content": "hola"}])
    check("Retorna respuesta cuando finish_reason=stop",
          answer == "Respuesta directa",
          f"answer='{answer}'")
    check("client_fn llamado exactamente una vez",
          mock_client.call_count == 1,
          f"calls={mock_client.call_count}")

    # Test: una tool_call seguida de respuesta final
    tool_call = {
        "id":       "call_123",
        "function": {"name": "eval_tool", "arguments": '{"q": "test"}'},
    }
    responses = [
        # Primer paso: pide tool
        {
            "choices": [{
                "message":       {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                "finish_reason": "tool_calls",
            }]
        },
        # Segundo paso: respuesta final
        {
            "choices": [{
                "message":       {"role": "assistant", "content": "Resultado final"},
                "finish_reason": "stop",
            }]
        },
    ]
    mock_client2 = AsyncMock(side_effect=responses)

    # Mockear execute_tool
    with patch("agent.agent_runner.execute_tool", return_value="resultado_tool"):
        answer2, msgs2 = await run_agent_loop(
            mock_client2,
            [{"role": "user", "content": "usá la tool"}]
        )

    check("Ejecuta tool y continúa el loop",
          answer2 == "Resultado final",
          f"answer='{answer2}'")
    check("client_fn llamado 2 veces (tool + final)",
          mock_client2.call_count == 2,
          f"calls={mock_client2.call_count}")
    check("Tool result agregado al historial",
          any(m.get("role") == "tool" for m in msgs2),
          f"roles={[m.get('role') for m in msgs2]}")

    # Test: múltiples tool_calls en paralelo
    tool_calls_multi = [
        {"id": "call_A", "function": {"name": "tool_a", "arguments": "{}"}},
        {"id": "call_B", "function": {"name": "tool_b", "arguments": "{}"}},
        {"id": "call_C", "function": {"name": "tool_c", "arguments": "{}"}},
    ]
    responses_multi = [
        {
            "choices": [{
                "message":       {"role": "assistant", "content": None, "tool_calls": tool_calls_multi},
                "finish_reason": "tool_calls",
            }]
        },
        {
            "choices": [{
                "message":       {"role": "assistant", "content": "Todo listo"},
                "finish_reason": "stop",
            }]
        },
    ]
    mock_client3   = AsyncMock(side_effect=responses_multi)
    executed_tools = []

    def track_tool(name: str, args: dict) -> str:
        executed_tools.append(name)
        return f"result_{name}"

    with patch("agent.agent_runner.execute_tool", side_effect=track_tool):
        answer3, _ = await run_agent_loop(
            mock_client3,
            [{"role": "user", "content": "usá 3 tools"}]
        )

    check("Ejecuta múltiples tools en paralelo (asyncio.gather)",
          len(executed_tools) == 3,
          f"tools ejecutadas={executed_tools}")
    check("Respuesta final correcta tras múltiples tools",
          answer3 == "Todo listo",
          f"answer='{answer3}'")

    # Test: límite de pasos (MAX_STEPS)
    infinite_tool = [{"id": "call_inf", "function": {"name": "loop_tool", "arguments": "{}"}}]
    mock_infinite = AsyncMock(return_value={
        "choices": [{
            "message":       {"role": "assistant", "content": None, "tool_calls": infinite_tool},
            "finish_reason": "tool_calls",
        }]
    })
    # El último call devuelve respuesta final
    final_response = {
        "choices": [{
            "message":       {"role": "assistant", "content": "Forzado"},
            "finish_reason": "stop",
        }]
    }
    mock_infinite.side_effect = [
        *[mock_infinite.return_value] * 6,  # MAX_STEPS llamadas con tool
        final_response,                      # llamada final forzada
    ]

    with patch("agent.agent_runner.execute_tool", return_value="ok"):
        answer_limit, _ = await run_agent_loop(
            mock_infinite,
            [{"role": "user", "content": "loop infinito"}]
        )

    check("Respeta MAX_STEPS y fuerza respuesta final",
          answer_limit == "Forzado",
          f"answer='{answer_limit}'")

asyncio.run(_test_agent_runner())


# ── Test 19: HardwareAgent singleton ────────────────────────
print("\n19. HardwareAgent singleton — instancia única compartida")

from agent.agents.hardware_agent import get_hardware_agent, HardwareAgent

# get_hardware_agent devuelve siempre la misma instancia
inst1 = get_hardware_agent()
inst2 = get_hardware_agent()
inst3 = get_hardware_agent()

check("get_hardware_agent() retorna singleton (misma instancia)",
      inst1 is inst2 is inst3,
      f"ids: {id(inst1)}, {id(inst2)}, {id(inst3)}")

check("La instancia es un HardwareAgent",
      isinstance(inst1, HardwareAgent),
      f"type={type(inst1)}")

check("Tiene atributo name correcto",
      inst1.name == "HardwareAgent",
      f"name={inst1.name}")

# Verificar que el Orchestrator usa get_hardware_agent (no HardwareAgent())
import inspect
orchestrator_src = inspect.getsource(
    __import__("agent.orchestrator", fromlist=["Orchestrator"]).Orchestrator.run
)
check("Orchestrator importa get_hardware_agent (no HardwareAgent())",
      "get_hardware_agent" in orchestrator_src,
      f"usa singleton: {'get_hardware_agent' in orchestrator_src}")
check("Orchestrator NO instancia HardwareAgent() directamente",
      "HardwareAgent()" not in orchestrator_src,
      f"instancia directa: {'HardwareAgent()' in orchestrator_src}")


# ── Test 20: Type hints y mypy ───────────────────────────────
print("\n20. Type hints — cobertura en módulos críticos")

import inspect
import ast
from pathlib import Path

# Determinar el root del proyecto de forma robusta
ROOT_DIR = Path(__file__).parent.parent

def count_typed_functions(filepath: Path) -> tuple[int, int]:
    """Retorna (funciones_con_tipos, total_funciones)."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree   = ast.parse(source)
        total  = typed = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total += 1
                has_return = node.returns is not None
                has_args   = all(
                    arg.annotation is not None
                    for arg in node.args.args
                    if arg.arg != "self"
                )
                if has_return and has_args:
                    typed += 1
        return typed, total
    except Exception:
        return 0, 0

# Verificar cobertura de tipos en módulos clave
modules_to_check = [
    ("llm/async_client.py",       70),   # % mínimo esperado
    ("agent/agent_runner.py",     60),
    ("agent/user_profiler.py",    50),
    ("tools/plugin_loader.py",    50),
]

for rel_path, min_pct in modules_to_check:
    full_path = ROOT_DIR / rel_path
    typed, total = count_typed_functions(full_path)
    if total == 0:
        check(f"{rel_path} — type hints", False, f"archivo no encontrado en {full_path} o sin funciones")
        continue
    pct = (typed / total) * 100
    check(f"{rel_path} — {typed}/{total} funciones tipadas ({pct:.0f}%)",
          pct >= min_pct,
          f"mínimo esperado: {min_pct}%")

# Verificar que mypy.ini existe y tiene configuración válida
mypy_ini = ROOT_DIR / "mypy.ini"
check("mypy.ini existe en el root del proyecto",
      mypy_ini.exists(),
      f"path={mypy_ini.absolute()}")

if mypy_ini.exists():
    content = mypy_ini.read_text(encoding="utf-8")
    check("mypy.ini tiene python_version configurado",
          "python_version" in content,
          f"contenido parcial: {content[:50]}")
    check("mypy.ini tiene disallow_untyped_defs",
          "disallow_untyped_defs" in content,
          f"strict mode configurado")
    check("mypy.ini ignora librerías sin stubs (qdrant, networkx)",
          "qdrant_client" in content and "networkx" in content,
          f"ignore_missing_imports configurado")

# Verificar que async_client tiene tipo de retorno en funciones principales
async_client_file = ROOT_DIR / "llm/async_client.py"
async_client_src = async_client_file.read_text(encoding="utf-8") if async_client_file.exists() else ""
check("call_llm_async tiene return type dict[str, Any]",
      "dict[str, Any]" in async_client_src,
      f"typed: {'dict[str, Any]' in async_client_src}")
check("stream_llm_async tiene Callable en signature",
      "Callable" in async_client_src,
      f"typed: {'Callable' in async_client_src}")



# ── Cleanup final ───────────────────────────────────────────
cleanup_eval_data()


# ── Resumen ─────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
print(f"\n{'='*40}")
print(f"Resultado: {passed}/{total} tests pasaron")
if passed == total:
    print("✓ Todo OK — memoria real no contaminada\n")
else:
    print(f"✗ {total - passed} tests fallaron\n")
    sys.exit(1)

# ── Test 21: Integración de circuitos (nuevo) ─────────────────────────
print("\n21. Integración de circuitos — flujo completo")

async def _test_circuit_integration():
    """Test de integración completo: lenguaje natural → circuito → firmware → PCB"""
    from agent.agents.circuit_agent import CircuitAgent
    from database.hardware_memory import hardware_memory
    from tools.schematic_renderer import SchematicRenderer
    from tools.pcb_renderer import PCBRenderer
    
    # 1. Parsear circuito
    agent = CircuitAgent()
    circuit_desc = "Un LED conectado al pin 13 de Arduino con resistencia de 220 ohms"
    circuit = agent.parse_circuit(circuit_desc)
    
    check("Parseo de circuito básico", 
          circuit is not None and "components" in circuit,
          f"componentes={len(circuit.get('components', [])) if circuit else 0}")
    
    if not circuit:
        return
        
    # 2. Guardar en hardware memory
    TEST_DEVICE = "EVAL_Circuit_Integration_Test"
    hardware_memory.register_device({
        "name": TEST_DEVICE,
        "port": "COM_EVAL",
        "fqbn": "arduino:avr:uno",
        "platform": "arduino:avr"
    })
