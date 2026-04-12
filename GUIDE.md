# Stratum — Guía de ejecución y testing

## 1. Requisitos previos

| Herramienta | Versión mínima | Notas |
|-------------|----------------|-------|
| Python | 3.10+ | `python --version` |
| pip | cualquiera | incluido con Python |
| reportlab | 4.2.5 | para export PDF (`pip install reportlab`) |
| Node.js | opcional | solo para rebuild mobile |

---

## 2. Configuración inicial (primera vez)

```bash
# 1. Crear y activar entorno virtual
python -m venv venv
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Copiar .env de ejemplo y completar claves
copy .env.example .env
```

Editar `.env` — campos obligatorios:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...      # https://openrouter.ai/keys
LLM_MODEL_FAST=openai/gpt-4o-mini
LLM_MODEL_SMART=openai/gpt-4o
```

El resto de campos tiene defaults válidos para uso local.

---

## 3. Levantar el servidor

```bash
.\venv\Scripts\activate
python run.py
```

Salida esperada:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

La UI web se abre en: **http://localhost:8000**

---

## 4. Interfaz de usuario

### 4.1 Layout general

La UI tiene **un único sidebar izquierdo** (`w-72`) con dos secciones colapsables:

```
┌─────────────────┬────────────────────────────────┐
│  CONVERSACIONES │                                │
│  (flex-1)       │     ÁREA PRINCIPAL             │
│  ─────────────  │     (chat o vista de módulo)   │
│  MÓDULOS        │                                │
│  (contraído)    │                                │
└─────────────────┴────────────────────────────────┘
```

- **CONVERSACIONES** — lista de sesiones de chat, ocupa la mayor parte del sidebar
- **MÓDULOS** — navegación a los paneles: DEVICES, INTEL, CALC, METRICS, SYSTEM

No hay sidebar derecho. Los módulos se abren en el área principal como vistas de pantalla completa.

### 4.2 Sesiones de chat

Cada conversación es una sesión independiente con memoria persistida:

| Acción | Cómo |
|--------|------|
| Nueva sesión | Botón `+ NUEVA` junto al encabezado CONVERSACIONES |
| Cambiar sesión | Click en cualquier sesión de la lista |
| Renombrar | Doble click en el título de la sesión |
| Borrar | Ícono de papelera (aparece al hacer hover) |
| Auto-título | Se genera automáticamente del primer mensaje enviado |

Las sesiones se agrupan en: **Hoy / Ayer / Anterior**.

### 4.3 Navegación entre módulos

Click en cualquier botón de la sección MÓDULOS abre la vista correspondiente en el área principal. El botón **← VOLVER AL CHAT** regresa al chat activo sin perder el estado.

| Módulo | Contenido |
|--------|-----------|
| DEVICES | Dispositivos hardware, lista de jobs, estadísticas HW |
| INTEL | Base de conocimiento, decisiones de diseño |
| CALC | Calculadora de fórmulas de ingeniería |
| METRICS | KPIs, actividad reciente, estado de memoria |
| SYSTEM | Stock, circuitos, esquemáticos, configuración |

### 4.4 Indicadores de estado

En el **pie del sidebar** hay tres puntos de estado de servicios:
- `SQLite` — base de datos local
- `Qdrant` — memoria vectorial
- `Ollama` — LLM local (si está configurado)

El indicador de conexión WebSocket está en el encabezado (punto verde/rojo).

---

## 5. Tests automatizados

### 5.1 Suite completa (script unificado)

```bash
# Con el servidor ya levantado:
python guide-test.py
```

Opciones disponibles:

```bash
python guide-test.py --url http://localhost:8000   # URL del servidor
python guide-test.py --skip-slow                   # omite tests con LLM / WebSocket
python guide-test.py --only smoke                  # solo smoke test
python guide-test.py --only sessions               # solo tests de sesiones
python guide-test.py --only circuits               # solo tests de circuitos
```

Suites disponibles con `--only`:

| Suite | Qué testea |
|-------|-----------|
| `smoke` | Health, stats, fórmulas |
| `sessions` | CRUD completo de sesiones de chat |
| `stock` | Componentes: create, read, search, adjust, delete |
| `calc` | Calculadora de fórmulas |
| `decisions` | Decisiones de diseño |
| `circuits` | Parse, DRC, BOM, CSV, PDF |
| `schematics` | Import KiCad/Eagle/LTspice |
| `hardware` | Dispositivos y firmware jobs |
| `intelligence` | Búsqueda semántica y grafo |
| `memory` | Facts, historial, perfil |
| `websocket` | Conexión WS chat y sesión |
| `pytest` | Ejecuta `pytest eval/` (requiere pytest) |

### 5.2 Tests legacy individuales

```bash
python eval/test_e2e_api.py           # E2E completo
python eval/test_circuit_integration.py
python eval/test_full_integration.py
python eval/run_eval.py               # Evaluación agente (127 casos)
```

---

## 6. Testing manual por feature

### 6.1 Health check

```
GET http://localhost:8000/api/health
```

Verificar:
- `status: "ok"`
- `routers_failed: []` — si hay routers fallidos, revisar consola

---

### 6.2 Sesiones de chat

**Crear sesión via API:**
```
POST http://localhost:8000/api/sessions
     body: {"title": "Test sesión"}
```

**Listar sesiones:**
```
GET http://localhost:8000/api/sessions
```

**Renombrar:**
```
PATCH http://localhost:8000/api/sessions/{id}/title
      body: {"title": "Nuevo título"}
```

**Borrar:**
```
DELETE http://localhost:8000/api/sessions/{id}
```

**Probar en UI:**
1. Abrir http://localhost:8000
2. Presionar `+ NUEVA` — debe aparecer nueva sesión en la lista
3. Escribir un mensaje → la sesión recibe el título del primer mensaje
4. Presionar `+ NUEVA` de nuevo → nueva sesión vacía
5. Hacer click en la sesión anterior → el chat cambia a esa conversación
6. Hover sobre una sesión → aparece el ícono de papelera
7. Click en papelera → confirmar eliminación

---

### 6.3 Chat principal

1. Abrir http://localhost:8000
2. Escribir en el input: `"Calcular resistencia para LED rojo a 5V"`
3. Verificar respuesta con el valor calculado (220Ω aprox.) y explicación

Casos a probar:

| Input | Resultado esperado |
|-------|--------------------|
| `"¿Cuánto consume un motor de 12V y 2A?"` | Respuesta con 24W |
| `"LED azul 3.3V 20mA, calcular R"` | ~68Ω, valor E24 sugerido |
| `"Convertidor BUCK 12V a 5V, 1A, eficiencia 85%"` | Duty cycle, corriente |
| `"¿Qué es un capacitor de desacople?"` | Explicación técnica |

---

### 6.4 Motor de cálculo — CALC

1. Ir a módulo **CALC** (sidebar → MÓDULOS → CALC)
2. Seleccionar fórmula en el dropdown
3. Completar parámetros y presionar **⚡ CALCULAR**

Fórmulas a verificar:

| Fórmula | Parámetros de prueba | Resultado esperado |
|---------|---------------------|-------------------|
| `resistor_for_led` | Vcc=5, Vled=2.1, Iled_mA=20 | ~145Ω → std 150Ω |
| `ohms_law` | voltage=12, resistance=220 | ~54.5 mA |
| `buck_converter` | Vin=12, Vout=5, Iout=1 | duty≈41.7%, Iin≈0.49A |
| `battery_autonomy` | capacity_mAh=2000, current_mA=50 | ~37h |
| `heat_sink_required` | power_W=10, Tjmax=150, Ta=25 | θ_required calculado |
| `capacitor_filter` | frequency=100, ripple_mV=50, current_A=1 | capacitancia en µF |

---

### 6.5 Stock de componentes — SYSTEM

**Agregar componente:**
1. Ir a módulo SYSTEM → sección STOCK
2. Completar el formulario: nombre, categoría, cantidad, costo unitario
3. Presionar ADD
4. Verificar que aparece en la lista

**Buscar:**
1. Escribir en el campo de búsqueda: `"resistencia"`
2. Verificar que filtra resultados

**Ajustar cantidad:**
1. En un componente existente, presionar `+` o `-`
2. Verificar que el stock cambia

**Endpoints:**

```
GET  http://localhost:8000/api/stock
GET  http://localhost:8000/api/stock/categories
GET  http://localhost:8000/api/stock/summary
GET  http://localhost:8000/api/stock/search?q=resistencia
POST http://localhost:8000/api/stock   body: {"name":"R 220Ω","category":"resistencia","quantity":100,"unit_cost":0.05}
```

---

### 6.6 Parsear circuito — SYSTEM → CIRCUIT_VIEWER

**Parsear desde texto:**
```
POST http://localhost:8000/api/circuits/parse?description=LED+rojo+parpadeante+con+Arduino+Uno&mcu=Arduino+Uno
```

O vía chat: `"Diseñar circuito: LED parpadeante con Arduino"`

Verificar en respuesta:
- `design_id` presente
- `components` con U1 (Arduino), R1 (resistencia), D1 (LED), C1 (decoupling)
- `warnings` — si el LLM omitió algo, debe aparecer `[Auto]`
- `drc` — objeto con `passed`, `errors`, `warnings`

**Circuit Viewer UI:**
1. En módulo SYSTEM, expandir sección CIRCUIT_VIEWER
2. Ingresar el ID obtenido
3. Presionar **DRC** → muestra tabla de errores/warnings
4. Presionar **BOM** → muestra tabla con costos del stock
5. Presionar **CSV** → descarga archivo `.csv`

---

### 6.7 DRC eléctrico

```
GET http://localhost:8000/api/circuits/{id}/drc
```

Respuesta esperada:

```json
{
  "errors": [],
  "warnings": [{"code": "NO_DECOUPLING_CAP", ...}],
  "passed": true,
  "summary": "0 errores, 1 advertencia",
  "counts": {"errors": 0, "warnings": 1, "info": 0}
}
```

**Para probar detección de errores:** Crear circuito con `"LED directo a 5V sin resistencia"` → DRC debe reportar `LED_WITHOUT_RESISTOR`.

---

### 6.8 BOM con costos

```
GET http://localhost:8000/api/circuits/{id}/bom
GET http://localhost:8000/api/circuits/{id}/bom.csv
```

Verificar:
- `lines` tiene una entrada por componente
- `total_cost` es la suma de `unit_cost` del stock
- `missing_components` lista los que no tienen match en stock
- CSV descargado tiene header + filas + fila TOTAL

---

### 6.9 Export PDF

```
GET http://localhost:8000/api/circuits/{id}/report.pdf
GET http://localhost:8000/api/circuits/{id}/report.pdf?include_firmware=false&include_decisions=false
```

El PDF debe contener (en orden):
1. Header con nombre del circuito y fecha
2. Descripción
3. Tabla de componentes
4. Redes / Nets
5. Firmware (si `include_firmware=true` y existe)
6. Decisiones de diseño (si `include_decisions=true`)
7. Tabla DRC con severidad, código, componente y mensaje
8. Tabla BOM con ref, nombre, stock, supplier y costo
9. Footer

---

### 6.10 Decisiones de diseño — INTEL

**Agregar decisión:**
1. Ir a módulo **INTEL** → sección DESIGN_DECISIONS
2. Completar: proyecto, componente, decisión, razonamiento
3. Presionar GUARDAR

**Endpoints:**
```
GET  http://localhost:8000/api/decisions
POST http://localhost:8000/api/decisions   body: {"project":"Test","component":"U1","decision":"Usar Arduino Uno","reasoning":"más familiar"}
GET  http://localhost:8000/api/decisions?project=Test
```

---

### 6.11 Import de esquemáticos

```
GET  http://localhost:8000/api/schematics/supported
POST http://localhost:8000/api/schematics/import
     body: {"content": "<xml KiCad/Eagle/LTspice>", "format": "kicad"}
```

Formatos soportados: `kicad`, `eagle`, `ltspice`, `json`

---

### 6.12 Simulación Wokwi

```
POST http://localhost:8000/api/circuits/{id}/simulate
```

Sin `WOKWI_CLI_TOKEN` en `.env`, retorna `diagram_json` para cargar en wokwi.com manualmente.

---

### 6.13 Generación de firmware (async)

```
POST http://localhost:8000/api/circuits/{device_name}/generate-firmware
     body: {"device_name": "mi_arduino", "task_description": "Parpadear LED en pin 13"}

# Verificar estado del job:
GET http://localhost:8000/api/jobs/{job_id}
```

Verificar:
- Retorna `{job_id, status: "pending"}` inmediatamente
- Polling del job hasta `status: "done"` o `"error"`
- Resultado contiene `firmware_path`, `code`, `attempts`
- El badge flotante (esquina inferior derecha) muestra el contador de jobs activos

---

### 6.14 Métricas — METRICS

1. Ir a módulo **METRICS**
2. Verificar KPIs: total memories, firmware flashes, circuits, decisions
3. Verificar timeline ACTIVIDAD_RECIENTE (muestra últimos eventos FLASH/DECISION mezclados)
4. Presionar REFRESH METRICS

---

### 6.15 Hardware Bridge (programación remota)

Solo si se tiene el cliente bridge corriendo en la PC con Arduino:

```bash
# En la PC con Arduino conectado:
python tools/hardware_bridge_client.py --url ws://localhost:8000/ws/hardware-bridge --token <BRIDGE_TOKEN>
```

Verificar en módulo DEVICES: punto verde + `CONNECTED`.

---

## 7. Verificación rápida (smoke test)

```bash
# Terminal 1 — servidor
.\venv\Scripts\activate && python run.py

# Terminal 2 — smoke test
python guide-test.py --only smoke
```

O manualmente en 30 segundos:

```bash
python -c "
import requests
base = 'http://localhost:8000'
h = requests.get(f'{base}/api/health').json()
print('Health:', h['status'], '| Routers fallidos:', h.get('routers_failed', []))
s = requests.get(f'{base}/api/stats').json()
print('Memories:', s.get('facts_count', 0), 'facts,', s.get('messages_count', 0), 'messages')
c = requests.get(f'{base}/api/calc/formulas').json()
print('Fórmulas:', len(c.get('formulas', [])))
sess = requests.get(f'{base}/api/sessions').json()
print('Sesiones:', len(sess.get('sessions', [])))
print('OK — servidor operativo')
"
```

---

## 8. Problemas frecuentes

| Problema | Causa probable | Solución |
|----------|----------------|----------|
| `ImportError: reportlab` | No instalado | `pip install reportlab` |
| `OPENROUTER_API_KEY inválida` | Key vencida o incorrecta | Renovar en https://openrouter.ai/keys |
| `402` en respuestas LLM | Saldo insuficiente | Recargar en https://openrouter.ai/credits |
| `Qdrant error` | Directorio `./memory_db` sin permisos | `mkdir memory_db` |
| PDF vacío / error 503 | reportlab no instalado | `pip install reportlab==4.2.5` |
| DRC retorna 404 | circuit_id no existe | Parsear un circuito primero |
| Port 8000 ocupado | Otro proceso usando el puerto | Cambiar `PORT=8001` en `.env` |
| `sentence-transformers` lento | Descarga modelo embedding (1ª vez) | Esperar ~2 min la primera vez |
| Sesiones no aparecen en sidebar | `chat_sessions` table no migrada | Reiniciar el servidor (migrations auto) |
| Chat no responde tras cambiar sesión | WS reconectándose | Esperar 1-2 segundos (reconexión auto) |

---

## 9. Estructura de directorios relevante

```
ai-memory-engine/
├── run.py                      # Punto de entrada
├── guide-test.py               # Script maestro de tests
├── GUIDE.md                    # Esta guía
├── .env                        # Variables de entorno (no commitear)
├── requirements.txt
├── api/
│   ├── server.py               # FastAPI app + routers
│   ├── routers/
│   │   ├── circuits.py         # /api/circuits — parse, DRC, BOM, PDF
│   │   ├── stock.py            # /api/stock — componentes
│   │   ├── decisions.py        # /api/decisions — diseño
│   │   ├── calc.py             # /api/calc — calculadoras
│   │   ├── hardware.py         # /api/hardware — devices, firmware
│   │   ├── schematics.py       # /api/schematics — import KiCad/Eagle
│   │   ├── memory.py           # /api/sessions + /api/facts + /api/stats
│   │   └── websockets.py       # /ws/chat — WebSocket con sesiones
│   └── static/
│       ├── index.html          # UI web principal (sesiones + vistas)
│       └── circuit_viewer.html # Visor SVG de circuitos
├── tools/
│   ├── electrical_drc.py       # Motor DRC — 14 reglas
│   ├── electrical_formulas.py  # 25 fórmulas de ingeniería
│   ├── bom_generator.py        # BOM con costos
│   ├── pdf_exporter.py         # Export PDF (DRC + BOM incluidos)
│   └── schematic_renderer.py   # Render SVG
├── agent/
│   ├── orchestrator.py         # Router de agentes
│   └── agents/
│       ├── circuit_agent.py    # Parseo de circuitos + DRC auto
│       └── electrical_calc_agent.py  # Cálculos eléctricos
├── database/
│   ├── sql_memory.py           # SQLite: facts, conversations, chat_sessions
│   ├── component_stock.py      # Stock con unit_cost
│   ├── circuit_design.py       # Diseños guardados
│   └── design_decisions.py     # Decisiones de diseño
└── eval/
    ├── test_e2e_api.py         # Tests E2E completos
    ├── test_circuit_integration.py
    └── run_eval.py             # Evaluación del agente (127 casos)
```
