# STRATUM — Contexto del Proyecto
> Última actualización: 2026-05-07
> Versión actual: **v4.29.0** (EDA pipeline refactor — Fases 1-3: IR + Registry + Constraint Engine 2026-05-07)
> Tagline: _"Tu memoria técnica siempre disponible"_
> Estado: **Production-ready** (local + Railway)
>
> Nota: el changelog de abajo refleja v4.23.0, v4.27.0, v4.28.0 y v4.29.0; las versiones intermedias (v4.24/4.25/4.26) están documentadas en la memoria del proyecto pero aún no migradas aquí.

> **2026-05-07 — v4.29.0 EDA refactor estructural (Fases 1-3 de 10):** primer tramo del refactor pedido en `instruc.txt` — eliminar el enfoque de fixes locales y migrar a una arquitectura EDA determinista LLM → IR → Validation → Constraints → Pin Alloc → Placement → Routing → Renderer → Exporters. **Fase 1 — Circuit IR** (`tools/eda/ir/`): pydantic v2, modelos `Circuit / Component / Pin / Net / Node / Trace / Via / Board / DesignRules / Constraint / ValidationIssue / CircuitMetadata / PlacementInfo / Footprint / Symbol`, enums `ElectricalType / Side / Layer / Severity`, `Vec2` frozen. Validación estructural (refs únicos, nodos→componentes existen, no duplicados de pin/net), roundtrip JSON limpio (`to_json` / `from_json`), `extra="forbid"` en todos los modelos. **Fase 2 — Component Registry** (`tools/eda/component_registry/`): YAML como fuente única de verdad. Schema pydantic (`ComponentSpec / PinSpec / MCUSpec / BusPins / VoltageSpec / WiringRequirement`) + `Registry` con lookup exacto por `type` y por alias case-insensitive + singleton lru_cached (`get_registry()`). 17 archivos YAML cubren: 6 MCUs (esp32, arduino_uno/nano/mega, esp8266, raspberry_pi_pico, stm32 con `forbidden_pins / input_only_pins / boot_strapping_pins / adc_pins / pwm_pins / preferred_buses` + pinout completo), 7 sensores (dht11/22, bmp280, hc_sr04, mpu6050, fc28, ds18b20), 3 power (lm7805, lm317, ams1117), l298n, relay_module, oled_ssd1306, ds3231, 5 pasivos (resistor, capacitor, capacitor_electrolytic, led, diode), fuse, screw_terminal. Cubre los tipos referenciados por DRC y la mayoría de `_TYPE_TO_FOOTPRINT` críticos. **Fase 3 — Constraint Engine** (`tools/eda/constraint_engine.py` + `rules.py`): engine declarativo con `ValidationContext` (snapshot indexado: `comp_by_ref / spec_by_ref / refs_in_net / nets_of_ref / refs_by_category` — todo O(1) para reglas), `ConstraintRule` + `RuleRegistry` con decorator `@rule_registry.register("CODE")`, `validate(circuit, rules=None)` y `run_drc(circuit)` (API compat con `tools/electrical_drc.py` legacy — devuelve dict). 19 reglas registradas: las 18 de `electrical_drc.py` migradas (NO_POWER_NET, SHORT_CIRCUIT, LED_WITHOUT_RESISTOR, ISOLATED_COMPONENT, DUPLICATE_NET_NODE, NO_DECOUPLING_CAP, NO_I2C_PULLUP, NO_ONEWIRE_PULLUP, HIGH_CURRENT_NO_FUSE, VOLTAGE_MISMATCH, MISSING_RESET_CAP, OVERCURRENT_PIN, SIGNAL_5V_ON_3V3_GPIO, MOTOR_DIRECT_TO_MCU, ESP_WIFI_NO_BULK_CAP, MCU_MISSING_POWER, RELAY_FLYBACK, AC_CONNECTOR_NO_FUSE) + 3 que reemplazan `mcu_pinout_validator.py` consumiendo el registry (`PIN_INVALID / PIN_FORBIDDEN / PIN_INPUT_ONLY_MISUSE`). **Tests**: +68 nuevos pasando (`test_eda_ir.py` 20, `test_eda_component_registry.py` 18, `test_eda_constraint_engine.py` 30). Suite full: **188 passed**, 3 fail / 21 errors (los pre-existentes de `electrical_formulas` y `versioning_sharing` — cero regresión sobre baseline 120). **Compat**: `tools/electrical_drc.py` y `tools/mcu_pinout_validator.py` no se tocaron — siguen importándose desde `circuit_agent.py` igual. La migración a usar el nuevo engine ocurre cuando los renderers/exporters consuman IR (Fases 7-10). **Decisiones**: pydantic v2 (no dataclasses) por validación gratis + JSON schema export; YAML (no JSON) por legibilidad de 50+ componentes; match exacto en `Registry.get` (no substring) — alias laxos como "c"/"r" matcheaban cualquier string; `extra="forbid"` en todo schema para detectar typos en YAML al startup. **Deps**: `requirements.txt` + `pydantic>=2.6,<3.0` + `PyYAML>=6.0,<7.0`. **Próximos pasos**: Fase 4 Pin Allocator (consume registry + IR para asignar GPIOs deterministas), Fase 5 Placement Engine, Fase 6 Routing Engine.

> **2026-05-06 — v4.28.0 EDA renderer overhaul:** schematic con hoja A4 ISO 7200 (frame + zone refs A-D / 1-8 + title block esquina inf-der), layout zonal proporcional al área útil, Manhattan-tree wire routing + collision-aware net labels. PCB con footprints reales por familia (MCU module / sensor / relay / TO-220 / TO-92 / axial / radial / generic), side panel off-board (PCB INFO + DRC + legend + stats), `_board_size` sumando anchos reales de zonas (fix overflow OLED). 3D viewer reemplaza breadboard por PCB FR4 verde con edge.cuts dorado + 4 mounting holes M3 + silkscreen STRATUM PCB + fiducials. Tests EDA 55/55, baseline 120 passing.

> **2026-05-06 — Maintenance:** dead code purge (`agent/keywords/circuit_keywords.py` + `tests/test_keywords.py`) + sync doc/repo (~15 discrepancias). Tests: 144 collected / 120 passing. Commits: `chore: remove dead circuit_keywords module` + `docs: sync CONTEXT-PROJECT.md with repo state`.

> **2026-05-06 — fix(agent) `62dd390` (pusheado):** `agent/session_store.py` (nuevo) reemplaza el singleton global `AgentState` por cache per-session con LRU+TTL+hidratación SQL. Resuelve bug estructural donde `conversation_history` y `active_circuit` se mezclaban entre chats simultáneos / pestañas / clientes WS concurrentes. `AgentController.state` se vuelve `@property` que resuelve vía `ContextVar` (cero churn en los 17 callsites). Bonus en el mismo commit: MCU footer SVG (`circuit_agent.py` propaga `_mcu`→`selected_mcu`), AsyncLLM transport recovery (`llm/async_client.py` retry-on-RuntimeError cuando TCPTransport queda cerrado pese a `is_closed=False`), chat UX (lista de componentes 12→25, nets 8→15), CTA opt-in para firmware cuando se detecta intent de control en el prompt. Tests: 120 passing (idéntico al baseline), cero regresión.

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
│   ├── agent_controller.py         # Recibe input, orquesta. `state` es @property que resuelve vía ContextVar a SessionStore
│   ├── agent_runner.py             # Loop de tool calling
│   ├── agent_state.py              # Estructura del estado por sesión (history, active_circuit, facts, platform, firmware_draft)
│   ├── session_store.py            # Cache per-session de AgentState (LRU=100, TTL=1800s, hidrata desde SQL en miss)
│   ├── orchestrator.py             # Routing keyword-first → LLM fast fallback
│   ├── user_profiler.py            # Perfil del usuario (heurísticas, sin LLM)
│   │
│   ├── agents/                     # Agentes especializados
│   │   ├── base_agent.py
│   │   ├── hardware_agent.py       # Facade (~122 líneas) — delega a mixins
│   │   ├── hardware_design.py      # Mixin: parse_circuit, save_circuit (~224 líneas)
│   │   ├── hardware_diff.py        # Mixin: _DiffMixin para firmware iterativo con diff
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
│   ├── proactive_consolidator.py   # Consolidación nocturna de memorias (~92 líneas)
│   ├── quality_estimator.py        # Estimación de calidad de respuesta (lazy import desde websockets)
│   └── session_continuity.py       # Continuidad de sesión entre reconexiones WS
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
│   │   ├── hardware_state.py       # /api/hardware/state/** (Live Hardware State Visualizer)
│   │   ├── knowledge.py            # /api/knowledge/**
│   │   ├── circuits.py             # /api/circuits/** (parse, schematic, breadboard, pcb, gerber)
│   │   ├── schematics.py           # /api/schematics/** (import, supported, list)
│   │   ├── calc.py                 # /api/calc/** (ElectricalCalcAgent)
│   │   ├── intelligence.py         # /api/intelligence/** (perfiles + fuentes, 9 endpoints)
│   │   ├── stock.py                # /api/stock/**
│   │   ├── decisions.py            # /api/decisions/**
│   │   ├── push.py                 # POST/DELETE /api/push/register
│   │   ├── projects.py             # /api/projects/** (project library)
│   │   └── websockets.py           # /ws/chat · /ws/signal · /ws/proactive
│   │
│   └── static/
│       ├── index.html              # Frontend principal Cyberpunk (~1136 líneas)
│       ├── styles.css              # Estilos separados (~593 líneas)
│       ├── app.js                  # Globals + init + navegación (~390 líneas, refactorizado)
│       ├── circuit_viewer.html     # Visualizador con drag & drop
│       ├── graph3d.html
│       └── modules/                # 16 módulos JS (plain <script>, no ES-modules)
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
│           ├── proactive.js        # connectProactiveWS, showProactiveNotification (~40 líneas)
│           ├── live_circuit.js     # Live Hardware State Visualizer (v4.2.0)
│           └── projects.js         # Project library UI
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
│   ├── fact_extractor.py           # Extracción de hechos (reemplaza memory_filter.py)
│   ├── short_memory.py             # deque(maxlen=MAX_SHORT_MEMORY) — O(1) add/pop
│   ├── memory_consolidator.py      # Fusión nocturna de memorias antiguas
│   └── pdf_memory.py
│
├── llm/
│   ├── async_client.py             # call_llm_text/async/stream — aceptan model= param, agent_id, use_cache
│   ├── openrouter_client.py        # Cliente sync + streaming
│   └── cache.py                    # Caché LLM
│
├── tools/
│   ├── electrical_formulas.py      # Re-export module (~79 líneas) + FORMULA_REGISTRY (25 fórmulas) — helpers privados no re-exportados
│   ├── formulas_basic.py           # helpers + ohms_law, resistor_* (~146 líneas)
│   ├── formulas_rc.py              # capacitor_*, rc_time_constant, low/high_pass_rc, lc_filter (~83 líneas)
│   ├── formulas_power.py           # power_dissipation, heat_sink, efficiency, fuse_rating (~67 líneas)
│   ├── formulas_converters.py      # buck, boost, transformer_turns_ratio (~99 líneas)
│   ├── formulas_opamp.py           # inverting_amp, non_inverting_amp, voltage_follower (~31 líneas)
│   ├── formulas_drives.py          # battery_autonomy, charge_time, motor_*, vfd (~95 líneas)
│   ├── electrical_drc.py           # DRC de circuitos (design rule check)
│   ├── schematic_parser.py         # KiCad v6, KiCad v5, LTspice, Eagle (~584 líneas)
│   ├── schematic_renderer.py       # Facade — re-exporta SchematicRenderer desde tools/eda/symbol_draw
│   ├── breadboard_renderer.py
│   ├── pcb_renderer.py             # Facade — re-exporta PCBRenderer + 4 helpers desde tools/eda/pcb_draw
│   ├── eda/                        # Renderer interno separado en 4 responsabilidades (v4.27.0)
│   │   ├── classifier.py           # classify_zone() — 6 zonas: ac/mcu/sensor/relay/output/other
│   │   ├── layout.py               # compute_schematic_layout, build_relay_groups, validate_positions
│   │   ├── router.py               # route_orthogonal (sch), route_traces + trace_color (PCB)
│   │   ├── symbol_draw.py          # SchematicRenderer (clase + ~50 _sym_* + drawing helpers)
│   │   └── pcb_draw.py             # PCBRenderer + _FOOTPRINT, _fp, _place_components, _board_size
│   ├── bom_generator.py
│   ├── circuit_synthesizer.py      # Síntesis de circuitos (~48 KB) — usa component_pinouts + component_types
│   ├── circuit_importer.py         # Import KiCad/Eagle (S-expr v5/v6, XML)
│   ├── component_pinouts.py        # Pinouts de componentes (~27 KB) — usado por circuit_agent
│   ├── component_types.py          # Tipos/categorías de componentes — usado por eda/* y synthesizer
│   ├── design_rules.py             # Reglas de diseño compartidas — usado por eda/symbol_draw, pcb_draw, layout
│   ├── firmware_generator.py       # LLM_MODEL_SMART, soporta micropython
│   ├── firmware_flasher.py         # arduino-cli + flash_micropython() via mpremote
│   ├── firmware_validator.py       # Validación de firmware generado (~14 KB)
│   ├── file_tools.py               # Helpers de archivo registrados en tool_registry
│   ├── datasheet_fetcher.py        # Auto-fetch datasheets (Alldatasheet/Mouser) — usado por agent_controller
│   ├── kicad_exporter.py           # Export .kicad_sch (símbolos custom + pre-pass)
│   ├── kicad_pcb_exporter.py       # Export .kicad_pcb (footprints SMD/THT)
│   ├── kicad_sym_parser.py         # Parser de símbolos .kicad_sym
│   ├── kicad_sym_renderer.py       # Render desde .kicad_sym (usado por eda/symbol_draw)
│   ├── kicad_symbols/              # Biblioteca de símbolos KiCad
│   ├── mcu_pinout_validator.py     # Validador de pinouts MCU (~5 KB) — circuit_agent ×3 lazy imports
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
│       ├── example_plugin.py       # + example_plugin.json (manifiesto)
│       └── homeassistant_plugin.py # + homeassistant_plugin.json (manifiesto)
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
│   └── knowledge_base.py           # Carga y chunking de documentos (consolidado)
│
├── infrastructure/
│   ├── vector_store.py             # Singleton Qdrant — server si QDRANT_URL, path local si no
│   └── embeddings.py               # MiniLM — carga local_files_only=True, fallback descarga
│
├── data/                           # Datos persistentes (montados en Railway como volumen)
│   └── component_library.json
│
├── knowledge_feed/                 # KB técnica indexada al startup (ver §9)
│   ├── 00_INSTRUCCIONES_USO.txt
│   ├── 01_electronica_analogica.txt
│   ├── 02_microcontroladores.txt
│   ├── 03_electronica_potencia.txt
│   ├── 04_plc_automatizacion.txt
│   ├── 05_sensores_protocolos.txt
│   ├── 06_instalaciones_electricas.txt
│   └── 07_formulas_calculos.txt
│
├── docs/                           # Documentación adicional del proyecto
├── imagen/                         # Recursos gráficos
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

Helpers internos en `formulas_basic` (privados, no re-exportados): `_E24`, `_FUSE_STD`, `_nearest_e24()`, `_nearest_fuse()`, `_result()`

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
✅ `/ws/chat?session=<uuid>`: cada conexión propaga `session_id` al `AgentController` (vía `ContextVar`). `SessionStore` (`agent/session_store.py`, commit `62dd390`) provee un `AgentState` aislado por sesión, hidratado lazy desde SQL en el primer turno (últimos 20 mensajes + facts del usuario). LRU=100 sesiones / TTL=1800s idle. Esto evita el bug previo donde `conversation_history` y `active_circuit` se mezclaban entre chats simultáneos. Título generado por IA (LLM, 5 palabras) tras el primer intercambio. Reconexión con backoff exponencial (2s → 4s → … → 8s).

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

### 4.39 3D Viewer Lighting + Schematic Dispatch Fix (v4.9.0)
✅ **3D Viewer — iluminación y cámara**:
  - `AmbientLight` reducido de 2.5 → 0.55: componentes ahora muestran sombras y profundidad real.
  - Cámara movida a `(0, 55, 170)` mirando `(0, 8, 0)` — ángulo oblicuo en vez de cenital, revela altura de componentes.
  - `PCFSoftShadowMap` + `shadow.mapSize` 2048×2048 — sombras suaves de alta resolución.
  - Fill light añadido `(−80, 40, −60)` — ilumina cara trasera de componentes para evitar áreas negras.
  - Fondo del renderer cambiado a `#1a1a2e` (azul oscuro EDA) — contrasta con PCB verde.
✅ **3D Viewer — nuevos meshes y color fix**:
  - Sensor modules (`moisture_sensor`, `sensor`): color cambiado de `0x1a5c34` (idéntico al PCB) a `0x1a3a5c` — ya no se funden con el board.
  - RTC module (`rtc`, `ds3231`, `ds1307`): nuevo mesh con PCB azul, portapila CR2032 (cilindro plateado), chip IC negro, edge highlight cyan.
✅ **Esquemático — dispatch expandido**:
  - Nuevo método `_sym_rtc()`: symbol IC box + barra header "RTC" + I2C pin stubs (SDA/SCL/VCC/GND) + símbolo portapila lateral.
  - Dispatch de tipos explícitos añadidos: `1n4007`, `1n5819`, `1n4148`, `zener` → `_sym_diode`; `rtc`, `ds3231`, `ds1307`, `pcf8523` → `_sym_rtc`; `bc547`, `bc557`, `2n2222` → `_sym_transistor`; `irf520`, `irf540`, `irfz44` → `_sym_mosfet`.
  - `_sym_generic` mejorado: muestra tipo (7 chars) + nombre + 4 pin stubs (2 por lado) en vez de solo una caja gris.

### 4.38 EDA Visualization — Light Theme KiCad-style (v4.8.0)
✅ **`tools/schematic_renderer.py`** reescrito completo — tema EDA light:
  - Fondo crema `#f5f6f7` + grilla fina (20px) + grilla mayor (100px) + borde área.
  - Paleta net dark/saturated para fondo claro: VCC=#cc0000, GND=#1a1a1a, I2C=#007744, SPI=#770077, UART=#885500.
  - 14+ símbolos SVG reescritos con `_SYM_STROKE=#1a1a2e`, fills claros por grupo funcional (MCU=#e8f0ff, sensor=#e8fff4, driver=#fff0e8, comm=#f4e8ff).
  - `_draw_power_rails()`: símbolo VCC (flecha arriba) y GND (3 líneas horizontales decrecientes) por red de alimentación.
  - MCU symbol: caja con header azul, pin stubs numerados 4×2 lados, nombre abreviado.
  - Title block EDA: sección inferior con dividers — TITLE / MCU+Power / Domain+Count / DRC badge / Stratum watermark.
✅ **`tools/pcb_renderer.py`** — pads THT y courtyard por componente:
  - Courtyard individual dashed amarillo (`#ffcc00`, dasharray 0.6,0.4) con clearance 0.5mm por componente.
  - Pads THT: anillo anular dorado (outer circle) + drill hole negro (inner circle).
  - Pads SMD con pitch calculado desde altura del componente.
  - Silkscreen blanco dashed por componente, ref label sobre courtyard.
✅ **`api/static/circuit_viewer.html`** — 3D parametric completo:
  - `_addComponent3D(comp, t, x, z)`: geometrías por tipo — resistor (CylinderGeometry horizontal + 3 bands + leads), LED (cuerpo + dome esférico translúcido), capacitor electrolítico (cilindro alto + disc plateado + K stripe), diodo axial (cylinder + cathode band), Arduino (PCB + USB + pin headers + IC), ESP32 (PCB + shield metálico + antenna trace), relay (cuerpo + coil housing), display (PCB + pantalla emissive), L298N (board + heatsink fins + IC), genérico IC (flat box + 4 filas de pines dorados).
  - `MeshStandardMaterial` con roughness/metalness reemplaza MeshPhongMaterial.
  - Layout: MCU types sorted first, resto en grid.
  - Wire arcs: smooth 5 puntos con `sin(t * PI)` en Y.
✅ **`agent/orchestrator.py`** — routing fix `circuit_design`:
  - `CIRCUIT_DESIGN_KEYWORDS` ampliado: `"parsea un circuito"`, `"parsea el circuito"`, `"parsea este circuito"`, `"parse a circuit"`, `"generá el esquemático"`, `"generá un circuito"`, `"generá la netlist"`, `"generar circuito"`, `"generar esquemático"`, `"generar netlist"`.
  - Root cause: `_keyword_route` itera el dict en orden; `hardware` keywords contenían `"circuito"` — capturaba antes que `circuit_design`.
✅ **Modelo LLM**: migrado a `anthropic/claude-sonnet-4-6` via Railway env vars (`OPENROUTER_MODEL`, `LLM_MODEL_SMART`, `LLM_MODEL_FAST`). Revirtido a `openai/gpt-4o-mini` por créditos insuficientes en OpenRouter (402 Payment Required).

### 4.40 EDA Renderer — Upgrade Profesional KiCad-level (v4.19.0)

#### `tools/pcb_renderer.py`
✅ **Trace width proporcional a corriente**: GND=1.0mm, VCC/PWR=0.5mm, I2C/SPI/UART=0.3mm, señal=0.25mm (antes todos 1.2mm o 0.5mm sin discriminación).
✅ **Routing por capa correcto**: nets de potencia van a bottom copper, señales a top copper. El segmento vertical de cada tramo L-shaped alterna layer automáticamente → genera vias en las intersecciones.
✅ **`_trace_color(layer, net_name)`**: GND=copper-bronce `#b87333`, VCC top=rojo `#cc3333`, VCC bot=bronce, señal top=oro `#daa520`, señal bot=`#c09030`.
✅ **Painter's algorithm**: bottom copper se dibuja primero, top copper encima — capas visualmente correctas.
✅ **GND flood fill real**: patrón SVG `<pattern id="gnd-hatch">` con hatch diagonal 45° (lines cada 2mm, 0.5px stroke-opacity 0.55). Cada componente conectado a GND recibe una zona de pour de 2.5mm de clearance.
✅ **SVG defs profesionales**:
  - `<pattern id="pcb-grid">` — cuadrícula 1mm sobre el FR4
  - `<radialGradient id="via-grad">` — gradiente radial dorado/bronce para vías
  - `<filter id="drc-glow">` — blur + merge para resaltar errores DRC
✅ **Edge.Cuts mejorado**: borde amarillo `#ffcc00` grosor 0.4mm (antes dasharray fino) + **4 crosshair markers** estilo KiCad en cada esquina (`_edge_cuts_corners()`).
✅ **Vías profesionales**: `<circle r=0.7>` con `fill="url(#via-grad)"` + drill hole `<circle r=0.32>` oscuro (antes círculo gris plano).
✅ **`_edge_cuts_corners(bw, bh)`**: nuevo helper estático — genera 8 líneas formando cruces de 2.4mm en las 4 esquinas de la placa.
✅ **`_render_pads(comp, ctype, ...)`**: nuevo helper estático —
  - MCU/large ICs: pads SMD rectangulares a lo largo de ambos lados (`rx=0.2`)
  - Pasivos: pads THT anillo anular (r=0.85) + drill hole (r=0.38)
  - Pads GND en bronce `#b87333`, resto en oro `#daa520`
✅ **Leyenda actualizada**: incluye widths de traza reales ("señal/0.25mm", "GND=1.0mm").

#### `tools/schematic_renderer.py`
✅ **6 símbolos nuevos registrados en dispatch**:
  - `_sym_transformer`: bobinado EI-core, 4 bumps primario + 4 secundario + líneas de núcleo + pins P/S
  - `_sym_bridge_rectifier`: diamante de 4 diodos triangulares + labels AC~·+·−
  - `_sym_fuse`: elipse IEC con zigzag interior (7 segmentos alternos) + valor
  - `_sym_varistor`: cuerpo de resistor + flecha diagonal bidireccional + "V" + leads
  - `_sym_mosfet_driver`: IC box 58×44px con header, IN/EN/VCC izquierda, HO/LO/GND derecha
  - `_sym_connector_ac`: housing IEC 3-pin con socket circles (L=rojo, N=azul, PE=verde) + labels
✅ **Dispatch ampliado** con 12 entradas nuevas: `transformer`, `bridge_rectifier`, `fuse`, `fuse_holder`, `varistor`, `mov`, `x_capacitor`, `mosfet_driver`, `gate_driver`, `uln2003`, `ir2104`, `connector_ac`, `iec_connector`.
✅ **`_sym_generic` reescrito** — ya no genera 4 stubs anónimos:
  - Lee `comp["pins"]` si existe (lista de dicts o strings)
  - Fallback inteligente por tipo: I2C→VCC/GND/SDA/SCL, UART→TX/RX, SPI→MOSI/MISO/SCK/CS, resto→VCC/GND/IN/OUT
  - Layout automático: mitad de pines en lado izquierdo, mitad en derecho
  - Pines VCC/VDD en rojo, GND en azul, resto en color texto
  - Numeración de pin en exterior (pequeño, gris `#999999`)
  - Notch IC en borde superior
  - Altura adaptativa según número de pines

#### `api/static/circuit_viewer.html` (Three.js)
✅ **Breadboard real** reemplaza el PCB verde genérico:
  - Base ABS blanca `#f5f5f0` — 195×130×8mm, `roughness=0.7`
  - **300 agujeros** (30 cols × 10 rows): pitch 5.08mm escalado, `CylinderGeometry r=0.9`, split A-E / F-J con gap de 6mm
  - **Gap central**: barra gris de separación entre las dos mitades
  - **Power bus strips**: rojo `#ff2222` (VCC outer) + azul `#2244cc` (GND inner) en ambos extremos
  - **Bus holes**: 120 dots metálicos `r=0.55`, `metalness=0.6`
  - **Labels sprites**: números de columna (1,5,10..30) y letras de fila (A-E) via `CanvasTexture`
✅ **Colores de cable estándar de laboratorio**:
  - GND = negro `#111111` (0x111111), cable gordo (r=0.60)
  - VCC/5V/3V3 = rojo `#dd1111`, cable gordo
  - SDA = azul `#2244ee`, SCL = amarillo `#ddcc00`
  - MOSI = púrpura `#9933aa`, MISO = magenta, SCK = violeta, CS = lila
  - TX = naranja `#ff8800`, RX = verde `#22cc44`
  - Control/relay = verde `#22cc44`, Analog = púrpura `#8833cc`
  - PWM = naranja, default pool = azul/teal/coral/rosa/verde
✅ **Wire radius**: power/GND=0.60 (antes 0.55), señales=0.35 (unchanged).
✅ **Zone layout**: corregido `pcbW → bbW` para coordenadas relativas al breadboard nuevo.


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

### Estado actual (2026-05-06): 144 colectados, 120 passing, 3 failed, 21 errors
```
pytest tests/  → 3 failed, 120 passed, 21 errors in 0.90s
```

Los 3 failures + 21 errors son **pre-existentes** (documentados en el changelog v4.27.0). En 2026-05-06 se eliminó el módulo dead `agent/keywords/circuit_keywords.py` y su test (`test_keywords.py`, 4 tests) — el conteo bajó de 124 a 120 sin regresiones.

### Suites principales
- `tests/` (148 tests) — pytest puro, sin servidor, sin red. Cubre EDA (classifier/layout/router/symbol_draw/pcb_draw), circuit_importer, firmware_generator, electrical_formulas, versioning_sharing.
- `eval/test_full_integration.py` (3 tests offline) — `test_complete_integration` (DB componentes, CircuitDesignManager), `test_kicad_connectivity` (parser v6 Union-Find), `test_kicad_legacy_connectivity` (parser v5).
- `eval/test_e2e_api.py` — requiere servidor en `:8000` (no se ejecuta offline).

---

## 8. DEUDA TÉCNICA RESUELTA

| Archivo original              | Antes    | Después                          | Motivo                          |
|-------------------------------|----------|----------------------------------|---------------------------------|
| `api/static/app.js`           | 2154 lín | 390 lín + 16 módulos | Separación de responsabilidades |
| `database/hardware_memory.py` | ~500 lín | 121 lín facade + 4 sub-DB (~639 lín total) | Tabla única → 4 tablas especializadas |
| `agent/proactive_engine.py`   | ~450 lín | 82 lín facade + 3 clases (~500 lín total) | Broadcast/Scheduler/Consolidator independientes |
| `agent/agents/electrical_calc_agent.py` | ~350 lín | 214 lín + prompts externos (196 lín) | Prompts LLM externalizados |
| `tools/electrical_formulas.py` | 564 lín | 79 lín re-export + 6 módulos (~521 lín total) | 25 fórmulas en 6 categorías |
| `tools/schematic_parser.py`   | legacy básico | Union-Find v5 + v6 (~584 lín) | Conectividad real trazada |
| `agent/agents/hardware_agent.py` | ~950 lín | 122 lín facade + 4 mixins (~946 lín total) | Mixin split por responsabilidad |

---

## 9. KNOWLEDGE BASE TÉCNICA

Archivos en `knowledge_feed/` — indexados automáticamente al startup via `index_knowledge_base()`:

| Archivo | Contenido |
|---|---|
| `00_INSTRUCCIONES_USO.txt` | Guía interna de uso del knowledge feed |
| `01_electronica_analogica.txt` | Ley de Ohm, filtros RC/RLC, op-amps, BJT, MOSFET, diodos, capacitores, inductores |
| `02_microcontroladores.txt` | Arduino UNO/MEGA, ESP32, ESP8266, STM32, Pico RP2040, I2C/SPI/UART/interrupciones |
| `03_electronica_potencia.txt` | Buck/Boost/Flyback, IGBT, MOSFET potencia, drivers de gate, motores, baterías, transformadores |
| `04_plc_automatizacion.txt` | Siemens S7, IEC 61131-3, Ladder, variadores VFD, servos, redes industriales, sensores 4-20mA |
| `05_sensores_protocolos.txt` | DHT/BMP/MPU, INA219, HX711, MQTT, HTTP, WebSocket, BLE, LoRa, Zigbee, SD/FRAM |
| `06_instalaciones_electricas.txt` | Normas IEC/AEA, secciones cables, MCB/RCD, puesta a tierra, motores, cuadros, iluminación |
| `07_formulas_calculos.txt` | Conversiones, caída de tensión, corrección FP, mecánica, hidráulica, PID, Fourier, ADC |

---

## 10. ROADMAP — DIFERENCIADORES PENDIENTES

> Las propuestas históricas 10.1–10.5 y 10.7 ya están implementadas y se documentan en §4 (datasheet auto-fetch §4.15, firmware iterativo §4.14, Wokwi §4.16, ZIP export §4.37, error patterns §4.5, platform context §4.13). Esta sección queda para roadmap real.

### 10.6 Voice-to-firmware pipeline completo ⭐⭐⭐ (pendiente)
**Impacto:** El ingeniero habla, el sistema genera código y wiring.
- La voz ya existe (Web Speech API) pero solo inserta texto en el prompt
- Mejora: modo "voice firmware" → el usuario describe en voz lo que quiere → el sistema genera firmware + esquema de conexiones + BOM en un solo paso
- **Implementación:** Detectar frases clave en el transcript de voz → disparar pipeline directo a `HardwareAgent._design_consult` + `CircuitAgent`

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

## 12. CODE QUALITY PASS — v4.11.0 (2026-04-24)

Revisión sistemática folder-a-folder (core → llm → memory → database → knowledge → tools → agent → api → cli). Sin cambios de funcionalidad.

### Archivos eliminados (dead code confirmado por grep)
| Archivo | Motivo |
|---|---|
| `memory/memory_filter.py` | Cero callers — check de 6 keywords reemplazado por `fact_extractor.py` |
| `memory/session_summarizer.py` | Cero callers — además usaba `LLM_API`/`LLM_MODEL` frozen en importación, sin `get_llm_headers()` |
| `knowledge/document_loader.py` | Cero callers — funcionalidad duplicada en `knowledge_base.py` |
| `knowledge/document_chunker.py` | Cero callers — misma razón |
| `tools/debug_tools.py` | Cero callers — print-based debug utilities |
| `tools/memory_viewer.py` | Cero callers — print-based viewer |

### Bugs corregidos
| Bug | Archivo(s) | Impacto |
|---|---|---|
| `asyncio` NameError silencioso | `agent_controller.py` | `_auto_fetch_datasheets()` nunca indexaba datasheets — NameError capturado por `except Exception` |
| Mutable default `dict` / `list` | `vector_memory.py`, `memory_consolidator.py`, `database/hardware_projects.py`, `database/hardware_memory.py` (×2) | Dicts/listas compartidos entre todas las llamadas |
| `datetime.utcnow()` deprecado | `database/design_decisions.py`, `database/component_stock.py`, `api/server.py`, `api/routers/hardware_bridge.py`, `api/routers/memory.py` (×2) | Python 3.12 deprecation + naive datetimes sin timezone |
| `_call_llm` (API privada expuesta) | `llm/openrouter_client.py`, `agent_controller.py`, `agent/agents/circuit_agent.py` | Función privada importada por 2 módulos externos — renombrada a `call_llm_sync` |
| `search_in_sources` dead branch | `memory/vector_memory.py` | `A or (B and A)` → precedencia de operadores hace `B and A` inalcanzable |
| `import asyncio` dentro de método | `agent/orchestrator.py`, `agent_controller.py` | Imports de función no añaden al namespace global — otros métodos del módulo no lo ven |
| Re-exports privados | `tools/electrical_formulas.py` | `_E24`, `_FUSE_STD`, `_nearest_e24`, `_nearest_fuse`, `_result` son privados de `formulas_basic` — removidos del import público |
| `os.getenv` en vez de `SQL_DB_PATH` | `database/intelligence.py` | Railway inyecta env vars con comillas — `_env()` / `SQL_DB_PATH` de `core.config` las strip |
| `int()` redundante | `knowledge/knowledge_base.py` | `total_chunks` y `total_files` ya son `int` |
| Inner `import uuid` | `database/sql_memory.py` | Import redundante dentro de función cuando ya existe `import uuid as _uuid` en el módulo |

### Mejoras de performance/estructura
| Mejora | Archivo(s) |
|---|---|
| `deque(maxlen=N)` reemplaza lista + `pop(0)` O(n) | `memory/short_memory.py`, `agent/agent_state.py` |
| `self._exact: dict` fast-path O(1) por hash+model | `llm/cache.py` (complementa el fast-path MD5 existente con sync exacto post-pruning) |

---

## 13. PENDIENTE TÉCNICO

- HardwareAgent: por defecto genera MicroPython en vez de C++/Arduino — system prompt de `_design_consult` debe preferir C++/Arduino salvo que el usuario pida explícitamente MicroPython
- Parser KiCad v5: usar coordenadas de pines reales del `.lib` si está disponible (actualmente usa `P X Y` del componente como fallback)
- Test e2e offline (mockear el servidor en pytest)
- App mobile: publicar en Play Store / App Store (requiere `google-services.json` FCM)

---

## 14. HISTORIAL DE VERSIONES

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
| v4.0.1  | 2026-04-20  | Fix crítico intent "modify": (1) "modify" faltaba en tupla de intents válidos en `_classify_intent()` → LLM respondía "modify" pero caía al fallback; (2) MODIFY_KEYWORDS se chequeaba después de DESIGN_KEYWORDS en `_classify_by_keywords()` → "hacelo más rápido" matcheaba design. Ahora el firmware diff se dispara correctamente. |
| v4.2.0  | 2026-04-21  | Chat→Circuit inline (orchestrator circuit_design intent + card embebida en chat con preview SVG + KiCad/BOM/Gerber/3D links); Live Hardware State visualizer (WebSocket /ws/hardware-state + serial STATE:{} + live_circuit.js overlay en SVG viewer) |
| v4.3.0  | 2026-04-21  | Import Eagle/KiCad (POST /circuits/import, parser S-expr + Eagle XML); Versioning (save/list/restore versiones con diff); Share via link público (token URL-safe, router sin auth); Firmware production-ready (watchdog, OTA ESP32/8266, STATE serial, error handling en todos los platforms) |
| v4.4.0  | 2026-04-21  | Multi-usuario real (user_id wired en parse/import, GET /circuits/ por usuario, update_owner); Editor visual de circuitos (+ Agregar componente modal, ✕ Eliminar con confirmación, 💾 Guardar → PUT /circuits/{id} con auto-versión, beforeunload dirty-check); Tests pytest 56/56 (test_circuit_importer, test_versioning_sharing, test_firmware_prompts, conftest con fixtures tmp_db) |
| v4.4.1  | 2026-04-21  | Verificación total: fix CRÍTICO IndexError parser S-expression (circuit_importer.py — validación bounds + paréntesis sin cerrar); fix ADVERTENCIA component_library.json sin try/except (fallback a dicts vacíos); fix ADVERTENCIA PUT /{id} no chequeaba save_version() retorno; fix INFO guard renderSchematic en viewer; fix INFO MULTI_USER documentado en .env.example. 56/56 tests siguen pasando. |
| v4.5.0  | 2026-04-21  | Fix domain_hint nunca pasado al prompt (circuito riego sin sensor humedad); regla anti-nodos-duplicados en CIRCUIT_PARSE_PROMPT; SVG responsivo 100%×100% (ya no se ve centrado en gris); Viewer 2D reescrito: fetch SVG servidor + pan/zoom (rueda, drag, doble-clic reset) + fallback client-side corregido (root cause: container.id vacío → SVG.js fallaba silenciosamente); Viewer 3D: OrbitControls r128, PCB verde con borde dorado, componentes tipados por tipo (14 estilos), cables con arco entre nets, sprite labels, iluminación 3 capas, _resetThreeJS(); Editor: click-to-select migrado al sidebar (compatible con server SVG) |
| v4.6.0  | 2026-04-22  | Performance: 11 fixes aplicados — SQLite persistente + WAL, dirty flag facts/graph, streaming en bloque, call_llm_async directo, SVG LRU cache, título en background, GZipMiddleware, fast-path hash SemanticCache, asyncio.get_event_loop() → get_running_loop(), requests → httpx (10 archivos). Tests: 56/56. |
| v4.7.0  | 2026-04-22  | Auditoría Semanas 1-3: MCU pin rules (6 plataformas), 15+ símbolos SVG nuevos, 3 DRC checks nuevos (5V→3V3/motor sin driver/ESP bulk cap), BOM agrupado+footprints KiCad, firmware retry 2x+error parsing inteligente, snippet library 18+ componentes, PCB renderer profesional (DRC highlight/copper pour/vias/pads/leyenda), export ZIP bundle (/export.zip). Tests: 56/56. |
| v4.8.0  | 2026-04-22  | EDA visualization rewrite: schematic light theme KiCad-style (fondo crema, grilla, 14 símbolos, title block, power rails VCC/GND); PCB THT annular pads + courtyard dashed + SMD pads; 3D viewer parametric completo (10 tipos de geometrías, MeshStandardMaterial, wire arcs suaves); routing fix "parsea un circuito" → circuit_design; migración modelo Claude Sonnet 4.6 (revertida por créditos). |
| v4.9.0  | 2026-04-23  | 3D viewer: AmbientLight 2.5→0.55, cámara oblicua (0,55,170), PCFSoftShadowMap 2048, fill light, fondo #1a1a2e, sensor color fix, RTC mesh (CR2032+IC). Schematic: _sym_rtc nuevo, dispatch 14 tipos explícitos (1n4007/zener/bc547/irf520/etc), _sym_generic mejorado con pins. |
| v4.10.0 | 2026-04-23  | KiCad Symbol Renderer (Opción B): parser S-expressions KiCad (kicad_sym_parser.py), renderer con auto-fit (kicad_sym_renderer.py), 13 símbolos reales descargados de gitlab.com/kicad/libraries (R,C,C_Polarized,L,D,LED,Battery,ESP32,ESP8266,DS3231,DS1307). Integrado en schematic_renderer.py con fallback transparente. Símbolos KiCad activos: resistor/capacitor/inductor/diodo/LED/batería/ESP32/ESP8266/RTC. |
| v4.12.0 | 2026-04-24  | Fix context loss en circuit follow-ups: orchestrator.run() recibe `history`, detecta queries cortas sin contexto de circuito (<120 chars, sin keywords de dominio), enriquece description con últimos 5 msgs del usuario; MCU detection también escanea historial. CIRCUIT_PARSE_PROMPT reescrito: instrucciones explícitas para todos los componentes de protección, circuitos multi-carga y diseños 220VAC; eliminado ejemplo JSON que sesgaba al LLM hacia circuitos mínimos. Nuevo dominio "industrial" (220V AC, bombas hidráulicas, PLC, motores industriales) con domain_hint completo para etapa AC/DC, 5 relays numerados, Arduino Mega por defecto. Schematic renderer: canvas dinámico por número de componentes (n×90+300 × n×60+200), algoritmo de layout reescrito con spacing adaptivo y soporte multi-columna para grupos grandes. |
| v4.13.0 | 2026-04-24  | **Generación de circuitos industriales — precisión 100%** (basado en `REPORTE_ANALISIS_CIRCUITOS.md`). **F1 Generación**: +27 keywords de routing (`diseña el pcb y esquematico` y variantes argentinas → CIRCUIT_DESIGN); `_extract_load_count(desc)` detecta N de "5 bombas"/"tres motores" (regex números + palabras es); CIRCUIT_PARSE_PROMPT con regla N-cargas explícita (RL1..RLN, D_fly1..N, R1..RN, RELAY1_CTRL..RELAYn_CTRL, J2..J(N+1) — prohibido módulo multi-canal); `_validate_circuit()` ahora **auto-fixea** nodos duplicados (remueve del net secundario) y componentes flotantes (groundables → GND, otros → eliminados del JSON); chequeo post-LLM de compliance N-load. **F2 Esquemático** (`schematic_renderer.py`): layout por 4 zonas verticales (AC \| Power+MCU \| Relay-cells \| Output) con flujo de señal izq→der; `_build_relay_groups()` agrupa cada RLn con su Dn flyback + Rn control; `_draw_net_label()` con flags KiCad-style para nets de span >220px (en vez de wires largas cruzadas); `_draw_galvanic_barrier()` con zigzag dashed + etiqueta "BARRERA GALVÁNICA"; canvas mínimo 1500px. **F3 PCB** (`pcb_renderer.py`): `_pcb_zone()` 4 zonas horizontales (HV/MCU/Relay/Output con relay-cells stacked); +12 footprints industriales (transformer 80×60, smps 80×40, bridge_rectifier 8.5×5, fuse 30×14, varistor 10×7, voltage_regulator TO-220 10.5×14, optoacoplador DIP-4, inductor_cm 25×20, etc); board size dinámico sin tope (ej: 309×222mm para 30 comps); línea separación HV/LV con clearance band 3mm; `_per_comp_stack()` evita Y-overflow. **F4 3D viewer** (`circuit_viewer.html`): 8 nuevas geometrías (`transformer` con núcleo+bobinas, `voltage_regulator` TO-220 con tab metálico, `bridge_rectifier` con 4 pines, `fuse` cilindro semitransparente con filamento, `varistor` disco naranja, `smps` con vents, `connector` terminal block con tornillos, `optoacoplador` DIP-4, `inductor_cm` toroide); layout 3D mirroring del PCB (cells RL+D+R adyacentes); wires `TubeGeometry` con color coding por net (HV=naranja, VCC=rojo, GND=oscuro, ctrl=amarillo, I2C=verde, SPI=violeta, UART=marrón). **Validado**: 5/5 relays generados, 0 flotantes, 0 dups, 0 cramming inferior, all coords in-bounds. |
| v4.11.0 | 2026-04-24  | Code quality pass completo (9 carpetas core→llm→memory→database→knowledge→tools→agent→api→cli): 6 archivos dead eliminados (memory_filter, session_summarizer, document_loader, document_chunker, debug_tools, memory_viewer); mutable defaults corregidos (6 sitios); datetime.utcnow() → datetime.now(timezone.utc) (7 sitios); asyncio NameError silencioso en _auto_fetch_datasheets; _call_llm renombrado a call_llm_sync; deque en ShortMemory y AgentState; O(1) exact-match dict en SemanticCache; SQL_DB_PATH desde core.config en intelligence.py; re-exports privados (_E24/_nearest_e24/etc) removidos; import asyncio/LLM_MODEL_FAST a módulo en orchestrator.py; cli/utils.py + cli/status.py: from pathlib import Path movido a módulo (lazy imports eliminados). |
| v4.14.0 | 2026-04-25  | **Modo calidad + HPWL placement + auto-AC/DC + chat export fix**. Quality estimator nuevo (`agent/quality_estimator.py`) con `estimate_quality_time(query)` → `{seconds, phases, complexity, reasoning}` (3-180s según keywords). `agent_controller.process_input` y `orchestrator.run` aceptan callback `on_phase` y emiten fases (understanding→routing→responding · generating_circuit→validating→rendering). WebSockets reenvía evento `estimate` upfront + cada `phase`; timeout 180→240s. UI chat: tarjeta progreso con label fase activa, countdown elapsed/total, barra amarilla si supera estimado. **HPWL barycentric reorder** en `pcb_renderer.py` y `schematic_renderer.py` (3 iteraciones, ancla = zona más poblada): PCB −43%, schematic −67% reducción HPWL. **Auto-AC/DC stage** en `circuit_agent.py::_ensure_ac_dc_stage`: detecta keywords "220VAC/110VAC/red eléctrica" + MCU → agrega F1, MOV, T1, BR1, C1 2200µF, LM7805, C2 100nF + nets completos. **Flyback fix**: uno por relay (antes reusaba el mismo). **Chat export fix** en `chat.js`: `_pageMessages` se rellena al cargar historial. Layout packing: PCB y schematic calculan ancho real por zona, sin huecos. |
| v4.14.1 | 2026-04-25  | Fix saludos triviales sin LLM (orchestrator.run detecta "hola"/"gracias"/etc y responde directo); routing circuit_design más laxo (más keywords aceptados, menos falsos negativos al circuit-context-loss). |
| v4.18.0 | 2026-04-26  | **EDA audit: footprints reales + símbolos custom por instancia + pads SMD**. Auditoría de calidad (`instrucciones.txt`) detectó 4 gaps. **C3/S1 — `_TYPE_TO_FOOTPRINT` inválido** (`tools/kicad_exporter.py`): eliminada clave duplicada `mpu6050` (la segunda sobreescribía la primera en silencio); corregidos 12 refs inexistentes (`Sensor:HC-SR04`, `Display:LCD_16x2_I2C`, `Module:L298N`, etc.) por footprints reales de librerías KiCad estándar (e.g. `Relay_THT:Relay_SPDT_Omron_G5LE-1`, `Package_DIP:DIP-16_W7.62mm`, `Connector_PinHeader_2.54mm:PinHeader_1xNN_P2.54mm_Vertical`). **C1/C2 — símbolos genéricos para ICs complejos** (`tools/kicad_exporter.py`): agregada `_POWER_PIN_NAMES` (frozenset 23 nombres: GND, VCC, SDA, SCL, TX, RX, etc.) y `_make_custom_symbol(sym_id, display_name, left_pins, right_pins)` que genera un símbolo inline `Stratum:<cid>` con caja proporcional al número de pines, pines izquierda (power/analógicos) y derecha (I/O), longitud PIN_LEN=2.54mm, ángulos KiCad correctos (0=stub hacia afuera izquierda, 180=stub hacia afuera derecha), y devuelve el S-expr + dict `{pin_name: (dx, dy)}` con offsets a los puntos de conexión externos. `export()` actualizado en 4 puntos: (a) pre-pass construye `comp_sym/custom_sym_defs/custom_sym_offs` por componente; (b) `lib_symbols` emite las defs custom además de las estándar; (c) loop de instancias usa `comp_sym.get(cid, _lib_id(comp))`; (d) loop de labels y función interna `_abs_pin_pos` resuelven offsets desde `custom_sym_offs` primero. **C4 — pads SMD para módulos** (`tools/kicad_pcb_exporter.py`): agregado `_SMD_TYPES` frozenset (22 tipos: esp32, arduino_*, raspberry_pi_pico, stm32, oled, lcd, bmp280, mpu6050, l298n, drv8825, a4988, buck_converter, boost_converter, ams1117, etc.); `_emit_footprint` ramifica en `smd roundrect (size 1.5 1.0) (layers F.Cu F.Paste F.Mask) (roundrect_rratio 0.25)` para esos tipos vs `thru_hole circle (size 1.7 1.7) (drill 0.8) (layers *.Cu *.Mask)` para THT. Smoke test: `Stratum:U1` en sch + `smd roundrect` en pcb + `thru_hole circle` para R1/C1 — PASS. |
| v4.17.0 | 2026-04-26  | **EDA pipeline quality — wires en .kicad_sch + .kicad_pcb real**. Auditoría de calidad contra spec EDA detectó 2 gaps críticos: (a) `.kicad_sch` se exportaba con net labels solos, sin wires visibles al abrir en KiCad eeschema; (b) **no existía ningún `.kicad_pcb`** — sólo SVG + Gerber, sin round-trip con pcbnew. **F2.1 — wires explícitos** (`tools/kicad_exporter.py`): después de los net labels, `export_kicad_schematic` calcula posiciones absolutas de cada pin (centro_componente + offset_pin) y emite `(wire (pts (xy x1 y1) (xy x2 y2)) ...)` con star routing pin → trunk (median de pines) → pin, orth (H-then-V). Junctions emitidas en trunk para nets con ≥3 nodos. Helpers internos `_abs_pin_pos()`, `_wire()`. Net labels se mantienen (KiCad acepta ambos). Smoke test sample blink: 6 wires + 7 labels, S-expr balanceada. **F2.2 — `.kicad_pcb` real** (`tools/kicad_pcb_exporter.py` nuevo, ~280 líneas): emite KiCad v6 PCB con secciones `(general)(paper)(layers)(setup)(net N "name")` + `(footprint "lib:ref" (at x y) (layer F.Cu) ...)` con pads THT 1.7mm/drill 0.8mm + `(segment (start)(end)(width)(layer)(net N))` para tracks + `(gr_line)` Edge.Cuts del board outline. Reusa `_place_components`, `_route_traces`, `_board_size` del `pcb_renderer.py` (no duplica lógica) y el `_TYPE_TO_FOOTPRINT` (50 refs reales: `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal`, `Module:Arduino_Nano`, `Package_TO_SOT_THT:TO-220-3_Vertical`, etc.) del `kicad_exporter.py`. Pad map por tipo: 2-term (R/C/LED/D/L/fuse/varistor) → 2 pads, 3-term (TO-220, TO-92) → 3 pads, switch/button → 4, bridge_rectifier → 4 cuadrados, default → row de pads según `pins[]`. Aliases A/K/+/- → 1/2 para LEDs y diodos. Nets indexadas {1..N}, net 0 reservada. **Endpoint nuevo**: `GET /api/circuits/{id}/board.kicad_pcb` (paralelo al `/schematic.kicad_sch` ya existente). ZIP bundle ahora incluye `.kicad_pcb` además del `.kicad_sch` para round-trip completo con KiCad. Parse-back smoke: las 4 nets del JSON aparecen 1:1 en el PCB exportado. Sintaxis Python OK. |
| v4.16.0 | 2026-04-26  | **Fix routing + eficiencia + persistencia de circuito + transformador multi-tap** (post-mortem chat 7b4b0a94). **Bug A — diseñame no ruteaba a circuit_design** (`agent/orchestrator.py`): regex laxo extendido con `diseñ[aá]me`, `dame|d[aá]me`, `mostrame|muestrame|show` en verbos y `esquema` (sin acento) en sustantivos. **Bug B — "dame el esquema y pcb" caía a LLM router**: 19 literales nuevos en `CIRCUIT_DESIGN_KEYWORDS` ("dame el esquema", "dame el pcb", "esquema y pcb", combinaciones, etc.). **Bug C — ElectricalCalcAgent rechazaba transformadores multi-tap**: `transformer_turns_ratio(vp, vs, ...)` ahora acepta `vs: float | list[float]` y devuelve `{multi_tap: True, taps: [{vs, turns_ratio, secondary_current_a}, ...]}`; prompt `transformer_turns_ratio` con ejemplos para "220V a 12V y 24V" → `vs=[12,24]`; `_check_required` reconoce listas vacías como faltante; `_fmt_val` formatea listas. **Bug D — pérdida de contexto entre turnos (alucinación DHT22)**: `AgentState.set_active_circuit/get_active_circuit` persisten id+name+mcu+power+top_components tras un design exitoso; `_build_base_context` reinyecta el circuito activo con instrucción explícita "Si el usuario hace un follow-up ambiguo se refiere a ESTE circuito". **F1.3 — regresión "hola=180s"** (`agent_controller.py`): `_store_episode` (Qdrant insert + 2x SQL) bloqueaba el envío del token en greeting/circuit/hardware short-circuits → ahora token PRIMERO, persistencia con `asyncio.create_task(asyncio.to_thread(...))`. **F1.4 — skip extract_facts/relations en queries técnicas**: nuevo `_should_extract_facts` reusa `_keyword_route`; si el input cae en `circuit_design`/`hardware`/`code`/`research`, se saltan 2 LLM calls (~6s con gpt-4o-mini). **F1.7 — short-circuit hardware más permisivo**: condición `agents_used == ["hardware"]` (estricta) → `"hardware" in agents_used and len(hw_result) > 200` para que combinaciones como `["hardware","memory"]` no caigan al LLM principal que reescribía/alucinaba. Sintaxis verificada. Tests routing: 5/5 inputs ok (3 del chat fallido + greeting + memory). |
| v4.27.0 | 2026-05-06  | **Refactor EDA: split renderers en `tools/eda/`** (commit `1c25dfb`). `tools/schematic_renderer.py` (1849 LOC) y `tools/pcb_renderer.py` (1260 LOC) reducidos a facades de 5 y 20 LOC. Lógica movida a 6 módulos en `tools/eda/`: `classifier.py` (~110 LOC, `classify_zone` con las 6 zonas existentes `ac/mcu/sensor/relay/output/other`), `layout.py` (~290 LOC, `compute_schematic_layout`, `build_relay_groups`, `validate_positions`), `router.py` (~95 LOC, `route_orthogonal` schematic + `route_traces`/`trace_color` PCB), `symbol_draw.py` (~1380 LOC, clase `SchematicRenderer` completa + `_net_color`), `pcb_draw.py` (~1080 LOC, clase `PCBRenderer` + helpers de footprint/placement). **SVG output byte-equivalente al pre-refactor** — verificado por 4 parity tests por renderer (empty / MCU-only / relay group / AC+LV) que comparan `tools.eda.{symbol,pcb}_draw.{Schematic,PCB}Renderer` vs el original byte por byte. **No se cambió la semántica**: el plan original pedía 8 zonas (con `power` y `display` separadas), pero se eligió Opción B = mantener las 6 zonas actuales para no afectar el output visual de producción. **`kicad_pcb_exporter.py` no se tocó** — sigue importando los 4 helpers internos (`_place_components, _route_traces, _board_size, _fp`) que la facade del PCB reexporta. **+59 tests nuevos** en `tests/test_eda_*.py` (16 classifier + 15 layout + 16 router + 6 symbol_draw + 6 pcb_draw). Suite full: 124 passed; las 3 fallas + 21 errors son pre-existentes (`test_buck/boost/battery_*` en `electrical_formulas`, `test_versioning_sharing` por `cd_mod.DB_PATH` en conftest), verificado vía stash. |
| v4.23.0 | 2026-05-04  | **KiCad-style pipeline refactoring (4 etapas) + bugfixes sintetizador + higiene repo**. **Etapa 1 — `tools/design_rules.py` (nuevo)**: constantes centralizadas `MARGIN_MM=10`, `TITLE_BLOCK_H=20`, `PCB_CLEARANCE` (signal/power/pad_pad), `ZONE_ORDER`; `get_sheet_size(n)` devuelve A4/A3/A2/A1 según cantidad de componentes; `snap_to_grid(x, y, grid)`. **Etapa 2 — `schematic_renderer.py`**: separación compute→validate→draw al estilo KiCad; `_PX_PER_MM=4.0` como factor de escala SVG↔mm; `_compute_positions()` llama `_layout_components` con canvas derivado del sheet y snapea a grilla; `_validate_positions()` clampea a márgenes y resuelve solapamientos <15mm; `SchematicRenderer._draw_schematic()` encapsula los draw calls; `render_schematic_svg` orquesta las 3 fases. **Etapa 3 — `pcb_renderer.py`**: `_compute_pcb_placement()` y `_compute_pcb_routing()` extraídos; `PCBRenderer._draw_pcb()` (~150 líneas) encapsula drawing; bugfix crítico `_board_size()` — zona `"sensor"` faltaba en ambos dicts → `KeyError` en circuitos con sensores. **Etapa 4 — `circuit_synthesizer.py`**: `_build_placement_hints(components, nets)` — clasifica zonas, mapa de adyacencia por net, detecta caps de bypass/diodos flyback, agrupa por i2c_bus/power/outputs; resultado inyectado en `synthesize()["placement_hints"]`. **Bugfix sintetizador — invernadero 180s timeout**: `_find_handler` ignoraba bloques `{"type": "dht22"}` (sin campo `model`) → solo 5 componentes sintetizados → loop de reintentos LLM → timeout; fix: fallback en `model_map` también por `type` con normalización `replace("-","").replace("_","").replace(" ","")` (cubre `moisture_sensor`, `dht22`, etc.). **Higiene repo**: `.gitignore` — añadidos `imagen/` (era `Imagen/` — case-sensitive en Linux), `agent/keywords/`, `.cursorrules`, `.mcp.json`, `.claude/settings.json`, `.claude/skills/`; `Dockerfile` — eliminado comentario `# cache bust: 2026-04-13` stale; `tests/test_electrical_formulas.py` y `tests/test_keywords.py` commiteados (eran untracked). Test suite: 36 passed, 1 pre-existing failure (`test_buck_converter` → `KeyError: 'extra'` en `electrical_formulas.py`, no causado por esta sesión). Cero imports circulares entre los 4 módulos refactorizados. |
| v4.28.0 | 2026-05-06  | **EDA renderer overhaul (schematic + PCB + 3D)**. **Schematic** (`tools/eda/symbol_draw.py`, `tools/eda/layout.py`, `tools/design_rules.py`): hoja A4 ISO 7200 fija (no más viewBox dinámico) con marco doble + zone references A–D × 1–8 con tickmarks + corner brackets; title block ISO anclado en esquina inf-der (180×32mm) con campos TITLE / MCU / POWER / DOMAIN / COMP + DRC badge; layout zonal proporcional al área útil real (`drawing_area_px`) con pesos por zona en lugar de slots fijos px; routing Manhattan-tree (trunk vertical + stubs ortogonales) reemplaza el star-from-centroid; net labels con `_alloc_label_dx` (tracking de bbox + push perpendicular del stub) y triple-candidato vertical (top/centroid/bottom + bumps de ±16px) en el caso trunk; legend reposicionada dentro del marco interno top-right. **PCB** (`tools/eda/pcb_draw.py`): dispatcher de footprints por familia — `_draw_module_footprint` (MCU/sensor/driver/display: sub-PCB navy + pin headers gold + USB plata + pin1 dot + label), `_draw_relay_footprint` (cuerpo azul + band + bobina + 5 pin headers + RELAY silk), `_draw_to220_footprint` (heatsink tab plateado con mounting hole + cuerpo negro + 3 pads THT), `_draw_to92_footprint` (silueta D-shape + 3 pads), `_draw_axial_footprint` (pill body + bandas resistor / cathode stripe diodo + 2 pads en extremos), `_draw_radial_footprint` (cuerpo redondo + polarity stripe electrolytic / dome dot LED + 2 pads cercanos), `_draw_generic_footprint` (fallback). CSS embebido en `<defs><style>` para `.pad-smd`/`.pad-tht`/`.pad-header`/`.silk`/`.courtyard`/`.pin1-mark` (antes los `class="pad-smd"` no tenían efecto → pads salían fill negro invisible). Side panel off-board de 42mm con PCB INFO + DRC OK + layer legend + stats (BOARD/COMPS/NETS/LAYERS) + bottom strip con título — ya no tapa la copper. **Bug fix:** `_board_size` ahora suma los anchos reales de zonas activas + gaps + márgenes (antes clampaba a `min(80, n*8.5)` y dejaba a Arduino Uno + L298N + OLED off-board detrás del side panel). El renderer crece (no clampa) si las posiciones superan la estimación inicial. **3D viewer** (`api/static/circuit_viewer.html`): reemplaza el breadboard ABS blanco con holes 5.08mm + bus strips por un PCB FR4 verde (#0e4a1a) + soldermask traslúcido + edge.cuts gold con esquinas chamfered + 4 mounting holes M3 plated through-hole + silkscreen "STRATUM PCB" + nombre del circuito + 4 fiducials. **Verificación**: rendericé 2 circuitos distintos (ESP32+moisture+relay y Arduino Uno+L298N+OLED+LM7805), revisé visualmente cada componente, detecté el overflow del OLED y lo arreglé antes de reportar. Tests: EDA suite 55/55 passing, baseline general 120 passing (3 fail / 21 errors pre-existentes en `test_versioning_sharing.py`). |
| v4.15.0 | 2026-04-25  | **Fase 1 corrección eléctrica**. **F1.2 DRC reglas extra** (`tools/electrical_drc.py`): 3 checks nuevos — `MCU_MISSING_VCC` / `MCU_MISSING_GND` (cada MCU debe tener net VCC y GND), `RELAY_NO_FLYBACK` + `RELAY_FLYBACK_BAD_POLARITY` (cátodo debe estar en net de control y ánodo en GND, polaridad invertida quema MCU al apagar relay), `AC_CONNECTOR_NO_FUSE` + sub-warning `AC_CONNECTOR_FUSE_NOT_INLINE` (conector AC debe tener fusible aguas arriba en mismo net). **F1.3 Validador pinout MCU** (`tools/mcu_pinout_validator.py` nuevo): post-generación verifica que cada nodo `U.PIN` use un pin existente en el MCU declarado — cubre Arduino Uno/Nano/Mega, ESP32 (excluye GPIO6-11 flash interno), ESP8266, Pico, STM32 genérico. Detecta D14 en Nano, GPIO40 en ESP32, A8 en Uno, GPIO9 (flash). **F1.1 Review pass LLM** (`circuit_agent.py::_review_pass`): segundo pase con gpt-4o (LLM_MODEL_SMART) cuando hay errors DRC o pinout warnings. Acepta la versión revisada solo si (a) preserva el MCU original, (b) reduce el total `errors_drc + pinout_warns`. Skip si JSON >12k chars. Marker `[Auto-review] Revisión LLM aplicada — errors DRC X→Y` en warnings. Tests: 3 checks DRC nuevos (6 cases), validador pinout (7 cases), review pass (3 cases acepta/rechaza-MCU/rechaza-no-mejora), E2E con LLM mockeado (gen+review encadenados). |
| v4.29.0 | 2026-05-07  | **EDA refactor estructural — Fases 1-3 de 10** (de `instruc.txt`: migrar de fixes locales a pipeline EDA determinista LLM → IR → Validation → Constraints → Pin Alloc → Placement → Routing → Renderer → Exporters). **Fase 1 — Circuit IR** (`tools/eda/ir/`, pydantic v2): modelos `Circuit / Component / Pin / Net / Node / Trace / Via / Board / DesignRules / Constraint / ValidationIssue / CircuitMetadata / PlacementInfo / Footprint / Symbol`, enums `ElectricalType / Side / Layer / Severity`, `Vec2` frozen; validación estructural (refs únicos, nodos→componentes existen, no duplicados de pin/net), `extra="forbid"` en todos los modelos, roundtrip JSON limpio. **Fase 2 — Component Registry** (`tools/eda/component_registry/` + 17 YAMLs): schema pydantic (`ComponentSpec / PinSpec / MCUSpec / BusPins / VoltageSpec / WiringRequirement`) + singleton lru_cached (`get_registry()`), lookup exacto por type y por alias case-insensitive. Cubre 6 MCUs (esp32, arduino_uno/nano/mega, esp8266, pico, stm32 con `forbidden_pins / input_only_pins / boot_strapping_pins / adc_pins / pwm_pins / preferred_buses` + pinout completo), 7 sensores (dht11/22, bmp280, hc_sr04, mpu6050, fc28, ds18b20), 3 power (lm7805, lm317, ams1117), l298n, relay_module, oled_ssd1306, ds3231, 5 pasivos, fuse, screw_terminal. **Fase 3 — Constraint Engine** (`tools/eda/constraint_engine.py` + `rules.py`): engine declarativo con `ValidationContext` (snapshot indexado O(1)), `ConstraintRule` + `RuleRegistry` con `@rule_registry.register` decorator, `validate(circuit, rules=None)` y `run_drc(circuit)` (compat dict legacy). 19 reglas: las 18 de `electrical_drc.py` migradas + 3 nuevas que reemplazan `mcu_pinout_validator.py` consumiendo el registry (`PIN_INVALID / PIN_FORBIDDEN / PIN_INPUT_ONLY_MISUSE`). **Tests**: +68 nuevos (IR 20, registry 18, constraint engine 30) — full suite **188 passed** (3 fail / 21 errors pre-existentes, cero regresión). **Compat**: `tools/electrical_drc.py` y `tools/mcu_pinout_validator.py` no se tocaron — siguen importándose desde `circuit_agent.py`. La migración a usar el nuevo engine ocurre cuando los renderers/exporters consuman IR (Fases 7-10). **Decisiones**: pydantic v2 (no dataclasses) por validación gratis + JSON schema export; YAML (no JSON) por legibilidad; match exacto en `Registry.get` (no substring) — alias laxos como "c"/"r" matcheaban cualquier string; `extra="forbid"` para detectar typos en YAML al startup. **Deps**: `requirements.txt` + `pydantic>=2.6,<3.0` + `PyYAML>=6.0,<7.0`. **Próximo**: Fase 4 Pin Allocator. |

---

## 15. DECISIONES DE ARQUITECTURA

Decisiones no-obvias ya tomadas. No reabrir sin un motivo concreto y medible.

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| HardwareAgent como facade + 4 mixins | Clase monolítica (~950 líneas) | Archivos >250 líneas dificultan el contexto del agente; cada mixin tiene responsabilidad única (design/firmware/keywords/memory_ops); reduce conflictos de merge |
| OpenRouter como único gateway LLM | Llamadas directas a OpenAI/Anthropic | Un solo cliente httpx soporta múltiples providers; cambio de modelo sin tocar código; `LLM_PROVIDER`, `LLM_MODEL_FAST`, `LLM_MODEL_SMART` como env vars en Railway |
| NetworkX + JSON para grafo de memoria | Neo4j, memgraph | NetworkX es zero-dependency y corre in-process; persiste en un único JSON; Neo4j requeriría server adicional en Railway (costo + complejidad) |
| SQLite + WAL + conexión persistente | PostgreSQL | Deploy con un solo archivo en volumen `/data`; WAL + RLock son suficientes para la carga esperada (<100 usuarios); sin proceso de DB separado |
| Qdrant (local path o cloud) | Chroma (solo local), Pinecone (cloud-only) | Mismo cliente para dev (path local) y prod (QDRANT_URL cloud); sin vendor lock-in; `QDRANT_URL` vacío → path local automático |
| Plain JS modules con `<script>` y scope global | React, Vue, Svelte | Los `onclick=` en HTML requieren scope global; un bundler añadiría build step sin beneficio real para el tamaño del proyecto; 14 módulos JS son mantenibles sin framework |
| `deque(maxlen=N)` para ShortMemory y AgentState | `list` + `list.pop(0)` | `list.pop(0)` es O(n) — desplaza todo el array; `deque` es O(1) en ambos extremos con bound automático |
| `_env()` en `core/config.py` para todas las env vars críticas | `os.getenv()` directo | Railway (y algunos shells CI) inyectan valores con comillas circundantes (`"value"`) — `_env()` las strippea; `os.getenv` directo las deja |
| Orquestador keyword-first, LLM como fallback | Solo LLM para routing | Keywords O(1) sin latencia; el LLM introduce 200–500ms; el fallback LLM captura solo los casos ambiguos que los keywords no cubren |
| Lazy initialization de VectorStore y EmbeddingModel | Eager init en startup | `sentence-transformers` carga torch (~60–120s); QdrantClient inicia storage embebido; lazy garantiza que uvicorn bindee el puerto en <1s y Railway no falla el healthcheck |
| SemanticCache con `_exact: dict` O(1) + cosine similarity como fallback | Solo cosine similarity | El dict O(1) evita llamar MiniLM para hits exactos (mismo texto + modelo + TTL vigente); la cosine similarity captura paráfrasis — ambos se complementan |
| Hardware Agent bypassa el LLM principal cuando `agents_used == ["hardware"]` | Siempre pasar por LLM principal | El LLM principal reescribía o contradecía la respuesta del HardwareAgent (que incluye código C++ ya validado); el bypass preserva el firmware generado intacto |
| Título de sesión con fallback inmediato + LLM en background | Bloquear `done` hasta tener título LLM | La generación LLM del título tomaba 2–4s extra en el `done`; con `asyncio.create_task` el `done` llega inmediato y el título actualiza el sidebar vía evento `session_title` separado |

---

## 16. CONTRATOS DE API INTERNA

Funciones públicas críticas que varios módulos consumen. Cambiar la firma o el contrato requiere grep de todos los callers.

### `llm/async_client.py`

| Función | Firma | Contrato |
|---|---|---|
| `call_llm_async` | `(messages, temperature=0.7, timeout=120.0, agent_id, agent_name, tools=None, model=None) → dict` | Retorna response JSON completo (`choices[0].message.content`). **Raise** `httpx.HTTPError` en fallo HTTP. Usar cuando se necesita el dict completo (tool calling, finish_reason, etc.) |
| `call_llm_text` | `(messages, temperature=0.0, timeout=30.0, agent_id, agent_name, model=None, use_cache=True) → str` | Retorna solo el texto de la respuesta. **Nunca raise** — retorna `""` en error. Activa SemanticCache cuando `temperature==0.0 and use_cache==True`. El modelo default es `get_llm_model()` (runtime, no frozen). |
| `stream_llm_async` | `(messages, on_token, temperature=0.7, agent_id, agent_name, model=None) → str` | Llama `on_token(str)` por cada token recibido. Retorna texto completo al terminar. Nunca raise. `on_token` puede ser sync o async — el caller normaliza. |
| `close` | `() → None` | Cierra el `httpx.AsyncClient` compartido. Llamar solo en shutdown (una vez). |

### `llm/openrouter_client.py`

| Función | Firma | Contrato |
|---|---|---|
| `call_llm_sync` | `(messages, tools=None, model=None, response_format=None, timeout=120) → dict` | Versión **síncrona** bloqueante. Usada por `Orchestrator` (pasada como `client_fn`) y por cualquier código que corra fuera del event loop. Retorna el response dict completo o `{}` en error. |

### `core/prompt_builder.py`

| Función | Firma | Contrato |
|---|---|---|
| `build_prompt` | `(user_input, history, memories, facts, graph_context="", user_profile_context="", system_prompt=None, source_context="") → str` | Ensambla el prompt final para el LLM principal. Secciones vacías se omiten (no aparece el label "Memorias relevantes:" si `memories` está vacío). Agrega `"Hoy es {fecha}"` al base prompt. Orden de secciones: base → source_context → user_profile → facts → graph → memories → history → input. |

### `memory/vector_memory.py`

| Función | Firma | Contrato |
|---|---|---|
| `store_memory` | `(text, metadata=None) → bool` | Guarda episodio en Qdrant con consolidación previa. **Retorna `False`** si la memoria fue descartada por redundante (no guardar de nuevo). Tipos en `metadata["type"]` que saltean consolidación: `"knowledge"`, `"hardware"`, `"session_summary"`, `"fact_update"`, `"consolidated_summary"`. |
| `search_memory` | `(query, top_k=5) → list[str]` | Retorna lista de textos relevantes. Retorna `[]` si Qdrant no está disponible. LRU cache de 128 entradas / 5min. |
| `search_memory_with_scores` | `(query, top_k=5) → list[dict]` | Retorna `[{text, score, metadata}]`. Score es semántico × decay temporal (`MEMORY_DECAY_RATE`). |
| `search_in_sources` | `(query, source_ids, top_k=5) → str` | Filtra resultados por `metadata["source_id"] in source_ids`. Retorna string concatenado de los textos relevantes, o `""` si no hay resultados. |
| `invalidate_search_cache` | `() → None` | Invalida el LRU cache completo. Llamar tras guardar memorias relevantes que deben aparecer en búsquedas inmediatas. |

### `memory/fact_extractor.py`

| Función | Firma | Contrato |
|---|---|---|
| `extract_facts` | `async (text) → dict` | Extrae hechos del texto del usuario. **Early return `{}`** si `len(text) < 15` o ningún keyword coincide. Guarda automáticamente en DB via `store_fact`. Llama `memory_consolidator.process_new_fact` antes de guardar. Usa `call_llm_text` con `temperature=0`. |

### `database/sql_memory.py` — singleton `_default`

| Método | Firma | Contrato |
|---|---|---|
| `store_fact` | `(key, value, user_id="default")` | Upsert en tabla `facts`. Incrementa `_facts_seq` (dirty flag). |
| `get_all_facts` | `(user_id="default") → dict` | Retorna `{key: value}`. O(n) sobre la tabla. |
| `store_message` | `(role, content, session_id, user_id, elapsed_ms=None)` | Inserta en `conversations`. No actualiza `last_msg_at` de la sesión — llamar `touch_session` por separado. |
| `touch_session` | `(session_id, user_id="default")` | Upsert en `chat_sessions`. Crea la sesión si no existe. Llamar tras cada mensaje del usuario. |
| `get_conversation_by_session` | `(session_id, limit=20) → list[dict]` | Retorna `[{role, content, timestamp, elapsed_ms}]` ordenados cronológicamente. |
| `_facts_seq` | `int` (attr) | Incrementa en cada `store_fact`/`delete_fact`. El WS handler lo compara antes de incluir `facts` en el payload `done`. |

### `database/intelligence.py` — singleton `intelligence_db`

| Método | Firma | Contrato |
|---|---|---|
| `get_active_profile` | `() → dict \| None` | Retorna el perfil AI activo con campos: `system_prompt` (str), `active_sources` (list de source_ids). Si no hay perfil activo, retorna `None` y el AgentController usa el `DEFAULT_SYSTEM_PROMPT` de `prompt_builder.py`. |

---

## 17. COBERTURA DE TESTS

Tests actuales: **144 colectados en `tests/`** (120 passing, 3 failed, 21 errors pre-existentes). Más 3 en `eval/` offline + suites e2e que requieren servidor.

| Módulo | Tests | Cobertura | Notas |
|---|---|---|---|
| `tools/circuit_importer.py` | ✅ 18 | Alta | KiCad S-expr (v5/v6), Eagle XML, bounds validation, extensión |
| `database/circuit_design.py` | ✅ 22 | Media-alta | Versioning, sharing, update_circuit, user isolation |
| `tools/firmware_generator.py` | ✅ 16 | Media | Watchdog/OTA/STATE por plataforma, `_clean_code()` |
| `tools/circuit_importer.py` (eval) | ✅ 3 | Básica | `eval/test_full_integration.py` — KiCad + CircuitDesignManager básico |
| `agent/orchestrator.py` | ⚠️ 0 | Ninguna | Routing crítico — keywords y fallback LLM sin tests |
| `agent/agent_controller.py` | ⚠️ 0 | Ninguna | Pipeline principal — process_input sin tests |
| `memory/vector_memory.py` | ⚠️ 0 | Ninguna | store/search Qdrant — requiere mock de QdrantClient |
| `memory/fact_extractor.py` | ⚠️ 0 | Ninguna | LLM call interna — requiere mock de call_llm_text |
| `database/sql_memory.py` | ⚠️ 0 | Ninguna | CRUD principal — el conftest.py tiene `tmp_db` fixture disponible para usarlo |
| `llm/cache.py` | ⚠️ 0 | Ninguna | SemanticCache — lógica O(1) + cosine sin tests |
| `llm/async_client.py` | ⚠️ 0 | Ninguna | Client httpx — requiere mock de httpx |
| `tools/schematic_renderer.py` (facade) | ✅ — | Smoke import | Implementación real en `tools/eda/symbol_draw.py` |
| `tools/pcb_renderer.py` (facade) | ✅ — | Smoke import | Implementación real en `tools/eda/pcb_draw.py` |
| `tools/eda/classifier.py` | ✅ 16 | Buena | `tests/test_eda_classifier.py` — todas las zonas + heurísticas |
| `tools/eda/layout.py` | ✅ 15 | Buena | `tests/test_eda_layout.py` — relay grouping, zonas, snap, validate |
| `tools/eda/router.py` | ✅ 16 | Buena | `tests/test_eda_router.py` — widths, layers, skip <0.001mm |
| `tools/eda/symbol_draw.py` | ✅ 6 | Parity | `tests/test_eda_symbol_draw.py` — 4 parity tests vs renderer original |
| `tools/eda/pcb_draw.py` | ✅ 6 | Parity | `tests/test_eda_pcb_draw.py` — 4 parity tests vs renderer original |
| `tools/electrical_formulas.py` + módulos | ✅ sí | Media | `tests/test_electrical_formulas.py` cubre las 25 fórmulas |
| `tools/electrical_drc.py` | ⚠️ 0 | Ninguna | 15 DRC checks — lógica determinística, fácil de testear |
| `api/routers/*` | 0 | — | Solo via `eval/test_e2e_api.py` (requiere servidor en :8000) |
| `memory/memory_consolidator.py` | 0 | — | |
| `memory/graph_memory.py` | 0 | — | |
| `tools/firmware_flasher.py` | 0 | — | Requiere hardware físico |
| `tools/kicad_exporter.py` | 0 | — | `_make_custom_symbol`, pre-pass, `_abs_pin_pos` — candidatos a unit tests |
| `tools/kicad_pcb_exporter.py` | 0 | — | `_emit_footprint` SMD/THT branching — candidato a unit test |

> **Prioridad para agregar tests** (retorno más alto): `tools/electrical_formulas.py` (puras, 0 deps, cubrirían 25 fórmulas con ~30 tests), `tools/electrical_drc.py` (determinístico), `database/sql_memory.py` (conftest.py ya tiene `tmp_db`), `llm/cache.py` (O(1) dict + TTL lógica).

---

## 18. MAPA DE DEPENDENCIAS

Capas de dependencia de infraestructura hacia arriba. Una capa solo debe importar capas iguales o inferiores.

```
Capa 0 — Núcleo puro (solo stdlib, sin imports internos)
  core/config.py          ← os, logging
  core/logger.py          ← logging
  core/prompt_builder.py  ← datetime (stdlib)

Capa 1 — Infraestructura y clientes externos
  infrastructure/embeddings.py    ← core/config, core/logger + sentence-transformers (lazy)
  infrastructure/vector_store.py  ← infrastructure/embeddings, core/config + qdrant-client (lazy)
  llm/cache.py                    ← core/logger + hashlib, MiniLM (lazy via embeddings)
  llm/openrouter_client.py        ← core/config + httpx
  llm/async_client.py             ← core/config, core/logger + httpx
  database/sql_memory.py          ← core/config + sqlite3
  database/hardware_memory.py     ← database/hardware_{devices,firmware,circuits,projects}
  database/hardware_devices.py    ← core/config + sqlite3
  database/hardware_firmware.py   ← core/config + sqlite3
  database/hardware_circuits.py   ← core/config + sqlite3
  database/hardware_projects.py   ← core/config + sqlite3
  database/circuit_design.py      ← core/config + sqlite3
  database/design_decisions.py    ← core/config + sqlite3
  database/component_stock.py     ← core/config + sqlite3
  database/intelligence.py        ← core/config + sqlite3
  memory/graph_memory.py          ← core/config, core/logger + networkx
  memory/short_memory.py          ← core/config (MAX_SHORT_MEMORY) + collections

Capa 2 — Dominio de memoria (usa Capa 1)
  memory/vector_memory.py         ← infrastructure/vector_store, core/config, core/logger
                                    + memory/memory_consolidator (lazy, dentro de store_memory)
  memory/memory_consolidator.py   ← memory/vector_memory (⚠️ potencial circular — verificar),
                                    core/logger
  memory/graph_extractor.py       ← memory/graph_memory, llm/async_client
  memory/fact_extractor.py        ← database/sql_memory, llm/async_client, core/logger
                                    + memory/memory_consolidator (lazy)
  memory/pdf_memory.py            ← memory/vector_memory, core/logger

Capa 3 — Herramientas y knowledge (usa Capas 0-2)
  knowledge/knowledge_base.py     ← memory/vector_memory, core/logger
  tools/formulas_*.py             ← solo stdlib (math) — Capa 0 en la práctica
  tools/electrical_formulas.py    ← tools/formulas_* (re-export)
  tools/electrical_drc.py         ← stdlib
  tools/firmware_generator.py     ← llm/async_client, core/config, core/logger
  tools/firmware_flasher.py       ← core/config, core/logger + subprocess
  tools/schematic_renderer.py     ← core/logger + svgwrite
  tools/kicad_exporter.py         ← stdlib
  tools/circuit_importer.py       ← stdlib
  tools/bom_generator.py          ← stdlib
  tools/web_search.py             ← httpx
  tools/code_executor.py          ← stdlib (subprocess/exec)
  tools/tool_registry.py          ← memory/pdf_memory (⚠️ tools importa memory — cross-capa aceptado)
  tools/plugin_loader.py          ← core/logger
  tools/datasheet_fetcher.py      ← llm/async_client, knowledge/knowledge_base

Capa 4 — Agentes (usa Capas 0-3)
  agent/agents/base_agent.py      ← core/logger
  agent/agents/research_agent.py  ← tools/web_search, core/logger
  agent/agents/code_agent.py      ← tools/code_executor, core/logger
  agent/agents/memory_agent.py    ← memory/*, database/sql_memory, core/logger
  agent/agents/hardware_agent.py  ← database/hardware_memory, llm/*, tools/firmware_*,
                                    tools/schematic_renderer, agent/agents/hardware_*.py
  agent/agents/circuit_agent.py   ← database/circuit_design, tools/*, llm/openrouter_client
  agent/agents/electrical_calc_agent.py ← tools/electrical_formulas, llm/async_client
  agent/orchestrator.py           ← agent/agents/*, llm/async_client
  agent/agent_controller.py       ← agent/orchestrator, memory/*, database/sql_memory,
                                    core/prompt_builder, llm/*, agent/user_profiler
  agent/user_profiler.py          ← database/sql_memory, core/logger
  agent/proactive_*.py            ← agent/agents/*, memory/*, database/*, llm/*

Capa 5 — API (usa Capas 0-4)
  api/auth.py                     ← core/config, database/sql_memory
  api/routers/*.py                ← agent/*, database/*, memory/*, tools/*
  api/server.py                   ← api/routers/*, core/config
  api/job_worker.py               ← api/app_state

Capa 6 — Entrada (usa Capas 0-5)
  cli/*.py                        ← database/*, memory/*, core/*
  run.py                          ← cli/*, api/server (via uvicorn)
```

### Violaciones / anomalías conocidas

| Archivo | Problema | Riesgo |
|---|---|---|
| `memory/vector_memory.py` ↔ `memory/memory_consolidator.py` | Posible circular: `vector_memory` importa `memory_consolidator` dentro de `store_memory()`; verificar si `memory_consolidator` importa `vector_memory` a nivel módulo | ⚠️ verificar — si ambos importan en top-level → `ImportError` |
| `tools/tool_registry.py` | Capa 3 importa `memory/pdf_memory` (Capa 2) | Aceptado — dependency ascendente controlada |
| `api/routers/websockets.py` | Importa `api.app_state` dentro de la función WS (lazy) para evitar circular con `api/server.py` | Intencional — no romper |

## 19. FIXES MEDIO PRIORITY — v4.23.0 (2026-04-30)

6 fixes de prioridad MEDIA de la auditoría. 56/56 tests passing post-apply.

### Commits

| Hash | Descripción |
|------|-------------|
| (pendiente push) | `fix(quality): 6 medium-priority audit fixes` |

### Fix 1 — Connection leaks en `database/intelligence.py`

6 métodos abrían conexión sin context manager, dejando handles abiertos si ocurría una excepción.

| Método | Antes | Después |
|--------|-------|---------|
| `_init_tables` | `conn = self._conn()` + `conn.commit()` + `conn.close()` | `with self._conn() as conn:` |
| `create_profile` | ídem | ídem |
| `update_profile` | ídem + early-return con close manual | ídem — early-return sin close |
| `create_source` | ídem | ídem |
| `mark_indexed` | ídem | ídem |
| `delete_source` | ídem | ídem |

`sqlite3.Connection` como context manager hace auto-commit/rollback; la conexión es GC'd al salir del scope.

### Fix 2 — `pytest.ini` — evitar recolección de venv y eval

```ini
testpaths = tests
addopts = --ignore=venv --ignore=eval
```

Evita que pytest camine `venv/` (lento, falsos positivos) y `eval/` (scripts standalone que tocan DB de producción).

### Fix 3 — `eval/` tests — fixture `tmp_db`

- Creado `eval/conftest.py` con fixture `tmp_db` (parchea `database.circuit_design.DB_PATH` a DB temporal).
- `test_full_integration.py::test_complete_integration` recibe `tmp_db` como parámetro — ya no escribe en DB de producción si se corre con `pytest eval/`.
- `test_circuit_integration.py` no tiene funciones `test_*` → pytest no lo colecta; sigue siendo script standalone.

### Fix 4 — `tools/component_types.py` — tabla de dispatch única

Creado `tools/component_types.py` con definición canónica de:

```python
_MCU_TYPES       # idéntico en ambos renderers
_RELAY_TYPES     # idéntico en ambos renderers
_ZONE_SENSOR_TYPES  # unión de schematic (superset) + pcb (añade ina260, ultrasonic_sensor)
```

- `tools/schematic_renderer.py` y `tools/pcb_renderer.py` ahora importan desde ahí.
- `tools/kicad_pcb_exporter.py` no importa estos sets directamente → sin impacto.

### Fix 5 — Eliminar `package.json` / `package-lock.json`

4 paquetes `@aethermind/*` sin referencias en ningún archivo Python, Dockerfile ni `railway.toml`. Eliminados con `git rm`.

### Fix 6 — `requirements.txt` / `requirements-dev.txt`

| Cambio | Detalle |
|--------|---------|
| `numpy>=1.24.0,<2.0.0` | Upper bound para evitar breaking changes de NumPy 2.x |
| Creado `requirements-dev.txt` | `pytest>=8.0.0` y `pytest-asyncio>=0.23.0` movidos fuera de prod deps |
| `agent/agent_controller.py` | `import asyncio` debe estar a nivel módulo (corregido en v4.11.0) — cualquier nuevo método que use `asyncio.*` lo requiere | Monitorear en nuevos métodos |