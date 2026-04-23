# STRATUM — Contexto del Proyecto
> Última actualización: 2026-04-22
> Versión actual: **v4.7.0**
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
- Cada 30min: detecta errores recurrentes en hardware **y en vector memory** (ADC2, watchdog, conectividad, etc.)
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
✅ **Nuevo diseño CAD-instrument** (v4.0): design system completo con `panel-cnr`, `ruler`, `msg-user`/`msg-agent` diferenciados, acento azul cyan.
✅ **Navegación mobile via hamburger** `☰`: sidebar deslizable con todos los módulos, sin bottom nav.
✅ **Empty state chat**: cuando no hay mensajes muestra ícono + tags clickeables en lugar de void negro.
✅ Chat streaming token a token con **markdown progresivo** (render parcial cada 120ms, no solo al finalizar).
✅ **Textarea auto-expandible** para el input (crece hasta 220px, scroll interno, Enter=enviar, Shift+Enter=nueva línea, Esc=limpiar).
✅ **Contador de caracteres** en el input (visible cuando hay texto, rojo >3000).
✅ **Botón COPY** en cada bloque de código (aparece al hover, usa Clipboard API).
✅ **Scroll inteligente**: solo fuerza scroll al fondo si el usuario ya estaba ahí.
✅ **Rate limit countdown**: el botón enviar muestra `3s → 2s → 1s` en vez de burbuja de error.
✅ Tab calculadora eléctrica (25 fórmulas con formularios específicos).
✅ Tab INTEL: gestión de perfiles AI + fuentes de conocimiento.
✅ Sesiones múltiples: sidebar con lista, switcheo, delete, título IA.
✅ Motor proactivo vía `/ws/proactive`.
✅ Offline queue: mensajes enviados sin conexión se persisten y se reintentan al reconectar.
✅ **TTS (Text-to-Speech)**: botón en cada mensaje del agente — Web Speech API, idioma es-AR.
✅ **Export MD**: descarga el mensaje del agente como `.md`.
✅ **Export ZIP**: botón `ZIP` en header — descarga `chat.md` + `firmware.cpp` + `decisiones.md` de la sesión.
✅ **Snippets `/`**: tipear `/` muestra menú con 15 plantillas de ingeniería (↑↓, Enter, Esc).
✅ **Ctrl+K buscar**: búsqueda semántica unificada en memoria de chat + KB, retorna `{text, score}`.
✅ **Proyecto Activo**: CRUD en sidebar, se inyecta en contexto LLM vía `_build_base_context()`.
✅ **Adjuntar archivos**: `.ino`, `.txt`, `.cpp`, `.py`, `.json`, imágenes.
✅ **Voice auto-send**: botón `send_time_extension` — activado, tras reconocimiento de voz el mensaje se envía solo.
✅ **Push notifications backend**: `proactive_scheduler.py` llama `send_push_to_all()` en eventos proactivos.

### 4.13 Platform Context Persistente (v4.0)
✅ `AgentState.session_platform` — detecta `arduino`/`micropython`/`esp-idf`/`platformio` en cada mensaje.
✅ `AgentController._detect_and_set_platform()` — parsea keywords y actualiza el estado de sesión.
✅ `HardwareAgent._design_consult()` — usa C++/Arduino como default, respeta la plataforma detectada.
✅ Firmware draft en sesión: `AgentState.current_firmware_draft` guarda el último código generado.

### 4.14 Firmware Iterativo con Diff (v4.0 / fix v4.0.1)
✅ Intent `modify` en `HardwareAgent` — detectado por LLM y keywords ("hacelo más rápido", "agregá wifi", etc.).
✅ `_DiffMixin._modify_firmware()` — toma el draft actual, aplica el cambio incremental via LLM, genera diff `unified`.
✅ Respuesta incluye bloque `diff` coloreado (verde/rojo) + código completo actualizado.
✅ El nuevo código se persiste en `AgentState` para futuras modificaciones encadenadas.
⚠️ Fix v4.0.1: `"modify"` estaba ausente de la tupla de intents válidos en `_classify_intent()` — el LLM lo clasificaba bien pero el resultado era descartado. Además MODIFY_KEYWORDS se evaluaba después de DESIGN_KEYWORDS. Ambos bugs corregidos en `hardware_agent.py`.

### 4.15 Datasheet Auto-Fetch (v4.0)
✅ `tools/datasheet_fetcher.py` — detecta nombres de CIs en texto via regex (`lm\d+`, `ne\d+`, `irf\d+`, etc.).
✅ URLs directas para TI, ST, Microchip (LM317, LM7805, LM35, NE555, ULN2003, L298N, INA219...).
✅ Fallback: búsqueda web DuckDuckGo → parseo PDF con `pdfplumber`.
✅ Fallback final: resumen LLM si no encuentra el PDF.
✅ Todo se cachea en `agent_files/datasheets/` e indexa en KB automáticamente en background.
✅ Hook en `AgentController._auto_fetch_datasheets()` — se dispara como `asyncio.create_task` por cada mensaje.

### 4.17 Generación de Circuitos con Dominio Detectado (v4.1 / fix v4.5.0)
✅ `CircuitAgent` detecta automáticamente el dominio del proyecto (irrigación, domótica, motor, IoT, display, audio, etc.) con `_detect_domain()`.
✅ Selección automática del MCU óptimo por dominio (ESP32 para IoT/riego/domótica, Arduino para control simple).
✅ Hints de dominio inyectados en el prompt: componentes recomendados, reglas de protección (flyback para relays, caps bulk para motores, pull-ups I2C), advertencias de seguridad.
✅ Post-validación por dominio: riego sin relay → warning, motor sin driver → warning, IoT sin WiFi → warning.
✅ Auto-agrega diodo flyback 1N4007 cuando detecta relay sin diodo de protección.
✅ Cleanup JSON mejorado: extrae el JSON aunque el LLM incluya texto extra antes/después.
✅ Respuesta incluye `detected_domain` y `selected_mcu` para trazabilidad.
⚠️ Fix v4.5.0: `domain_hint` se calculaba pero nunca se pasaba al `.format()` del `CIRCUIT_PARSE_PROMPT` → circuito de riego salía sin sensor de humedad de suelo (FC-28/YL-69). Fix: `{domain_hint}` agregado al template y `domain_hint=domain_hint` al format call.
⚠️ Fix v4.5.0: Agregada regla `CRÍTICO: cada nodo en UN SOLO net, nunca repetido` al prompt → elimina warnings de nodos duplicados entre nets.

Dominios soportados:
- `irrigation` → ESP32, sensor humedad suelo, sensor nivel agua, relay bomba, RTC DS3231
- `domotics` → ESP32, relay, DHT22, PIR, LED estado
- `motor` → Arduino, L298N/DRV8825, caps bulk 470µF, diodos flyback
- `power_supply` → regulador, fuse, caps
- `display` → ESP32, OLED/LCD I2C, NeoPixel
- `sensor_hub` → ESP32, múltiples sensores I2C
- `iot` → ESP32, cap bulk WiFi, LED heartbeat
- `audio` → ESP32, amplificador I2S, buzzer

### 4.18 SchematicRenderer Mejorado (v4.1 / fix v4.5.0)
✅ **Layout funcional**: MCU al centro, entradas a la izquierda, salidas a la derecha, power en franja superior, comunicaciones arriba-derecha.
✅ **14 símbolos electrónicos precisos**: resistor (IEC rectangle), LED (triángulo con barra cátodo y flechas de luz), capacitor (placas paralelas con polarity), button (SPST con actuador), MCU (box con header cyan), relay (bobina + contacto), MOSFET-N (símbolo estándar con G/D/S), transistor NPN, diodo, motor (M en círculo), buzzer (con ondas sonoras), sensor genérico, display OLED/LCD, IC genérico.
✅ **Color-coding de nets**: VCC/power=rojo, GND=gris, I2C=verde, SPI=magenta, UART=naranja, PWM=naranja oscuro, datos=azul.
✅ **Routing ortogonal**: cables L-shaped (horizontal primero, luego vertical) con junction dots.
✅ **Title block**: nombre, descripción, MCU, power, dominio detectado, badges DRC y warnings.
✅ **Leyenda de nets** en esquina superior derecha con colores.
✅ **Grid de fondo** (dots 20px) como papel de esquemático.
✅ **Anotaciones DRC** inline (primeros 3 errores).
⚠️ Fix v4.5.0: SVG generado con `size=(1000, 700)` fijo → el browser lo mostraba centrado sobre fondo gris al abrir `/api/circuits/{id}/schematic.svg` directamente. Fix: `size=('100%', '100%')` con `viewBox="0 0 1000 700"` → SVG responsivo que llena toda la pantalla.

### 4.19 KiCad Export — .kicad_sch (v4.1)
✅ `tools/kicad_exporter.py` — genera archivos `.kicad_sch` válidos para KiCad 6/7/8.
✅ **Símbolos embebidos** (lib_symbols): Device:R, Device:C, Device:LED, Device:D, Device:SW_Push, Device:IC_Generic, power:VCC, power:GND.
✅ **Instancias de componentes** con Reference y Value correctos, UUIDs únicos.
✅ **Net labels** colocados en las posiciones de pin exactas (offsets definidos por símbolo). Conectividad eléctrica correcta sin necesidad de dibujar wires manuales.
✅ **Símbolos de power** (power:VCC, power:GND) auto-generados para nets de alimentación.
✅ **Title block** con nombre, fecha, descripción y fuente de alimentación.
✅ Placement en grid de 2.54mm (100mil). MCU centrado, pasivos en grilla adyacente.
✅ Endpoint: `GET /api/circuits/{id}/schematic.kicad_sch` — descarga directa.

### 4.30 MCU Pin Assignment Rules (v4.7.0)
✅ `MCU_PIN_RULES` dict en `circuit_agent.py` con restricciones exactas para 6 plataformas: Arduino Uno, Nano, Mega, Raspberry Pi Pico, ESP32, ESP8266.
✅ `_mcu_pin_rules(mcu: str) -> str` — resolución fuzzy (substring match) del MCU detectado al bloque de reglas correspondiente.
✅ `{mcu_pin_rules}` inyectado en `CIRCUIT_PARSE_PROMPT` — el LLM recibe las restricciones reales de pines antes de generar la netlist (PWM solo en D3/D5/D6/D9/D10/D11 en Uno, ADC seguro solo en GPIO32-39 con WiFi en ESP32, GPIO34/35/36/39 input-only, etc.).

### 4.31 SchematicRenderer — 15+ símbolos nuevos (v4.7.0)
✅ Dispatch dict expandido de ~25 a ~60 entradas: `capacitor_electrolytic`, `arduino_micro`, `raspberry_pi_pico`, `dc_motor`, `stepper`/`stepper_motor`, `servo`, `l298n`, `drv8825`/`a4988`/`tb6600`, `moisture_sensor`, `hc_sr04`/`ultrasonic`, `voltage_regulator`/`lm7805`/`ams1117`/`lm317`/`regulator`, `buck_converter`/`boost_converter`, `hc_05`/`hc05`/`nrf24l01`/`rf_module`/`lora`, `connector`/`header`/`pin_header`/`terminal_block`, `inductor`, `battery`/`battery_18650`/`lipo`.
✅ 12 nuevos métodos símbolo SVG: `_sym_l298n`, `_sym_stepper_driver`, `_sym_regulator`, `_sym_moisture`, `_sym_ultrasonic`, `_sym_connector`, `_sym_rf_module`, `_sym_converter`, `_sym_stepper`, `_sym_servo`, `_sym_inductor`, `_sym_battery`.

### 4.32 Electrical DRC — 3 checks nuevos (v4.7.0)
✅ Check 13 `SIGNAL_5V_ON_3V3_GPIO` — sensor 5V (HC-SR04, ECHO) directo en GPIO de ESP32/Pico sin divisor resistivo → `error`.
✅ Check 14 `MOTOR_DIRECT_TO_MCU` — motor DC/stepper en GPIO sin driver (L298N/DRV8825) → `error`.
✅ Check 15 `ESP_WIFI_NO_BULK_CAP` — ESP32/ESP8266 sin capacitor bulk ≥10µF en VCC → `warning`.
✅ Helper `_parse_cap_uf(value)` — parsea strings "100nF", "10µF", "1mF" a float µF para el check de bulk cap.

### 4.33 BOM Grouping + KiCad Footprints (v4.7.0)
✅ BOM agrupado: componentes idénticos (mismo tipo+valor para pasivos, mismo tipo+nombre para módulos) se consolidan en una línea con `qty_needed` y `refs` (lista de IDs).
✅ `_group_key(comp)` y `_resolve_footprint(comp)` en `bom_generator.py`.
✅ `_TYPE_TO_FOOTPRINT` dict (~50 entradas) mapea tipo de componente a footprint KiCad real (e.g. `"resistor"` → `"Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"`).
✅ `bom_to_csv()` actualizado: columnas `Refs`, `Footprint`, compatible backward con `ref` (singular).
✅ KiCad exporter (`kicad_exporter.py`) también usa `_TYPE_TO_FOOTPRINT` — rellena la propiedad `"Footprint"` en cada instancia de símbolo.

### 4.34 Firmware — Retry 2x + Error Parsing inteligente (v4.7.0)
✅ `_extract_compile_errors(raw_error, max_lines=25)` — filtra el ruido verbose de arduino-cli (líneas `Compiling/Linking/Building/Using/FQBN/Platform/Sketch uses/avrdude`) y retiene solo las líneas con diagnósticos reales (`error:`, `warning:`, `undefined reference`, `was not declared`, etc.).
✅ Loop de corrección LLM extendido a 2 intentos: intento 0 con `temperature=0.1`, intento 1 con `temperature=0.05` y nota explícita "el primer fix no funcionó".
✅ Auto-instalación de librerías faltantes (`install_missing_libraries()`) antes de los intentos LLM.

### 4.35 Firmware Snippet Library (v4.7.0)
✅ `COMPONENT_SNIPPETS` dict en `firmware_generator.py` con patrones de código validados para 18+ tipos: DHT22/DHT11, DS18B20, HC-SR04, BMP280, MPU6050, relay, servo, OLED, LCD, RTC/DS3231, moisture sensor, PIR, L298N, DRV8825/A4988, NeoPixel/WS2812, HX711, FC-28. Cada entrada tiene `includes`, `lib` (nombre para arduino-cli) y `snippet` con el código de uso real.
✅ `_SNIPPET_ALIASES` — mapea tipos resueltos internos al snippet key correspondiente.
✅ `get_firmware_snippets(components)` — escanea lista de componentes, colecta snippets relevantes, retorna bloque formateado con includes, hints de instalación y código de ejemplo.
✅ Inyectado automáticamente en el system prompt de `generate_firmware()` y `generate_firmware_for_circuit()` cuando se proveen componentes.

### 4.36 PCB Renderer — Mejoras visuales profesionales (v4.7.0)
✅ DRC error highlighting: componentes con errores DRC reciben borde rojo + SVG `<filter id="glow">` (feMorphology + feGaussianBlur + feComposite) + badge "!" rojo superpuesto.
✅ GND copper pour: rectángulos de cobre hachureados cerca de los pads GND (`fill="url(#hatch)"`).
✅ Via symbols en junctions de trazas: círculo gris con drill hole oscuro, hasta 40 vías por diseño.
✅ Pad rendering correcto: pads SMD rectangulares (`rx="0.2"`) para ICs/módulos grandes; pads THT circulares con drill hole interior negro para pasivos.
✅ Pin 1 chamfer: triángulo de polígono en la esquina superior-izquierda del footprint de ICs.
✅ Leyenda de capas en esquina superior-derecha: Top Copper / Bottom Copper / Vias con swatches de color.
✅ DRC summary strip al pie del board con conteo de errores y warnings.
✅ `stroke-linecap="round"` en todas las trazas de cobre.

### 4.37 Export ZIP Bundle (v4.7.0)
✅ `GET /api/circuits/{id}/export.zip` — descarga un ZIP completo del proyecto con:
  - `schematic.svg` — esquemático renderizado (listo para abrir en navegador)
  - `<name>.kicad_sch` — esquemático KiCad v6 (abrir en KiCad 6/7/8)
  - `bom.csv` — lista de materiales con cantidad y footprints
  - `netlist.json` — netlist completa en JSON
  - `pcb_layout.svg` — layout PCB con capas y pads
  - `gerber/<layer>.gbr` — archivos Gerber RS-274X para fabricación
  - `README.txt` — resumen del proyecto + resultados DRC

### 4.20 PCBRenderer Mejorado (v4.1)
✅ **Placement funcional**: MCU en centro, pasivos pequeños en cluster adyacente, módulos grandes en columna izquierda, varios en fila inferior.
✅ **Routing Manhattan 2-capas**: trazas de poder (1.2mm, bottom copper dorado) y señales (0.5mm, top copper amarillo).
✅ **14 footprints dimensionados**: resistor 6.5×2.5mm, capacitor 3×3mm, ESP32 18×25.4mm, Arduino Uno 68.6×53.4mm, relay 19×15.5mm, etc.
✅ **SVG mejorado**: fondo PCB verde oscuro #1a4a1a, trazas cobre coloreadas por capa, pads dorados con drill holes, courtyard amarillo, silkscreen con ref ID, info de fabricación al pie.
✅ **Gerber RS-274X completo** (8 archivos): copper_top.gtl, copper_bottom.gbl, silkscreen_top.gto, soldermask_top.gts, soldermask_bot.gbs, drills.xln (Excellon), outline.gko, README.txt.
✅ README.txt en el ZIP Gerber con dimensiones del board y lista de advertencias.

### 4.29 Circuit Viewer Profesional — 2D + 3D (v4.5.0)

#### Viewer 2D — Esquemático de alta calidad
✅ `renderSchematic()` reescrita como función `async`: fetch del SVG generado por el servidor (`/api/circuits/{id}/schematic.svg`) e inyectado directamente en el DOM — muestra los 14 símbolos eléctricos reales, grid de fondo, color-coding de nets, title block, badges DRC.
✅ **Pan/zoom interactivo** sobre el SVG del servidor via `_initSVGPanZoom()`:
  - Rueda del mouse → zoom (rango 0.15× – 10×)
  - Click + drag → paneo (viewBox manipulation, sin pérdida de calidad)
  - Doble clic → reset a vista completa
✅ **Fallback client-side** (`_renderSchematicFallback()`) para circuitos sin ID (nuevos no guardados) — renderer SVG nativo corregido, con colores por tipo de componente y drag & drop funcionando.
⚠️ Fix root cause: el renderer anterior hacía `SVG().addTo('#' + container.id)` con `container.id = ''` (vacío) → SVG.js buscaba el selector `#` (inválido) → `draw` undefined → todo el render fallaba silenciosamente → pantalla en blanco.

#### Viewer 3D — Breadboard/PCB Three.js
✅ **Three.js OrbitControls** (`r128`) agregado vía CDN: rotación, zoom (scroll), pan (botón derecho). `dampingFactor=0.06` para movimiento suave.
✅ **PCB verde profesional** con borde dorado (EdgesGeometry) — reemplaza el breadboard beige que rotaba solo.
✅ **Componentes tipados con colores reales**: ESP32 azul oscuro, relay naranja, capacitor celeste, diodo negro, sensor verde, display azul marino, motor driver azul índigo, etc. Tamaños proporcionales al footprint real (ESP32: 32×4×22mm, Arduino Uno: 44×4×32mm).
✅ **Cables con arco elevado** entre nodos de cada net — colores distintos por red (rojo=VCC, verde=GND, azul=señal, etc.).
✅ **Labels sprite** flotantes sobre cada componente (canvas texture → THREE.Sprite), texto ID del componente en cyan sobre fondo semitransparente.
✅ **Iluminación mejorada**: AmbientLight 2.5, DirectionalLight 1.8 con sombras, HemisphereLight para fill desde abajo.
✅ **Grid helper** oscuro (300 unidades, 30 divisiones) como referencia de profundidad.
✅ `_resetThreeJS()` — limpia la escena completa al cargar un nuevo circuito (evita duplicación de objetos entre circuitos).
⚠️ Fix: la animación original hacía `threeScene.children[2].rotation.y += 0.005` → crash si había menos de 3 hijos. Eliminado — el movimiento ahora es solo via OrbitControls.

### 4.28 Verificación total y hardening (v4.4.1)
Verificación exhaustiva del proyecto detectó y corrigió 5 issues:

**CRÍTICO — `tools/circuit_importer.py`**
✅ `parse_expr()` no validaba bounds antes de acceder a `tokens[pos[0]]` → `IndexError` con archivos `.kicad_sch` malformados (paréntesis sin cerrar, archivo truncado).
Fix: validación `pos[0] >= len(tokens)` con `ValueError` descriptivo; loop `while` con guard `pos[0] < len(tokens)`.

**ADVERTENCIA — `database/circuit_design.py`**
✅ `component_library.json` se cargaba en tiempo de importación sin manejo de errores → `FileNotFoundError` o `JSONDecodeError` crasheaba todo el servidor al arrancar.
Fix: `try/except (FileNotFoundError, JSONDecodeError)` con fallback `{"components": {}, "aliases": {}}`.

**ADVERTENCIA — `api/routers/circuits.py`**
✅ `PUT /{circuit_id}` llamaba `save_version()` sin verificar el retorno → si la DB fallaba, los cambios se aplicaban sin versión de respaldo.
Fix: `if ver < 0: raise HTTPException(500)` antes de aplicar los cambios.

**INFO — `api/static/circuit_viewer.html`**
✅ Patch de `renderSchematic` sin guard de existencia → fallo silencioso si la función se carga en diferente orden en el futuro.
Fix: `console.error()` explícito si `typeof renderSchematic === 'undefined'`.

**INFO — `.env.example`**
✅ `MULTI_USER` sin comentario → comportamiento no documentado para nuevos deployments.
Fix: comentario explicando `false` (single-user, sin login) vs `true` (JWT obligatorio).

**Resultado:** 56/56 tests siguen pasando tras todos los fixes. Todos los routers de `server.py` existen con atributos correctos. Sin conflictos de rutas FastAPI. Todos los JS referenciados en HTML existen.

### 4.25 Multi-usuario real (v4.4)
✅ `update_owner(design_id, user_id)` en `CircuitDesignManager` — asigna user_id post-parse.
✅ `/parse` y `/import` endpoints reciben `user_id` de JWT y llaman `update_owner()` / `save_design(user_id)`.
✅ `GET /api/circuits/` — lista circuitos filtrados por el usuario autenticado (user_id del JWT).
✅ `list_designs(user_id)` ya filtraba por user_id — ahora se usa correctamente desde los endpoints.
✅ Auth frontend (`auth.js`) ya guardaba JWT en localStorage y lo inyectaba en todas las requests autenticadas.

### 4.26 Editor Visual de Circuitos (v4.4 / actualizado v4.5.0)
✅ `update_circuit(design_id, components, nets, name, description)` en `CircuitDesignManager`.
✅ `PUT /api/circuits/{id}` — actualiza componentes/nets; auto-guarda versión "pre-edit" antes de aplicar cambios.
✅ Toolbar del viewer: botón **+ Agregar** (modal con 13 tipos de componentes), **✕ Eliminar {id}** (aparece al seleccionar), **💾 Guardar** (aparece cuando hay cambios).
✅ Modal de agregar: ID, Tipo (select), Nombre, Valor — valida ID único antes de agregar.
✅ `beforeunload` avisa si hay cambios sin guardar.
✅ `_viewerFetch()` helper — usa JWT de localStorage para autenticar requests del viewer.
⚠️ v4.5.0: click-to-select migrado de elementos SVG (ya no existen en la vista server-side) a los items de la lista de componentes del sidebar. Cada item tiene `data-comp-id` y llama `_selectComponent()` al hacer clic. `_wireEditorClicksOnList()` se llama al final de `renderComponentsList()`.

### 4.27 Tests Automatizados pytest (v4.4)
✅ `tests/conftest.py` — fixtures `sample_circuit`, `tmp_db` (DB SQLite temporal via monkeypatch), `mgr` (CircuitDesignManager aislado).
✅ `tests/test_circuit_importer.py` — 18 tests: KiCad S-expression (title, componentes, nets, power symbols excluidos, error en contenido inválido), Eagle XML (componentes, valores, nets con nodos, inferencia de tipo), dispatcher (extensión .kicad_sch/.sch/unsupported, KiCad5 legacy error).
✅ `tests/test_versioning_sharing.py` — 22 tests: versioning (save, increment, unknown circuit, list, fields, reason, snapshot, restore, auto-backup, diff con added), sharing (create, idempotent, get by token, invalid token, revoke, revoke+recreate), update_circuit (componentes, nombre, nonexistent, update_owner con user isolation).
✅ `tests/test_firmware_prompts.py` — 16 tests: todos los platforms tienen watchdog/OTA/STATE/error handling; `_clean_code()` elimina backticks y preserva código.
✅ **56/56 tests pasaron en 1.39s** — sin mocks de LLM, sin llamadas de red, tests de unidad puros.

### 4.21 Import Eagle/KiCad (v4.3)
✅ `tools/circuit_importer.py` — importa `.kicad_sch` (KiCad 6/7/8 S-expression) y `.sch` (Eagle XML).
✅ Parser S-expression recursivo propio (sin dependencias externas).
✅ Parser Eagle XML con ElementTree: extrae `<part>` → componentes, `<net>/<pinref>` → nets con nodos reales.
✅ Auto-detecta formato por extensión y contenido del archivo.
✅ Endpoint: `POST /api/circuits/import` (multipart/form-data, archivo .kicad_sch o .sch).
✅ Guarda el circuito importado en DB + crea versión inicial "import" automáticamente.

### 4.22 Versioning de Circuitos (v4.3)
✅ Tabla `circuit_versions` ya existía — ahora completamente implementada.
✅ `save_version(circuit_id, reason)` — snapshot JSON del circuito completo con razón del cambio.
✅ `get_versions(circuit_id)` — lista de versiones con diff (componentes agregados/removidos entre versiones).
✅ `get_version_snapshot(circuit_id, version)` — snapshot completo de una versión.
✅ `restore_to_version(circuit_id, version)` — guarda versión actual primero, luego restaura.
✅ Endpoints:
  - `GET /api/circuits/{id}/versions` — lista con diff summary
  - `GET /api/circuits/{id}/versions/{ver}` — snapshot de versión
  - `POST /api/circuits/{id}/versions/save?reason=...` — snapshot manual
  - `POST /api/circuits/{id}/restore/{ver}` — restaurar (auto-backup primero)

### 4.23 Share via link público (v4.3)
✅ Tabla `circuit_shares (token, circuit_id)` — token `secrets.token_urlsafe(16)`, idempotente.
✅ `POST /api/circuits/{id}/share` → `{token, url, viewer_url}` — genera link público.
✅ `DELETE /api/circuits/{id}/share` → revoca el token.
✅ `GET /api/circuits/shared/{token}` — datos del circuito (no requiere auth).
✅ `GET /api/circuits/shared/{token}/viewer` — viewer HTML de solo-lectura (no requiere auth).
✅ Router público `_public_router` separado del router autenticado para que los endpoints compartidos no requieran JWT.

### 4.24 Firmware Production-Ready (v4.3)
✅ **Watchdog timer** en todos los platforms: AVR (`avr/wdt.h`), ESP32 (`esp_task_wdt`), ESP8266 (`ESP.wdtEnable`), MicroPython (`machine.WDT`).
✅ **OTA Update** (ArduinoOTA) generado automáticamente en ESP32/ESP8266 cuando el circuito tiene WiFi.
✅ **STATE serial reporting**: loop() emite `STATE:{...}` JSON con valores de pines/sensores/actuadores — compatible con el live hardware visualizer (/ws/hardware-state).
✅ **Error handling**: validación de rangos en lecturas de sensores, retry en inicializaciones I2C, fallback values.
✅ Prompts actualizados en todos los platforms (arduino:avr, esp32:esp32, esp8266:esp8266, micropython).

### 4.16 Wokwi Simulate (v4.0)
✅ `GET /api/hardware/wokwi/{device_name}` — genera `diagram.json` del circuito guardado para el dispositivo.
✅ Usa `tools/wokwi_simulator.py` existente + `hardware_memory.get_circuit_context()`.
✅ Retorna `{url, diagram_json, has_circuit, device}`.

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

## 11. PERFORMANCE — v4.6.0 (2026-04-22)

### Análisis aplicado: 11 fixes en 6 commits

#### 🔴 Alto impacto (resueltos)

**Fix 1 — Streaming char-by-char → bloque único (`agent_controller.py`)**
- Rutas `hw_md` y `hw_result` enviaban 500+ `await on_token(char)` individuales.
- Reemplazado por un único `await on_token(text)`. El cliente recibe el mismo JSON, sin overhead de 500 round-trips.

**Fix 2 + 8 — Conexión SQLite persistente + WAL (`sql_memory.py`, `circuit_design.py`)**
- Ambas clases abrían una conexión nueva por operación (~5ms de overhead × 5 ops/mensaje).
- Ahora: conexión persistente (`check_same_thread=False`) + `threading.RLock()` + `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`.
- `_get_connection()` / `_get_conn()` son `@contextmanager` que ceden la conexión bajo lock — callers sin cambios.
- `.gitignore`: `memory.db-wal` / `memory.db-shm` agregados.
- Tests: 0.79s → 0.41s (−48% de tiempo en test suite).

**Fix 3 — Dirty flag facts/graph (`sql_memory.py`, `graph_memory.py`, `websockets.py`, `chat.js`)**
- `get_all_facts()` y `graph_memory.stats()` se ejecutaban tras cada mensaje aunque nada había cambiado.
- Solución: contadores de mutación `_facts_seq` (incrementa en `store_fact`/`delete_fact`) y `_seq` (incrementa en `add_relation`). El handler WS compara antes de llamarlos.
- `done` payload omite `facts`/`graph` cuando no cambiaron; el cliente conserva los últimos.
- `chat.js`: tolera `facts`/`graph` ausentes en `done`.

**Fix 4 — `call_llm_async` directo en `agent_controller.py`**
- El fallback no-streaming usaba `asyncio.to_thread(_call_llm, messages)` — spawn de thread + `requests.post` bloqueante.
- Reemplazado por `await call_llm_async(messages=..., agent_id=..., agent_name=...)` — httpx async con connection pool compartido, sin thread extra.

#### 🟡 Impacto medio (resueltos)

**Fix 5 — Cache LRU del SVG schematic (`api/routers/circuits.py`)**
- `SchematicRenderer().render_schematic_svg(circuit_data)` se recalculaba desde cero en cada request.
- Agregado: `OrderedDict` LRU de 20 entradas, TTL 10 min, key = `(circuit_id, updated_at)`. Invalidación automática cuando el circuito cambia.

**Fix 6 — Título de sesión en background (`websockets.py`, `chat.js`)**
- La generación del título LLM bloqueaba el `done` 2-4s extra.
- Ahora: `done` se envía inmediato con fallback `user_input[:60]` guardado en DB. El título LLM llega como evento `session_title` separado vía `asyncio.create_task(_generate_title_async(...))`.
- `chat.js`: nuevo handler para `data.type === 'session_title'` que actualiza el texto del sidebar.

**Fix 7 — GZipMiddleware (`api/server.py`)**
- No había compresión HTTP. JSON y SVGs viajaban sin comprimir.
- `app.add_middleware(GZipMiddleware, minimum_size=1000)` — una línea, aplica solo a respuestas HTTP (no WebSocket).

**Fix 8** — ver Fix 2.

#### 🟢 Bajo impacto (resueltos)

**Fix 9 — Fast-path hash exacto en `llm/cache.py`**
- `SemanticCache.get()` computaba embedding MiniLM + cosine similarity en cada llamada aunque existiera un hit exacto.
- Agregado fast-path: MD5 del `key_text` se calcula antes de `_embed()`. Si hay entry con mismo hash, model y TTL vigente → retorna directo, sin llamar MiniLM.

**Fix 10 — `asyncio.get_event_loop()` deprecado**
- 5 ocurrencias: `api/server.py`, `api/routers/websockets.py`, `api/routers/hardware_state.py`, `api/routers/hardware_bridge.py` (×2).
- Reemplazados por `asyncio.get_running_loop()` en contextos async; `time.monotonic()` para rate-limit clock; `call_bridge_sync` simplificado para no depender de `get_event_loop()`.

**Fix 11 — `requests` → `httpx` en 10 archivos de producción**
- `import requests` / `requests.post` / `requests.get` reemplazados por `httpx` drop-in en:
  `memory/session_summarizer.py`, `llm/openrouter_client.py`,
  `agent/agents/hardware_{agent,design,diff,firmware}.py`,
  `agent/agents/{research,vision}_agent.py`,
  `tools/{datasheet_fetcher,firmware_generator}.py`.
- `datasheet_fetcher`: agregado `follow_redirects=True` (httpx es strict por defecto).
- `eval/test_e2e_api.py`, `guide-test.py`, `GUIDE.md` sin tocar (scripts externos).
- Producción sin dependencia directa en `requests`.

### Stack técnico actualizado
- SQLite: **WAL mode** + conexión persistente (sin overhead de open/close).
- HTTP interno: **httpx** exclusivamente (requests eliminado de producción).
- WebSocket `done`: **liviano** (facts/graph solo cuando cambian, título en background).
- Compresión: **GZip** en respuestas HTTP ≥1000B.
- SemanticCache: **fast-path MD5** antes de MiniLM.
- SVG schematic: **LRU cache** 20 entradas / 10min.

### Commits de la sesión
```
66ff10f  perf: fix 11 — requests → httpx en 10 archivos de producción
0017aa7  perf: fix 10 — asyncio.get_event_loop() (deprecado)
3280f8a  perf: ronda 4 — cache SVG schematic + fast-path hash llm cache
450f45c  perf: ronda 3 — call_llm async directo en agent_controller
ed31a91  perf: ronda 2 — conexión SQLite persistente + WAL
3fd3e67  perf: ronda 1 — 4 fixes de performance
```

---

## 12. PENDIENTE TÉCNICO

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
| v4.0.0  | 2026-04-20  | Platform context persistente (C++ por default); firmware iterativo con diff coloreado (_DiffMixin, intent "modify"); datasheet auto-fetch + indexado KB en background; export ZIP sesión (chat.md + firmware.cpp + decisiones.md); error patterns en vector memory; Wokwi endpoint diagram.json; voice auto-send pipeline |
| v4.1.0  | 2026-04-20  | CircuitAgent domain-aware (8 dominios, MCU auto-select, hints por dominio, flyback auto-add); SchematicRenderer refactor (14 símbolos, layout funcional, routing ortogonal, color-coding, title block); KiCad exporter nuevo (kicad_exporter.py, símbolos embebidos, net labels, power symbols, endpoint GET /schematic.kicad_sch); PCBRenderer mejorado (placement funcional, routing 2-capas, 14 footprints, Gerber RS-274X 8 archivos + README) |
| v4.7.0  | 2026-04-22  | Auditoría Semanas 1-3: MCU pin rules (6 plataformas), 15+ símbolos SVG nuevos, 3 DRC checks nuevos (5V→3V3/motor sin driver/ESP bulk cap), BOM agrupado+footprints KiCad, firmware retry 2x+error parsing inteligente, snippet library 18+ componentes, PCB renderer profesional (DRC highlight/copper pour/vias/pads/leyenda), export ZIP bundle (/export.zip). Tests: 56/56. |
| v4.6.0  | 2026-04-22  | Performance: 11 fixes aplicados — SQLite persistente + WAL, dirty flag facts/graph, streaming en bloque, call_llm_async directo, SVG LRU cache, título en background, GZipMiddleware, fast-path hash SemanticCache, asyncio.get_event_loop() → get_running_loop(), requests → httpx (10 archivos). Tests: 56/56. |
| v4.5.0  | 2026-04-21  | Fix domain_hint nunca pasado al prompt (circuito riego sin sensor humedad); regla anti-nodos-duplicados en CIRCUIT_PARSE_PROMPT; SVG responsivo 100%×100% (ya no se ve centrado en gris); Viewer 2D reescrito: fetch SVG servidor + pan/zoom (rueda, drag, doble-clic reset) + fallback client-side corregido (root cause: container.id vacío → SVG.js fallaba silenciosamente); Viewer 3D: OrbitControls r128, PCB verde con borde dorado, componentes tipados por tipo (14 estilos), cables con arco entre nets, sprite labels, iluminación 3 capas, _resetThreeJS(); Editor: click-to-select migrado al sidebar (compatible con server SVG) |
| v4.4.1  | 2026-04-21  | Verificación total: fix CRÍTICO IndexError parser S-expression (circuit_importer.py — validación bounds + paréntesis sin cerrar); fix ADVERTENCIA component_library.json sin try/except (fallback a dicts vacíos); fix ADVERTENCIA PUT /{id} no chequeaba save_version() retorno; fix INFO guard renderSchematic en viewer; fix INFO MULTI_USER documentado en .env.example. 56/56 tests siguen pasando. |
| v4.4.0  | 2026-04-21  | Multi-usuario real (user_id wired en parse/import, GET /circuits/ por usuario, update_owner); Editor visual de circuitos (+ Agregar componente modal, ✕ Eliminar con confirmación, 💾 Guardar → PUT /circuits/{id} con auto-versión, beforeunload dirty-check); Tests pytest 56/56 (test_circuit_importer, test_versioning_sharing, test_firmware_prompts, conftest con fixtures tmp_db) |
| v4.2.0  | 2026-04-21  | Chat→Circuit inline (orchestrator circuit_design intent + card embebida en chat con preview SVG + KiCad/BOM/Gerber/3D links); Live Hardware State visualizer (WebSocket /ws/hardware-state + serial STATE:{} + live_circuit.js overlay en SVG viewer) |
| v4.3.0  | 2026-04-21  | Import Eagle/KiCad (POST /circuits/import, parser S-expr + Eagle XML); Versioning (save/list/restore versiones con diff); Share via link público (token URL-safe, router sin auth); Firmware production-ready (watchdog, OTA ESP32/8266, STATE serial, error handling en todos los platforms) |
| v4.0.1  | 2026-04-20  | Fix crítico intent "modify": (1) "modify" faltaba en tupla de intents válidos en `_classify_intent()` → LLM respondía "modify" pero caía al fallback; (2) MODIFY_KEYWORDS se chequeaba después de DESIGN_KEYWORDS en `_classify_by_keywords()` → "hacelo más rápido" matcheaba design. Ahora el firmware diff se dispara correctamente. |
