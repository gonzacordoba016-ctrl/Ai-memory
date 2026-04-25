# REPORTE DE ANÁLISIS — GENERACIÓN DE CIRCUITOS STRATUM
> Fecha: 2026-04-24  
> Circuito analizado: ID 16 — "Controlador de Bombas de Presión" (5 bombas, 220VAC → 50VDC)  
> Sesión: `9b0fe0bb`

---

## 1. CONTEXTO DEL CASO DE USO

**Petición del usuario:**
1. "Necesito que diseñes un circuito para controlar 5 bombas de presion, tengo una entrada de 220v y necesito controlar la parte de 50v de los motores"
2. "diseña el pcb y esquematico" → **fue a agente DIRECT** (no generó nada)
3. "dame el esquematico" → fue a CIRCUIT_DESIGN → generó ID 16

**Lo que debería haberse generado:**
- 5 relays independientes (uno por bomba)
- Etapa de alimentación AC: fusible + varistor + filtro EMI
- Etapa de rectificación: transformador + puente rectificador + caps de filtro
- Etapa de regulación 5V para MCU
- Fuente 50VDC para bombas (o SMPS externo)
- MCU (Arduino Mega) con pines D22-D30 para relays
- 5 optoacopladores para aislamiento galvánico
- Conectores de salida por bomba

---

## 2. PROBLEMA A: ROUTING — "diseña el pcb y esquematico" FUE A DIRECT

### Síntoma
Cuando el usuario dijo "diseña el pcb y esquematico", el agente respondió con instrucciones de texto para usar KiCad manualmente (agente DIRECT, 188.4s de respuesta). No se generó ningún circuito. Solo en la tercera petición ("dame el esquematico") se activó CIRCUIT_DESIGN.

### Causa raíz
`agent/orchestrator.py` — `CIRCUIT_DESIGN_KEYWORDS` no contiene la frase exacta.

Las keywords actuales incluyen:
- `"el esquematico y pcb"`, `"esquematico y pcb"` (sin acento)
- `"generame el pcb"`, `"dame el esquematico"` (sí está)

Pero NO incluyen:
- `"diseña el pcb y esquematico"` ← frase exacta del usuario
- `"diseña el esquematico y pcb"` ← variante
- `"diseña el pcb"` ← forma directa
- `"crear el esquematico"`, `"crear el pcb"`
- `"quiero el esquematico"`, `"quiero el pcb"`
- `"haceme el esquematico"`, `"haceme el pcb"`

Además, la keyword `"esquemático"` (con tilde) sí está en la lista de `hardware` keywords (línea ~114), lo que puede causar que algunas variantes vayan a HARDWARE en vez de CIRCUIT_DESIGN.

### Impacto: CRÍTICO
El usuario tuvo que enviar 3 mensajes para obtener lo que pidió en el 2do. La frase "diseña el pcb y esquematico" es la más natural en español argentino.

---

## 3. PROBLEMA B: LLM GENERA 1 RELAY EN VEZ DE 5

### Síntoma
El circuito ID 16 tiene 21 componentes pero **solo 1 relay (U2)**. El usuario pidió control de 5 bombas independientes. Se generó:
- `U2` — Relay Module 5V (SRD-05VDC-SL-C) — **uno solo**
- No hay U3-RL/RL2/RL3/RL4/RL5

### Causa raíz
El `CIRCUIT_PARSE_PROMPT` dice:
> "Un relay independiente (RLn) + diodo flyback (Dn) por cada carga"

Pero el LLM interpreta esto como "usar un relay modular que agrupa las 5 cargas" en lugar de generar 5 componentes JSON separados. El prompt no tiene una instrucción **explícita y cuantitativa** como:
> "CRÍTICO: si el usuario pide N cargas/bombas/motores, el JSON DEBE contener N componentes relay separados: RL1, RL2, ..., RLN, cada uno con su propio diodo flyback D_flyN y su propio net de control RELAYn_CTRL."

El prompt además dice "Relay individual por carga" en el domain_hint de `industrial`, pero el LLM también tiene la tendencia a generar un único "Relay Module" de múltiples canales (como un módulo relay de 8 canales) en vez de relays individuales.

### Evidencia del error
El campo `warnings` del circuito dice:
- `"[Auto] Diodo flyback D1 (1N4007) conectado para relay U2"` → solo hay 1 relay que necesita flyback
- `"Componente U3 (Optoacoplador PC817) no tiene nets asignados"` → el opto fue generado pero nunca conectado
- `"Nodo duplicado: J1.N en nets 'VCC_220VAC' y 'GND'"` → error en la netlist

### Impacto: CRÍTICO
Un controlador de 5 bombas con 1 relay es funcionalmente imposible de construir. El circuito generado no puede controlar 5 bombas independientemente.

---

## 4. PROBLEMA C: ESQUEMÁTICO — LAYOUT PLANO, ILEGIBLE

### Síntoma (observado en `esquematico 1.PNG` y `esquematico 2.PNG`)

**esquematico 1.PNG (vista general):**
- Todos los componentes están alineados en una sola fila horizontal en la parte superior del canvas
- Las conexiones (wires) caen verticalmente desde esa fila y luego van horizontalmente hasta conectar con el Arduino Mega (U1) en el centro-izquierda
- El canvas es extremadamente ancho (21 componentes × ~90px = ~1890px mínimo) pero los componentes se ven microscópicos
- El Arduino Mega aparece en la parte inferior-izquierda, aislado del resto
- Los 5 relays (que deberían ser 5 bloques distintos) no existen — solo hay 1

**esquematico 2.PNG (zoom en fila de componentes):**
- Los componentes son: D1, C1(100nF), C2(2200µF/DC_VCC), C3(100nF/RELAY1_CTRL), C4(10µF), GND, F1 (Fusible), F2 (Fusible)
- Están alineados perfectamente en una sola fila horizontal
- Las wires bajan verticalmente de cada componente y se unen en una línea horizontal inferior (bus)
- Esta topología es completamente al revés de cómo debería ser un esquemático:
  - En un esquemático real, la señal fluye de izquierda a derecha
  - La alimentación (VCC) va arriba y GND abajo
  - Las cargas (relays) están a la derecha del MCU
  - Los sensores/entrada están a la izquierda del MCU

### Causa raíz — `tools/schematic_renderer.py`

#### Causa raíz 1: Clasificación de grupos insuficiente
La función `_comp_group()` asigna componentes a 5 grupos: `mcu`, `input`, `output`, `power`, `comm`, `misc`.

Con 21 componentes del circuito ID 16:
- `mcu`: U1 (Arduino Mega) — 1 componente
- `output`: U2 (Relay Module) — 1 componente  
- `power`: C1, C2, C3, C4, D1, U5, U6 — ~7 componentes (arriba en fila)
- `misc`: U3, U4, U7, D2, F1, F2, L1, J1, J2, R1, R2, R3, R4, R5 — 14 componentes (fila inferior)

El grupo `misc` con 14 componentes se coloca todos en una sola fila inferior, con `spacing_x=110`. Eso crea una fila de 14×110 = 1540px de ancho. En un canvas de ~2100px, los componentes se apilan horizontalmente en una sola línea.

#### Causa raíz 2: La fila "power" va a Y=75 (arriba)
Los componentes de potencia (D1, C1, C2, C3, C4) van a `positions[comp["id"]] = (120 + i * pwr_step, max(75, spacing_y // 2))`. Esto los pone en la parte superior del canvas, antes que el MCU.

Para un circuito de potencia industrial, la topología correcta es:
```
[AC INPUT] → [EMI+Fuse] → [Transformer] → [Rectifier] → [Filter Caps] → [Regulators]
                                                                               ↓
                                                                          [MCU 5V]
                                                                               ↓
                                                                     [Relay drivers × 5]
                                                                               ↓
                                                                     [Output connectors × 5]
```

#### Causa raíz 3: Sin net labels — wires largas cruzadas
El renderer dibuja **wires físicas** entre todos los nodos de un net, usando `_route_orthogonal()`. Para un circuito con 16 nets y 21 componentes, esto genera docenas de líneas cruzadas.

En KiCad real, cuando un net tiene nodos en lugares muy separados, se usa un **net label** (una etiqueta de texto con el nombre del net) en vez de dibujar una wire larga. Así el esquemático queda limpio y readable.

El renderer actual no implementa net labels — todos los nodos se conectan con wires físicas, independientemente de la distancia.

#### Causa raíz 4: Símbolos no tienen pines orientados
El símbolo del MCU (`_sym_mcu()`) tiene 4 pines en cada lado (hardcodeados: `n_pins = 4`). Los pines no coinciden con los nets reales del circuito. En un esquemático profesional, los pines del MCU están orientados: señales a la derecha, alimentación arriba/abajo.

#### Causa raíz 5: Sin zonas/secciones visuales
Un esquemático industrial de esta complejidad debería tener:
- Zona AC (con borde de advertencia de alta tensión)
- Zona DC de control (5V)
- Zona DC de potencia (50V)
- Una línea de separación galvánica visible entre AC/control y potencia

El renderer no tiene concepto de zonas.

---

## 5. PROBLEMA D: PCB — LAYOUT COMPLETAMENTE INCORRECTO

### Síntoma (observado en `pcb 1.PNG` y `pcb 2.PNG`)

**pcb 1.PNG (vista general):**
- U2 (Relay Module) ocupa un bloque grande en la esquina superior-izquierda (~15% del board)
- U1 (Arduino Mega) está en el centro del board, mediano
- **19 componentes restantes están todos apiñados en una sola fila en la parte inferior** del board
- Hay una enorme área vacía en el centro-derecha del board
- Las trazas son largas, con muchos cruces

**pcb 2.PNG (zoom):**
- La fila inferior está tan comprimida que los labels de componentes se superponen
- U3 (Opto), U4 (Transformador), U5 (Puente rectificador), U6 (Regulador), U7 (SMPS), D2, F1, F2, L1, J1, J2 están todos en una fila de ~10px de altura
- Las trazas van de este cluster inferior al relay (superior-izquierda) y Arduino (centro) en largas líneas
- No hay separación entre la zona de alta tensión y la zona de control

### Causa raíz — `tools/pcb_renderer.py`

#### Causa raíz 1: Placement igual al mismo problema del schematic
`_place_components()` usa los mismos grupos: mcu (centro), small (cluster derecho-abajo), large (columna izquierda), misc (fila inferior).

Para 21 componentes:
- `mcu`: U1 → (cx, cy) — centro
- `large`: U2 (Relay) → (margin+20, margin+20) — esquina superior-izquierda
- `small`: R1-R5, C1-C4, D1, D2 → grid abajo-derecha del MCU
- `misc`: U3, U4, U5, U6, U7, F1, F2, L1, J1, J2 → fila inferior (`bx + i*14, by`)

Con `spacing = 14mm` entre misceláneos y 10 componentes, la fila inferior mide 140mm. Si `board_h = max(90, n*6+20) = max(90, 126+20) = 146mm`, la fila inferior en `by = 146-5-10 = 131mm` tiene 10 componentes en 14mm de paso. A 3.78px/mm, eso son ~53px entre componentes — muchos se superponen.

#### Causa raíz 2: `_board_size()` no escala bien con muchos componentes
```python
base_w = max(50.0, n * 8.0 + 30.0)  # 21 comps → 198mm → capped a 200mm
base_h = max(40.0, n * 6.0 + 20.0)  # 21 comps → 146mm → capped a 160mm
```
Con 21 componentes, el board es 200×160mm. Pero todos los large+misc van en la columna izquierda o fila inferior. El centro y la derecha quedan vacíos.

#### Causa raíz 3: No hay separación física AC/DC
Para un PCB de 220VAC, hay normativas de clearance (IPC-2221):
- Entre pistas de 220V y 5V: mínimo 2.5mm clearance
- No se pueden poner pistas de alta tensión paralelas a pistas de señal sin clearance

El PCBRenderer actual no tiene concepto de clearance zones ni copper pours aislados.

#### Causa raíz 4: Sin footprints correctos para módulos industriales
El dict `_FOOTPRINT` no tiene:
- Transformador (grande, ~80×60mm)
- SMPS module (Mean Well, ~80×40mm)
- Puente rectificador GBU (5×8mm)
- SSR relay (Fotek SSR-25DA, 45×53mm)
- Fusible porta-fusible (30×14mm)
- Inductor de modo común (grande)

Estos componentes tienen footprints incorrectos — caen en `_DEFAULT_FP = (10.0, 8.0)` que es demasiado pequeño.

---

## 6. PROBLEMA E: VISOR 3D — BAJA CALIDAD VISUAL

### Síntoma (observado en `3d 1.PNG` y `3d 2.PNG`)

**3d 1.PNG (vista general):**
- Componentes son mayormente cajas planas negras/grises sin diferenciación visual
- Layout tiene los mismos problemas del PCB (cluster de componentes en una esquina, el resto esparcido)
- Wires no son claramente visibles
- El relay (U2) es visible como caja azul grande
- El Arduino Mega es visible pero sus pines no se ven

**3d 2.PNG (zoom + ángulo diferente):**
- Se pueden ver ~25 componentes como cajas planas de distintos tamaños
- Los colores son: azul (relay), negro/gris oscuro (pasivos genéricos), rojo (algo), blanco (algo)
- No hay diferenciación visual entre: relay, transformador, regulador, capacitor, fusible
- Falta altura en los componentes — todo se ve en 2D flat sobre el PCB verde
- No hay cables de conexión visibles entre componentes

### Causa raíz — `api/static/circuit_viewer.html`

#### Causa raíz 1: Geometrías genéricas para tipos no mapeados
La función `_addComponent3D()` tiene casos específicos para: resistor, led, capacitor, diode, arduino, esp32, relay, display, l298n, y luego un `default` que genera una caja plana.

Los componentes del circuito ID 16 que no tienen geometría específica:
- `mcu` (genérico) → caja plana
- `optoacoplador` → caja plana
- `transformador` → caja plana
- `puente_rectificador` → caja plana
- `voltage_regulator` (LM7805) → caja plana (debería ser TO-220)
- `smps` → caja plana
- `varistor` → caja plana
- `fuse` → caja plana
- `inductor` → caja plana
- `connector` → caja plana

Solo relay y Arduino tienen geometría 3D específica. 19 de 21 componentes son cajas planas genéricas.

#### Causa raíz 2: Layout 3D hereda el layout PCB incorrecto
El 3D viewer usa las posiciones del circuito que vienen del PCB renderer. Si el PCB tiene layout incorrecto, el 3D también lo tiene.

#### Causa raíz 3: Cables (wires) casi invisibles
Los cables en 3D son arcos delgados (líneas ThreeJS). A la escala del board y con la iluminación actual, son prácticamente invisibles a menos que se haga zoom máximo.

---

## 7. PROBLEMA F: NETLIST TIENE ERRORES ESTRUCTURALES

### Síntoma
El circuito generado tiene estos warnings:
1. `"[Auto] Diodo flyback D1 (1N4007) conectado para relay U2"` — el auto-checker agregó un flyback pero con conexión incorrecta
2. `"Nodo duplicado: J1.N en nets 'VCC_220VAC' y 'GND'"` — el nodo J1.N está en dos nets simultáneamente
3. `"Componente U3 (Optoacoplador PC817) no tiene nets asignados"` — U3 fue generado pero el LLM no lo conectó a ningún net

### Causa raíz — `agent/agents/circuit_agent.py`

#### Causa raíz 1: Nodo duplicado no se corrige automáticamente
`_validate_circuit()` detecta nodos duplicados y los reporta como warnings, pero **no los corrige**. El circuito se guarda con el error. Cuando el renderer intenta conectar J1.N, lo dibuja en el net que lo encuentra primero.

#### Causa raíz 2: Componentes desconectados no se reconectan
`_validate_circuit()` detecta que U3 no tiene nets asignados y lo reporta, pero **no lo elimina ni lo conecta**. En el esquemático y PCB, U3 aparece como un componente flotante sin conexiones.

#### Causa raíz 3: El LLM no fuerza conexiones para todos los componentes
El prompt dice "Conectar TODOS los componentes en al menos un net" pero el LLM generó U3 (PC817) sin conectarlo. Esto pasa porque el LLM genera la lista de componentes y la lista de nets de forma semi-independiente.

---

## 8. TABLA RESUMEN DE PROBLEMAS

| # | Área | Severidad | Descripción breve | Archivo afectado |
|---|------|-----------|-------------------|------------------|
| A | Routing | CRÍTICO | "diseña el pcb y esquematico" → DIRECT (no genera circuito) | `orchestrator.py` |
| B1 | Generación | CRÍTICO | 1 relay generado en vez de 5 | `circuit_agent.py` (prompt) |
| B2 | Generación | ALTO | Componentes generados sin conectar (U3 flotante) | `circuit_agent.py` (prompt + validate) |
| B3 | Generación | ALTO | Nodo duplicado J1.N en dos nets | `circuit_agent.py` (no auto-fix) |
| C1 | Esquemático | CRÍTICO | Todos los componentes en fila horizontal única | `schematic_renderer.py` (layout) |
| C2 | Esquemático | ALTO | Wires largas cruzadas en vez de net labels | `schematic_renderer.py` (routing) |
| C3 | Esquemático | ALTO | Sin zonas/secciones (AC / Control / Potencia) | `schematic_renderer.py` (missing feature) |
| C4 | Esquemático | MEDIO | Símbolos MCU no muestran pines reales | `schematic_renderer.py` (sym_mcu) |
| D1 | PCB | CRÍTICO | 19 de 21 componentes apiñados en fila inferior | `pcb_renderer.py` (placement) |
| D2 | PCB | CRÍTICO | Sin separación AC/DC, sin clearance zones | `pcb_renderer.py` (missing feature) |
| D3 | PCB | ALTO | Footprints incorrectos para transformador, SMPS, SSR | `pcb_renderer.py` (footprint dict) |
| D4 | PCB | ALTO | Board size capped a 200×160mm — insuficiente | `pcb_renderer.py` (board_size) |
| E1 | 3D | ALTO | 19/21 componentes son cajas genéricas sin geometría | `circuit_viewer.html` |
| E2 | 3D | MEDIO | Cables 3D invisibles a zoom normal | `circuit_viewer.html` |
| F | General | MEDIO | "diseña el pcb y esquematico" activa HARDWARE (texto) no CIRCUIT_DESIGN | `orchestrator.py` |

---

## 9. ESPECIFICACIONES DE LO QUE DEBERÍA GENERAR

### 9.1 Netlist correcta para "5 bombas 220VAC → 50VDC"

```json
{
  "name": "Controlador 5 Bombas de Presión 220VAC/50VDC",
  "components": [
    {"id": "U1",  "type": "arduino_mega",       "name": "Arduino Mega 2560"},
    {"id": "RL1", "type": "relay_module",        "name": "Relay 5V 10A — Bomba 1"},
    {"id": "RL2", "type": "relay_module",        "name": "Relay 5V 10A — Bomba 2"},
    {"id": "RL3", "type": "relay_module",        "name": "Relay 5V 10A — Bomba 3"},
    {"id": "RL4", "type": "relay_module",        "name": "Relay 5V 10A — Bomba 4"},
    {"id": "RL5", "type": "relay_module",        "name": "Relay 5V 10A — Bomba 5"},
    {"id": "D1",  "type": "diode", "value": "1N4007", "name": "Flyback RL1"},
    {"id": "D2",  "type": "diode", "value": "1N4007", "name": "Flyback RL2"},
    {"id": "D3",  "type": "diode", "value": "1N4007", "name": "Flyback RL3"},
    {"id": "D4",  "type": "diode", "value": "1N4007", "name": "Flyback RL4"},
    {"id": "D5",  "type": "diode", "value": "1N4007", "name": "Flyback RL5"},
    {"id": "F1",  "type": "fuse",  "value": "10",     "name": "Fusible AC 10A"},
    {"id": "D6",  "type": "varistor", "value": "S20K275", "name": "MOV protección"},
    {"id": "T1",  "type": "transformer",         "name": "Transformador 220VAC/12VAC 50VA"},
    {"id": "BR1", "type": "bridge_rectifier",    "name": "Puente GBU4J"},
    {"id": "C1",  "type": "capacitor_electrolytic", "value": "2200", "unit": "µF", "name": "Cap filtro"},
    {"id": "U2",  "type": "voltage_regulator",   "name": "LM7805 +5V"},
    {"id": "C2",  "type": "capacitor", "value": "100", "unit": "nF", "name": "Cap desacoplo MCU"},
    {"id": "SMPS1","type": "smps",                "name": "Fuente SMPS 50VDC 5A"},
    {"id": "J1",  "type": "connector",            "name": "Entrada 220VAC"},
    {"id": "J2",  "type": "connector",            "name": "Salida Bomba 1"},
    {"id": "J3",  "type": "connector",            "name": "Salida Bomba 2"},
    {"id": "J4",  "type": "connector",            "name": "Salida Bomba 3"},
    {"id": "J5",  "type": "connector",            "name": "Salida Bomba 4"},
    {"id": "J6",  "type": "connector",            "name": "Salida Bomba 5"},
    {"id": "R1",  "type": "resistor", "value": "470", "unit": "Ω", "name": "R control RL1"},
    {"id": "R2",  "type": "resistor", "value": "470", "unit": "Ω", "name": "R control RL2"},
    {"id": "R3",  "type": "resistor", "value": "470", "unit": "Ω", "name": "R control RL3"},
    {"id": "R4",  "type": "resistor", "value": "470", "unit": "Ω", "name": "R control RL4"},
    {"id": "R5",  "type": "resistor", "value": "470", "unit": "Ω", "name": "R control RL5"}
  ],
  "nets": [
    {"name": "VCC_220VAC_L",  "nodes": ["J1.L", "F1.1", "D6.1"]},
    {"name": "VCC_220VAC_N",  "nodes": ["J1.N", "T1.PRI_N", "SMPS1.AC_N"]},
    {"name": "VCC_220VAC_F",  "nodes": ["F1.2", "T1.PRI_L", "SMPS1.AC_L", "D6.2"]},
    {"name": "VCC_12VAC_A",   "nodes": ["T1.SEC_A", "BR1.AC1"]},
    {"name": "VCC_12VAC_B",   "nodes": ["T1.SEC_B", "BR1.AC2"]},
    {"name": "RECTIFIED_VCC", "nodes": ["BR1.PLUS", "C1.PLUS", "U2.IN"]},
    {"name": "GND",           "nodes": ["BR1.MINUS", "C1.MINUS", "U2.GND", "U1.GND", "C2.2", "RL1.GND", "RL2.GND", "RL3.GND", "RL4.GND", "RL5.GND"]},
    {"name": "VCC_5V",        "nodes": ["U2.OUT", "U1.VIN", "C2.1", "RL1.VCC", "RL2.VCC", "RL3.VCC", "RL4.VCC", "RL5.VCC"]},
    {"name": "VCC_50V",       "nodes": ["SMPS1.PLUS", "RL1.COM", "RL2.COM", "RL3.COM", "RL4.COM", "RL5.COM"]},
    {"name": "GND_50V",       "nodes": ["SMPS1.MINUS", "J2.N", "J3.N", "J4.N", "J5.N", "J6.N"]},
    {"name": "RELAY1_CTRL",   "nodes": ["U1.D22", "R1.1", "RL1.IN"]},
    {"name": "RELAY2_CTRL",   "nodes": ["U1.D24", "R2.1", "RL2.IN"]},
    {"name": "RELAY3_CTRL",   "nodes": ["U1.D26", "R3.1", "RL3.IN"]},
    {"name": "RELAY4_CTRL",   "nodes": ["U1.D28", "R4.1", "RL4.IN"]},
    {"name": "RELAY5_CTRL",   "nodes": ["U1.D30", "R5.1", "RL5.IN"]},
    {"name": "PUMP1_OUT",     "nodes": ["RL1.NO", "J2.P"]},
    {"name": "PUMP2_OUT",     "nodes": ["RL2.NO", "J3.P"]},
    {"name": "PUMP3_OUT",     "nodes": ["RL3.NO", "J4.P"]},
    {"name": "PUMP4_OUT",     "nodes": ["RL4.NO", "J5.P"]},
    {"name": "PUMP5_OUT",     "nodes": ["RL5.NO", "J6.P"]}
  ]
}
```

### 9.2 Layout de esquemático correcto (descripción)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ZONA AC (alta tensión — borde rojo)                                  │
│  J1 ──F1──┬── T1 ─── BR1 ─── C1 ─── U2(LM7805) ─── VCC_5V         │
│  220VAC   D6(MOV)                                                    │
│           └── SMPS1 ─────────────────────────────── VCC_50V         │
├──────────────────────────────────────────────────────────────────────┤
│ ZONA CONTROL (baja tensión)                                          │
│                    U1 (Arduino Mega)                                 │
│                  D22 ──R1──RL1──D1_fly──┐                            │
│                  D24 ──R2──RL2──D2_fly──│── VCC_5V                  │
│                  D26 ──R3──RL3──D3_fly──│                            │
│                  D28 ──R4──RL4──D4_fly──│                            │
│                  D30 ──R5──RL5──D5_fly──┘                            │
├──────────────────────────────────────────────────────────────────────┤
│ ZONA SALIDA (50VDC)                                                  │
│  RL1.NO ── J2 (Bomba 1)    RL4.NO ── J5 (Bomba 4)                  │
│  RL2.NO ── J3 (Bomba 2)    RL5.NO ── J6 (Bomba 5)                  │
│  RL3.NO ── J4 (Bomba 3)                                              │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.3 Layout de PCB correcto (descripción)

```
┌──────────────────────────────────────────────────────────────────────┐
│ [ZONA HV — clearance 5mm]          │ [ZONA LV]                      │
│  J1   F1   D6   T1   BR1   C1      │   U2(7805)   U1(Mega)  C2      │
│  220VAC─────────────────────────── │ ──5V──────────────────────     │
│  SMPS1─────────────────────────── │ ──50V──────────────────────     │
├────────────────────────────────────┤                                 │
│ [RELAY ZONE — 5 módulos en columna]│ [CONNECTORS OUT]               │
│  RL1 + D1 + R1                     │  J2 (Bomba 1)                  │
│  RL2 + D2 + R2                     │  J3 (Bomba 2)                  │
│  RL3 + D3 + R3                     │  J4 (Bomba 3)                  │
│  RL4 + D4 + R4                     │  J5 (Bomba 4)                  │
│  RL5 + D5 + R5                     │  J6 (Bomba 5)                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 10. PLAN DE IMPLEMENTACIÓN PROPUESTO

### FASE 1 — Generación correcta de netlists (circuit_agent.py + orchestrator.py)

**F1.1 — Routing keywords (15 min)**
Archivo: `agent/orchestrator.py`
Agregar a `CIRCUIT_DESIGN_KEYWORDS`:
```python
"diseña el pcb y esquematico", "diseña el esquematico y pcb",
"diseña el pcb", "haceme el pcb", "quiero el pcb",
"crear el esquematico", "crear el pcb",
"quiero el esquematico", "quiero ver el circuito",
"diseña el circuito completo", "haceme el circuito",
"generar el pcb", "generar esquematico",
```

**F1.2 — Prompt de generación con N cargas explícito (30 min)**
Archivo: `agent/agents/circuit_agent.py`
Agregar al `CIRCUIT_PARSE_PROMPT`:
```
REGLA CRÍTICA PARA N CARGAS/BOMBAS/MOTORES:
Si la descripción menciona N unidades (ej: "5 bombas", "3 motores", "4 relays"):
- DEBES generar exactamente N componentes relay separados: RL1, RL2, ..., RLN
- DEBES generar exactamente N diodos flyback separados: D_fly1, D_fly2, ..., D_flyN
- DEBES generar exactamente N resistencias de control: R1, R2, ..., RN
- DEBES generar exactamente N nets de control: RELAY1_CTRL, ..., RELAYn_CTRL
- DEBES generar exactamente N connectores de salida: J2, J3, ..., J(N+1)
- NO comprimas N cargas en un solo componente "relay de N canales"
- Cada componente debe estar conectado en al menos UN net
```

**F1.3 — Post-validación y auto-fix de nodos duplicados (30 min)**
Archivo: `agent/agents/circuit_agent.py`
En `_validate_circuit()`: cuando detecta nodo duplicado, removerlo del net secundario automáticamente (no solo reportar). Cuando detecta componente flotante, intentar conectarlo a GND o eliminarlo del JSON.

**F1.4 — Detección de N cargas en el prompt (30 min)**
Archivo: `agent/agents/circuit_agent.py`
Agregar función `_extract_load_count(description: str) -> int` que extrae el número de cargas del texto ("5 bombas" → 5, "tres motores" → 3). Inyectar en el prompt como: `"Número de cargas detectadas: {N} — generar {N} relays independientes"`.

### FASE 2 — Esquemático con layout profesional (schematic_renderer.py)

**F2.1 — Net labels en vez de wires largas (1-2h)**
Implementar `_draw_net_label(dwg, name, x, y, direction)` que dibuja una etiqueta de net (flag triangular con texto) en vez de dibujar wires para conexiones largas. Regla: si dos nodos están a >200px de distancia, usar net label en lugar de wire.

**F2.2 — Layout por zonas/secciones (2-3h)**
Reescribir `_layout_components()` con topología de flujo de señal:
- Detectar zona AC (transformer, rectifier, EMI), zona Control (MCU, optoacopladores), zona Relay (relay × N, flybacks × N), zona Salida (conectores)
- Asignar coordenadas de zona: AC=izquierda, Control=centro, Relay=derecha, Output=extremo-derecho
- Dentro de cada zona, stack vertical de componentes con spacing fijo
- Para N relays, stack vertical de N bloques (relay+diode+resistor agrupados juntos)

**F2.3 — Grupos de componentes asociados (relay+driver+diode) (1h)**
Antes del layout, detectar grupos lógicos: cada relay tiene un diodo flyback y una resistencia de control asociada. Colocarlos juntos en el espacio como una "celda" de relay.

**F2.4 — Línea de aislamiento galvánico (30 min)**
Dibujar una línea vertical con zigzag (símbolo de barrera galvánica) entre la zona AC y la zona de control. Agregar texto "BARRERA GALVÁNICA".

**F2.5 — Símbolo MCU con pines reales (1h)**
En `_sym_mcu()`, para Arduino Mega usar más pines (al menos 8 por lado), con los nombres de los pines relevantes del circuito (D22, D24... basados en los nets que conectan al MCU).

### FASE 3 — PCB con placement por zonas (pcb_renderer.py)

**F3.1 — Placement por zonas (2-3h)**
Reescribir `_place_components()` con 4 zonas horizontales:
- Zona izquierda (x: 0-30%): componentes AC de alta tensión
- Zona centro-izquierda (x: 30-50%): MCU + reguladores  
- Zona centro-derecha (x: 50-80%): N relay modules en columna vertical
- Zona derecha (x: 80-100%): conectores de salida

**F3.2 — Footprints industriales (1h)**
Agregar al dict `_FOOTPRINT`:
```python
"transformer":        (80.0, 60.0),  # Transformador toroidal
"smps":               (80.0, 40.0),  # Mean Well tipo
"bridge_rectifier":   (8.5, 5.0),    # GBU4J
"ssr":                (45.0, 53.0),  # Fotek SSR-25DA
"fuse_holder":        (30.0, 14.0),  # Porta-fusible 5×20mm
"inductor_cm":        (25.0, 20.0),  # Inductor modo común
"varistor":           (10.0, 7.0),   # MOV disco
"voltage_regulator":  (10.5, 14.0),  # TO-220
"optoacoplador":      (6.5, 9.0),    # DIP-4
```

**F3.3 — Zona de clearance AC/DC (1h)**
Dibujar una línea de separación en el PCB (linea amarilla/roja con texto "HV ZONE / LV ZONE") con clearance de 3mm entre pistas de alta y baja tensión. Agregar copper pour separado para GND_HV y GND_LV.

**F3.4 — Board size dinámico por cantidad de relays (30 min)**
Calcular board size basado en los footprints reales de los componentes:
```python
board_w = zona_AC_w + zona_MCU_w + zona_relay_w + zona_out_w + margins
board_h = max(altura_de_cada_zona) + margins
```

### FASE 4 — Visor 3D con geometrías realistas (circuit_viewer.html)

**F4.1 — Geometrías 3D para tipos industriales (2-3h)**
Agregar casos en `_addComponent3D()`:
- `transformer`: caja grande con bobinas visibles (toro o caja E-core)
- `voltage_regulator`: TO-220 con tab metálico
- `bridge_rectifier`: encapsulado cuadrado con 4 pines
- `relay_module`: PCB verde con relay electromecánico + indicador LED
- `fuse`: tubo cilíndrico transparente
- `varistor`: disco redondo naranja/azul
- `smps`: caja rectangular con ventilación
- `connector`: bloque terminal con tornillos visibles
- `optoacoplador`: encapsulado DIP-4

**F4.2 — Layout 3D igual al PCB (1h)**
Usar las mismas zonas del PCB: zona HV a la izquierda, MCU en el centro, relays a la derecha, conectores en el borde.

**F4.3 — Wires 3D más visibles (30 min)**
Aumentar el grosor de los wires, usar `MeshTubeGeometry` en vez de líneas. Color coding por tipo de net: rojo=VCC, negro=GND, amarillo=señal de control, naranja=potencia alta.

---

## 11. ARCHIVOS A MODIFICAR

| Archivo | Cambios |
|---------|---------|
| `agent/orchestrator.py` | +15 keywords en CIRCUIT_DESIGN_KEYWORDS |
| `agent/agents/circuit_agent.py` | Prompt N-cargas explícito + `_extract_load_count()` + auto-fix nodos flotantes/duplicados |
| `tools/schematic_renderer.py` | Layout por zonas, net labels, agrupación relay+driver+diode, símbolo barrera galvánica |
| `tools/pcb_renderer.py` | Placement 4 zonas, footprints industriales, clearance AC/DC, board size dinámico |
| `api/static/circuit_viewer.html` | 8 nuevas geometrías 3D, layout por zonas, wires más visibles |

---

## 12. MÉTRICAS DE ÉXITO

Para validar que la implementación es correcta, el circuito "5 bombas 220VAC→50VDC" debe:

| Métrica | Actual (ID 16) | Target |
|---------|----------------|--------|
| Número de relays en netlist | 1 | 5 |
| Número de diodos flyback | 1 | 5 |
| Número de nets de control | 1 (RELAY1_CTRL) | 5 (RELAY1_CTRL ... RELAY5_CTRL) |
| Componentes flotantes | 1 (U3) | 0 |
| Nodos duplicados | 1 (J1.N) | 0 |
| Layout esquemático | 1 fila horizontal | 3 zonas verticales |
| PCB — componentes en fila inferior | 14 | 0 |
| PCB — zonas separadas AC/DC | No | Sí |
| 3D — tipos sin geometría propia | 19/21 | ≤3/21 |
| Routing "diseña el pcb y esquematico" | DIRECT | CIRCUIT_DESIGN |

---

*Reporte generado por análisis de: `stratum_chat_9b0fe0bb_1777070651030.md`, `esquematico 1.PNG`, `esquematico 2.PNG`, `pcb 1.PNG`, `pcb 2.PNG`, `3d 1.PNG`, `3d 2.PNG`*
