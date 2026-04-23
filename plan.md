# Plan — KiCad Symbol Renderer (Opción B)
> Objetivo: símbolos esquemáticos 100% KiCad sin instalar KiCad
> Estimado: 1 día de trabajo

---

## Contexto

Stratum ya genera archivos `.kicad_sch`. El problema es que los símbolos SVG
son dibujados a mano y se ven "aproximados". KiCad guarda los símbolos reales
en archivos `.kicad_sym` (texto plano, S-expressions) que contienen las
primitivas exactas (polylines, arcs, circles, pins). Parsearlos y renderizarlos
nos da calidad 100% KiCad sin instalar el programa.

---

## Fase 1 — Bajar y parsear los symbol files (mañana AM)

### 1.1 Descargar solo los símbolos necesarios

Los `.kicad_sym` están en:
https://gitlab.com/kicad/libraries/kicad-symbols

No bajar todo el repo (pesado). Solo los archivos que necesitamos:

| Archivo `.kicad_sym` | Componentes cubiertos |
|----------------------|-----------------------|
| `Device.kicad_sym` | R, C, L, D, LED, Q (transistor), MOSFET, battery |
| `MCU_Espressif.kicad_sym` | ESP32, ESP8266 |
| `MCU_Microchip_ATmega.kicad_sym` | Arduino (ATmega328, ATmega2560) |
| `Relay.kicad_sym` | relays genéricos |
| `Display.kicad_sym` | OLED, LCD |
| `Sensor.kicad_sym` | sensores genéricos |
| `RTC.kicad_sym` | DS3231, DS1307 |
| `Interface_UART.kicad_sym` | módulos HC-05, etc. |

Guardarlos en: `tools/kicad_symbols/` (solo los 8 archivos, ~2-5 MB total).

### 1.2 Escribir el parser `tools/kicad_sym_parser.py`

El formato de un símbolo en `.kicad_sym` es:

```
(symbol "Device:R"
  (pin passive line (at -1.016 0 180) ...)
  (symbol "R_0_1"
    (polyline (pts (xy -1.016 -1.016) (xy 1.016 -1.016) ...))
    (rectangle (start -1.016 -0.762) (end 1.016 0.762))
  )
)
```

El parser necesita extraer:
- `polyline` → lista de puntos → SVG `<polyline>`
- `rectangle` → start/end → SVG `<rect>`
- `circle` → center + radius → SVG `<circle>`
- `arc` → start/mid/end → SVG `<path>` con arc
- `pin` → posición + dirección + nombre → stub line + label

Función principal:
```python
def load_symbol(lib_path: str, symbol_name: str) -> dict:
    """Retorna primitivas SVG del símbolo KiCad."""
    # Retorna: {"primitives": [...], "pins": [...], "bbox": (x1,y1,x2,y2)}
```

Escala KiCad → SVG: KiCad usa mm con 1 unidad = 1mm. Multiplicar × 10 para
obtener píxeles a escala razonable en el SVG.

### 1.3 Escribir `tools/kicad_sym_renderer.py`

```python
class KiCadSymRenderer:
    def render_symbol(self, dwg, symbol_data, cx, cy, scale=10) -> None:
        """Dibuja las primitivas KiCad centradas en (cx, cy)."""
```

Colores: seguir el tema EDA light actual (`#1a1a2e` stroke, fills por grupo).

---

## Fase 2 — Integrar con SchematicRenderer (mañana tarde)

### 2.1 Modificar `tools/schematic_renderer.py`

Cambiar el dispatch en `_draw_component()`:

```python
from tools.kicad_sym_renderer import KiCadSymRenderer

_kicad_renderer = KiCadSymRenderer()

# Mapa tipo → (lib_file, symbol_name)
KICAD_SYMBOL_MAP = {
    "resistor":    ("Device", "R"),
    "capacitor":   ("Device", "C"),
    "capacitor_electrolytic": ("Device", "C_Polarized"),
    "led":         ("Device", "LED"),
    "diode":       ("Device", "D"),
    "1n4007":      ("Device", "D"),
    "transistor":  ("Device", "Q_NPN_BCE"),
    "mosfet":      ("Device", "Q_NMOS_GSD"),
    "inductor":    ("Device", "L"),
    "esp32":       ("MCU_Espressif", "ESP32-WROOM-32"),
    "relay":       ("Relay", "RELAY_CO"),
    "ds3231":      ("RTC", "DS3231"),
    "rtc":         ("RTC", "DS3231"),
    # etc.
}

def _draw_component(self, dwg, comp, pos):
    t = comp.get("resolved_type", "generic").lower()
    if t in KICAD_SYMBOL_MAP:
        lib, sym = KICAD_SYMBOL_MAP[t]
        sym_data = _kicad_renderer.load_cached(lib, sym)
        if sym_data:
            _kicad_renderer.render_symbol(dwg, sym_data, *pos)
            self._draw_labels(dwg, comp, pos)  # ref + value encima/abajo
            return
    # Fallback: método propio actual
    self._draw_component_fallback(dwg, comp, pos)
```

### 2.2 Cache de símbolos parseados

Los `.kicad_sym` se parsean una vez al arrancar el servidor y se guardan en
memoria (dict en `KiCadSymRenderer`). El parse es O(n líneas del archivo), rápido.

```python
_symbol_cache: dict[str, dict] = {}  # "Device:R" → primitivas

def load_cached(self, lib: str, sym: str) -> dict | None:
    key = f"{lib}:{sym}"
    if key not in _symbol_cache:
        _symbol_cache[key] = self._parse_from_file(lib, sym)
    return _symbol_cache.get(key)
```

---

## Fase 3 — PCB con footprints reales (opcional, si sobra tiempo)

KiCad también tiene archivos `.kicad_mod` (footprints PCB) en el repo:
https://gitlab.com/kicad/libraries/kicad-footprints

Misma lógica: parsear pads, courtyard, silkscreen de los footprints reales.
Archivos útiles: `Resistor_THT.pretty/R_Axial_DIN0207.kicad_mod`, etc.

Esto es Fase 3 — no es necesario para la mejora visual principal.

---

## Archivos a crear/modificar

| Acción | Archivo |
|--------|---------|
| CREAR | `tools/kicad_symbols/` (carpeta + 8 archivos .kicad_sym) |
| CREAR | `tools/kicad_sym_parser.py` |
| CREAR | `tools/kicad_sym_renderer.py` |
| MODIFICAR | `tools/schematic_renderer.py` — integrar renderer + fallback |
| MODIFICAR | `CONTEXT-PROJECT.md` — documentar v4.10.0 |

---

## Orden de ejecución del día

1. **9:00** — Bajar los 8 archivos `.kicad_sym` del GitLab de KiCad
2. **9:30** — Escribir `kicad_sym_parser.py` + tests manuales en Python
3. **11:00** — Escribir `kicad_sym_renderer.py` con escala y colores EDA
4. **13:00** — Integrar en `schematic_renderer.py` con fallback
5. **14:00** — Probar en local con el circuito de riego (ID 12)
6. **15:00** — Ajustar escala/offset/colores según resultado visual
7. **16:00** — Commit + push + verificar en Railway
8. **16:30** — Documentar en CONTEXT-PROJECT v4.10.0

---

## Criterio de éxito

El esquemático del circuito de riego (ESP32 + relay + sensores + RTC) debe
mostrar los mismos símbolos que KiCad Desktop: resistor con rectangle IEC,
LED con triángulo+barra, ESP32 como IC box con pines numerados reales,
DS3231 con pinout correcto.
