# STRATUM — Agente de IA para Electrónica e Ingeniería

## Visión del Producto

Stratum es un **super-ingeniero de IA** especializado en electrónica, microcontroladores y sistemas embebidos. Permite al usuario diseñar circuitos, generar esquemáticos, layouts PCB y firmware mediante lenguaje natural. También detecta, identifica y controla hardware conectado al PC (Arduino, ESP32, Raspberry Pi Pico, STM32, etc).

**No es un wrapper de ChatGPT.** El núcleo de diseño de circuitos es determinístico — Python puro, sin LLM.

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| API | FastAPI + uvicorn |
| WebSocket | FastAPI WebSocket nativo |
| LLM | OpenRouter (GPT-4o-mini por defecto) / Ollama local |
| Persistencia SQL | SQLite via `database/__init__.py::get_db_path()` |
| Vector store | Qdrant (cloud o embebido local) |
| Grafo de memoria | NetworkX → JSON en disco |
| Frontend | HTML/JS estático + Three.js r128 |
| Mobile | Eliminado del repo principal |
| Deploy | Local (`python run.py serve`) |
| Tests | pytest 373+ tests |

---

## Arquitectura

```
HTTP/WS (api/server.py + routers)
        │
        ▼
SessionStore[sid] → AgentState (history, facts, active_circuit)
        │
        ▼
AgentController.process_input()
   ├── extract_facts()         → SQLite + NetworkX
   ├── extract_relations()     → NetworkX
   ├── search_memory()         → Qdrant + decay temporal
   └── Orchestrator.run()      → timeout 180s
          ├── keyword_route()  → zero-LLM, regex
          └── LLM fallback     → direct
                ↓
         [circuit_design] → CircuitAgent → CircuitSynthesizer (determinístico)
         [hardware]       → HardwareAgent | ElectricalCalcAgent
         [research/code]  → BaseAgent ReAct (max 4 pasos)
         [memory]         → MemoryAgent (SQL + Qdrant + NetworkX)
                ↓
        build_prompt() → stream_llm_async() → WS frame
```

### Pipeline EDA (circuitos)

```
Input usuario (lenguaje natural)
        ↓
LLM — extrae spec estructurada
        ↓
CircuitSynthesizer (Python puro, sin LLM)
  ├── _add_*_block() por tipo de componente
  ├── PinAllocator — asigna GPIO sin conflictos
  ├── BusManager — I2C/SPI/UART compartidos
  └── ElectricalDRC — reglas eléctricas
        ↓
Netlist: {components[], nets[], placement_hints}
        ↓
┌──────────────────────────────────────┐
│  tools/eda/                          │
│  ├── classifier.py  → zonas         │
│  ├── layout.py      → posiciones    │
│  ├── router.py      → wires/trazas  │
│  ├── symbol_draw.py → SVG esquema   │
│  └── pcb_draw.py    → SVG PCB       │
└──────────────────────────────────────┘
        ↓
Renders: schematic.svg | pcb.svg | pcb.json | gerber | kicad
        ↓
circuit_viewer.html (Three.js PCB 3D)
```

---

## Variables de Entorno

```env
# LLM
LLM_PROVIDER=openrouter          # openrouter | ollama | lmstudio
LLM_MODEL_FAST=openai/gpt-4o-mini
LLM_MODEL_SMART=openai/gpt-4o-mini
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
MAX_TOKENS=4096                  # límite explícito por request

# Base de datos local
DATA_DIR=./database              # todas las DBs van aqui
GRAPH_DB_PATH=./database/graph_memory.json
VECTOR_DB_PATH=./memory_db

# Qdrant (opcional — si no se define usa embebido local)
QDRANT_URL=https://...qdrant.io
QDRANT_API_KEY=...
QDRANT_COLLECTION=agent_memory

# Auth
JWT_SECRET=...                   # requerido si MULTI_USER=true
MULTI_USER=false

# Misc
MEMORY_DECAY_RATE=0.01
```

### Variables locales (NO commitear)

```env
DISABLE_SSL_VERIFY=true          # solo en Windows local
```

---

## Estructura de Directorios

```
ai-memory-engine/
├── agent/
│   ├── agent_controller.py      # orquesta cada turno
│   ├── orchestrator.py          # routing keyword → agente
│   ├── session_store.py         # LRU+TTL+SQL hydration
│   └── agents/
│       ├── circuit_agent.py     # pipeline EDA
│       ├── hardware_agent.py    # hardware detection
│       ├── electrical_calc_agent.py
│       ├── code_agent.py        # firmware Arduino/MicroPython
│       ├── research_agent.py
│       └── memory_agent.py      # SQL + Qdrant + NetworkX
├── api/
│   ├── server.py                # FastAPI app + lifespan
│   └── routers/
│       ├── websockets.py        # /ws/chat principal
│       ├── circuits.py          # /api/circuits/*
│       ├── hardware.py          # /api/hardware/*
│       ├── knowledge.py         # /api/knowledge/*
│       ├── calc.py              # /api/calc/*
│       └── ...
├── tools/
│   ├── circuit_synthesizer.py   # NÚCLEO — síntesis determinística
│   ├── eda/
│   │   ├── classifier.py        # zonas de componentes
│   │   ├── layout.py            # posiciones x,y
│   │   ├── router.py            # wires y trazas
│   │   ├── symbol_draw.py       # SVG esquemático
│   │   ├── pcb_draw.py          # SVG PCB
│   │   └── component_registry/  # pines + criticals por tipo
│   ├── design_rules.py          # hojas normalizadas, grid, clearances
│   ├── component_types.py       # sets de tipos compartidos
│   ├── electrical_drc.py        # Design Rule Check
│   ├── firmware_generator.py    # genera código Arduino/MicroPython
│   ├── hardware_detector.py     # detecta USB/serial devices
│   ├── firmware_flasher.py      # flashea via arduino-cli/mpremote
│   └── serial_monitor.py        # monitor serial básico
├── database/
│   ├── __init__.py              # get_db_path() — fuente de verdad
│   ├── sql_memory.py            # facts, conversations, sessions
│   ├── circuit_design.py        # diseños guardados
│   └── component_stock.py       # inventario de componentes
├── memory/
│   ├── graph_memory.py          # NetworkX → JSON
│   ├── fact_extractor.py        # LLM → facts estructurados
│   └── graph_extractor.py       # LLM → relaciones
├── infrastructure/
│   └── vector_store.py          # Qdrant wrapper
├── llm/
│   ├── async_client.py          # cliente httpx async principal
│   └── json_utils.py            # strip_fences()
├── core/
│   ├── config.py                # todas las vars de entorno
│   └── prompt_builder.py        # system prompt + contexto
├── api/static/
│   ├── index.html               # frontend principal
│   ├── circuit_viewer.html      # viewer: esquemático + PCB 3D + layout
│   └── modules/
│       ├── chat.js              # WebSocket + UI chat
│       ├── circuits.js          # integración viewer
│       ├── kb.js                # knowledge base UI
│       ├── calc.js              # calculadora
│       ├── hardware.js          # devices UI
│       ├── intelligence.js      # perfiles + decisiones
│       ├── metrics.js           # stats UI
│       └── stock.js             # inventario UI
├── tests/                       # 373+ tests pytest
├── docs/
│   ├── STRATUM.md               # ESTE ARCHIVO — fuente de verdad
│   ├── ARCHITECTURE.md          # análisis técnico detallado
│   └── PRE_CLEANUP_AUDIT.md     # auditoría pre-limpieza
├── Dockerfile
├── railway.toml
└── requirements.txt
```

---

## Estado Actual — Lo que Funciona

| Feature | Estado |
|---|---|
| Chat con memoria persistente | ✅ Funcional |
| Síntesis de circuitos determinística | ✅ Funcional |
| Esquemático 2D (SVG) con frame ISO | ✅ Funcional |
| PCB Layout 2D con trazas por capas | ✅ Funcional |
| PCB 3D viewer (Three.js desde pcb.json) | ✅ Funcional |
| Botón Flip en PCB 3D | ✅ Funcional |
| Tooltip hover en PCB 3D | ✅ Funcional |
| DRC eléctrico | ✅ Funcional |
| Export KiCad (.kicad_sch / .kicad_pcb) | ✅ Parcial (sin validación GUI) |
| Export BOM CSV | ✅ Funcional |
| Export Gerber | ⚠️ Experimental (no validado para manufactura) |
| Cálculo eléctrico (Ohm, divisores, etc.) | ✅ Funcional |
| Fast path (saludos, fecha/hora) | ✅ Funcional (<1s) |
| Detección hardware USB/serial | ✅ Implementado (no testeado con hw real) |
| Generación de firmware Arduino | ✅ Implementado |
| Knowledge base (upload + búsqueda) | ✅ Parcial (bug Qdrant lazy init) |
| Auth JWT multi-usuario | ✅ Implementado (MULTI_USER=false por defecto) |
| Deploy local | Funcional |
| Cache busting dinámico (git hash) | ✅ Funcional |

---

## Bugs Conocidos y Pendientes

### Críticos

| Bug | Archivo | Fix |
|---|---|---|
| Chat no restaura historial tras restart backend | `api/static/modules/chat.js` | Resuelto 2026-05-12: rehidrata tras limpiar DOM por nuevo `server_start` |
| Panel SYSTEM/stock desalineado (IDs distintos) | `stock.js` vs `index.html` | Resuelto 2026-05-12: JS alineado a IDs `stock-*` reales |
| MEMORY_DB_PATH documentado pero ignorado en runtime | `core/config.py` | Unificar: runtime usa `DATA_DIR` via `get_db_path()` |

### Medios

| Bug | Archivo | Fix |
|---|---|---|
| KB lista vacía si Qdrant no inicializó | `knowledge/knowledge_base.py` | Resuelto 2026-05-12: guard lazy antes de `scroll`, sin log de error en startup |
| CALC avanzado no cableado al DOM | `modules/calc.js` | Resuelto 2026-05-12: DOM actual `calc-R/C/out` usa `/api/calc/compute` |
| `_store_episode()` duplica mensajes en sesión `default` | `agent/agent_controller.py` | Resuelto 2026-05-12: se propaga `session_id`, fallback `_default` |
| QDRANT_COLLECTION documentado pero ignorado | `core/config.py` | Resuelto 2026-05-12: lee `QDRANT_COLLECTION`, fallback `VECTOR_COLLECTION` |
| Gerbers no validados para manufactura | `tools/eda/pcb_draw.py` | Agregar validación con gerbv o kicad-cli |

### Bajos

| Bug | Fix |
|---|---|
| Botones Gerber/Firmware/Simular en viewer son placeholders | Resuelto 2026-05-12: conectados a endpoints reales o modal claro |
| Logs exponen prefijo de API key en startup | Resuelto 2026-05-12: solo loguea si la key esta configurada |
| Knowledge graph tiene nodos stale | Regenerar tras limpieza |

---

## Componentes Soportados

### Síntesis (CircuitSynthesizer)

MCUs: `esp32`, `esp8266`, `arduino_uno`, `arduino_nano`, `arduino_mega`, `stm32`, `raspberry_pi_pico`

Sensores: `bmp280`, `bme280`, `dht22`, `dht11`, `mpu6050`, `ds18b20`, `hc_sr04`, `pir`, `ina219`, `hx711`, `ds3231`, `moisture_sensor`, `mq2`, `mq7`, `mq135`

Comunicación: `sx1276` (LoRa), `hc05` (Bluetooth), `nrf24l01`, `esp8266` (WiFi)

Display: `oled`, `lcd_i2c`, `tft`

Actuadores: `relay`, `l298n`, `drv8825`, `a4988`, `servo`, `neopixel`, `motor_dc`

Power: `lm7805`, `lm1117`, `ams1117`, `transformer`, `bridge_rectifier`

Protección: `fuse`, `varistor`, `diode`, `transistor_npn`

### Component Registry (criticals de hardware)

Componentes con criticals documentados para prevenir daño:
- `nrf24l01`: VCC máx 3.6V — 5V destruye
- `hc05`: RXD máx 3.3V — 5V daña
- `drv8825` / `a4988`: Cap 100µF VMOT obligatorio
- `servo`: Fuente externa requerida (picos 1A+)
- `neopixel`: R 300-500Ω en DATA obligatoria
- `mq2` / `mq7` / `mq135`: Calentamiento 2min antes de lectura

---

## Reglas de Diseño EDA

```python
# Hojas normalizadas (design_rules.py)
1-8 comps   → A4 (297×210mm, grid 2.54mm)
9-20 comps  → A3 (420×297mm, grid 2.54mm)
21-40 comps → A2 (594×420mm, grid 2.54mm)
41+ comps   → A1 (841×594mm, grid 2.54mm)

# Anchos de traza PCB
GND         → 1.0mm
VCC/*       → 0.5mm
I2C/SPI     → 0.3mm
señales     → 0.25mm

# Zonas de layout (izquierda → derecha)
ac → power → mcu → sensor → other → relay → output
```

---

## Tests

```bash
# Correr todos los tests
pytest -q

# Tests EDA solamente
pytest tests/test_eda_* tests/test_pcb_json_endpoint.py -q

# Con DB temporal explícita
DATA_DIR=.pytest-data-dir pytest -q
```

Estado actual: **373 passed**

---

## Deploy Local

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu OPENROUTER_API_KEY

# 4. Correr
python run.py serve --port 8080

# 5. Tests
pytest -q
```

---

## Roadmap

### Semana 1 — Base estable
- [x] Fix: chat rehidrata historial tras restart backend
- [x] Fix: alinear stock.js con DOM actual (SYSTEM)
- [x] Fix: KB `_ensure_connected()` antes de list
- [x] Fix: `_store_episode()` pasar session_id
- [x] Fix: CALC conectar al backend real
- [x] Fix: QDRANT_COLLECTION desde env
- [x] Fix: viewer sin botones placeholder vacios
- [x] Fix: no loguear prefijos de API key
- [x] Fix: guards para IDs legacy en JS
- [x] Fix: health check profundo de Qdrant

### Semana 2 — EDA quality
- [ ] Símbolos propios para sensores faltantes (MQ-*, HC-SR04, PIR)
- [ ] Footprints realistas para a4988, drv8825, servo, l298n
- [ ] Validación Gerber con gerbv/kicad-cli
- [ ] Modelos 3D por footprint desde registry

### Semana 3 — Frontend consolidado
- [x] Limpiar IDs legacy de módulos JS
- [x] Cablear botones placeholder del viewer
- [ ] WebSocket serial monitor en UI
- [ ] Módulo hardware con scan real

### Semana 4 — Producción
- [ ] Tests con mocks de hardware
- [ ] Fallback si OpenRouter está caído
- [ ] Rate limit por usuario
- [ ] Pruning automático de NetworkX/Qdrant

---

## Principios de Desarrollo

1. **El LLM interpreta. El sistema diseña.** CircuitSynthesizer es determinístico — misma spec → mismo circuito.
2. **Surgical changes.** No refactorizar lo que no está roto.
3. **Tests antes de commits.** 373+ passing antes de cada push.
4. **Sin LLM theater.** Si se puede hacer con código, no usar LLM.
5. **Cache busting dinámico.** El JS se versiona con el git hash del commit.
6. **Lazy DB init.** Las DBs se inicializan en el primer request, no en startup.

---

*Ultima actualizacion: 2026-05-12 | Semana 1 fixes aplicados | Commit base: main*
