# STRATUM — Contexto del Proyecto
> Última actualización: 2026-04-20
> Versión actual: **v3.9.0**
> Tagline: _"Tu memoria técnica siempre disponible"_
> Estado: **Production-ready** (local + Railway)

---

## 1. CONCEPTO CENTRAL

Stratum es un **asistente de ingeniería electrónica con memoria persistente**. Un "Hardware Memory Engine" que recuerda todo el contexto técnico del ingeniero entre sesiones: circuitos, componentes, pines, conexiones, decisiones de diseño, fallos anteriores.

**Scope:** No es solo para Arduino. Asiste con microcontroladores (Arduino, ESP32, STM32, Pico, MicroPython), electrónica de potencia (VFD, contactores, fuentes switching), automatización industrial (PLC, Modbus, ladder), electrónica analógica/digital, sensores/actuadores, comunicaciones (I2C, SPI, CAN, RS-485, MQTT) y diseño de circuitos (esquemáticos, netlists, PCB, cálculo de componentes).

---

## 2. STACK TÉCNICO

| Capa           | Tecnología                                                          |
|----------------|---------------------------------------------------------------------|
| Backend        | Python 3.11 · FastAPI · asyncio · uvicorn                           |
| LLM            | OpenRouter (gpt-4o-mini fast · gpt-4o smart) — cloud               |
| Memoria SQL    | SQLite (`data/memory.db`)                                           |
| Memoria Vector | Qdrant — server mode (`QDRANT_URL`) o path local (`VECTOR_DB_PATH`)|
| Memoria Grafo  | NetworkX (`data/graph_memory.json`)                                 |
| Hardware       | arduino-cli · pyserial · mpremote (MicroPython)                     |
| Frontend web   | HTML · CSS (`styles.css`) · JS plain (modules sin ES-modules)       |
| Frontend mobile| Capacitor 6 (Android + iOS) · HTML/JS mobile-first · bottom nav    |
| Embeddings     | sentence-transformers/all-MiniLM-L6-v2 (384 dims)                  |
| Visión         | GPT-4o-mini via OpenRouter (detección de provider en runtime)       |
| Renderizado    | svgwrite (esquemáticos SVG, PCB, breadboard)                        |
| Deploy         | Docker · Railway (Dockerfile, PORT injection, healthcheck `/api/health`)|
| Push           | Firebase Cloud Messaging (FCM) — opcional (`FIREBASE_SERVER_KEY`)   |

---

## 3. ARQUITECTURA DE ARCHIVOS

```
ai-memory-engine/
│
├── run.py                          # Punto de entrada único (serve/setup/status/export/import/reset/bridge)
├── requirements.txt
├── .env / .env.example
├── Dockerfile
├── railway.toml                    # builder=dockerfile, healthcheck /health, restart on_failure
│
├── agent/                          # NÚCLEO DEL AGENTE
│   ├── agent_controller.py         # Recibe input, inyecta perfil activo, orquesta
│   ├── agent_runner.py             # Loop de tool calling
│   ├── agent_state.py              # Estado de sesión (historial)
│   ├── orchestrator.py             # Routing keyword-first → LLM fast fallback
│   ├── user_profiler.py            # Perfil del usuario (heurísticas, sin LLM)
│   │
│   ├── agents/                     # Agentes especializados
│   │   ├── base_agent.py
│   │   ├── hardware_agent.py       # Facade (~122 líneas) — delega a mixins
│   │   ├── hardware_design.py      # Mixin: parse_circuit, save_circuit (~224 líneas)
│   │   ├── hardware_firmware.py    # Mixin: generate, compile, flash, serial (~250 líneas)
│   │   ├── hardware_keywords.py    # Mixin: clasificación por keywords (~140 líneas)
│   │   ├── hardware_memory_ops.py  # Mixin: consultas a hardware_memory (~210 líneas)
│   │   ├── circuit_agent.py
│   │   ├── vision_agent.py         # GPT-4o-mini OpenRouter + LLaVA Ollama (detección runtime)
│   │   ├── research_agent.py       # DuckDuckGo
│   │   ├── code_agent.py           # Sandbox Python
│   │   ├── memory_agent.py         # Lectura vectorial+SQL+grafo sin LLM
│   │   └── electrical_calc_agent.py # Cálculo eléctrico: classify→extract→Python calc→explain (~214 líneas)
│   │
│   ├── prompts/                    # Prompts LLM externalizados
│   │   ├── __init__.py
│   │   └── electrical_calc_prompts.py  # CLASSIFY_PROMPT, EXTRACT_PARAMS_PROMPTS, EXPLAIN_PROMPT (~196 líneas)
│   │
│   ├── proactive_engine.py         # Facade orquestador (~82 líneas)
│   ├── proactive_broadcast.py      # Gestión de colas asyncio de clientes WS (~81 líneas)
│   ├── proactive_scheduler.py      # Loops periódicos: devices/inactive/errors/daily (~245 líneas)
│   └── proactive_consolidator.py   # Consolidación nocturna de memorias (~92 líneas)
│
├── api/                            # SERVIDOR WEB
│   ├── server.py                   # FastAPI app + lifecycle
│   ├── app_state.py                # Singletons: agent, proactive_engine, job_queue, jobs
│   ├── auth.py                     # JWT (MULTI_USER mode)
│   ├── limiter.py                  # Rate limiting
│   ├── job_worker.py               # Worker async de la cola de jobs (background)
│   │
│   ├── routers/
│   │   ├── auth.py                 # POST /api/auth/login
│   │   ├── memory.py               # /api/stats, /api/facts, /api/history, /api/search, /api/graph
│   │   ├── hardware.py             # /api/hardware/** (devices, firmware, circuits, library, vision, signal)
│   │   ├── hardware_bridge.py      # /ws/hardware-bridge · /api/hardware/bridge/status
│   │   ├── knowledge.py            # /api/knowledge/**
│   │   ├── circuits.py             # /api/circuits/** (parse, schematic, breadboard, pcb, gerber)
│   │   ├── schematics.py           # /api/schematics/** (import, supported, list)
│   │   ├── calc.py                 # /api/calc/** (ElectricalCalcAgent)
│   │   ├── intelligence.py         # /api/intelligence/** (perfiles + fuentes, 9 endpoints)
│   │   ├── stock.py                # /api/stock/**
│   │   ├── decisions.py            # /api/decisions/**
│   │   ├── push.py                 # POST/DELETE /api/push/register
│   │   └── websockets.py           # /ws/chat · /ws/signal · /ws/proactive
│   │
│   └── static/
│       ├── index.html              # Frontend principal Cyberpunk (~1136 líneas)
│       ├── styles.css              # Estilos separados (~43 líneas)
│       ├── app.js                  # Globals + init + navegación (~170 líneas, refactorizado)
│       ├── circuit_viewer.html     # Visualizador con drag & drop
│       ├── graph3d.html
│       └── modules/                # 14 módulos JS (plain <script>, no ES-modules)
│           ├── utils.js            # escHtml, renderMarkdown, addLog, offline queue (~124 líneas)
│           ├── auth.js             # authFetch, JWT, doLogin, loadAuthStatus (~71 líneas)
│           ├── sessions.js         # loadSessions, switchSession, deleteSession (~126 líneas)
│           ├── chat.js             # connectWS, sendMessage, streaming (~178 líneas)
│           ├── health.js           # loadHealth, bridge status, Wokwi status (~121 líneas)
│           ├── hardware.js         # loadHardware, oscilloscope, vision modal (~318 líneas)
│           ├── intelligence.js     # perfiles + fuentes de conocimiento (~154 líneas)
│           ├── calc.js             # calcSwitchForm, calcCompute, calcShowResult (~129 líneas)
│           ├── circuits.js         # DRC, BOM, Wokwi simulate (~131 líneas)
│           ├── kb.js               # kbLoadDocuments, kbUploadFile, kbSearch (~117 líneas)
│           ├── stock.js            # stock summary, search, import schematic (~112 líneas)
│           ├── metrics.js          # loadMetrics, charts firmw/stock (~289 líneas)
│           ├── decisions.js        # webLoadDecisions, webSaveDecision (~63 líneas)
│           └── proactive.js        # connectProactiveWS, showProactiveNotification (~40 líneas)
│
├── core/
│   ├── config.py                   # LLM_API, LLM_MODEL_*, DB paths, QDRANT_URL, PORT, ALLOWED_ORIGINS, MULTI_USER
│   ├── logger.py
│   └── prompt_builder.py           # build_prompt(system_prompt=, source_context=)
│
├── database/
│   ├── sql_memory.py               # CRUD SQLite: facts, conversations (con session_id), sessions
│   ├── hardware_memory.py          # Facade (~121 líneas) — delega a 4 sub-DB
│   ├── hardware_devices.py         # Tabla hardware_devices (~108 líneas)
│   ├── hardware_firmware.py        # Tabla firmware_history (~124 líneas)
│   ├── hardware_circuits.py        # Tablas circuit_context + circuit_history (~237 líneas)
│   ├── hardware_projects.py        # Tabla project_library + _auto_save_to_library (~170 líneas)
│   ├── circuit_design.py           # Tabla circuit_designs (con positions en metadata)
│   ├── component_stock.py          # Inventario de componentes
│   ├── design_decisions.py         # Decisiones de diseño
│   └── intelligence.py             # Tablas ai_profiles + knowledge_sources (4 perfiles por defecto)
│
├── memory/
│   ├── vector_memory.py            # Qdrant: store/search episodios, caché LRU 128/5min
│   ├── graph_memory.py             # NetworkX: relaciones entre entidades
│   ├── graph_extractor.py
│   ├── fact_extractor.py
│   ├── short_memory.py
│   ├── memory_consolidator.py      # Fusión nocturna de memorias antiguas
│   ├── memory_filter.py
│   ├── session_summarizer.py
│   └── pdf_memory.py
│
├── llm/
│   ├── async_client.py             # call_llm_text/async/stream — aceptan model= param, agent_id, use_cache
│   ├── openrouter_client.py        # Cliente sync + streaming
│   └── cache.py                    # Caché LLM
│
├── tools/
│   ├── electrical_formulas.py      # Re-export module (~79 líneas) + FORMULA_REGISTRY (25 fórmulas)
│   ├── formulas_basic.py           # helpers + ohms_law, resistor_* (~146 líneas)
│   ├── formulas_rc.py              # capacitor_*, rc_time_constant, low/high_pass_rc, lc_filter (~83 líneas)
│   ├── formulas_power.py           # power_dissipation, heat_sink, efficiency, fuse_rating (~67 líneas)
│   ├── formulas_converters.py      # buck, boost, transformer_turns_ratio (~99 líneas)
│   ├── formulas_opamp.py           # inverting_amp, non_inverting_amp, voltage_follower (~31 líneas)
│   ├── formulas_drives.py          # battery_autonomy, charge_time, motor_*, vfd (~95 líneas)
│   ├── electrical_drc.py           # DRC de circuitos (design rule check)
│   ├── schematic_parser.py         # KiCad v6, KiCad v5, LTspice, Eagle (~584 líneas)
│   ├── schematic_renderer.py       # SVG con posiciones guardadas
│   ├── breadboard_renderer.py
│   ├── pcb_renderer.py
│   ├── bom_generator.py
│   ├── firmware_generator.py       # LLM_MODEL_SMART, soporta micropython
│   ├── firmware_flasher.py         # arduino-cli + flash_micropython() via mpremote
│   ├── hardware_bridge_client.py   # Bridge PC: ejecuta jobs locales enviados desde el backend
│   ├── hardware_detector.py        # Detecta USB + REPL MicroPython automáticamente
│   ├── serial_monitor.py
│   ├── signal_reader.py
│   ├── web_search.py               # DuckDuckGo
│   ├── code_executor.py            # Sandbox Python
│   ├── tool_registry.py
│   ├── plugin_loader.py
│   ├── push_notifier.py            # FCM push notifications
│   ├── wokwi_simulator.py
│   ├── plc_parser.py
│   ├── platformio_exporter.py
│   ├── pdf_exporter.py
│   └── plugins/
│       ├── example_plugin.py
│       └── homeassistant_plugin.py
│
├── cli/                            # CLI de administración (subcomandos de run.py)
│   ├── __init__.py
│   ├── setup.py                    # Instala deps, configura entorno
│   ├── status.py                   # Estado de la memoria
│   ├── backup.py                   # export/import ZIP
│   ├── reset.py                    # Borrar toda la memoria
│   └── utils.py
│
├── knowledge/
│   ├── knowledge_base.py
│   ├── document_loader.py
│   └── document_chunker.py
│
├── infrastructure/
│   ├── vector_store.py             # Singleton Qdrant — server si QDRANT_URL, path local si no
│   └── embeddings.py               # MiniLM — carga local_files_only=True, fallback descarga
│
├── data/                           # Datos persistentes (montados en Railway como volumen)
│   └── component_library.json
│
├── eval/                           # Tests
│   ├── run_eval.py
│   ├── test_circuit_integration.py
│   ├── test_full_integration.py    # 3 tests offline (integration + kicad v6 + kicad v5 legacy)
│   └── test_e2e_api.py             # Tests e2e (requieren servidor corriendo en :8000)
│
└── stratum-mobile/                 # App móvil Capacitor 6
    ├── package.json
    ├── capacitor.config.ts          # appId: com.stratum.hardware
    └── www/
        └── index.html               # UI mobile-first: bottom nav, FAB cámara, push, haptics
```

---

## 4. FEATURES PRINCIPALES

### 4.1 Motor de Memoria Triple
- ✅ **SQL (SQLite):** Facts, conversaciones por `session_id`, sesiones con título auto-generado, dispositivos, firmware, circuitos, biblioteca de proyectos
- ✅ **Vectorial (Qdrant):** Server mode vía `QDRANT_URL` + `QDRANT_API_KEY`, o path local como fallback. Búsqueda semántica MiniLM (384 dims). Caché LRU 128/5min. `search_in_sources(query, source_ids)` para filtrar por fuente
- ✅ **Grafo (NetworkX):** Relaciones entre entidades, persistido en JSON. Compatible NX 3.2+ (manejo `edges=` vs `"links"`)

### 4.2 Agentes Especializados

| Agente              | Modelo LLM     | Estado | Función                                            |
|---------------------|----------------|--------|----------------------------------------------------|
| HardwareAgent       | smart          | ✅     | Programa, compila, flashea, debuggea — facade de 4 mixins |
| ElectricalCalcAgent | fast + default | ✅     | 25 fórmulas Python puras — LLM solo clasifica y explica |
| CircuitAgent        | smart          | ✅     | NL → netlist JSON → DB                             |
| VisionAgent         | gpt-4o-mini    | ✅     | Analiza imágenes de circuitos (OpenRouter o LLaVA) |
| ResearchAgent       | default        | ✅     | Búsqueda DuckDuckGo                                |
| CodeAgent           | default        | ✅     | Ejecuta Python en sandbox                          |
| MemoryAgent         | (sin LLM)      | ✅     | Consulta vectorial + SQL + grafo                   |
| Orchestrator        | fast           | ✅     | Routing keyword-first → LLM fast fallback          |

### 4.3 Motor de Cálculo Eléctrico (ElectricalCalcAgent)
✅ Flujo: clasificar tipo (LLM fast) → extraer parámetros (LLM) → **calcular con fórmulas Python puras** → explicar (LLM). El LLM NO hace las cuentas.

**25 fórmulas disponibles** en 6 categorías:
- `formulas_basic`: ohms_law, resistor_for_led, resistor_voltage_divider, resistor_power
- `formulas_rc`: capacitor_filter, rc_time_constant, capacitor_energy, low_pass_rc, high_pass_rc, lc_filter
- `formulas_power`: power_dissipation, heat_sink_required, efficiency, fuse_rating
- `formulas_converters`: buck_converter, boost_converter, transformer_turns_ratio
- `formulas_opamp`: inverting_amp, non_inverting_amp, voltage_follower
- `formulas_drives`: battery_autonomy, charge_time, motor_power, vfd_frequency_for_rpm, motor_torque

Helpers compartidos en `formulas_basic`: `_E24`, `_FUSE_STD`, `_nearest_e24()`, `_nearest_fuse()`, `_result()`

### 4.4 Parser de Esquemáticos

| Formato          | Soporte        | Conectividad real |
|------------------|----------------|-------------------|
| KiCad v6+ (.kicad_sch) | ✅         | ✅ Union-Find, lib_symbols, rotación de pines |
| KiCad v5 (.sch)  | ✅             | ✅ Union-Find, Wire Wire Line, P X Y fallback |
| LTspice (.asc)   | ✅             | Básico (FLAG nets) |
| Eagle (.sch XML) | ✅             | pinref → nodes    |

**KiCad v6 Union-Find:** extrae lib_symbols → calcula coordenadas mundo con rotación → wires + junctions + net labels → Union-Find con tolerancia 0.5mm → nodes `"REF.PIN"`.

**KiCad v5 Union-Find:** parsea `Wire Wire Line` (coords en línea siguiente) → `Connection ~ X Y` → `Text Label/GLabel/HLabel` (nombre en línea siguiente) → usa `P X Y` del componente como posición-pin fallback → Union-Find con tolerancia 25 mils.

### 4.5 Motor Proactivo (Background)
✅ 4 loops independientes en background:
- Cada 60s: detecta nuevos dispositivos USB → notifica en `/ws/proactive`
- Cada 1h: avisa dispositivos inactivos (3+ días)
- Cada 30min: detecta errores recurrentes
- A medianoche: consolidación automática de memorias antiguas (`memory_consolidator`)

### 4.6 Cola de Jobs Async
✅ Operaciones largas (compile, flash, parse_circuit) se despachan sin bloquear el WebSocket:
- `POST /api/circuits/{device}/generate-firmware` → `{ "job_id": "...", "status": "pending" }`
- `GET /api/jobs/{job_id}` → polling de estado
- Al completar: `/ws/proactive` emite `{ "type": "job_complete", ... }`

### 4.7 Sesiones WebSocket Persistentes
✅ `/ws/chat?session=<uuid>`: carga los últimos 20 mensajes de SQLite, inyecta en el agente. Título generado por IA (LLM, 5 palabras) tras el primer intercambio completo. Reconexión con backoff exponencial (2s → 4s → … → 8s).

### 4.8 Hardware Bridge (Programación Remota)
✅ Arquitectura: `[Celular/web] → [Railway] → /ws/hardware-bridge → [PC+Arduino]`
- Backend expone `/ws/hardware-bridge?token=<token>` — el PC se conecta como cliente bridge
- `_program_device()` detecta si el bridge está conectado → despacha job al PC
- `python run.py bridge --url https://stratum.railway.app --token <token>`

### 4.9 AI Intelligence — Perfiles y Fuentes
✅ 4 perfiles por defecto: Técnico Conciso (activo), Mentor Arduino, Debug Mode, Producción.
Cambiar perfil → tono y contexto cambian en el siguiente mensaje sin reiniciar.

### 4.10 MicroPython Nativo
✅ `flash_micropython()` via `mpremote cp + reset`. `detect_micropython_repl()` detecta `>>>`. `hardware_detector.py` auto-detecta REPL al listar dispositivos.

### 4.11 Seguridad
✅ JWT (`MULTI_USER=true`) — todos los endpoints sensibles y WebSockets protegidos.
✅ Rate limiting por endpoint (SlowAPI).
✅ CORS cerrado a `ALLOWED_ORIGINS` (lista por comas en env var Railway).
✅ `/data` configurado como volumen persistente en Railway.
✅ `BRIDGE_TOKEN` para autenticar el bridge client.

### 4.12 Frontend Web
✅ CSS + JS extraídos a `styles.css` y 15 módulos JS (plain `<script>` tags para mantener scope global necesario por `onclick=`).
✅ Chat streaming token a token con **markdown progresivo** (render parcial cada 120ms, no solo al finalizar).
✅ **Textarea auto-expandible** para el input (crece hasta 220px, scroll interno, Enter=enviar, Shift+Enter=nueva línea, Esc=limpiar).
✅ **Contador de caracteres** en el input (visible >50 chars, rojo >3000).
✅ **Botón COPY** en cada bloque de código (aparece al hover, usa Clipboard API).
✅ **Scroll inteligente**: solo fuerza scroll al fondo si el usuario ya estaba ahí.
✅ **Rate limit countdown**: el botón enviar muestra `3s → 2s → 1s` en vez de burbuja de error.
✅ Tab calculadora eléctrica (25 fórmulas con formularios específicos).
✅ Tab INTEL: gestión de perfiles AI + fuentes de conocimiento.
✅ Sesiones múltiples: sidebar con lista, switcheo, delete, título IA.
✅ Motor proactivo vía `/ws/proactive`.
✅ Offline queue: mensajes enviados sin conexión se persisten y se reintentan al reconectar.
✅ **URLs producción correctas**: `https://` + `wss://` en Railway, `http://` + `ws://` en localhost (sin puerto hardcodeado).
✅ **Health dots correctos**: LLM verde con OpenRouter (`llm_provider` set), Qdrant verde si `not_initialized` (opcional).
✅ **Historial de sesión en orden correcto**: `loadSessionHistory` no invierte mensajes (ya vienen cronológicos del backend).
✅ **TTS (Text-to-Speech)**: botón en cada mensaje del agente — Web Speech API, idioma es-AR, cancela al reclickear.
✅ **Export MD**: descarga el mensaje del agente como `.md` con un click.
✅ **Snippets `/`**: tipear `/` en el input muestra menú con 15 plantillas de ingeniería (↑↓ navegar, Enter seleccionar, Esc cerrar). 
✅ **Ctrl+K buscar**: modal de búsqueda semántica en memoria vectorial — resultados clickeables inyectan texto en el input.
✅ **Proyecto Activo**: sección en sidebar con lista de proyectos, activar/desactivar, crear (nombre, MCU, componentes, descripción). El proyecto activo se inyecta en el contexto de cada conversación vía `_build_base_context()`.
✅ **Adjuntar archivos**: botón clip en input — `.ino`, `.txt`, `.cpp`, `.py`, `.json`, imágenes. Texto se inserta como bloque de código en el prompt; imágenes como `[Imagen adjunta: nombre]`.
✅ **Firmware diff**: botón DIFF en vista de historial de dispositivo — muestra diff coloreado (verde/rojo) entre las últimas 2 versiones de firmware.
✅ **Push notifications backend**: `proactive_scheduler.py` llama `send_push_to_all()` en eventos `device_connected` e `device_inactive`.

---

## 5. MEMORIA DEL AGENTE

### Tres capas por turno
```
Usuario escribe mensaje
  ↓
short_memory: últimos N mensajes del contexto de sesión
  ↓
vector_memory: búsqueda semántica en Qdrant (episodios previos relevantes)
  ↓
graph_memory: relaciones de entidades del grafo NetworkX
  ↓
fact_extractor: hechos SQL del usuario
  ↓
prompt_builder: ensambla system_prompt (perfil activo) + source_context + memoria recuperada
  ↓
LLM genera respuesta
  ↓
fact_extractor: extrae nuevos hechos → SQLite
graph_extractor: extrae nuevas relaciones → NetworkX
vector_memory.store(): guarda episodio → Qdrant
```

### Fix aplicado — memories=[]
`vector_memory.py`: cuando Qdrant no está disponible o la colección está vacía, retorna `[]` en vez de lanzar excepción. El agente funciona en modo degradado (sin memoria vectorial) si Qdrant no está accesible.

### Consolidación nocturna
`memory_consolidator.py` fusiona episodios con más de N días en resúmenes comprimidos. Se dispara a medianoche desde `proactive_consolidator.py`. También se puede disparar en el shutdown del servidor (`consolidate_on_exit()`).

---

## 6. SEGURIDAD Y DEPLOY

### Variables de entorno requeridas (Railway)
```
OPENROUTER_API_KEY=...
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=openai/gpt-4o-mini
LLM_MODEL_FAST=openai/gpt-4o-mini
LLM_MODEL_SMART=openai/gpt-4o
MULTI_USER=false
JWT_SECRET=...
MEMORY_DECAY_RATE=0.01
MEMORY_DB_PATH=/data/database/memory.db
VECTOR_DB_PATH=/data/memory_db
GRAPH_DB_PATH=/data/database/graph_memory.json
QDRANT_COLLECTION=agent_memory
VECTOR_COLLECTION=agent_memory
QDRANT_URL=https://<cluster>.cloud.qdrant.io      # Qdrant Cloud (configurado)
QDRANT_API_KEY=...                                 # JWT key de Qdrant Cloud (configurado)
ALLOWED_ORIGINS=https://tu-app.up.railway.app      # Opcional
BRIDGE_TOKEN=...                                   # Opcional, para hardware bridge
FIREBASE_SERVER_KEY=...                            # Opcional, para push notifications
```
> Railway no lee `.env` — todas las variables se configuran en el dashboard de Railway.
> `QDRANT_URL` y `QDRANT_API_KEY` configurados y operativos con Qdrant Cloud (us-west-2).

### Railway deploy
- Builder: Dockerfile (`python:3.11-slim`, pre-descarga embedding model en build time)
- Start: `python run.py serve --no-reload`
- Health check: `GET /api/health` (timeout 120s)
- Restart: on_failure, max 3 reintentos
- Volumen: `/data` para SQLite, Qdrant local, graph_memory.json

### CORS
`ALLOWED_ORIGINS` acepta lista separada por comas o `"*"`. En producción: solo el dominio Railway.

### Rate limiting
SlowAPI — límites configurados por endpoint en `api/limiter.py`.

---

## 7. TESTS

### Estado actual: 3/3 pasan (offline)
```
eval/test_full_integration.py::test_complete_integration        ✅
eval/test_full_integration.py::test_kicad_connectivity          ✅  (parser v6 Union-Find)
eval/test_full_integration.py::test_kicad_legacy_connectivity   ✅  (parser v5 Union-Find)
```

`eval/test_e2e_api.py` — requiere servidor corriendo en `:8000` (no se ejecuta offline).

### Cobertura
- `test_complete_integration`: importaciones, DB de componentes, CircuitDesignManager, HardwareAgent._format_circuit_for_firmware
- `test_kicad_connectivity`: parser KiCad v6 — 2 componentes, 3 nets (VCC/ANODE/GND), nodes poblados con REF.PIN, DRC ejecutable, sin SHORT_CIRCUIT
- `test_kicad_legacy_connectivity`: parser KiCad v5 — 2 componentes (R1/LED1), 2 nets separados (VCC/GND), nodes != []

---

## 8. DEUDA TÉCNICA RESUELTA

| Archivo original              | Antes    | Después                          | Motivo                          |
|-------------------------------|----------|----------------------------------|---------------------------------|
| `api/static/app.js`           | 2154 lín | 170 lín + 14 módulos (~1816 lín total) | Separación de responsabilidades |
| `database/hardware_memory.py` | ~500 lín | 121 lín facade + 4 sub-DB (~639 lín total) | Tabla única → 4 tablas especializadas |
| `agent/proactive_engine.py`   | ~450 lín | 82 lín facade + 3 clases (~500 lín total) | Broadcast/Scheduler/Consolidator independientes |
| `agent/agents/electrical_calc_agent.py` | ~350 lín | 214 lín + prompts externos (196 lín) | Prompts LLM externalizados |
| `tools/electrical_formulas.py` | 564 lín | 79 lín re-export + 6 módulos (~521 lín total) | 25 fórmulas en 6 categorías |
| `tools/schematic_parser.py`   | legacy básico | Union-Find v5 + v6 (~584 lín) | Conectividad real trazada |
| `agent/agents/hardware_agent.py` | ~950 lín | 122 lín facade + 4 mixins (~946 lín total) | Mixin split por responsabilidad |

---

## 9. KNOWLEDGE BASE TÉCNICA

Archivos en `agent_files/knowledge/` — indexados automáticamente al startup via `index_knowledge_base()`:

| Archivo | Contenido |
|---|---|
| `01_electronica_analogica.txt` | Ley de Ohm, filtros RC/RLC, op-amps, BJT, MOSFET, diodos, capacitores, inductores |
| `02_microcontroladores.txt` | Arduino UNO/MEGA, ESP32, ESP8266, STM32, Pico RP2040, I2C/SPI/UART/interrupciones |
| `03_electronica_potencia.txt` | Buck/Boost/Flyback, IGBT, MOSFET potencia, drivers de gate, motores, baterías, transformadores |
| `04_plc_automatizacion.txt` | Siemens S7, IEC 61131-3, Ladder, variadores VFD, servos, redes industriales, sensores 4-20mA |
| `05_sensores_protocolos.txt` | DHT/BMP/MPU, INA219, HX711, MQTT, HTTP, WebSocket, BLE, LoRa, Zigbee, SD/FRAM |
| `06_instalaciones_electricas.txt` | Normas IEC/AEA, secciones cables, MCB/RCD, puesta a tierra, motores, cuadros, iluminación |
| `07_formulas_calculos.txt` | Conversiones, caída de tensión, corrección FP, mecánica, hidráulica, PID, Fourier, ADC |

---

## 10. MEJORAS PROPUESTAS — DIFERENCIADORES CLAVE

Las siguientes mejoras están ordenadas por impacto percibido vs herramientas existentes (ChatGPT, Copilot, Claude). El criterio: ¿puede hacerlo otra herramienta sin configuración especial? Si no → diferenciador real.

### 10.1 Datasheet auto-fetch + indexado ⭐⭐⭐⭐⭐
**Impacto:** El mayor diferenciador técnico posible.
- El usuario escribe el nombre de un CI (ESP32, LM317, IRF520, etc.) → el sistema busca el datasheet en Alldatasheet/Mouser → lo parsea y lo indexa automáticamente en la KB
- Cuando luego pregunta "¿cuánta corriente puede dar el LM317?" → la respuesta viene del datasheet real, no de la memoria del LLM
- Ninguna otra herramienta hace esto automáticamente. ChatGPT inventa valores. Stratum los verifica.
- **Implementación:** `tools/datasheet_fetcher.py` + endpoint `POST /api/kb/fetch-datasheet?ic=LM317` + trigger en HardwareAgent cuando detecta nombre de CI

### 10.2 Firmware iterativo con diff ⭐⭐⭐⭐⭐
**Impacto:** Cambia completamente el flujo de trabajo de programación.
- Actualmente: cada mensaje regenera el firmware desde cero
- Mejora: el sistema mantiene el "firmware activo" en la sesión → cuando el usuario dice "hacelo más rápido" o "agregá el sensor de humedad", hace un PATCH del código y muestra un diff coloreado
- El ingeniero ve exactamente qué cambió, no tiene que releer todo
- **Implementación:** `agent_state.py` guarda `current_firmware_draft`, `HardwareAgent` detecta intent `"modify"` → aplica cambio incremental + genera diff con `difflib`

### 10.3 Wokwi auto-simulate ⭐⭐⭐⭐
**Impacto:** Probar código sin tener el hardware físico.
- Al generar firmware, botón "SIMULAR" → abre Wokwi con el ESP32/Arduino y el código ya cargado, en un iframe o nueva tab
- El sistema construye el JSON de Wokwi con los componentes correctos (LED en pin X, sensor en pin Y) basado en el circuito guardado en memoria
- Ninguna herramienta de chat hace esto end-to-end automáticamente
- **Implementación:** `tools/wokwi_simulator.py` ya existe — extender para generar el JSON de diagrama desde `hardware_circuits.py`

### 10.4 Sesión compartida / export de proyecto ⭐⭐⭐⭐
**Impacto:** El ingeniero puede documentar y compartir trabajo completo.
- Export de sesión completa como PDF técnico: código, cálculos, esquemas, decisiones de diseño, todo formateado profesionalmente
- O como ZIP: firmware `.cpp`, schematic `.svg`, BOM `.csv`, decisiones `.md`
- Útil para entregas a clientes, documentación interna, portfolio
- **Implementación:** `tools/pdf_exporter.py` ya existe — integrar con endpoint `GET /api/sessions/{id}/export?format=pdf|zip`

### 10.5 Memoria de errores + patrones ⭐⭐⭐⭐
**Impacto:** El asistente se vuelve más útil cuanto más se usa — diferenciador directo vs herramientas sin memoria.
- El sistema detecta cuándo el mismo error aparece múltiples veces en la historia → proactivamente sugiere una solución raíz
- Ejemplo: "Esta es la 3ra vez que tu ESP32 se desconecta del WiFi. En las sesiones anteriores coincidió con uso de ADC2 — ese pin no funciona con WiFi activo. Cambié los pines a ADC1."
- **Implementación:** `proactive_scheduler.py` agrega un loop que analiza errores recurrentes en `graph_memory` + `vector_memory`

### 10.6 Voice-to-firmware pipeline completo ⭐⭐⭐
**Impacto:** El ingeniero habla, el sistema genera código y wiring.
- La voz ya existe (Web Speech API) pero solo inserta texto en el prompt
- Mejora: modo "voice firmware" → el usuario describe en voz lo que quiere → el sistema genera firmware + esquema de conexiones + BOM en un solo paso
- **Implementación:** Detectar frases clave en el transcript de voz → disparar pipeline directo a `HardwareAgent._design_consult` + `CircuitAgent`

### 10.7 Context de plataforma persistente en sesión ⭐⭐⭐
**Impacto:** Elimina la inconsistencia actual (MicroPython vs C++ en la misma sesión).
- Cuando el usuario menciona "Arduino IDE", "C++", "MicroPython", o una plataforma específica, el sistema lo guarda como contexto de sesión
- Todos los mensajes siguientes usan esa plataforma por defecto sin necesidad de repetirla
- **Implementación:** `agent_state.py` agrega `session_platform: str` → `agent_controller.py` lo inyecta en el system prompt → `hardware_agent.py` lo usa en `_design_consult`

---

## 11. PENDIENTE TÉCNICO

- HardwareAgent: por defecto genera MicroPython en vez de C++/Arduino — system prompt de `_design_consult` debe preferir C++/Arduino salvo que el usuario pida explícitamente MicroPython
- Parser KiCad v5: usar coordenadas de pines reales del `.lib` si está disponible (actualmente usa `P X Y` del componente como fallback)
- Test e2e offline (mockear el servidor en pytest)
- App mobile: publicar en Play Store / App Store (requiere `google-services.json` FCM)

---

## 12. HISTORIAL DE VERSIONES

| Versión | Fecha       | Cambios principales |
|---------|-------------|---------------------|
| v1.0.0  | 2026-03-01  | Base: FastAPI + SQLite + Qdrant + HardwareAgent |
| v1.2.0  | 2026-03-15  | Cola de jobs async, /api/jobs/** |
| v1.3.0  | 2026-03-20  | Sesiones WS persistentes, modelo dual fast/smart, MicroPython nativo |
| v2.1.0  | 2026-03-28  | AI Intelligence (perfiles + fuentes), Docker + Railway deploy |
| v2.2.0  | 2026-04-07  | App mobile Android corriendo, VisionAgent OpenRouter, fixes NetworkX/facts |
| v2.3.0  | 2026-04-07  | Hardware Bridge (programación remota), sesiones mobile, URL configurable |
| v3.0.0  | 2026-04-09  | Split app.js → 14 módulos JS, CSS extraído, offline queue, burbuja vacía fix |
| v3.1.0  | 2026-04-10  | JWT auth en todos los endpoints sensibles |
| v3.2.0  | 2026-04-11  | KiCad v6 Union-Find parser, fix Railway startup, Qdrant siempre en prompt |
| v3.3.0  | 2026-04-13  | ElectricalCalcAgent routing fix, markdown UI mejorado, server-restart detection |
| v3.4.0  | 2026-04-14  | hardware_memory.py → 4 sub-DB + facade; proactive_engine → 3 clases; electrical_calc_agent → prompts externos |
| v3.5.0  | 2026-04-16  | electrical_formulas.py → 6 módulos; KiCad v5 Union-Find parser; hardware_agent → 4 mixins |
| v3.6.0  | 2026-04-17  | Eliminar Aethermind; URLs rotas JS (decisions/stock/schematics); polling consolidado (30s/60s); healthcheck /api/health; load_dotenv override=True; Railway deploy funcional con volumen /data |
| v3.7.0  | 2026-04-17  | Fix wss/https en producción; fix health dots (LLM+Qdrant); fix historial orden doble-reverse; textarea auto-expandible; markdown streaming progresivo; botón COPY en código; scroll inteligente; rate limit countdown; contador chars; Esc limpia input; título sesión por IA; Qdrant Cloud configurado; 7 archivos KB técnica indexados |
| v3.8.0  | 2026-04-17  | TTS en mensajes; Export MD; snippets `/` (15 plantillas ingeniería); Ctrl+K búsqueda semántica modal; Proyecto Activo sidebar (CRUD + activar + inyección en contexto LLM); adjuntar archivos en chat (.ino/.txt/.cpp/imagen); firmware diff coloreado en hardware view; push notifications en eventos proactivos |
| v3.9.0  | 2026-04-20  | Nuevo diseño UI CAD-instrument (design system completo); bottom nav eliminado → hamburger mobile; composer simplificado; empty state chat mobile; agent routing fix (escribí/código → design, no query); Ctrl+K unificado memoria+KB con {text,score}; 15 mensajes de sesión larga testeados; KB indexada con 10 documentos |
