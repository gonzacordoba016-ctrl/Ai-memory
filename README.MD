# STRATUM

### Hardware Memory Engine

> _Tu Arduino te recuerda. Vos no tenés que repetirlo._

Stratum es un agente de IA que corre **100% local** especializado en programar microcontroladores. Resuelve el problema central de los LLMs conversacionales en desarrollo de hardware: la amnesia de contexto. Cuando le decís "programá el Arduino", ya sabe qué sensores tenés conectados, en qué pines, qué falló la semana pasada y cómo lo resolviste.

```
"Hacé parpadear el LED del sensor de temperatura"
→ Stratum recuerda el circuito, genera el firmware, lo compila y lo flashea.
```

---

## ¿Qué hace?

- **Genera, compila y flashea firmware C++** a Arduino, ESP32, ESP8266, RP2040, STM32 desde lenguaje natural
- **Recuerda el circuito completo** entre sesiones — componentes, pines, conexiones, historial de fallos
- **Instala librerías C++ faltantes automáticamente** si el compilador las necesita
- **Agente proactivo** — te notifica cuando un dispositivo se conecta, lleva días inactivo o tiene errores recurrentes
- **Motor de memoria triple** (SQL + Vectorial + Grafo) con consolidación nocturna automática
- **Modelo mental del usuario** — aprende tu nivel, plataformas preferidas y estilo de respuesta
- **Plugin system** — agregá herramientas propias sin tocar el core
- **Export/import de memoria** — llevá tu contexto de una PC a otra
- **Análisis visual de circuitos** con LLaVA (requiere cámara + `ollama pull llava:7b`)

---

## Stack

| Componente | Tecnología                                |
| ---------- | ----------------------------------------- |
| Backend    | Python 3.10+ · FastAPI · asyncio          |
| LLM        | Ollama · qwen2.5:7b (local, sin internet) |
| Memoria    | SQLite · Qdrant · NetworkX                |
| Hardware   | arduino-cli · pyserial                    |
| Frontend   | HTML · Tailwind CSS · WebSockets          |

---

## Instalación

**Requisitos previos:**

- Python 3.10+
- [Ollama](https://ollama.com/download) instalado
- [arduino-cli](https://arduino.github.io/arduino-cli/latest/installation/) en el PATH (opcional, solo para flashear)

```bash
# 1. Clonar el repositorio
git clone https://github.com/gonzacba17/stratum.git
cd stratum

# 2. Correr el instalador
python install.py

# El instalador:
# ✓ Instala dependencias Python
# ✓ Descarga el modelo qwen2.5:7b (~4.7GB, solo la primera vez)
# ✓ Crea la estructura de directorios
# ✓ Genera el .env con la configuración por defecto
# ✓ Inicia el servidor automáticamente
```

**O manualmente:**

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn api.server:app --port 8000 --reload
```

Abrí `http://localhost:8000` en el navegador.

---

## Uso rápido

Una vez iniciado, hablale directamente:

```
"Tengo un DHT22 en el pin 2, un LED en el pin 13 y una pantalla LCD I2C"
→ Guarda el contexto del circuito

"Mostrá la temperatura en la pantalla y parpadeá el LED si supera 30°"
→ Genera el firmware específico para TU circuito, compila y flashea

"El LED no parpadea"
→ Lee el monitor serial, diagnostica y corrige el código
```

### Comandos CLI (modo terminal)

```
python main.py

/help      → ayuda
/memory    → ver hechos conocidos
/search    → buscar en memoria vectorial
/pdf       → ingestar documentación
/exit      → guardar sesión y salir
```

### Gestión de memoria

```bash
python manage.py status          # estado actual
python manage.py export          # backup en ZIP
python manage.py import backup.zip --merge
python manage.py reset --confirm
```

---

## Features

### Triple Memoria

Stratum mantiene tres capas de memoria sincronizadas:

- **SQL** — hechos estructurados e historial de conversaciones
- **Vectorial (Qdrant)** — búsqueda semántica de episodios
- **Grafo (NetworkX)** — relaciones entre entidades (usuario → trabaja_en → empresa)

### Plugin System

Extendé Stratum sin tocar el core:

```python
# tools/plugins/mi_plugin.py
PLUGIN_NAME        = "home_assistant"
PLUGIN_DESCRIPTION = "Controla dispositivos del hogar"

def encender_luz(habitacion: str) -> str:
    # tu código acá
    return f"Luz de {habitacion} encendida"

PLUGIN_TOOLS = [{
    "function":    encender_luz,
    "name":        "encender_luz",
    "description": "Enciende la luz de una habitación",
    "parameters":  { "type": "object", "properties": { "habitacion": {"type": "string"} }, "required": ["habitacion"] }
}]
```

Guardá el archivo, reiniciá Stratum — el agente ya puede usar `encender_luz`.

### Agente Proactivo

Stratum no espera que le preguntes. Corre loops en background:

| Loop                  | Intervalo | Acción                                           |
| --------------------- | --------- | ------------------------------------------------ |
| Device detection      | 30s       | Notifica cuando conectás un dispositivo          |
| Inactivity check      | 1h        | Avisa si un proyecto lleva 3+ días sin actividad |
| Error patterns        | 30min     | Detecta fallos recurrentes y sugiere debug       |
| Nightly consolidation | 00:00hs   | Comprime memorias antiguas automáticamente       |

---

## Plataformas soportadas

Arduino UNO · Mega · Nano · Mini · Leonardo · Due · Zero · MKR · Micro  
ESP32 · ESP32-S2 · ESP32-S3 · ESP32-C3  
ESP8266 · NodeMCU · Wemos D1  
Raspberry Pi Pico · RP2040  
STM32 (Blue Pill · Nucleo)  
Teensy 3.x · 4.x  
Adafruit Feather · Trinket  
Seeeduino XIAO

---

## Estructura del proyecto

```
stratum/
├── agent/                  # Agentes especializados y orquestador
│   ├── agents/
│   │   ├── hardware_agent.py
│   │   ├── research_agent.py
│   │   ├── code_agent.py
│   │   └── vision_agent.py
│   ├── agent_controller.py
│   ├── orchestrator.py
│   ├── proactive_engine.py
│   └── user_profiler.py
├── api/
│   ├── server.py
│   └── static/             # Frontend
├── core/                   # Config, logger, prompt builder
├── database/               # SQLite drivers
├── llm/                    # Clientes LLM (async httpx)
├── memory/                 # Vectorial, grafo, consolidador
├── tools/
│   ├── plugins/            # ← Tus plugins van acá
│   ├── firmware_flasher.py
│   ├── hardware_detector.py
│   └── serial_monitor.py
├── eval/
│   └── run_eval.py         # 127 tests
├── install.py
├── manage.py
└── main.py
```

---

## Tests

```bash
python eval/run_eval.py
```

```
Resultado: 127/127 tests pasaron
✓ Todo OK — memoria real no contaminada
```

Los tests cubren: SQL, Qdrant, grafo, hardware memory, async stack, extractores, orchestrator, proactive engine, vision agent, user profiler, plugin system, consolidación nocturna, agent runner, sandbox, type hints.

---

## Contribuir

Las contribuciones son bienvenidas. Este proyecto es de uso libre y las mejoras benefician a toda la comunidad.

1. Forkear el repositorio
2. Crear una rama (`git checkout -b feature/mi-mejora`)
3. Correr los tests antes de hacer PR (`python eval/run_eval.py`)
4. Abrir un Pull Request con descripción clara de qué cambia y por qué

**Áreas donde hay más para hacer:**

- Soporte a más plataformas de hardware (PLCs, MicroPython nativo)
- Autenticación para uso multi-usuario
- Dashboard de métricas más rico
- Integración con Home Assistant via plugin
- Tests de integración end-to-end con hardware real

---

## Licencia

**Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**

Podés usar, modificar y distribuir este proyecto libremente para usos no comerciales, siempre que des crédito y mantengas la misma licencia en tus derivados. Para uso comercial, contactame.

[![CC BY-NC-SA 4.0](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

---

_Construido con Ollama · FastAPI · arduino-cli_
