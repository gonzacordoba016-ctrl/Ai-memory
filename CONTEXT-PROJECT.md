# STRATUM — Context & Memory para Agente
> Última actualización: 2026-04-08
> Versión del proyecto: v2.8.0
> Autor: gonzacba17

---

## 1. ¿QUÉ ES STRATUM?

Stratum es un **agente de IA local** especializado en programar microcontroladores. Es un "Hardware Memory Engine" — un sistema que recuerda el circuito completo del usuario entre sesiones (componentes, pines, conexiones, fallos anteriores) y puede generar, compilar y flashear firmware desde lenguaje natural.

**Tagline:** _"Tu Arduino te recuerda. Vos no tenés que repetirlo."_

**Ejemplo de uso:**
```
Usuario: "Hacé parpadear el LED del sensor de temperatura"
→ Stratum recuerda el circuito, genera el firmware C++, lo compila con arduino-cli, y lo flashea al dispositivo.
```

---

## 2. STACK TECNOLÓGICO

| Capa           | Tecnología                                                          |
|----------------|---------------------------------------------------------------------|
| Backend        | Python 3.11 · FastAPI · asyncio · uvicorn                           |
| LLM            | OpenRouter (openai/gpt-4o-mini fast · openai/gpt-4o smart) — cloud |
| Memoria SQL    | SQLite (database/memory.db)                                         |
| Memoria Vector | Qdrant — server mode (QDRANT_URL) o modo local (VECTOR_DB_PATH)     |
| Memoria Grafo  | NetworkX (database/graph_memory.json)                               |
| Hardware       | arduino-cli · pyserial · mpremote (MicroPython)                     |
| Frontend web   | HTML estático · CSS (Cyberpunk, Space Grotesk, #a4ffb9/#00cbfe)     |
| Frontend mobile| Capacitor 6 (Android + iOS) · HTML/JS mobile-first · bottom nav    |
| Embeddings     | sentence-transformers/all-MiniLM-L6-v2 (384 dims)                  |
| Visión         | GPT-4o-mini via OpenRouter (fallback LLaVA via Ollama)              |
| Renderizado    | svgwrite (esquemáticos SVG, PCB, breadboard)                        |
| Deploy         | Docker · Railway (Dockerfile build, PORT injection, health check)   |
| Push           | Firebase Cloud Messaging (FCM) — opcional, vía FIREBASE_SERVER_KEY |

---

## 3. ESTRUCTURA DEL PROYECTO

```
c:\wamp64\www\ai-memory-engine\
│
├── run.py                     # ★ Punto de entrada único (serve / setup / status / export / import / reset / bridge)
├── requirements.txt           # Dependencias Python
├── package.json               # Paquetes npm
├── .env                       # Configuración local (LLM_PROVIDER, OPENROUTER_API_KEY, etc.)
├── .env.example               # ★ Template completo de variables de producción
├── Dockerfile                 # ★ Build para Railway/Render/Fly.io (pre-descarga embedding model)
├── railway.toml               # ★ Config Railway (builder dockerfile, healthcheck, restart)
├── .dockerignore              # ★ Excluye .env, *.db, __pycache__, node_modules
│
├── agent/                     # 🧠 NÚCLEO DEL AGENTE
│   ├── agent_controller.py    # Controlador principal — recibe input, orquesta, responde
│   ├── agent_runner.py        # Loop de ejecución con herramientas (tool calling)
│   ├── agent_state.py         # Estado de sesión (historial, hechos en memoria)
│   ├── orchestrator.py        # Enrutador de agentes (keyword + LLM fast routing)
│   ├── proactive_engine.py    # Motor proactivo (notificaciones autónomas en background)
│   │                          # ★ Tiene método público broadcast(str) para job_worker
│   ├── user_profiler.py       # Modelo mental del usuario (heurísticas estáticas, sin LLM)
│   └── agents/                # Agentes especializados
│       ├── base_agent.py      # Clase base
│       ├── hardware_agent.py  # ★ Principal — programa, debuggea, lee señales, consulta memoria HW
│       │                      #   ★ _program_via_bridge() — delega al bridge si está conectado
│       ├── circuit_agent.py   # Parsea circuitos NL → netlist JSON → DB (usa LLM_MODEL_SMART)
│       ├── vision_agent.py    # Analiza imágenes de circuitos con LLaVA
│       ├── research_agent.py  # Búsqueda web (DuckDuckGo)
│       ├── code_agent.py      # Ejecuta código Python en sandbox
│       └── memory_agent.py    # Consulta memoria vectorial y SQL (sin LLM, solo lectura)
│
├── api/                       # 🌐 SERVIDOR WEB
│   ├── server.py              # FastAPI app — lifecycle + health + routers (~120 líneas)
│   ├── app_state.py           # ★ Singletons compartidos: agent, proactive_engine, job_queue, jobs
│   ├── job_worker.py          # ★ Worker async de la cola de jobs (loop permanente en background)
│   ├── routers/
│   │   ├── memory.py          # /api/stats, /api/facts, /api/history?session_id=, /api/search,
│   │   │                      #   /api/graph, /api/profile, /api/plugins, /api/agents/status,
│   │   │                      #   /api/jobs/{id}, /api/jobs
│   │   ├── hardware.py        # /api/hardware/** (devices, firmware, circuits, library, vision, signal)
│   │   ├── hardware_bridge.py # ★ /ws/hardware-bridge (relay PC↔cloud), /api/hardware/bridge/status
│   │   │                      #   send_to_bridge(), call_bridge_sync(), is_bridge_connected()
│   │   ├── knowledge.py       # /api/knowledge/** (documents, index, search)
│   │   ├── circuits.py        # /api/circuits/** (parse, parse-async, schematic, breadboard,
│   │   │                      #   pcb, gerber, generate-firmware, PUT layout)
│   │   ├── websockets.py      # /ws/chat?session= · /ws/signal · /ws/proactive
│   │   ├── intelligence.py    # ★ /api/intelligence/** (9 endpoints — perfiles + fuentes)
│   │   └── push.py            # ★ POST/DELETE /api/push/register (tokens FCM)
│   └── static/
│       ├── index.html         # Frontend principal (UI Cyberpunk) — ★ tab INTEL, sesiones persistentes
│       ├── circuit_viewer.html# ★ Visualizador de circuitos con drag & drop
│       └── graph3d.html       # Visualizador 3D del grafo de memoria
│
├── core/                      # ⚙️ CONFIGURACIÓN
│   ├── config.py              # LLM_API, LLM_MODEL, LLM_MODEL_FAST, LLM_MODEL_SMART,
│   │                          #   PROVIDER, DB paths, QDRANT_URL, PORT ★, ALLOWED_ORIGINS ★
│   ├── logger.py              # Logger centralizado
│   └── prompt_builder.py      # ★ build_prompt() acepta system_prompt override + source_context
│
├── database/                  # 💾 PERSISTENCIA
│   ├── sql_memory.py          # CRUD SQLite: facts, conversations (con session_id)
│   ├── hardware_memory.py     # Memoria de hardware: devices (con micropython), firmware, circuits, library
│   │                          # ★ Agrega get_device_info()
│   ├── circuit_design.py      # Diseños de circuitos (circuit_designs)
│   │                          # ★ get_design() retorna positions. Agrega update_layout()
│   ├── intelligence.py        # ★ CRUD tablas ai_profiles + knowledge_sources
│   │                          #   4 perfiles por defecto, get_active_profile(), activate_profile()
│   ├── memory.db              # Base de datos SQLite principal
│   └── graph_memory.json      # Persistencia del grafo NetworkX
│
├── memory/                    # 🧠 CAPAS DE MEMORIA
│   ├── vector_memory.py       # Almacena/busca episodios en Qdrant (caché LRU 5min/128)
│   │                          # ★ Agrega search_in_sources(query, source_ids) — filtra por source_id
│   ├── graph_memory.py        # Grafo de relaciones (NetworkX)
│   ├── graph_extractor.py     # Extrae relaciones del texto → grafo
│   ├── fact_extractor.py      # Extrae hechos del texto → SQL
│   ├── short_memory.py        # Memoria de corto plazo (últimos N mensajes)
│   ├── memory_consolidator.py # Consolida memorias antiguas (fusión nocturna)
│   ├── memory_filter.py       # Filtra memorias relevantes
│   ├── session_summarizer.py  # Resume sesiones al cerrar
│   └── pdf_memory.py          # Ingesta de PDFs a memoria vectorial
│
├── llm/                       # 🤖 CLIENTES LLM
│   ├── openrouter_client.py   # Cliente síncrono + streaming. _call_llm(model=) soportado
│   └── async_client.py        # call_llm_async/text/stream — todos aceptan model= param
│
├── tools/                     # 🔧 HERRAMIENTAS
│   ├── hardware_detector.py   # Detecta dispositivos USB. ★ Detecta REPL MicroPython automáticamente
│   ├── firmware_generator.py  # Genera código con LLM_MODEL_SMART. Soporta micropython platform
│   ├── firmware_flasher.py    # arduino-cli. ★ Agrega flash_micropython() y detect_micropython_repl()
│   ├── hardware_bridge_client.py # ★ Cliente bridge para PC — conecta al backend remoto y ejecuta jobs
│   ├── serial_monitor.py      # Lee datos del puerto serial
│   ├── signal_reader.py       # Lectura de señales analógicas en tiempo real
│   ├── schematic_renderer.py  # ★ Usa positions guardadas en metadata si existen
│   ├── breadboard_renderer.py # Renderiza breadboard 3D (datos JSON)
│   ├── pcb_renderer.py        # Renderiza layout PCB + genera Gerber
│   ├── push_notifier.py       # ★ FCM push notifications — tabla push_tokens, send_push_to_all()
│   ├── code_executor.py       # Sandbox para ejecutar Python
│   ├── web_search.py          # Búsqueda DuckDuckGo
│   ├── tool_registry.py       # Registro de herramientas para tool calling
│   ├── plugin_loader.py       # Carga plugins dinámicamente desde tools/plugins/
│   ├── memory_viewer.py       # CLI viewer de memoria
│   ├── debug_tools.py         # Info del sistema
│   ├── file_tools.py          # Lectura/escritura de archivos
│   └── plugins/               # Directorio de plugins del usuario
│
├── stratum-mobile/            # ★ App móvil (Capacitor 6 — Android + iOS)
│   ├── package.json           # Deps: @capacitor/core + android + ios + plugins nativos
│   ├── capacitor.config.ts    # appId: com.stratum.hardware — server.url Railway
│   └── www/
│       └── index.html         # UI mobile-first: bottom nav, camera FAB, push, haptics
│                              #   ★ Sesiones persistentes, URL configurable, backoff exponencial
│                              #   ★ Tab MENU → SETTINGS (input URL, presets, test, CLEAR SESSION)
│
├── knowledge/                 # 📚 BASE DE CONOCIMIENTO
│   ├── knowledge_base.py      # Indexa documentos en vectores
│   ├── document_loader.py     # Carga documentos
│   └── document_chunker.py    # Divide documentos en chunks
│
├── infrastructure/            # 🏗️ INFRAESTRUCTURA
│   ├── vector_store.py        # ★ Singleton Qdrant — server mode si QDRANT_URL, si no path local
│   └── embeddings.py          # Modelo de embeddings (MiniLM)
│
└── eval/                      # 🧪 TESTS
    ├── run_eval.py             # Suite de tests
    ├── test_circuit_integration.py
    └── test_full_integration.py
```

---

## 4. FEATURES IMPLEMENTADAS (✅ Funcionando)

### 4.1 Motor de Memoria Triple
- **SQL (SQLite):** Facts, conversaciones (con `session_id`), dispositivos (con flag `micropython`), firmware, circuitos, biblioteca
- **Vectorial (Qdrant):** Server mode vía `QDRANT_URL` o path local como fallback. Búsqueda semántica con MiniLM (384 dims). Caché LRU 128/5min
- **Grafo (NetworkX):** Relaciones entre entidades. Persistido en JSON

### 4.2 Agentes Especializados
Routing: keywords estáticos (zero-LLM) → LLM fast (fallback)

| Agente        | Modelo LLM    | Función                                              |
|---------------|---------------|------------------------------------------------------|
| HardwareAgent | smart         | Programa, compila, flashea, debuggea, señales, memoria HW, guarda circuitos (★ save_circuit intent) |
| CircuitAgent  | smart         | Parsea descripciones → netlist JSON → guarda en DB   |
| VisionAgent   | gpt-4o-mini (OpenRouter) o llava:7b (Ollama) | Analiza imágenes de circuitos — detecta provider en runtime |
| ResearchAgent | default       | Búsqueda web DuckDuckGo                              |
| CodeAgent     | default       | Ejecuta Python en sandbox                            |
| MemoryAgent   | (sin LLM)     | Lee vectorial + SQL + grafo, sintetiza               |
| Orchestrator  | fast (routing)| Enruta a agentes por keyword o LLM fast              |

### 4.3 Pipeline Hardware Completo
```
NL → HardwareAgent → detect_devices() → generate_firmware() (LLM smart) →
compile_firmware() o flash_micropython() → [auto-install libs] → [LLM fix] →
flash_firmware() → read_serial() → save_firmware() → store_in_vector_memory()
```

### 4.4 Pipeline de Circuitos
```
NL → CircuitAgent.parse_circuit() → LLM smart genera netlist JSON →
Validación → circuit_design.save_design() → ID →
SchematicRenderer (con posiciones guardadas) → SVG visualizable
```

### 4.5 Motor Proactivo (Background)
- Cada 60s: detecta nuevos dispositivos USB
- Cada 1h: avisa dispositivos inactivos (3+ días)
- Cada 30min: detecta errores recurrentes
- A medianoche: consolidación nocturna de memorias
- Emite eventos de job completion vía `broadcast()`

### 4.6 Cola de Jobs Async (v1.2.0)
Operaciones largas (compile, flash, parse_circuit) se despachan en background sin bloquear el WebSocket:
- `POST /api/circuits/{device}/generate-firmware` → retorna `{ "job_id": "...", "status": "pending" }` inmediatamente
- `POST /api/circuits/parse-async` → ídem
- `GET /api/jobs/{job_id}` → polling del estado
- `GET /api/jobs` → lista todos los jobs de la sesión
- El worker async corre en background desde el startup del servidor
- Al completar, `/ws/proactive` emite `{ "type": "job_complete", "job_id": "...", "status": "done"|"error" }`

**Estructura de un job:**
```python
{
    "job_id":      str,    # UUID
    "type":        str,    # "generate_firmware" | "parse_circuit"
    "status":      str,    # "pending" | "running" | "done" | "error"
    "progress":    int,    # 0-100
    "result":      Any,
    "error":       str | None,
    "created_at":  str,    # ISO 8601
    "finished_at": str | None,
}
```

### 4.7 Sesiones WebSocket Persistentes (v1.3.0)
`/ws/chat` acepta parámetro opcional `?session=<uuid>`:
- Si se pasa session_id existente → carga los últimos 20 mensajes de SQLite e inyecta en el agente
- Si no se pasa → genera un nuevo UUID
- Primer mensaje del servidor: `{ "type": "session", "session_id": "...", "resumed": true|false }`
- Cada mensaje user/assistant se persiste en SQLite con su `session_id`

### 4.8 Modelo Dual Fast/Smart (v1.3.0)
| Modelo        | Env var             | Usado por                              |
|---------------|---------------------|-----------------------------------------|
| Fast (3b)     | `LLM_MODEL_FAST`    | Orchestrator (routing LLM)             |
| Smart (7b)    | `LLM_MODEL_SMART`   | FirmwareGenerator, CircuitAgent        |
| Default       | `LLM_MODEL`         | Resto del sistema                      |

Todas las funciones LLM aceptan `model=` param: `call_llm_async`, `call_llm_text`, `stream_llm_async`, `_call_llm`.

### 4.9 Soporte MicroPython Nativo (v1.3.0)
- `firmware_generator.py`: plataforma `"micropython"` con prompt especializado (machine, utime, etc.)
- `firmware_flasher.py`: `flash_micropython(script_path, port)` via `mpremote cp + reset`
- `firmware_flasher.py`: `detect_micropython_repl(port)` — envía Ctrl+C y detecta `>>>` en la respuesta
- `hardware_detector.py`: detecta REPL automáticamente en Pico/ESP32/ESP8266 al listar dispositivos
- `hardware_memory.py`: columna `micropython` (INTEGER 0/1) en `hardware_devices` con migración automática
- Al generar firmware, si el dispositivo tiene `micropython=True` → usa `flash_micropython()` en vez de `compile_firmware()`

### 4.10 Circuit Editor Interactivo — Drag & Drop (v1.3.0)
- `circuit_viewer.html`: componentes SVG son arrastrables (vanilla JS, sin frameworks)
- Al soltar un nodo → guarda posición via `PUT /api/circuits/{id}/layout`
- Las posiciones persisten en el campo `metadata.positions` de `circuit_designs`
- `get_design()` retorna `positions` junto con el circuito
- `schematic_renderer.py`: si `circuit_data["positions"]` existe, las usa en vez de calcular automáticamente

### 4.11 Motor de Memoria — Features heredadas
- Caché LRU 128/5min en `search_memory()` e `invalidate_search_cache()`
- Decaimiento temporal sobre scores de Qdrant (MEMORY_DECAY_RATE)
- Consolidación nocturna automática via `memory_consolidator`
- Perfil del usuario por inferencia silenciosa (sin LLM, heurísticas estáticas)

### 4.12 Frontend Web (Cyberpunk UI)
- Chat con streaming token por token · Rate limiting WS (3s/1 procesando)
- Stats panel (hechos, memoria, grafo, dispositivos)
- Visualizador de circuitos (esquemático/breadboard/PCB/Gerber + drag & drop)
- Motor proactivo conectado vía `/ws/proactive`
- ★ Tab INTEL (entre SEARCH y SYSTEM): gestión de perfiles AI + fuentes de conocimiento
- ★ Badge del perfil activo en el header

### 4.13 Health Check Extendido
`GET /api/health` verifica SQLite, Qdrant y Ollama/proxy activamente.

### 4.14 Sistema de Plugins
Archivo `.py` en `tools/plugins/` con `PLUGIN_TOOLS` → se carga automáticamente al iniciar.

### 4.15 Punto de Entrada Único — run.py

### 4.16 AI Intelligence — Perfiles y Fuentes de Conocimiento (v2.1.0)
- **`database/intelligence.py`** — tablas `ai_profiles` + `knowledge_sources`. 4 perfiles por defecto al iniciar:
  - `Técnico Conciso` (activo por defecto) — respuestas cortas, solo código
  - `Mentor Arduino` — explica decisiones, paso a paso
  - `Debug Mode` — diagnóstico, pide logs serial
  - `Producción` — conservador, código probado
- **`api/routers/intelligence.py`** — 9 endpoints bajo `/api/intelligence/`
- **`core/prompt_builder.py`** — `build_prompt()` acepta `system_prompt=` override y `source_context=` extra
- **`agent/agent_controller.py`** — inyecta perfil activo en cada `process_input()`:
  - Lee `get_active_profile()` → obtiene system_prompt + active_sources
  - Llama `search_in_sources(query, source_ids)` si hay fuentes habilitadas
- **`memory/vector_memory.py`** — `search_in_sources(query, source_ids, top_k=4)` filtra por metadato `source_id` en Qdrant

**Flujo:** Cambiar perfil → el agente responde con tono y contexto distintos en el siguiente mensaje (sin reiniciar).

### 4.17 Deploy en Producción — Docker + Railway (v2.1.0)
- **`Dockerfile`** — `python:3.11-slim`, instala gcc, pre-descarga embedding model en build time
- **`railway.toml`** — builder dockerfile, healthcheckPath `/api/health`, restart on failure
- **`core/config.py`** — `PORT` y `ALLOWED_ORIGINS` configurables via env (ALLOWED_ORIGINS admite lista separada por comas o `"*"`)
- **`api/server.py`** — CORS usa `ALLOWED_ORIGINS`, `allow_credentials=True`
- **`infrastructure/vector_store.py`** — pasa `api_key=QDRANT_API_KEY` al cliente cuando está en server mode
- **`run.py`** — `PORT = int(os.getenv("PORT", str(port)))` — Railway inyecta PORT automáticamente

### 4.20 Sesiones Persistentes + URL Configurable + Hardware Bridge (v2.3.0 — 2026-04-07)

#### Fase 1 — Sesiones persistentes (mobile + desktop)
- **`api/routers/memory.py`** — `/api/history` acepta `?session_id=<id>&limit=N` (usa `get_conversation_by_session()` existente en sql_memory)
- **`stratum-mobile/www/index.html`** — `_session_id` en localStorage; `connectWS()` pasa `?session=<id>` al WS; maneja `{ type: "session", session_id, resumed }` del servidor; carga historial via `loadSessionHistory()` si `resumed=true`; badge "SESIÓN REANUDADA" por 4 segundos
- **`api/static/index.html`** — misma lógica de sesión: `_session_id` en localStorage, WS con `?session=`, `loadSessionHistory()`, `loadFacts()` al reconectar
- Reconexión con **backoff exponencial** en ambos frontends: 2s → 4s → 8s → ... → 30s máximo

#### Fase 2 — URL configurable (mobile)
- **`stratum-mobile/www/index.html`** — `DEFAULT_BACKEND` como fallback, `getBackend()` lee localStorage primero
- Sección **SETTINGS** en tab MENU:
  - Input BACKEND_URL con el valor actual
  - Botones: `LOCAL WiFi` (restaura DEFAULT_BACKEND) · `RAILWAY` (prompt para ingresar URL cloud)
  - Botón `TEST` — hace `GET /api/health` con timeout 5s, muestra ✓ OK o ✗ error
  - Botón `GUARDAR` — persiste en localStorage, cierra WS existentes, reconecta
  - Botón `CLEAR SESSION` — borra session_id de localStorage, desconecta para forzar sesión nueva
- `localStorage.stratum_backend_url` — persiste URL entre reinicios
- `localStorage.stratum_session_id` — persiste sesión entre reinicios y cambios de red

#### Fase 3 — Hardware Bridge (programación remota desde cualquier red)
**Arquitectura:**
```
[Celular / PC web]  →  [Railway / Backend]  →  /ws/hardware-bridge  →  [PC + Arduino]
```

- **`api/routers/hardware_bridge.py`** (nuevo):
  - WS endpoint `/ws/hardware-bridge?token=<token>` — acepta conexión del bridge client
  - `is_bridge_connected()` — check de conexión activa
  - `send_to_bridge(job_type, payload, timeout=120)` — async, retorna resultado via Future
  - `call_bridge_sync(job_type, payload, timeout=120)` — wrapper síncrono para threads (usa `run_coroutine_threadsafe`)
  - `set_event_loop(loop)` — inyecta el event loop del proceso uvicorn
  - `GET /api/hardware/bridge/status` — `{ connected, connected_at, pending_jobs }`
  - Token auth: solo verifica si `BRIDGE_TOKEN` está configurado en `.env`
  - Al desconectar: resuelve todos los Futures pendientes con error

- **`tools/hardware_bridge_client.py`** (nuevo):
  - Handlers por tipo de job: `detect`, `generate`, `compile`, `flash`, `serial`, `program`
  - Job `program` — pipeline completo: generate_firmware → compile_firmware → detect_devices → flash_firmware → devuelve code + port + serial_output
  - Backoff exponencial en reconexión: 3s → 6s → ... → 60s máximo
  - Logging coloreado con timestamps
  - CLI entry point: `python tools/hardware_bridge_client.py --url <url> --token <token>`

- **`agent/agents/hardware_agent.py`** — `_program_device()` detecta bridge al inicio:
  ```python
  if is_bridge_connected():
      return self._program_via_bridge(task, context, call_bridge_sync)
  ```
  - `_program_via_bridge()` — extrae device_name y circuit_context, envía job `program` al bridge, formatea respuesta igual que el flash local

- **`api/server.py`** — importa `hardware_bridge` router; en `startup_event()` llama `hardware_bridge.set_event_loop(asyncio.get_event_loop())`; `app.include_router(hardware_bridge.router)` agregado

- **`run.py`** — subcomando `bridge`:
  ```bash
  python run.py bridge --url https://stratum.up.railway.app --token <token>
  ```

- **`.env.example`** — nueva variable `BRIDGE_TOKEN=` con instrucciones de generación

**Flujo end-to-end:**
```
1. PC: python run.py bridge --url https://stratum.railway.app --token abc123
2. Celular: MENU → SETTINGS → URL Railway → GUARDAR
3. Chat: "Hacé parpadear el LED del pin 13"
4. Backend: HardwareAgent → is_bridge_connected() == True → send_to_bridge("program", {...})
5. Bridge en PC: generate_firmware → compile_firmware → flash → read_serial
6. Resultado llega al celular
```

### 4.19 Sesión Android + Fixes (v2.2.0 — 2026-04-07)

#### App Mobile corriendo en dispositivo físico
- **Build Android exitoso** — `npx cap sync android` + Android Studio Run
- **Push notifications deshabilitado** temporalmente (requiere `google-services.json` de Firebase). Solución: `npm uninstall @capacitor/push-notifications && npx cap sync android`
- **VisionAgent con OpenRouter** — `agent/agents/vision_agent.py` reescrito para detectar `LLM_PROVIDER` en runtime. Si `openrouter` → usa `openai/gpt-4o-mini` con API vision (messages + image_url base64). Si `ollama` → LLaVA como antes. Env var override: `VISION_MODEL_OPENROUTER`
- **`/api/hardware/vision/status`** actualizado para reportar provider correcto (no llama más a `_check_vision_model` que no existe)
- **Foto de Arduino UNO analizada exitosamente** — `components=4` detectados

#### Fixes de bugs
- **`node_link_graph` NetworkX** (`memory/graph_memory.py`) — try/except para compatibilidad entre versiones. NX 3.2+ usa kwarg `edges=`; versiones anteriores usan clave `"links"`. Ahora: intenta con `edges="edges"`, fallback restaura clave `"links"` antes del segundo intento
- **`ON CONFLICT` en tabla facts** (`database/sql_memory.py`) — migración automática al startup: si la tabla `facts` fue creada con `UNIQUE(key)` sin `user_id`, la recrea con `UNIQUE(user_id, key)` preservando datos
- **Embeddings offline** (`infrastructure/embeddings.py`) — carga con `local_files_only=True` primero (evita timeout HuggingFace en cada startup). Fallback a descarga si no está en cache
- **`save_circuit` intent en HardwareAgent** — nuevo intent + keywords (`guardá el circuito para X`, etc.). Extrae nombre del dispositivo con regex. El circuito se guarda en `hardware_memory` y también persiste en `facts["__last_vision_circuit"]` para sobrevivir reloads del servidor
- **Bypass LLM principal para hardware** (`agent/agent_controller.py`) — cuando `hardware` es el único agente activo y retorna resultado, se devuelve directo sin re-procesar con el LLM principal (evitaba que el LLM reescribiera/contradijera las respuestas del agente)
- **Orquestador** (`agent/orchestrator.py`) — keywords de `save_circuit` agregadas al router de `hardware`

#### Perfil activo recomendado
- Usar **"Técnico Conciso"** en tab INTEL. "Debug Mode" activa preguntas diagnósticas en todas las respuestas.

### 4.18 App Mobile — Capacitor 6 (v3.0.0 objetivo)
- **`stratum-mobile/`** — proyecto Capacitor 6. `appId: com.stratum.hardware`
- **Plugins nativos incluidos:** `@capacitor/camera`, `@capacitor/push-notifications`, `@capacitor/local-notifications`, `@capacitor/network`, `@capacitor/haptics`
- **`stratum-mobile/www/index.html`** — UI mobile-first completa:
  - Bottom navigation (CHAT / INTEL / DEVICES / SEARCH / MENU)
  - FAB cámara (abre modal, usa `Capacitor.Plugins.Camera.getPhoto()` nativo; fallback `input[type=file]`)
  - Push notifications: solicita permiso, registra token FCM en backend
  - Haptic feedback en envío de mensajes
  - Toasts para notificaciones proactivas
  - Detección automática de entorno nativo vs web (`isNative()`)
  - Soporta conexión a backend local por WiFi (configurable)
- **`tools/push_notifier.py`** — tabla `push_tokens` (SQLite), `send_push_to_all()` via FCM legacy HTTP. No-op si `FIREBASE_SERVER_KEY` no está definida
- **`api/routers/push.py`** — `POST /api/push/register`, `DELETE /api/push/register`
- **`agent/proactive_engine.py`** — `_broadcast()` llama `send_push_to_all()` antes del broadcast WS

**Build Android:**
```bash
cd stratum-mobile && npm install
# Editar capacitor.config.ts con URL real del backend en Railway
npx cap add android && npx cap sync android && npx cap open android
# Android Studio → Build → Generate Signed APK / AAB
```
Reemplaza `main.py`, `install.py` y `manage.py`:
```bash
python run.py                        # servidor (por defecto)
python run.py serve --port 8080
python run.py serve --no-reload      # producción
python run.py setup                  # instalar deps, configurar
python run.py setup --no-ollama
python run.py status                 # estado de la memoria
python run.py export [-o bkp.zip]    # backup a ZIP
python run.py import bkp.zip [--merge]
python run.py reset --confirm        # borrar toda la memoria
python run.py bridge --url https://stratum.up.railway.app --token <token>  # ★ bridge client
```

---

## 5. ENDPOINTS API (puerto 8000)

### REST — Memoria
| Método | Ruta                       | Descripción                        |
|--------|----------------------------|------------------------------------|
| GET    | /api/stats                 | Stats globales                     |
| GET    | /api/facts                 | Todos los hechos del usuario       |
| GET    | /api/history?session_id=&limit= | ★ Historial por sesión o global  |
| GET    | /api/search?q=...&top_k=5  | Búsqueda semántica                 |
| GET    | /api/graph                 | Grafo de relaciones completo       |
| GET    | /api/profile               | Perfil inferido del usuario        |
| DELETE | /api/profile               | Reset perfil                       |
| GET    | /api/agents/status         | Lista de agentes                   |
| GET    | /api/plugins               | Plugins cargados                   |
| GET    | /api/jobs/{job_id}         | ★ Estado de un job async           |
| GET    | /api/jobs                  | ★ Lista todos los jobs             |

### REST — Hardware
| Método | Ruta                                  | Descripción                        |
|--------|---------------------------------------|------------------------------------|
| GET    | /api/health                           | Health check extendido             |
| GET    | /api/hardware/devices                 | Conectados + registrados           |
| GET    | /api/hardware/firmware/{device}       | Historial firmware                 |
| GET    | /api/hardware/stats                   | Stats de hardware                  |
| GET    | /api/hardware/circuit/{device}        | Circuito de un dispositivo         |
| GET    | /api/hardware/circuits                | Todos los circuitos                |
| POST   | /api/hardware/circuit/{device}        | Guardar circuito                   |
| POST   | /api/hardware/circuit/{device}/note   | Agregar nota                       |
| GET    | /api/hardware/library                 | Biblioteca de proyectos            |
| GET    | /api/hardware/library/search?q=...    | Buscar en biblioteca               |
| POST   | /api/hardware/vision/analyze          | Analizar imagen con LLaVA          |
| GET    | /api/hardware/vision/status           | Estado modelo de visión            |
| GET    | /api/hardware/signal                  | Datos señal actual                 |
| POST   | /api/hardware/signal/start            | Iniciar señal                      |
| POST   | /api/hardware/signal/stop             | Detener señal                      |

### REST — Circuitos
| Método | Ruta                                    | Descripción                           |
|--------|-----------------------------------------|---------------------------------------|
| GET    | /api/circuits/viewer                    | Visualizador HTML                     |
| POST   | /api/circuits/parse?description=&mcu=  | Parsear circuito (bloqueante)         |
| POST   | /api/circuits/parse-async              | ★ Parsear circuito (retorna job_id)   |
| GET    | /api/circuits/{id}/schematic.svg        | Esquemático SVG                       |
| GET    | /api/circuits/{id}/breadboard           | Datos breadboard 3D                   |
| GET    | /api/circuits/{id}/pcb.svg              | Layout PCB SVG                        |
| GET    | /api/circuits/{id}/gerber               | Archivos Gerber                       |
| PUT    | /api/circuits/{id}/layout               | ★ Guardar posiciones drag & drop      |
| POST   | /api/circuits/{device}/generate-firmware| Generar firmware (retorna job_id)     |

### REST — Knowledge
| Método | Ruta                          | Descripción            |
|--------|-------------------------------|------------------------|
| GET    | /api/knowledge/documents      | Documentos indexados   |
| POST   | /api/knowledge/index          | Indexar KB             |
| GET    | /api/knowledge/search?q=...   | Buscar en KB           |
| GET    | /api/proactive/status         | Estado motor proactivo |

### REST — AI Intelligence (★ v2.1.0)
| Método | Ruta                                          | Descripción                                 |
|--------|-----------------------------------------------|---------------------------------------------|
| GET    | /api/intelligence/profiles                    | Listar perfiles de comportamiento           |
| POST   | /api/intelligence/profiles                    | Crear perfil                                |
| PUT    | /api/intelligence/profiles/{id}               | Editar perfil                               |
| DELETE | /api/intelligence/profiles/{id}               | Eliminar perfil                             |
| POST   | /api/intelligence/profiles/{id}/activate      | Activar perfil (afecta próxima respuesta)   |
| GET    | /api/intelligence/sources                     | Listar fuentes de conocimiento              |
| POST   | /api/intelligence/sources                     | Crear fuente (texto / URL / archivo)        |
| DELETE | /api/intelligence/sources/{id}                | Eliminar fuente                             |
| POST   | /api/intelligence/sources/{id}/index          | Vectorizar fuente en Qdrant                 |
| GET    | /api/intelligence/active                      | Perfil activo + fuentes habilitadas         |

### REST — Push Notifications (★ v2.1.0)
| Método | Ruta                    | Descripción                          |
|--------|-------------------------|--------------------------------------|
| POST   | /api/push/register      | Registrar token FCM del device       |
| DELETE | /api/push/register      | Desregistrar token FCM               |

### REST — Hardware Bridge (★ v2.3.0)
| Método | Ruta                              | Descripción                                 |
|--------|-----------------------------------|---------------------------------------------|
| GET    | /api/hardware/bridge/status       | Estado del bridge client (connected, jobs)  |

### WebSockets
| Ruta                      | Función                                              |
|---------------------------|------------------------------------------------------|
| /ws/chat?session=<uuid>   | ★ Chat con streaming + sesiones persistentes         |
| /ws/signal                | Telemetría en tiempo real desde Arduino              |
| /ws/proactive             | Notificaciones autónomas + job completion events     |
| /ws/hardware-bridge?token=| ★ Relay entre backend y bridge client en la PC      |

---

## 6. CONFIGURACIÓN (.env)

```env
# LLM — OpenRouter (cloud)
LLM_PROVIDER=openrouter           # ollama | lmstudio | openrouter
OPENROUTER_API_KEY=sk-or-v1-...  # ★ API key de openrouter.ai
OPENROUTER_MODEL=openai/gpt-4o-mini
LLM_MODEL_FAST=openai/gpt-4o-mini # routing, clasificadores, memoria
LLM_MODEL_SMART=openai/gpt-4o     # firmware, circuitos, generación de código

# LLM — Ollama (alternativa local)
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=qwen2.5:3b
# LLM_MODEL_FAST=qwen2.5:3b
# LLM_MODEL_SMART=qwen2.5:7b
# OLLAMA_BASE_URL=http://localhost:11434

# Memoria
MEMORY_DB_PATH=./database/memory.db
VECTOR_DB_PATH=./memory_db        # usado si QDRANT_URL está vacío
QDRANT_URL=http://localhost:6333  # ★ server mode (vacío = path local)
QDRANT_API_KEY=                   # ★ requerido para Qdrant Cloud
VECTOR_COLLECTION=agent_memory
MEMORY_DECAY_RATE=0.01

# Auth
MULTI_USER=false
JWT_SECRET=stratum-dev-secret-change-in-production
JWT_EXPIRE_MINUTES=1440

# ★ CORS y servidor (producción)
ALLOWED_ORIGINS=*                 # capacitor://localhost,https://tu-dominio.com en prod
PORT=8000                         # Railway lo inyecta automáticamente

# ★ Push Notifications (opcional — app mobile)
# FIREBASE_SERVER_KEY=AAAAxxxxxxxxxx...

# ★ Hardware Bridge (v2.3.0 — programación remota)
# Token para autenticar el bridge client en la PC
# Generá uno con: python -c "import secrets; print(secrets.token_hex(32))"
BRIDGE_TOKEN=

# Debug
DEBUG=true
LOG_LEVEL=INFO
```

**Puertos:**
- OpenRouter API: https://openrouter.ai (cloud, sin puertos locales)
- Qdrant server: 6333
- Servidor API: 8000 (o el que inyecte Railway via `PORT`)

---

## 7. CÓMO INICIAR

```bash
# 1. Activar venv
.\venv\Scripts\activate

# 2. Iniciar servidor
python run.py

# 3. Abrir en navegador
http://localhost:8000
http://localhost:8000/api/circuits/viewer   # visualizador de circuitos
```

> **Nota:** El proxy `npx @aethermind/proxy` ya no es necesario cuando `LLM_PROVIDER=openrouter`.

**Primera vez / setup:**
```bash
python run.py setup
```

**Producción (sin hot-reload):**
```bash
python run.py serve --no-reload
```

---

## 8. TABLAS SQLite (database/memory.db)

| Tabla             | Campos clave                                                                  |
|-------------------|-------------------------------------------------------------------------------|
| facts             | key, value                                                                    |
| conversations     | session_id ★, role, content, timestamp                                        |
| hardware_devices  | device_name, port, fqbn, platform, micropython ★, first_seen, last_seen       |
| firmware_history  | device_name, task, code, filename, success, serial_out, timestamp, notes      |
| circuit_context   | device_name, project_name, description, components (JSON), connections (JSON) |
| project_library   | name, description, code, platform, tags (JSON)                                |
| circuit_designs   | id, name, description, components (JSON), nets (JSON), metadata (JSON)        |
| circuit_versions  | circuit_id, version, snapshot (JSON), reason                                  |
| ai_profiles       | ★ id, name, description, system_prompt, model_fast, model_smart, active_sources (JSON), is_default |
| knowledge_sources | ★ id, name, type (file/url/text/vector), content, description, indexed, index_date |
| push_tokens       | ★ id, token (FCM), platform, created_at                                       |

**★ Columnas/tablas agregadas con migración automática al iniciar.**

`metadata` de `circuit_designs` incluye: `{ "power", "warnings", "positions": { "comp_id": {"x", "y"} } }`

---

## 9. PROBLEMAS CONOCIDOS Y SOLUCIONES

### 9.1 Bloqueo de Qdrant en modo local
**Problema:** `RuntimeError: Storage folder ./memory_db is already accessed by another instance`
**Solución:** Configurar `QDRANT_URL=http://localhost:6333` en `.env` y levantar Qdrant como servicio independiente. En modo server no existe este límite.

### 9.2 Latencia del LLM en CircuitAgent
**Problema:** El parseo puede tardar 10-30s bloqueando el cliente
**Solución:** Usar `POST /api/circuits/parse-async` en vez de `/parse` — retorna job_id inmediatamente, hacer polling con `GET /api/jobs/{id}`

### 9.3 PowerShell vs curl
**Problema:** `curl` en PowerShell es alias de `Invoke-WebRequest`
**Solución:** Usar siempre `curl.exe` en PowerShell.

### 9.4 Ollama ya corriendo
**Problema:** `Error: listen tcp 127.0.0.1:11434: bind: Solo se permite un uso`
**Solución:** Ollama corre como servicio de Windows. No ejecutar `ollama serve` manualmente.

### 9.5 Flash MicroPython falla
**Problema:** `mpremote no encontrado`
**Solución:** `pip install mpremote` y verificar que el dispositivo responde con `>>>` (REPL activa).

### 9.6 Error 402 / 401 en LLM gateway
**Problema:** `Client error '402'` en `aethermind-agentos-production.up.railway.app` o `'401 Unauthorized'` en `openrouter.ai`
**Causas posibles:**
- 402: créditos agotados en el gateway de Aethermind
- 401: API key inválida o expirada en OpenRouter
- Causa sistémica: `LLM_API` y `LLM_MODEL` se evaluaban al **importar** el módulo — antes de que `load_dotenv()` corriera, quedando con valores por defecto

**Solución aplicada (v2.0.1 + diagnóstico):**
- `core/config.py`: `get_llm_headers()` ahora lee `LLM_PROVIDER` en runtime (no al importar); agrega log INFO con el prefijo de la key usada
- `llm/async_client.py`: funciones `_get_llm_api()` y `_get_llm_model()` evalúan en runtime
- `llm/openrouter_client.py`: usa los helpers de runtime
- `api/server.py`: `load_dotenv(override=True)` + log de startup con provider/url/model/key-prefix
- URL hardcodeada `aethermind-agentos-production.up.railway.app` → `https://openrouter.ai/api/v1/chat/completions`
- Headers de Aethermind (`X-Client-Token`, `X-Agent-Id`) removidos del bloque `openrouter` (no necesarios para OpenRouter directo)

### 9.7 Error 402 desde el proxy local de AetherMind (puerto 11435)
**Problema:** `402 Payment Required` en `aethermind-agentos-production.up.railway.app` incluso con `LLM_PROVIDER=openrouter` en `.env`
**Root cause:** `OLLAMA_BASE_URL=http://localhost:11435` apuntaba al proxy local de `@aethermind/setup` (instalado con npm). Ese proxy en el 11435 reenvía todas las peticiones al gateway cloud de Aethermind, que retornaba 402 (créditos agotados). Cuando el sistema resolvía `LLM_PROVIDER=ollama` desde una variable de entorno del sistema (sobrepisando el `.env`), iba a puerto 11435 → proxy → 402.
**Solución:** Cambiar `OLLAMA_BASE_URL=http://localhost:11434` (puerto real de Ollama). El proxy de Aethermind en 11435 queda ignorado.
**Diagnóstico rápido:** Verificar la línea `[STARTUP] LLM_PROVIDER=... | key prefix=...` al arrancar el servidor — muestra exactamente qué provider y key se están usando en runtime.
- `.env`: `OPENROUTER_API_KEY` actualizada, modelos cambiados a `openai/gpt-4o-mini` / `openai/gpt-4o`

### 9.8 Build Android falla — Java 8 en vez de Java 11/17/21 (AGP 8.2.1)
**Problema:** Error `Incompatible because this component declares a component for use during compile-time, compatible with Java 11 and the consumer needed a component for use during runtime, compatible with Java 8`. El Android Gradle Plugin 8.2.1 requiere mínimo Java 11 para compilar.

**Root cause:** La variable de entorno global de Windows `JAVA_HOME` tenía un salto de línea oculto embebido en el valor:
```
C:\Program
  Files\Android\Android Studio\jbr
```
Esto hacía que `gradlew.bat` interpretara solo `C:\Program` como directorio (inválido), fallara silenciosamente y cayera al `java.exe` genérico del PATH del sistema, que era Java 8.

**Solución aplicada (dos capas de protección):**
1. **Fix global:** PowerShell con `[Environment]::SetEnvironmentVariable` corrigió `JAVA_HOME` en el scope `User` a la cadena exacta sin saltos:
   ```
   C:\Program Files\Android\Android Studio\jbr
   ```
2. **Hardcoded en el proyecto:** Para inmunizar el proyecto ante futuros problemas de entorno, se agregó en `stratum-mobile/android/gradle.properties`:
   ```properties
   org.gradle.java.home=C:/Program Files/Android/Android Studio/jbr
   ```
   Nota: Gradle acepta `/` como separador incluso en Windows.

**Después del fix:** Reiniciar Android Studio / hacer "Sync Project with Gradle Files" para que limpie el contexto Java 8 cacheado.

**JDK usado:** Java 21 (bundleado con Android Studio — `jbr/`). AGP 8.2.1 es compatible.

---

## 10. SESIONES DE TRABAJO (Log)

### Sesión 2026-04-08 — Firmware Retry + Offline Queue Web (v2.8.0)

**1. Firmware Retry Inteligente con Error Memory**

1. ✅ **`database/hardware_memory.py`** — nuevo método `get_recent_failures(device_name, limit=3)`: consulta `firmware_history` WHERE `success=0 AND serial_out != ''`, retorna lista de strings con los errores de compilación más recientes del device.

2. ✅ **`tools/firmware_generator.py`** — `generate_firmware()` y `generate_firmware_for_circuit()` aceptan nuevos params: `past_errors: list[str] = None` y `compile_error: str = ""`. Si hay `past_errors` → se inyectan en el prompt como "ERRORES PREVIOS A EVITAR". Si hay `compile_error` (reintento) → se inyecta como "ERROR DEL INTENTO ANTERIOR — Corregí el código".

3. ✅ **`api/routers/circuits.py`** — `_generate_and_compile()` reescrita con loop de hasta 3 intentos (`MAX_RETRIES = 3`):
   - Intento 1: llama con `past_errors` del historial del device (contexto preventivo)
   - Intento 2-3: llama con `compile_error` del intento anterior (corrección reactiva)
   - Cada fallo intermedio se guarda en `firmware_history` con `success=False` para aprendizaje futuro
   - Resultado incluye campo `attempts` con el número de intentos usados
   - Si todos fallan → retorna el último código generado con `success: False`

**2. Offline Queue en Web Frontend**

4. ✅ **`api/static/index.html`** — CSS: `.msg-queued` y `.queue-badge`. Variable `_offlineQueue` desde `localStorage.stratum_web_offline_queue`. Funciones: `_saveQueue()`, `_updateQueueBadge()` (inyecta badge en `#status-text`), `_enqueueMessage(text)` (agrega a cola, renderiza en `#chat-area`, loguea en panel). `drainOfflineQueue()` idéntico al mobile: elimina `.msg-queued`, envía en secuencia, espera `done`/`error` entre mensajes. `sendMessage()` modificado: si WS no conectado → `_enqueueMessage()`. `ws.onopen` llama `drainOfflineQueue()`. Al init: renderiza mensajes encolados de sesiones previas.

---

### Sesión 2026-04-08 — Bridge Badge Web + LLM Semantic Cache (v2.7.0)

**1. Bridge Status Badge en web frontend**

1. ✅ **`api/static/index.html`** — Card `#bridge-card-web` en sidebar derecho antes de ACTIVE_JOBS: `#bridge-icon-web`, `#bridge-status-web`, `#bridge-dot-web`, `#bridge-since-web`. `loadBridgeStatus()` hace GET `/api/hardware/bridge/status`, colorea en `#8eff71` si conectado. Card border-left cambia a verde. Agregado a `setInterval(loadBridgeStatus, 10000)` en init.

**2. LLM Semantic Cache**

2. ✅ **`llm/cache.py`** (nuevo) — `SemanticCache`: cache en memoria con TTL 30min, threshold cosine 0.93, máx 512 entradas. `get(messages, model)`: embeda el key text (últimos 2 mensajes), busca por cosine similarity, retorna hit si score >= threshold. `set(messages, model, response)`: embeda y guarda, poda expirados y duplicados (hash MD5). `stats()` y `clear()`. Instancia global `llm_cache`. Usa `infrastructure.embeddings.embedding_model` (MiniLM 384 dims) para embedar sin llamadas extra.

3. ✅ **`llm/async_client.py`** — `call_llm_text()` extendido con param `use_cache: bool = True`. Antes de llamar al LLM: si `temperature == 0.0 and use_cache` → intenta `llm_cache.get()`. Después de respuesta exitosa: `llm_cache.set()`. Cache fallo es silencioso (no rompe el flujo). Funciona para todos los llamadores existentes sin cambios (default activo).

4. ✅ **`api/routers/memory.py`** — `GET /api/cache/stats` retorna `{entries, ttl_seconds, threshold}`. `POST /api/cache/clear` limpia el cache manualmente.

5. ✅ **`api/static/index.html`** — Indicador `Cache: N` en el header junto a SQLite/Qdrant/Ollama. `loadHealth()` hace GET `/api/cache/stats` y actualiza `#svc-cache`.

**Qué se cachea:** llamadas deterministas (`temperature=0`) de clasificadores, extractores y el router del orchestrator. Firmware generation y streaming NO se cachean (temperatura > 0 o streaming). Ahorro estimado: 30-60% de tokens en clasificación/routing.

---

### Sesión 2026-04-08 — Pipeline Foto → Circuito → Firmware (v2.6.0)

**Feature: foto → circuito → firmware en 3 pasos desde el modal de cámara**

**Flujo completo:**
```
Foto → POST /api/hardware/vision/analyze
     → Resultado en modal (descripción + componentes + selector MCU)
     → Botón PROGRAMAR ESTO
     → POST /api/circuits/parse-async  (job)  → poll → netlist JSON
     → POST /api/hardware/circuit/{slug}       → guarda en hardware_memory
     → POST /api/circuits/{slug}/generate-firmware (job) → poll → código
     → Mensaje en chat con firmware + resultado de compilación
```

**Cambios en `stratum-mobile/www/index.html`:**

1. ✅ **Modal CIRCUIT_SCANNER rediseñado** — nuevo panel `#cam-result-panel` con: descripción truncada (280 chars), contador de componentes, `<select id="cam-mcu-select">` con 4 opciones (Arduino Uno / ESP32 / ESP8266 / Raspberry Pi Pico). Panel `#cam-pipeline-steps` con 4 pasos visuales (PARSEAR / GUARDAR / GENERAR / LISTO) con `step-icon` coloreable. Dos filas de botones: `#cam-btns-default` (CAPTURAR + ANALIZAR) y `#cam-btns-result` (CERRAR + PROGRAMAR) que se intercambian al terminar el análisis.

2. ✅ **`analyzeCameraImage()` modificado** — en vez de cerrar el modal al detectar éxito, guarda `_visionResult` y llama `_showVisionResult()`. Ya no cierra automáticamente.

3. ✅ **`_showVisionResult(result)`** — intercambia botones, rellena el panel de resultado, oculta la barra de progreso.

4. ✅ **`_pollJob(jobId)`** — helper async, poll cada 1.5s, max 3 min (120 iteraciones), resuelve en `result` o lanza error.

5. ✅ **`_setStep(stepId, state)`** — colorea cada paso del pipeline: `pending` gris, `running` cyan pulsante, `done` verde, `error` rojo.

6. ✅ **`programFromVision()`** — pipeline completo:
   - Device slug: `mcu.toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'')` (ej: `arduino_uno`, `esp32`)
   - Step 1: `POST /api/circuits/parse-async?description=...&mcu=...` → poll → `circuitData`
   - Step 2: `POST /api/hardware/circuit/{slug}` con `{project_name, description, components, connections}`
   - Step 3: `POST /api/circuits/{slug}/generate-firmware` con `task_description` → poll → `fwResult`
   - Resultado: `addMessage('agent', ...)` con resumen + snippet de código (400 chars)
   - Cierra modal después de 2s. En error: resetea botón y colorea pasos en rojo.

7. ✅ **`closeCameraModal()` extendido** — resetea `_visionResult`, oculta `#cam-result-panel` y `#cam-pipeline-steps`, restaura `#cam-btns-default`, llama `_setStep` a `pending` en los 4 pasos.

8. ✅ **`window.programFromVision`** expuesto como global.

**Nota:** `FirmwareRequest.task_description` ya existía en `api/routers/circuits.py:36` — el endpoint acepta el body JSON sin cambios.

---

### Sesión 2026-04-08 — Bridge Badge + Offline Queue (v2.5.0)

**1. Hardware Bridge Status Badge (mobile)**

1. ✅ **`stratum-mobile/www/index.html`** — Header: `#bridge-dot` (punto verde/gris) junto a `#conn-dot`. Panel DEVICES: card `#bridge-card` con icono `router`, `#bridge-status-text` (`CONNECTED`/`DISCONNECTED`/`UNREACHABLE`), `#bridge-since` (minutos conectado o pending jobs). Función `checkBridgeStatus()`: GET `/api/hardware/bridge/status`, colorea dot + icon + texto en verde `#8eff71` si conectado, gris si no. `startBridgePoll()` / `stopBridgePoll()` arrancan/detienen el `setInterval(10000)` al entrar/salir del panel DEVICES. Integrado en `switchPanel()`.

**2. Offline Message Queue (mobile)**

2. ✅ **`stratum-mobile/www/index.html`** — CSS: `.msg-queued` (mensaje gris punteado opaco 60%) y `.queue-badge` (badge inline en status bar). Variable `_offlineQueue` inicializada desde `localStorage.stratum_offline_queue`. `sendMessage()` modificado: si `ws.readyState !== 1` → llama `_enqueueMessage(text)` en vez de fallar silenciosamente. `_enqueueMessage()`: push a la cola, persiste en localStorage, renderiza el mensaje como `.msg-queued` con label `QUEUED`, muestra toast "Sin conexión". `_updateQueueBadge()`: inyecta count en el status text. `drainOfflineQueue()`: al reconectar WS, elimina los `.msg-queued` de la UI y envía cada mensaje en secuencia esperando `done`/`error` antes del siguiente (timeout safety 30s). `ws.onopen` llama `drainOfflineQueue()` si hay cola. Al init: renderiza mensajes encolados de sesiones anteriores.

---

### Sesión 2026-04-08 — Fix Build Android + Voice Input + Chart.js + Rate Limiting (v2.4.0)

Implementación de 3 mejoras de UX/confiabilidad + fix crítico del build Android.

**0. Fix Build Android — JAVA_HOME con newline oculto**

0. ✅ **`JAVA_HOME` global (Windows User env)** — La variable tenía un `\n` embebido que partía la ruta en dos líneas (`C:\Program` / `  Files\Android\Android Studio\jbr`). Gradle la interpretaba como directorio inválido y caía silenciosamente a Java 8 del PATH del sistema. Corregida via PowerShell `[Environment]::SetEnvironmentVariable`. AGP 8.2.1 requiere mínimo Java 11.
0. ✅ **`stratum-mobile/android/gradle.properties`** — Agregada línea `org.gradle.java.home=C:/Program Files/Android/Android Studio/jbr` para hardcodear el JDK 21 del Android Studio en el proyecto e inmunizarlo ante futuros problemas de entorno del sistema.

**1. Voice Input — Web Speech API (ambos frontends)**

1. ✅ **`api/static/index.html`** — CSS: clase `.voice-active` con animación roja pulsante (`steps(4,end)`). HTML: botón `#voice-btn` con icono `mic` insertado entre el botón de cámara y el de envío. JS: funciones `_initVoice()` y `toggleVoice()` — usa `SpeechRecognition`/`webkitSpeechRecognition`, idioma `es-AR`, `continuous: false`, `interimResults: false`. Al obtener resultado, inserta transcript en `#prompt` y hace `focus()`. Maneja errores silenciosamente (`no-speech` ignorado).
2. ✅ **`stratum-mobile/www/index.html`** — CSS: misma clase `.voice-active`. HTML: botón `#voice-btn` con icono `mic` junto al send. JS: misma lógica, `window.toggleVoice` expuesto como global (necesario porque el script usa `type="module"` y el `onclick` en HTML no accede al scope del módulo).

**2. Chart.js Oscilloscope en tiempo real (web frontend)**

3. ✅ **`api/static/index.html`** — Chart.js 4.4.4 añadido vía CDN (`cdn.jsdelivr.net`). `<div id="osc-bars">` reemplazado por `<div class="flex-1 relative"><canvas id="osc-chart"></canvas></div>`. Nueva función `_initOscChart()`: crea line chart con `borderColor: #00cbfe`, `backgroundColor: rgba(0,203,254,0.06)`, sin animación (`animation: false`), escala Y fija 0–1023, grilla sutil `rgba(73,72,71,0.2)`, sin labels. `renderOscilloscope()` reescrita: mapea `signalBuffer` a array de 40 puntos con `null` en posiciones vacías, actualiza con `_oscChart.update('none')` para zero-lag. Último punto destacado en `#a4ffb9`. `renderIdleOscilloscope()` reescrita: carga datos de onda idle con `borderColor: rgba(0,203,254,0.2)`.

**3. Rate Limiting — slowapi 0.1.9 (backend)**

4. ✅ **`api/limiter.py`** (nuevo) — módulo compartido con instancia `Limiter(key_func=get_remote_address, default_limits=[])`. Separado de `server.py` para evitar circular imports al importarlo desde los routers.
5. ✅ **`api/server.py`** — importa `limiter` desde `api.limiter`, registra `app.state.limiter`, agrega `SlowAPIMiddleware` y `_rate_limit_exceeded_handler` (retorna `429 Too Many Requests` con body JSON).
6. ✅ **`api/routers/circuits.py`** — `@limiter.limit("5/minute")` en `parse_circuit()` y `parse_circuit_async()`. Agregado `request: Request` como primer parámetro (requerido por slowapi).
7. ✅ **`api/routers/hardware.py`** — `@limiter.limit("3/minute")` en `analyze_circuit_image()`. Request ya existía en la firma.
8. ✅ **`api/routers/knowledge.py`** — `@limiter.limit("2/minute")` en `trigger_index()`. Agregado `request: Request`.
9. ✅ **`requirements.txt`** — `slowapi==0.1.9` añadido. Instalado en venv.

**Tabla de límites aplicados:**

| Endpoint | Límite | Razón |
|----------|--------|-------|
| `POST /api/circuits/parse` | 5/min | LLM smart (gpt-4o), costoso |
| `POST /api/circuits/parse-async` | 5/min | ídem (job async) |
| `POST /api/hardware/vision/analyze` | 3/min | Vision API costosa |
| `POST /api/knowledge/index` | 2/min | Embedding + Qdrant upsert |

---

### Sesión 2026-04-07 — Plan Sesiones + URL + Hardware Bridge (v2.3.0)

Ejecución completa del plan de 3 fases aprobado en la sesión anterior.

**Fase 1 — Sesiones persistentes:**
1. ✅ **`api/routers/memory.py`** — `/api/history` acepta `?session_id=<id>&limit=N`; usa `get_conversation_by_session()` existente en sql_memory cuando se pasa el param
2. ✅ **`stratum-mobile/www/index.html`** — `_session_id` (localStorage), `_wsRetryDelay` (backoff); `connectWS()` reescrita con session param + backoff exponencial + manejo de `{ type: "session" }`; `loadSessionHistory(sid)` carga historial y lo renderiza; `showSessionBadge()` muestra badge 4s; `DEFAULT_BACKEND` como const, `getBackend()` lee localStorage
3. ✅ **`api/static/index.html`** — misma lógica: `_session_id`, `_wsRetryDelay`, `connectWS()` con `?session=`, `loadSessionHistory()` con log en panel de actividad

**Fase 2 — URL configurable (mobile):**
4. ✅ **`stratum-mobile/www/index.html`** — sección SETTINGS en tab MENU con: input BACKEND_URL, presets LOCAL/RAILWAY, botón TEST (`/api/health` con AbortSignal.timeout(5s)), botón GUARDAR (persiste + reconecta), botón CLEAR SESSION; `initSettingsPanel()` carga el valor actual al abrir el tab; `setPreset()`, `testConnection()`, `saveSettings()`, `clearSession()` expuestas como window globals

**Fase 3 — Hardware Bridge:**
5. ✅ **`api/routers/hardware_bridge.py`** (nuevo) — WS endpoint `/ws/hardware-bridge?token=`; estado global `_bridge_ws` + dict `_pending` de Futures; `send_to_bridge()` async (crea Future, envía JSON, espera con timeout); `call_bridge_sync()` usa `run_coroutine_threadsafe` para llamadas desde threads síncronos del HardwareAgent; `set_event_loop()` inyectado en startup; `GET /api/hardware/bridge/status`; al desconectar resuelve todos los Futures pendientes con error
6. ✅ **`tools/hardware_bridge_client.py`** (nuevo) — handlers para 6 tipos de job (detect/generate/compile/flash/serial/program); job `program` hace pipeline completo; `run_bridge()` con backoff 3s→60s; `_process_and_reply()` como task async para no bloquear el recv loop; CLI entry point
7. ✅ **`agent/agents/hardware_agent.py`** — `_program_device()` intenta `from api.routers.hardware_bridge import is_bridge_connected, call_bridge_sync` al inicio; si bridge conectado → `_program_via_bridge()`; `_program_via_bridge()` extrae device_name, obtiene circuit_context de hardware_memory, llama `call_bridge_sync("program", {...}, timeout=180)`, formatea respuesta idéntica al flash local
8. ✅ **`api/server.py`** — importa `hardware_bridge` desde `api/routers`; `hardware_bridge.set_event_loop(asyncio.get_event_loop())` en `startup_event()`; `app.include_router(hardware_bridge.router)` entre hardware y knowledge
9. ✅ **`run.py`** — subcomando `bridge` con args `--url` (required) y `--token` (default desde env); llama `asyncio.run(run_bridge(args.url, args.token))`
10. ✅ **`.env.example`** — `BRIDGE_TOKEN=` con instrucciones de generación con `secrets.token_hex(32)`

---

### Sesión 2026-04-06 — Migración LLM a OpenRouter directo (v2.0.1)

**Problema:** El gateway de Aethermind (`aethermind-agentos-production.up.railway.app`) respondía con `402 Payment Required`. Al migrar a OpenRouter, aparecía `401 Unauthorized` porque la API key llegaba inválida.

**Root cause:** `LLM_API`, `LLM_MODEL` y el check de `PROVIDER` en `config.py` y `async_client.py` se evaluaban al **tiempo de import del módulo** — antes de que `load_dotenv()` fuese llamado en `cmd_serve()`. Resultado: las variables quedaban con valores por defecto (`ollama`), ignorando el `.env`.

**Cambios aplicados:**

1. ✅ **`.env`** — `OPENROUTER_API_KEY` actualizada con la nueva key válida. Modelos cambiados: `OPENROUTER_MODEL=openai/gpt-4o-mini`, `LLM_MODEL_FAST=openai/gpt-4o-mini`, `LLM_MODEL_SMART=openai/gpt-4o`.

2. ✅ **`core/config.py`** — URL `openrouter` hardcodeada → `https://openrouter.ai/api/v1/chat/completions`. `get_llm_headers()` refactorizada para leer `LLM_PROVIDER` desde `os.getenv()` en cada invocación (runtime), no desde la constante de módulo `PROVIDER`. Headers de Aethermind (`X-Client-Token`, `X-Agent-Id`, `X-Agent-Name`, `X-Environment`) removidos del path `openrouter` — OpenRouter no los necesita. Agregados `HTTP-Referer` y `X-Title` (headers recomendados por OpenRouter).

3. ✅ **`llm/async_client.py`** — Reemplazados imports estáticos `LLM_API` y `LLM_MODEL` por funciones `_get_llm_api()` y `_get_llm_model()` que leen `os.getenv()` en cada llamada. `call_llm_async()` y `stream_llm_async()` usan los helpers. Eliminado import de `LLM_API` / `LLM_MODEL` del encabezado del módulo.

4. ✅ **`llm/openrouter_client.py`** — Eliminado import duplicado de `stream_llm_async`. `_call_llm()` usa `_get_llm_api()` y `_get_llm_model()` en vez de constantes.

5. ✅ **`core/config.py` — Log de diagnóstico** — `get_llm_headers()` loguea en INFO el prefijo de la key que envía en cada request (`[Config] LLM -> openrouter | key prefix: sk-or-v1-...`), permitiendo verificar en los logs qué credencial se está usando realmente en runtime.

6. ✅ **`api/server.py` — dotenv override + log de startup** — `load_dotenv()` cambiado a `load_dotenv(override=True)` para que el `.env` pise cualquier variable heredada de la sesión de PowerShell o del proceso padre. Agregado `print()` de diagnóstico al arrancar el proceso hijo de uvicorn (muestra `LLM_PROVIDER`, key prefix y modelo). Agregado log en `startup_event()` que muestra `provider`, `LLM_API` URL y `LLM_MODEL` activos (`[Server] LLM provider=...`).

**Pendiente de verificación:** el 401 sigue activo. Si los logs de startup muestran `key prefix=sk-or-v1-6d0cf...` y persiste el 401, el problema es que esa key de OpenRouter no tiene cuenta activa/créditos — verificar en https://openrouter.ai/keys.

---

### Sesión 2026-04-06 — Build Android (Capacitor — Fase 6.5)

**Contexto:** Primera vez ejecutando el build nativo Android desde `stratum-mobile/`.

**Pasos ejecutados:**

1. ✅ `npm install` en `stratum-mobile/` — 105 paquetes instalados. 2 vulnerabilidades high (en deps transitivas de Capacitor, no críticas para el build).
2. ✅ `npm install -D typescript` — Capacitor requiere TypeScript para parsear `capacitor.config.ts`. No estaba en el `package.json` inicial.
3. ✅ `npx cap add android` — proyecto Android generado en `stratum-mobile/android/`. 5 plugins detectados: `@capacitor/camera@6.1.3`, `@capacitor/haptics@6.0.3`, `@capacitor/local-notifications@6.1.3`, `@capacitor/network@6.0.4`, `@capacitor/push-notifications@6.0.5`.
4. ✅ `npx cap open android` — Android Studio abrió correctamente el proyecto.

**Estado actual:** Android Studio abierto, Gradle sincronizando. Próximo paso manual: esperar sync → conectar teléfono con depuración USB → Run ▶ o Build APK.

**Problema encontrado:**
- `npx cap add android` fallaba con `[error] Could not find installation of TypeScript` antes de instalar TypeScript. Solución: `npm install -D typescript` primero.

**Para distribuir el APK:**
- Debug (testing): **Build → Build APK(s)** → `android/app/build/outputs/apk/debug/app-debug.apk`
- Release (Play Store): **Build → Generate Signed Bundle/APK** → crear keystore → `app-release.apk`
- Sideload directo: `adb install app-debug.apk` con teléfono conectado por USB

---

### Sesión 2026-04-06 — Fases 4, 5 y 6 (v2.1.0 + base v3.0.0)

**Fase 4 — AI Intelligence:**

1. ✅ **`database/intelligence.py`** — tablas `ai_profiles` + `knowledge_sources`. 4 perfiles seeded por defecto (Técnico Conciso activo). `get_active_profile()`, `activate_profile()`, full CRUD para perfiles y fuentes.
2. ✅ **`api/routers/intelligence.py`** — 9 endpoints `/api/intelligence/*`. Indexación de fuentes: chunking + embedding + upsert a Qdrant con `source_id` en metadata.
3. ✅ **`core/prompt_builder.py`** — `build_prompt()` acepta `system_prompt=` (override del perfil activo) y `source_context=` (texto de fuentes habilitadas).
4. ✅ **`agent/agent_controller.py`** — step 4 nuevo: carga perfil activo antes de construir el prompt. Llama `search_in_sources()` si hay `active_sources` en el perfil.
5. ✅ **`memory/vector_memory.py`** — `search_in_sources(query, source_ids, top_k=4)`: filtra resultados Qdrant por campo `source_id` en payload. Caché LRU por key `sis:{query}:{source_ids}:{top_k}`.
6. ✅ **`api/static/index.html`** — tab INTEL agregada en sidebar: PERFILES (lista + activar + crear inline) + FUENTES (lista + indexar + toggle). Badge de perfil activo en header.

**Fase 5 — Deploy:**

7. ✅ **`Dockerfile`** — `python:3.11-slim` + gcc. Pre-descarga `all-MiniLM-L6-v2` en build time. `CMD ["python", "run.py", "serve", "--no-reload"]`.
8. ✅ **`railway.toml`** — builder: dockerfile, healthcheckPath: `/api/health`, restartPolicyType: on_failure.
9. ✅ **`.dockerignore`** — excluye `.env`, `*.db`, `__pycache__`, `node_modules`, backups.
10. ✅ **`core/config.py`** — `PORT = int(os.getenv("PORT", "8000"))`, `ALLOWED_ORIGINS` parseado desde env (coma-separated o `"*"`).
11. ✅ **`api/server.py`** — CORS usa `ALLOWED_ORIGINS`, `allow_credentials=True`. Registra `intelligence.router` y `push.router`.
12. ✅ **`infrastructure/vector_store.py`** — `api_key=os.getenv("QDRANT_API_KEY")` al instanciar cliente en server mode (Qdrant Cloud).
13. ✅ **`run.py`** — `port = int(os.getenv("PORT", str(port)))`.
14. ✅ **`.env.example`** — template completo: LLM, SQLite, Qdrant Cloud, JWT, CORS, PORT, Firebase, Wokwi.

**Fase 6 — App Mobile:**

15. ✅ **`stratum-mobile/package.json`** — Capacitor 6 core + android + ios + 5 plugins nativos.
16. ✅ **`stratum-mobile/capacitor.config.ts`** — `appId: com.stratum.hardware`, `appName: Stratum`, `server.url` apuntando a Railway. Comment para WiFi local.
17. ✅ **`stratum-mobile/www/index.html`** — UI mobile-first completa: bottom nav 5 tabs, FAB cámara, push notifications init, haptic feedback, toasts proactivos, detección nativo vs web.
18. ✅ **`tools/push_notifier.py`** — tabla `push_tokens`, `register_token()`, `get_all_tokens()`, `send_push_to_all()` via FCM legacy HTTP. No-op si no hay `FIREBASE_SERVER_KEY`.
19. ✅ **`api/routers/push.py`** — `POST /api/push/register`, `DELETE /api/push/register`.
20. ✅ **`agent/proactive_engine.py`** — `_broadcast()` crea task async `send_push_to_all()` antes del broadcast WS. Push llega incluso cuando no hay clientes WS conectados.

**Pendiente manual (Fase 6.5):** buildear APK/AAB en Android Studio y distribuir. Requiere `npx cap add android && npx cap sync android && npx cap open android`.

---

### Sesión 2026-04-06 — Fase 3 completa (v2.0.0)

**Fase 3 — Ecosistema y escalabilidad:**

1. ✅ **3.1 Simulación Wokwi** — `tools/wokwi_simulator.py`: `generate_wokwi_diagram(circuit_data)` convierte netlist Stratum al formato `diagram.json` de Wokwi (WOKWI_TYPE_MAP con 30+ componentes, conexiones con colores por tipo de pin). `run_wokwi_cli()` intenta simulación headless con wokwi-cli si está instalado y `WOKWI_CLI_TOKEN` configurado; si no, retorna `status: "unavailable"` con el diagram.json listo para cargar en wokwi.com. Endpoint `POST /api/circuits/{id}/simulate` en `circuits.py`.

2. ✅ **3.2 Plugin Manifesto + Instalación Remota** — `plugin_loader.py`: nuevo método `install_from_zip(bytes)` extrae ZIP, valida `plugin.json` (campos: name, version, entry, permissions), copia `.py` + `.json` a plugins/, hace hot-reload sin reiniciar. `uninstall(name)` desregistra tools y elimina archivos. `_read_manifest()` lee `plugin.json` junto al `.py` si existe. Endpoints `POST /api/plugins/install` (upload ZIP) y `DELETE /api/plugins/{name}` en `memory.py`. `tools/plugins/example_plugin.json` de ejemplo creado.

3. ✅ **3.3 Multi-usuario JWT** — `api/auth.py`: `encode_token`, `decode_token`, `get_current_user` (FastAPI Dependency). En `MULTI_USER=false` retorna `"default"` sin verificar. `api/routers/auth.py`: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `GET /api/auth/status`. Tabla `users` en `sql_memory.py` con `create_user`, `get_user_by_username`, `get_user_by_id`. Columna `user_id TEXT DEFAULT 'default'` agregada a: `facts`, `conversations`, `hardware_devices`, `firmware_history`, `circuit_context`, `project_library`, `circuit_designs` — todas con `ALTER TABLE` automático al iniciar. `core/config.py`: `MULTI_USER`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`. `.env`: `MULTI_USER=false`, `JWT_SECRET`, `WOKWI_CLI_TOKEN`. `requirements.txt`: `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`.

**Nuevos endpoints v2.0.0:**
- `POST /api/circuits/{id}/simulate` — genera diagram.json Wokwi + simulación opcional
- `POST /api/plugins/install` — instala plugin desde ZIP
- `DELETE /api/plugins/{name}` — desinstala plugin en caliente
- `POST /api/auth/register` — registro de usuario
- `POST /api/auth/login` — login, retorna JWT
- `GET /api/auth/me` — info del usuario autenticado
- `GET /api/auth/status` — si multi-user está activo

---

### Sesión 2026-04-01 — Plan de Escalado v1.2.0 + v1.3.0

**Fase 1 — Estabilidad (v1.2.0):**
1. ✅ **1.3 Unificar capas vectoriales** — verificado que `QdrantClient` existe solo en `infrastructure/vector_store.py`. `memory/vector_memory.py` solo tiene lógica de negocio.
2. ✅ **1.1 Qdrant Server Mode** — `VectorStore.__init__()` ahora usa `QdrantClient(url=QDRANT_URL)` si la variable está definida, `QdrantClient(path=VECTOR_DB_PATH)` como fallback. `QDRANT_URL` exportada desde `core/config.py`. Ya estaba configurada en `.env`.
3. ✅ **1.2 Cola de Jobs async** — `api/app_state.py` tiene `job_queue: asyncio.Queue` y `jobs: dict`. `api/job_worker.py` creado con `job_worker_loop()` y `_run_job()`. Arranca desde `startup_event()` en `server.py`. Endpoints `generate-firmware` y `parse-async` retornan `{job_id, status: "pending"}` inmediatamente. `GET /api/jobs/{id}` y `GET /api/jobs` expuestos en `memory.py`. `ProactiveEngine.broadcast(str)` agregado para emisión desde el worker.

**Fase 2 — UX y capacidades (v1.3.0):**
4. ✅ **2.2 Modelo dual fast/smart** — `LLM_MODEL_FAST` y `LLM_MODEL_SMART` en `core/config.py` y `.env`. `call_llm_async`, `call_llm_text`, `stream_llm_async`, `_call_llm` aceptan `model=` param. Orchestrator usa `LLM_MODEL_FAST` en routing LLM. `firmware_generator.py` importa `LLM_MODEL_SMART as LLM_MODEL`. `circuit_agent.py` pasa `model=LLM_MODEL_SMART` a `_call_llm`.
5. ✅ **2.1 Sesiones WS persistentes** — `sql_memory.py`: columna `session_id` en `conversations` con `ALTER TABLE` automático + índice. `store_message()` y `get_recent_messages()` aceptan `session_id=`. Nuevo `get_conversation_by_session()`. `websockets.py`: `/ws/chat` acepta `?session=<uuid>`, emite `{type: "session", session_id, resumed}`, persiste user/assistant en SQLite, carga historial al reconectar.
6. ✅ **2.3 MicroPython nativo** — `firmware_flasher.py`: `flash_micropython(script_path, port)` + `detect_micropython_repl(port)`. `hardware_detector.py`: detecta REPL en plataformas candidatas al listar. `hardware_memory.py`: columna `micropython` en `hardware_devices` con migración auto + `get_device_info()` + `register_device()` persiste el flag. `circuits.py`: endpoint `generate-firmware` detecta MicroPython y usa `flash_micropython` en vez de `compile_firmware`.
7. ✅ **2.4 Circuit editor drag & drop** — `database/circuit_design.py`: `update_layout(design_id, positions)` + `get_design()` retorna `positions`. `schematic_renderer.py`: usa posiciones guardadas si `circuit_data["positions"]` existe, calcula automáticamente para los que faltan. `circuits.py`: `PUT /api/circuits/{id}/layout`. `circuit_viewer.html`: funciones `_initDraggable()` y `_saveLayout()` en vanilla JS; grupos SVG nativos arrastrables con mousedown/mousemove/mouseup; posiciones aplicadas desde `currentCircuit.positions`.

**Refactor entrada:**
8. ✅ **run.py** — punto de entrada único que consolida `main.py`, `install.py` y `manage.py`. Subcomandos: `serve`, `setup`, `status`, `export`, `import`, `reset`. `main.py`, `install.py` y `manage.py` eliminados.

---

### Sesión 2026-03-31 — Bugs, Mejoras y Refactor (v1.1.0)
1. ✅ Bug fix `knowledge/documents` — `scroll()` desempaquetado como tupla
2. ✅ Health check extendido — SQLite, Qdrant, Ollama
3. ✅ COMPONENT_LIBRARY: 5 → 32 componentes + ~70 aliases
4. ✅ Prompt CircuitAgent: 9 reglas obligatorias + auto-add resistencias para LEDs
5. ✅ Caché LRU 5min/128 en `search_memory()`
6. ✅ Rate limiting WS chat: 3s/1 procesando
7. ✅ Refactor `api/server.py` → routers modulares en `api/routers/`

### Sesión 2026-03-26 (noche) — Auditoría y Limpieza
1. ✅ Archivos muertos eliminados: `episodic_memory.py`, `models.py`, `knowledge_vertorizer.py`
2. ✅ `generate_firmware_for_circuit()` completada
3. ✅ Singleton `CircuitAgent` + async wrapping con `asyncio.to_thread()`
4. ✅ Hardware polling: 30s → 60s. Log "No se detectaron" DEBUG en vez de INFO

---

## 11. ROADMAP

### Completado ✅
- [x] Prompt CircuitAgent mejorado (9 reglas + auto-add resistencias)
- [x] `generate_firmware_for_circuit()` completa
- [x] COMPONENT_LIBRARY: 5 → 32 componentes
- [x] Refactor `server.py` en routers modulares
- [x] Qdrant server mode
- [x] Cola de jobs async
- [x] Capas vectoriales unificadas
- [x] Sesiones WS persistentes
- [x] Modelo dual fast/smart
- [x] Soporte MicroPython nativo
- [x] Circuit editor drag & drop
- [x] Simulación Wokwi — `tools/wokwi_simulator.py`
- [x] Plugin manifesto + instalación desde ZIP
- [x] Multi-usuario JWT
- [x] **AI Intelligence** — perfiles de comportamiento + fuentes de conocimiento configurables
- [x] **Deploy Docker + Railway** — Dockerfile, railway.toml, CORS configurable, Qdrant Cloud
- [x] **App Mobile Capacitor 6** — Android + iOS, cámara nativa, push FCM, haptics

### Pendiente
- [ ] **6.5 Build APK/AAB** — Android Studio abierto ✅, Gradle sincronizando. Pendiente: Run en dispositivo / Generate Signed APK
- [ ] Dashboard de métricas (gráficos, timeline de proyectos)
- [ ] Tests E2E con hardware real
- [ ] Exportar proyectos como PlatformIO
- [ ] Integración Home Assistant via plugin
- [ ] Soporte PLCs (Ladder, Modbus)
- [ ] IA local en mobile vía Tailscale + Ollama en server doméstico

---

## 12. PLATAFORMAS SOPORTADAS

| Familia               | Modelos                                              |
|-----------------------|------------------------------------------------------|
| Arduino               | UNO, Mega, Nano, Mini, Leonardo, Due, Zero, MKR, Micro, Every |
| ESP32                 | ESP32, ESP32-S2, ESP32-S3, ESP32-C3                  |
| ESP8266               | NodeMCU, Wemos D1, FTDI                              |
| Raspberry Pi Pico     | RP2040, Pico W, Pico 2 — ★ con REPL MicroPython     |
| STM32                 | Blue Pill (GenF4)                                    |
| Teensy                | 3.x, 4.x                                            |
| Adafruit              | Feather M0/M4, QT Py RP2040                          |
| Seeeduino XIAO        | SAMD21, RP2040, ESP32C3, ESP32S3                     |

---

## 13. ARCHIVOS ELIMINADOS (Histórico)

| Archivo               | Fecha      | Motivo                                               |
|-----------------------|------------|------------------------------------------------------|
| `memory/episodic_memory.py`  | 2026-03-26 | Código muerto — nadie lo importaba              |
| `database/models.py`         | 2026-03-26 | Tablas definidas inline en sql_memory.py        |
| `knowledge/knowledge_vertorizer.py` | 2026-03-26 | Typo + llamaba método inexistente         |
| `.pyre_configuration`        | 2026-03-26 | Pyre no se usa, existe pyrightconfig.json       |
| `memory.db` (raíz)           | 2026-03-26 | Duplicado de database/memory.db                 |
| `main.py`                    | 2026-04-01 | Consolidado en run.py                           |
| `install.py`                 | 2026-04-01 | Consolidado en run.py setup                     |
| `manage.py`                  | 2026-04-01 | Consolidado en run.py status/export/import/reset|

---

## 14. NOTAS PARA EL AGENTE (v1.3.0)

1. **Punto de entrada:** `python run.py` (no `python api/server.py`, no `uvicorn` directo)
2. **Qdrant sin bloqueo:** configurar `QDRANT_URL=http://localhost:6333` y levantar Qdrant como servicio
3. **Nunca** instanciar `QdrantClient` fuera de `infrastructure/vector_store.py`
4. **Jobs:** operaciones largas deben encolarse con `job_queue.put()` y retornar `{job_id}`. No bloquear endpoints
5. **Modelo LLM:** usar `LLM_MODEL_SMART` para generación de código/circuitos, `LLM_MODEL_FAST` para clasificación/routing
6. **Sesiones WS:** el cliente debe guardar el `session_id` recibido en el mensaje `{type: "session"}` y pasarlo en reconexión con `?session=<uuid>`
7. **MicroPython:** si `hardware_memory.get_device_info(name)["micropython"]` es True → usar `flash_micropython()` y plataforma `"micropython"` en `generate_firmware()`
8. **Layout circuitos:** las posiciones de drag & drop se guardan en `metadata.positions` de `circuit_designs`. `get_design()` ya las retorna
9. **Imports circulares:** los singletons `agent`, `proactive_engine`, `job_queue`, `jobs` viven en `api/app_state.py`. Los routers los importan desde ahí
10. **Caché búsquedas:** `search_memory()` cachea 5min/LRU128. `invalidate_search_cache()` para forzar re-búsqueda
11. **Rate limiting WS:** 3s entre mensajes + 1 procesando. Ajustable con `_WS_RATE_WINDOW` en `websockets.py`
12. **SIEMPRE** usar `curl.exe` en PowerShell (no `curl`)
13. **OpenRouter:** `LLM_PROVIDER=openrouter` apunta a `https://openrouter.ai/api/v1/chat/completions`. Requiere `OPENROUTER_API_KEY`. El proxy `npx @aethermind/proxy` **no es necesario** con este provider
14. **Config en runtime:** `LLM_API`, `LLM_MODEL` y `get_llm_headers()` se leen en cada llamada desde `os.getenv()` — NO uses las constantes de módulo `LLM_API`/`LLM_MODEL` en código nuevo; usa `_get_llm_api()` / `_get_llm_model()` de `llm/async_client.py`
15. **CircuitAgent** usa singleton `_get_circuit_agent()` en `circuits.py` — no crear instancias por request
16. **Llamadas LLM en async** deben ir en `asyncio.to_thread()` para no bloquear el event loop
17. **Perfil AI activo:** `intelligence_db.get_active_profile()` retorna el perfil activo. `activate_profile(id)` marca `is_default=1` solo para ese perfil (limpia los demás). Cambiar perfil surte efecto en el siguiente mensaje sin reiniciar
18. **Fuentes de conocimiento:** indexar con `POST /api/intelligence/sources/{id}/index`. El agente usa solo las fuentes en `active_sources[]` del perfil activo. `search_in_sources()` filtra por `source_id` en Qdrant payload
19. **Deploy:** usar `ALLOWED_ORIGINS=capacitor://localhost,https://tu-dominio.com` en producción. SQLite en Railway requiere un volumen montado en `/app/database`
20. **Push notifications:** son opcionales. Sin `FIREBASE_SERVER_KEY` el sistema funciona igual — `push_notifier.py` hace no-op silenciosamente
21. **App mobile:** en WiFi local, cambiar `server.url` en `capacitor.config.ts` a la IP local del PC. En producción, apuntar al backend Railway. No requiere rebuild si se usa `server.url` (Capacitor carga el remote HTML)
22. **Puerto 11435:** es el proxy de AetherMind (`@aethermind/setup`). **No** es Ollama. Si `OLLAMA_BASE_URL` apunta ahí, las requests van al gateway cloud de Aethermind. Puerto real de Ollama: **11434**

---

_Este archivo es la memoria del proyecto. Actualizarlo después de cada sesión significativa._
_Última actualización: 2026-04-06 — Build Android iniciado. TypeScript requerido por Capacitor CLI. Android Studio abierto con proyecto listo._
