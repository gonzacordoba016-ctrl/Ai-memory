# Stratum / ai-memory-engine — Análisis Técnico Profundo

> Repositorio: `C:\wamp64\www\ai-memory-engine` · Branch: `main` · Commit: `175583db`
> 1.493 archivos · 31.516 nodos en grafo (28.598 funciones, 1.056 clases). Comunidades reales (excluyendo `node_modules/typescript`): `agent-agent (181)`, `modules-circuit (391)`, `tools-sym (383)`, `database-db (160)`, `memory-memory (41)`.

---

## 1. ARQUITECTURA REAL (no marketing)

Stratum es un **chat asistente con memoria persistente especializado en electrónica**, expuesto vía FastAPI + WebSocket. Por debajo es un *orquestador keyword-first → ReAct subagents* sobre OpenAI-compatible APIs (OpenRouter/Ollama/LMStudio). Tres almacenes de memoria (SQLite + Qdrant + NetworkX) y un pipeline determinista de síntesis de circuitos que **no es LLM theater** — es Python puro armado a mano.

### Diagrama de capas

```
HTTP/WS (api/server.py + routers)
        │
        ▼
SessionStore[sid] → AgentState (history deque(20), facts, active_circuit, firmware_draft)
        │
        ▼
AgentController.process_input()  ← ContextVar(_current_session)
   │     │
   │     ├── extract_facts()  (LLM JSON)
   │     ├── extract_relations()  (LLM JSON → graph_memory)
   │     ├── search_memory()  (Qdrant + decay temporal + LRU/TTL cache)
   │     ├── Orchestrator.run()  (180s timeout)
   │     │      ├── _keyword_route()  zero-LLM, regex
   │     │      └── LLM fallback (LLM_MODEL_FAST, t=0)
   │     │             ↓
   │     │      [research|code|memory] → BaseAgent.run() → asyncio.run(run_agent_loop, max_steps=4)
   │     │      [circuit_design]       → CircuitAgent (pipeline determinista 2-stage)
   │     │      [hardware]             → HardwareAgent | ElectricalCalcAgent
   │     │
   │     ├── build_prompt(history, facts, memorias, graph_context, profile, source_context)
   │     └── stream_llm_async() → on_token → WS frame
        │
        ▼
SQLite store_message + add_message a state + episode vector + profiler.update
```

### Stack
- **API**: FastAPI + uvicorn, GZip middleware, slowapi rate limit, JWT (`MULTI_USER` env-toggled).
- **LLM**: httpx client (sync + async compartidos, connection pool), provider-agnostic vía `core/config.py:get_llm_api/headers/model`.
- **Persistencia**: SQLite (memory.db, sessions, facts, circuits, jobs, stock), Qdrant embebido o cloud (vectores 384-dim `all-MiniLM-L6-v2`), NetworkX en `graph_memory.json`.
- **Frontend**: HTML/JS estático (`api/static`) + Capacitor mobile (Android/iOS) en `stratum-mobile/`.
- **Deploy**: Dockerfile + Railway (volumen `/data`, lazy-init de DB para sobrevivir mount race).

### Patrones arquitectónicos
- **Per-session state cache** con LRU+TTL+SQL hydration (`SessionStore`, fix muy reciente — antes era singleton global y mezclaba chats).
- **Orchestrator-as-router** (no es agent supervisor) — devuelve lista de agentes y los ejecuta en paralelo aparente, pero secuencial.
- **ReAct con cap rígido** (`BaseAgent.max_steps = 4`).
- **Strangler Pattern parcial**: pipeline determinista (`CircuitSynthesizer`) reemplazó al CircuitAgent puramente LLM tras un refactor explícito (commits `e749f7a`, `31bb8ea`, `cde1553`).
- **Lazy init en startup** (DB y Qdrant) para que el healthcheck de Railway pase antes de montar volumen.

---

## 2. ENTRY POINT REAL

| Capa | Archivo | Función |
|------|---------|---------|
| CLI | `run.py` | `cmd_serve()` levanta `uvicorn api.server:app` |
| ASGI | `api/server.py` | `app = FastAPI(...)`, monta routers, `@app.on_event("startup")` |
| Init | `api/server.py:_init_agents_background()` | crea `AgentController()` + `ProactiveEngine()` en `asyncio.create_task` |
| Estado global | `api/app_state.py` | módulo-singleton: `agent`, `proactive_engine` |
| Entry de turno | `api/routers/websockets.py:90` | `ws_chat(websocket, session, token)` |
| Pipeline | `agent/agent_controller.py:_process_input_impl` | dispara fases: `understanding → routing → ... → responding` |

**Cómo entra el input**: cliente abre `wss://.../api/ws/chat?session=<id>&token=<jwt>` → server emite `{type:"session", session_id, resumed, server_start}` → cliente envía `{message: "..."}` → handler corre `processing=True` mutex local + rate-limit 3s → crea `_task = asyncio.create_task(agent.process_input(...))` → loop `await asyncio.wait_for(asyncio.shield(_task), 15.0)` con heartbeat `{type:"thinking"}` cada 15s hasta `_timeout=240s` total.

**Cómo termina**: `process_input` retorna `{text, agents_used, circuit_id, circuit_name}`. WS persiste assistant message en SQL, emite `{type:"done", content, agents_used, elapsed_ms, facts?, graph?, circuit_design_id?}`. En el primer mensaje, también dispara `_generate_title_async` y `_send_session_context` en background.

**Continuations**: no hay loop multi-turno automático; cada `receive_text` es independiente. El history se reconstruye desde SQL en el SessionStore al primer acceso. No hay reintentos automáticos a nivel turno — si falla, error al cliente.

---

## 3. FLUJO INTERNO DETALLADO (un turno completo)

```
ws_chat (api/routers/websockets.py:90)
  ├─ _ws_require_auth(token)                                  # JWT opcional
  ├─ sql_db.store_message("user", input, session_id)
  ├─ sql_db.touch_session(session_id)
  ├─ estimate_quality_time(input)  ─→ {seconds, phases, complexity}
  │     emit {type:"estimate", ...}
  └─ asyncio.create_task(agent.process_input(input, on_token, on_phase, session_id))
       │
       ▼
  AgentController.process_input  (agent/agent_controller.py)
    └─ _current_session.set(session_id)                       # ContextVar
        └─ _process_input_impl
             ├─ phase("understanding")
             ├─ asyncio.gather(
             │     extract_facts(input),                      # memory/fact_extractor.py — LLM JSON
             │     extract_relations(input)                   # memory/graph_extractor.py — LLM JSON
             │   )
             │   → store_fact() en SQL
             │   → graph_memory.add_facts_from_dict()
             │
             ├─ phase("routing")
             ├─ orch_result = await asyncio.wait_for(
             │     Orchestrator.run(query, context, history, on_phase),
             │     timeout=180.0)
             │
             │     Orchestrator.route(query):                 # agent/orchestrator.py
             │       1) _keyword_route(q)                     # KEYWORD_ROUTES + 2 regex precompiladas
             │          - CIRCUIT_DESIGN_KEYWORDS literal
             │          - _CIRCUIT_REGEX (verbo + sustantivo)
             │          - _CIRCUIT_MCU_REGEX (mcu+componente)
             │          - 'hardware'|'research'|'code'|'memory'|'calc' literals
             │       2) si None → call_llm_text(ROUTING_PROMPT, model=FAST, t=0, 30s)
             │       3) fallback ['direct']
             │
             │     Orchestrator.run(...):
             │       if 'memory'  in agents: asyncio.to_thread(memory_agent.run, ...)
             │       if 'research' in agents: asyncio.to_thread(research_agent.run, ...)
             │       if 'code'    in agents: asyncio.to_thread(code_agent.run, ...)
             │       if 'circuit_design' in agents: CircuitAgent() (síncrono, pipeline determinista)
             │           ├─ _detect_domain(q)                 # pre-pass keywords
             │           ├─ _select_mcu(q, history)           # detecta MCU mencionado
             │           ├─ _extract_circuit_spec()           # LLM Stage1: solo spec/params
             │           ├─ CircuitSynthesizer.build()        # Python: pone wires, BOM, gerber
             │           ├─ _capa1_validate_spec()
             │           ├─ _capa2_drc_with_retry()           # design rules check
             │           └─ save_design() → SQL → returns design_id
             │       if 'hardware' in agents:
             │           ec_handled = is_calc_query → ElectricalCalcAgent.run()
             │           else → asyncio.to_thread(hw_agent.run, ...)
             │       returns {agents_used, results, combined_context}
             │
             ├─ Si agents_used contiene 'hardware' y result es firmware:
             │     state.set_firmware_draft(<bloque ```cpp>)
             │
             ├─ phase("retrieving_memory")
             ├─ memories = asyncio.to_thread(search_memory, input, 5)
             │     vector_store.search() → top_k*3 → decay exp(-rate*days) → top_k
             │     LRU cache (128) TTL 5min
             │
             ├─ source_context = search_in_sources(input, profile.active_sources)
             ├─ profile_context = profiler.format_for_prompt()
             │
             ├─ prompt = build_prompt(input, history, memories, facts,
             │                         graph_context=combined_context,
             │                         user_profile_context=profile_context,
             │                         system_prompt=ai_system_prompt,
             │                         source_context=...)
             │
             ├─ phase("responding")
             ├─ if on_token:
             │     stream_llm_async([{role:"user", content:prompt}], on_token)
             │   else:
             │     call_llm_async(...) → response.choices[0].message.content
             │
             ├─ state.add_message("assistant", response)
             ├─ _store_episode(input, response)              # vector_store.upsert
             ├─ profiler.update_from_interaction(input, response)
             └─ asyncio.create_task(_auto_fetch_datasheets(...))   # background
       ▼
  ws_chat back-half:
    ├─ sql_db.store_message("assistant", response, elapsed_ms)
    ├─ if first_msg: update_session_title(fallback) + bg LLM title
    └─ emit {type:"done", content, agents_used, elapsed_ms, facts?, graph?, circuit_id?}
```

**Dependencias críticas**: `httpx` (LLM transport), `qdrant-client` (vector), `sentence-transformers` (embeddings, modelo precargado en build), `networkx`, `pydantic v2`, `slowapi`, `passlib[bcrypt]`, `python-jose[jwt]`, `fastapi`, `uvicorn`.

---

## 4. STATE MANAGEMENT

### Layers
| Layer | Ubicación | Vida | Notas |
|-------|-----------|------|-------|
| `AgentState` | `agent/agent_state.py` | per-session | `deque(maxlen=20)` history, `dict` facts, `active_circuit`, `firmware_draft`, `platform` |
| `SessionStore` | `agent/session_store.py` | global | `OrderedDict[sid → (AgentState, ts)]` con `RLock`, **LRU `max_sessions`** + **TTL `ttl_seconds`**, hidrata desde `sql_db.get_conversation_by_session(sid, limit=history_limit)` |
| `_current_session` | ContextVar | per-task | propaga sid en async sin tocar firmas |
| SQL | `database/sql_memory.py` | persistente | tablas: facts, sessions, conversation, circuits, jobs, stock, intelligence; `_facts_seq`/`_graph_seq` para diffs incrementales en WS |
| Qdrant | `infrastructure/vector_store.py` | persistente | singleton lazy-init, colección 384-dim cosine, `store/search` sync |
| NetworkX | `memory/graph_memory.py` | persistente | JSON dump, `_seq` counter |
| `_search_cache` | `memory/vector_memory.py` | proceso | LRU 128 + TTL 300s para búsquedas |

### Concurrencia
- **`processing` flag** local en `ws_chat` impide pipelining en una conexión.
- **`_WS_RATE_WINDOW = 3.0s`** rate limit per-connection.
- **`SessionStore` RLock** protege OrderedDict, pero las mutaciones de `AgentState.conversation_history` (deque) **no están bajo lock**. Si el mismo session_id se abre en 2 pestañas, hay race en `add_message`.
- **`asyncio.to_thread`** para sync agents → multiplica thread pool, ContextVar se copia al thread (Python 3.9+ default), pero `asyncio.run` dentro de `BaseAgent.run` crea event loop fresco — la propagación corta ahí.
- **httpx AsyncClient compartido** con detección de `is_closed` y reset por error de transport.

### Anti-loops y finalización
- `BaseAgent.max_steps = 4` (cap duro en ReAct).
- `Orchestrator.run` no itera — one-shot dispatch.
- `process_input` no recurre — un turno = una llamada.
- Timeouts en cascada: WS 240s → Orchestrator 180s → LLM 120s → routing 30s → fact_extract 30s.
- **No hay checkpoint formal** — el "checkpoint" es la persistencia incremental en SQL/Qdrant después de cada turno.

---

## 5. ORQUESTACIÓN

**Sin framework**. No hay LangGraph/LangChain/CrewAI/Autogen. Es código a mano en `agent/orchestrator.py` (26KB).

### Routing
```python
KEYWORD_ROUTES = {
  "circuit_design": [literales]   # 30+ keywords + 2 regex compiladas perezosamente
  "hardware":       [...]
  "research":       [...]
  "code":           [...]
  "calc":           [...]
  "memory":         [...]
}
ELECTRICAL_CALC_KEYWORDS = [...]   # disambiguator dentro de "hardware"
```

Pipeline:
1. `_keyword_route()` — 0 LLM. Regex `_CIRCUIT_REGEX` compilada en class attribute (race benigna).
2. Fallback LLM `call_llm_text(ROUTING_PROMPT, model=FAST, t=0)` con guard JSON parse.
3. Fallback final: `["direct"]`.

### Branching/dispatch
Todos los agentes seleccionados se ejecutan **secuencialmente** en `Orchestrator.run`. **No es paralelo** aunque la firma async sugiere lo contrario (`asyncio.to_thread` no se hace `gather`'d). Ventaja: el contexto de un agente puede informar al siguiente vía `context_parts`. Desventaja: latencia se suma.

### Errors/retries
- `try/except` por agente — si uno falla, los otros siguen.
- En LLM: `_is_transport_closed_error` + `_reset_client()` (1 retry).
- Sin retry sistemático con backoff.
- En CircuitAgent: `_capa2_drc_with_retry` reintenta el LLM si DRC falla.

---

## 6. TOOL CALLING / INTEGRACIONES

### Registry (`tools/tool_registry.py`)
```python
TOOL_FUNCTIONS = {
    "web_search": web_search,
    "get_datetime": get_datetime,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "execute_python": execute_python,
    "ingest_pdf": ingest_pdf,
    "detect_hardware": detect_device_str,
    "read_serial": lambda port, duration=5: ...,
    "send_serial": send_serial,
}
TOOL_DEFINITIONS = [{type:"function", function:{name, description, parameters:JSONSchema}}, ...]
```

`execute_tool(name, args)` busca en `TOOL_FUNCTIONS` + `plugin_loader._functions`. **Validación cero a nivel parámetros** — confía en que el LLM matchee el JSON Schema. Si falla, exception se serializa en string.

### Plugins (`tools/plugin_loader.py` 15KB)
- Carga dinámica desde `tools/plugins/*.py` con `importlib.util.spec_from_file_location`.
- Valida `PLUGIN_NAME / PLUGIN_DESCRIPTION / PLUGIN_TOOLS`.
- Conflictos por nombre → último gana con WARNING.
- También soporta upload por ZIP via API.
- Manifest opcional en `plugin.json`.

### Agentes (`agent/agents/`)
| Agent | Tools que puede usar | Tipo |
|-------|---------------------|------|
| `ResearchAgent` | `web_search`, `get_datetime` | sync ReAct, prefilter en knowledge base local |
| `CodeAgent` | `execute_python`, `read_file`, `write_file`, `list_files` | sync ReAct |
| `MemoryAgent` | (sin tools, wrapper de `search_memory`) | sync |
| `HardwareAgent` | hardware tools | sync |
| `CircuitAgent` | (no usa tools del registry — pipeline propio) | sync, pipeline 2-stage |
| `ElectricalCalcAgent` | electrical_formulas | async |
| `VisionAgent` | vision tools | (existe pero no veo dispatch desde Orchestrator.run) |

**Cómo agregar tool**: editar `tool_registry.py` (hardcoded) o dropear archivo en `tools/plugins/`. Para dispatch desde un agente nuevo: agregar agente en `agent/agents/`, registrar en `Orchestrator.__init__`, agregar branch en `Orchestrator.run`, agregar keyword en `KEYWORD_ROUTES`. **Cuatro lugares** = high coupling.

---

## 7. MODELOS Y PROMPTS

### Configuración (`core/config.py`)
- `LLM_PROVIDER`: `openrouter | ollama | lmstudio` (env-toggled, sin fallback automático).
- `LLM_MODEL` / `LLM_MODEL_FAST` / `LLM_MODEL_SMART` — los tres se leen de env y se usan según contexto:
  - Routing → `LLM_MODEL_FAST`, t=0
  - Stream main → `LLM_MODEL` (default), t=0.7
  - Circuit synthesis → `LLM_MODEL_SMART`, t variable
  - fact_extractor → default model, t=0
- Embedding: `sentence-transformers/all-MiniLM-L6-v2` (precargado en Dockerfile).
- `MEMORY_DECAY_RATE = 0.01` — decay exponencial diario para vectores.

### System prompts
- Default (`prompt_builder.py:DEFAULT_SYSTEM_PROMPT`): 30 líneas encadenando dominios (microcontroladores, electrónica de potencia, automatización industrial, comunicaciones, diseño...). Es un **mega-system-prompt** — el modelo carga ~600 tokens de scope antes de cada turno.
- `ai_system_prompt`: por-sesión, viene del perfil de IA (`ai_profile.system_prompt`).
- Cada subagente tiene su propio system prompt.
- `ROUTING_PROMPT` en orchestrator pide JSON `{agents:[...], reason:"..."}`.
- `EXTRACTION_PROMPT` en fact_extractor pide JSON con campos cerrados.
- CircuitAgent tiene varios prompts: `CIRCUIT_SPEC_PROMPT` (Stage 1), `CIRCUIT_PARSE_PROMPT`, prompts por dominio (`DOMAIN_HINTS`).

### Structured outputs
- `call_llm_sync` acepta `response_format` pero **`call_llm_async` NO lo expone** — inconsistencia.
- **No hay Pydantic en outputs LLM**. Validación = `json.loads(content.replace("```json","").replace("```",""))` en try/except.
- CircuitAgent es la excepción: el output del LLM es spec mínima, todo el resto lo arma Python en `tools/eda/` (IR + ComponentRegistry + ConstraintEngine).

### Fortalezas
- Provider-agnostic (cambiar OpenRouter ↔ Ollama es 1 env var).
- Modelo precargado en build → cold-start <1s.
- Cache de búsquedas vectoriales.
- Streaming token-a-token via `stream_llm_async`.

### Debilidades / hallucinations
- Prompt builder concatena strings sin escape; si una memoria contiene `Asistente:` sintético confunde el modelo.
- Sin schema validation → fact_extractor puede silenciar JSON malformado y perder datos.
- "Datos conocidos del usuario" se inyecta as-is — si están corruptos, persisten turno tras turno.
- Routing por keywords es frágil ("¿qué es un circuito RC?" → `circuit_design` → CircuitAgent que intenta sintetizar).
- `DEFAULT_SYSTEM_PROMPT` declara competencias (PLCs, VFDs, etc.) que el modelo puede no tener — **alucinación inducida por overclaim**.

---

## 8. STRUCTURED OUTPUTS Y VALIDACIÓN

| Mecanismo | ¿Lo usa? | Notas |
|-----------|----------|-------|
| OpenAI `response_format` | parcial | solo `call_llm_sync`; el async no |
| OpenAI tool/function calling | sí | `TOOL_DEFINITIONS` (JSON Schema); ejecuta en `tool_registry.execute_tool` |
| Pydantic | tools/eda IR | sí, robusto en pipeline EDA |
| Pydantic en LLM outputs | **no** | hueco grande |
| Output parsers | manuales | `replace("```json","").replace("```","").strip()` + `json.loads` en try/except |
| Coerción tipos | manual | `str(value)` antes de store_fact |
| Anti-hallucination | regex pre-filter | KEYWORDS gate antes de LLM (fact_extractor) — bueno; routing keyword-first — bueno |

---

## 9. PROBLEMAS POTENCIALES (concretos)

### Bugs y fragilidades reales

1. **Race en `AgentState.conversation_history`** — `SessionStore` lockea el OrderedDict, no el `deque`. Dos requests simultáneos a la misma `session_id` (caso real con 2 pestañas) causan history desordenado o pérdida de mensaje.
   - Fix: agregar lock interno por AgentState o serializar `process_input` por sid (`asyncio.Lock` per-sid en SessionStore).

2. **ContextVar se rompe al saltar a thread → asyncio.run** — `_current_session` se copia al `to_thread` worker, pero el `asyncio.run(run_agent_loop(...))` dentro de `BaseAgent.run` crea loop fresco. Si `run_agent_loop` o sus tools consultan `_current_session.get()` no van a ver el sid actual — silencioso.
   - Fix: pasar `session_id` explícito a `BaseAgent.run` o usar contextvars.copy_context().

3. **`Orchestrator.__init__(call_llm_sync)` legacy** — el commit `175583d` arregló subagents para usar `call_llm_async`, pero `client_fn=call_llm_sync` aún se almacena. Code smell — vestigio que invita a regresiones.

4. **`KEYWORD_ROUTES` overlap silencioso** — "código" matchea `code`, pero si el query es "código C++ para Arduino que controle un LED en el circuito X" matchea `code` *y* `circuit_design` *y* `hardware`. `_keyword_route` retorna **el primer match** (orden: circuit_design → hardware → research → code → memory → calc), no el más específico. Misroutes garantizados.

5. **`asyncio.run` en sync subagent** — patrón anti-async clásico. Cada call de subagent crea event loop nuevo, paga overhead de bootstrap y rompe propagación de timeouts del request. Si el ws_chat cancela el `_task`, los `asyncio.to_thread → asyncio.run(...)` no propagan la cancelación.

6. **Cache vectorial sin invalidación por memoria stale** — `invalidate_search_cache()` solo se llama en `store_memory`, pero si el embedding model cambia (env var) o la colección Qdrant se corrompe, el cache sirve resultados incorrectos hasta TTL (5min).

7. **`response_text` cuando `response is None`** — el block ws_chat tras timeout deja `response = None`. Más abajo hace `getattr(agent, '_last_agents_used', [])` pero también persiste `if response_text` — verifica el path completo: si `response_text` queda undefined, hay NameError silencioso (depende de path arriba).

8. **`get_event_loop()` deprecation** — `_reset_client()` usa `asyncio.get_event_loop()` que en Python 3.12+ emite DeprecationWarning si no hay loop corriendo. Si el reset se llama en cleanup, falla.

9. **Costo escondido por turno**: hasta **5–7 llamadas LLM** en el peor caso:
   - `extract_facts` (gated por keywords, OK)
   - `extract_relations`
   - `Orchestrator.route` (si keyword no matchea)
   - subagente (research/hardware/code)
   - `stream_llm_async` final
   - `_generate_title_async` (1° mensaje)
   - `_send_session_context` (sesión nueva)

10. **Loops infinitos**: técnicamente no hay (max_steps=4, no recursión). Pero `_auto_fetch_datasheets` se lanza en `asyncio.create_task` sin `asyncio.gather` ni cleanup → si el cliente se desconecta, la task sigue. Memory leak potencial bajo carga.

11. **`processing` flag local solo a la conexión** — si hay 2 WS abiertos para mismo `session_id` (cliente reconecta), no hay mutex distribuido.

12. **`startup_event` en API moderna está deprecated** — FastAPI recomienda lifespan handler. `@app.on_event("startup")` aún funciona pero emite warning.

### Errores silenciosos
- `try/except Exception: pass` en `infrastructure/vector_store.py` (lazy init), en `_send_session_context`, en `_generate_title_async`, en `_auto_fetch_datasheets`. Diagnóstico de fallos requiere grep manual de logs.

### Coupling excesivo
- Para agregar un agente nuevo hay que tocar **4 archivos**: registrar en `Orchestrator.__init__`, branch en `Orchestrator.run`, keywords en `KEYWORD_ROUTES`, archivo en `agent/agents/`. Sin convención de auto-discovery.
- `agent_controller.py` (22KB) hace de todo: orquesta, persiste, perfila, autoenvía datasheets, detecta firmware en respuestas (regex `re.findall(r'```cpp...')`).

---

## 10. PERFORMANCE Y COSTOS

### Cuellos de botella
| Componente | Costo | Notas |
|-----------|-------|-------|
| `extract_facts` + `extract_relations` | 2 LLM calls/turno | t=0 mitiga, pero igual 2-5s c/u |
| Orchestrator routing | 1 LLM call si keyword falla | `LLM_MODEL_FAST` reduce ~50% |
| Subagent ReAct (research/code) | 1-4 LLM calls (max_steps=4) | tools impredecibles |
| Stream final | 1 LLM call larga | dominante en latencia percibida |
| CircuitAgent | 2-3 LLM calls (spec, parse, DRC retry) | + 100ms Python pipeline |
| Vector search | I/O Qdrant | cacheado 5min, OK |
| Embedding | sentence-transformers CPU | ~50ms/texto, OK |

**Latencia P99 estimada por turno simple**: 8-15s.
**Latencia P99 turno con CircuitAgent**: 30-60s (DRC retry + render).

### Tokens
- System prompt base: ~600 tok.
- Historial 20 mensajes: ~3-6k tok.
- Memorias top-5: ~500-1500 tok.
- Facts + graph_context: ~200-800 tok.
- **Prompt típico**: 5-10k input tokens. Más output. Con OpenRouter en modelo Smart ($/1M), un usuario activo puede generar **$1-5/día** fácilmente.

### Qué optimizaría primero
1. **Paralelizar** `extract_facts || extract_relations || search_memory` con `asyncio.gather` desde el inicio del turno — corta ~5-8s.
2. **Truncar history** dinámicamente (no maxlen=20 fijo): summarize >10 turnos atrás vía un único call al final del turno.
3. **Usar `response_format={type:"json_schema"}`** en fact_extractor con Pydantic — elimina retries por JSON malformado.
4. **Skip extract_facts/relations** en queries técnicas (ya hay `_TECHNICAL_ROUTES` flag — verificar que se aplica a fondo).
5. **Cachear embeddings** por hash del texto (no solo búsquedas).
6. **Remover** `_generate_title_async` y `_send_session_context` del path crítico — solo sesión nueva, OK, pero podrían ser un único call combinado.

### Escalabilidad
- **SessionStore in-memory** → no escala horizontal. Si despliegan 2 réplicas, cada una tiene su propio cache → state inconsistency.
  - Fix: Redis o sticky sessions.
- **Qdrant embebido** → un solo proceso. Para producción usar Qdrant Cloud (ya soportado vía `QDRANT_URL`).
- **SQLite** → un escritor simultáneo. Para >50 usuarios concurrentes, migrar a Postgres.
- **NetworkX en JSON** → carga full a memoria, escribe full al guardar. >10k nodes y arde. Migrar a NetworkX-DB o Neo4j.

---

## 11. ADAPTABILIDAD

### Reutilizable (50%)
- `tools/tool_registry.py` + `tools/plugin_loader.py` — patrón limpio.
- `agent/session_store.py` — domain-agnostic.
- `agent/agent_controller.py` (con poda) — patrón generalizable.
- `memory/` (vector + graph + facts) — domain-agnostic.
- `core/prompt_builder.py` — agnóstico, solo cambiar DEFAULT_SYSTEM_PROMPT.
- `llm/async_client.py` — provider-agnostic.
- `api/server.py` + auth + rate limit — boilerplate FastAPI portable.

### Hardcoded a hardware (50%)
- `agent/agents/circuit_agent.py`, `hardware_agent.py`, `electrical_calc_agent.py`, `code_agent.py` (templates Arduino).
- `tools/circuit_synthesizer.py`, `tools/eda/`, `tools/electrical_drc.py`, `tools/firmware_generator.py`, `tools/firmware_validator.py`, `tools/firmware_flasher.py`, `tools/schematic_parser.py`, `tools/plc_parser.py`, `tools/kicad_symbols/`, `tools/datasheet_fetcher.py`, `tools/component_pinouts.py`, `tools/hardware_detector.py`, `tools/serial_monitor.py`, `tools/wokwi_simulator.py`.
- `database/circuit_design.py`, `database/component_stock.py`.
- `KEYWORD_ROUTES` y todo en `core/prompt_builder.py:DEFAULT_SYSTEM_PROMPT`.
- Frontend `api/static/`.

### Para adaptar a otro dominio (trading / cyber / EDA / QA)
Tres pasos:
1. **Reemplazar agentes**: nuevo `agents/{trading|cyber|...}_agent.py` + nuevas tools en `tools/`.
2. **Reescribir routing**: `Orchestrator.KEYWORD_ROUTES` y los regex.
3. **Reescribir prompts**: `core/prompt_builder.py:DEFAULT_SYSTEM_PROMPT`.

Esto deja intacto: SessionStore, AgentController, fact_extractor (genérico), Orchestrator.run, plugin_loader, server.py, memoria triple. **~70% del esqueleto reutilizable**.

---

## 12. ARQUITECTURA MÍNIMA RECOMENDADA

Si reescribieras Stratum desde cero **conservando el espíritu** (chat técnico con memoria persistente y agentes especializados):

```
project/
├── api/
│   ├── server.py        # FastAPI + WS + lifespan handler (no on_event)
│   ├── auth.py          # JWT
│   └── routers/         # ws_chat, jobs, healthcheck
├── agent/
│   ├── controller.py    # process_input async, sin to_thread/asyncio.run
│   ├── orchestrator.py  # routing por LLM con response_format JSON Schema
│   ├── session.py       # SessionStore + AgentState con asyncio.Lock per-sid
│   └── agents/          # async-only, no sync
├── tools/
│   ├── registry.py      # auto-discovery via @tool decorator
│   └── plugins/
├── memory/
│   ├── store.py         # interfaz unificada SQL+vector
│   └── extractors.py    # fact + relation con Pydantic schemas
├── llm/
│   └── client.py        # async unificado (sin sync), structured output nativo
├── core/
│   ├── config.py
│   └── prompt.py
└── tests/
```

**Cambios estructurales clave**:

| Eliminar | Reemplazar por |
|----------|---------------|
| `BaseAgent.run` sync + `asyncio.run` | `async def run` + `await call_llm_async` |
| `asyncio.to_thread` masivo | agentes 100% async |
| `KEYWORD_ROUTES` + regex | LLM router con `response_format=json_schema` (Pydantic) y cache de routing por hash de query |
| `call_llm_sync` | borrar — solo async |
| Manual JSON parse en fact_extractor | Anthropic/OpenAI structured output con Pydantic |
| `@app.on_event("startup")` | `lifespan=...` async context manager |
| 4 lugares para registrar agente | decorator `@register_agent("name", keywords=[...])` |
| `agent_controller.py` 22KB monolito | dividir: TurnPipeline, MemoryPipeline, ResponsePipeline |
| NetworkX JSON | NetworkX en SQLite (`nx.to_dict_of_dicts` ↔ `dict_of_dicts_to_graph`) o Neo4j |

**Conservar**:
- SessionStore (LRU+TTL+SQL hydration) — diseño correcto.
- Triple memoria (SQL + vector + graph) — es el diferenciador.
- Plugin loader.
- CircuitSynthesizer determinista — el activo técnico real del repo.
- Provider-agnostic LLM (env-toggled).
- Lazy DB init (Railway-friendly).
- ContextVar para session propagation (mejorando la propagación al thread).

**Stack recomendado para reescritura**:
- FastAPI + uvicorn (mantener).
- Pydantic v2 para todo I/O LLM.
- httpx async (mantener).
- Qdrant Cloud o pgvector (eliminar embebido).
- Postgres + SQLAlchemy + asyncpg (reemplazar SQLite).
- Redis para SessionStore distribuido.
- structlog + OpenTelemetry para observability (hoy es solo `core.logger`).

---

## 13. ANÁLISIS CRÍTICO REAL

### Realmente útil (sólido técnicamente)
- **`CircuitSynthesizer` + EDA pipeline** (`tools/eda/`, `tools/circuit_synthesizer.py`). Es el activo técnico del repo. Mover lógica determinista del LLM al código fue **la decisión arquitectónica correcta** (commits Fases 1-10). Esto es lo que hace que el output sea reproducible y verificable. **No es LLM theater**.
- **SessionStore con LRU+TTL+SQL hydration**. Diseño limpio que arregla un bug real (singleton compartido).
- **Plugin loader**. Simple, valida campos, soporta ZIP. Buen ejemplo de extensibilidad sin tocar el core.
- **Provider-agnostic LLM client**. OpenRouter/Ollama/LMStudio con un env. Profesional.
- **Lazy DB init** para Railway. Solución específica a un problema real (volume mount race).

### LLM theater
- **MemoryAgent** — wrapper del search vectorial con system prompt para "investigar". Es 1 LLM call para reformular un `vector_store.search` que ya retorna texto. Borrarlo y poner el resultado directo.
- **Orchestrator routing fallback con LLM** — si los keywords cubren 90% de casos, el 10% restante igual cae en `direct`. La LLM call de routing rara vez aporta valor real, agrega 2-5s.
- **`_generate_title_async`** y **`_send_session_context`** — UX nice-to-have, pero suman LLM calls al primer mensaje.
- **`profiler.update_from_interaction`** — si llama LLM (no lo verifiqué a fondo), es costo escondido por turno.
- **`ProactiveEngine` loops** — útiles solo si el server tiene acceso al hardware del usuario (USB serial). En Railway/cloud, los 3 loops corren en vacío y solo gastan ciclos.
- **Mega system prompt** que declara competencia en VFDs, PLCs, IEC 61131-3, etc. — **overclaim que induce hallucinations** en modelos que no fueron entrenados específicamente en esos dominios.

### Frágil
- KEYWORD_ROUTES con substring matching y regex precompiladas en class attributes.
- 4 lugares para registrar un agente.
- `try/except Exception: pass` repartido sin telemetría.
- `processing` flag por conexión, no por session_id.
- `asyncio.run` dentro de threads (mezcla sync/async).
- ContextVar que no propaga a través de `asyncio.to_thread → asyncio.run`.
- Validación cero en outputs LLM excepto regex post-hoc.

### Diseño global
**Está bien diseñado para lo que es**: un proyecto solo-developer, evolutivo, con foco en electrónica, productionalizado en Railway con persistencia. Los recientes refactors (SessionStore, EDA pipeline determinista, async client compartido) muestran madurez arquitectónica creciente.

**No está bien diseñado para escalar**: in-memory state, SQLite, NetworkX JSON, sync/async mezclado, agent_controller monolítico, coupling fuerte agent↔orchestrator↔registry.

**Recomendación si lo querés llevar a producción multi-tenant**:
1. Antes de features nuevas, **converger todo a async puro**.
2. **SessionStore distribuido** (Redis).
3. **Postgres + Qdrant Cloud**.
4. **Pydantic en outputs LLM**, cero `json.loads(strip(content))`.
5. **Auto-discovery de agentes** (decorator).
6. **OpenTelemetry** para ver dónde se gastan los tokens y los segundos.
7. Reemplazar `KEYWORD_ROUTES` por **LLM router con caché LRU por hash**.
8. **Romper `agent_controller.py`** en 3-4 módulos.

El **núcleo defendible** (CircuitSynthesizer, SessionStore, plugin loader, memoria triple, lazy init) lo dejarías intacto.
