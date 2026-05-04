# agent/agents/circuit_agent.py

import json
import re
from typing import Dict, Any, Optional, List
from core.logger import get_logger
from core.config import LLM_MODEL_SMART, LLM_MODEL_FAST
from database.circuit_design import CircuitDesignManager
from tools.hardware_detector import resolve_component_type
from tools.component_pinouts import get_pinout_context_for_prompt
from tools.circuit_synthesizer import CircuitSynthesizer, BLOCK_TYPE_ALIASES
from llm.openrouter_client import call_llm_sync

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN DETECTION — fast pass before full parse
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    "industrial": ["220v", "220 v", "110v", "380v", "ac ", "corriente alterna",
                   "bomba hidráulica", "bomba hidraulica", "hydraulic pump",
                   "motor industrial", "alta tensión", "alta tension",
                   "transformador", "rectificador", "puente rectificador",
                   "potencia industrial", "plc", "variador", "contactor",
                   "neumático", "neumatico", "industrial", "trifásico",
                   "hidráulica", "hidraulica", "válvula hidráulica"],
    "irrigation": ["riego", "irrigation", "bomba de agua", "water pump", "humedad", "moisture",
                   "solenoid", "solenoide", "válvula", "valve", "goteo", "drip"],
    "domotics":   ["domótica", "home automation", "domotics", "smart home", "casa inteligente",
                   "pir", "movimiento", "motion", "puerta", "door", "cortina", "blind",
                   "enchufe", "socket", "cerradura", "lock"],
    "motor":      ["motor", "stepper", "servo", "paso a paso", "encoder", "driver",
                   "l298n", "drv8825", "a4988", "pwm motor", "brushless", "bldc"],
    "power_supply": ["fuente", "power supply", "regulador", "regulator", "buck", "boost",
                     "lm317", "lm7805", "switching", "cargador", "charger", "solar"],
    "display":    ["display", "oled", "lcd", "pantalla", "screen", "i2c display",
                   "ssd1306", "st7735", "ili9341", "neopixel", "ws2812", "rgb strip"],
    "sensor_hub": ["sensor", "temperatura", "humedad",
                   "presión", "pressure", "gas", "co2", "calidad del aire", "air quality",
                   "dht", "bmp280", "mpu6050", "hx711", "balanza", "scale"],
    "iot":        ["wifi", "mqtt", "http", "api", "cloud", "iot", "internet",
                   "blynk", "thingspeak", "telegram", "web server", "ota"],
    "audio":      ["audio", "sonido", "sound", "speaker", "altavoz", "micrófono",
                   "buzzer", "piezo", "i2s", "amplificador", "amp", "max98357"],
}

# MCU recommendation by domain
DOMAIN_MCU = {
    "industrial": "Arduino Mega",
    "irrigation": "ESP32",
    "domotics":   "ESP32",
    "motor":      "Arduino Uno",
    "power_supply": "Arduino Nano",
    "display":    "ESP32",
    "sensor_hub": "ESP32",
    "iot":        "ESP32",
    "audio":      "ESP32",
    "default":    "Arduino Uno",
}

# Extra guidance injected into the prompt per domain
DOMAIN_HINTS = {
    "irrigation": """
DOMINIO: Sistema de riego inteligente
- Usá sensor de humedad del suelo (ej: FC-28 analógico o capacitivo YL-69) para detectar nivel de agua
- Usá sensor de nivel de agua (HC-SR04 ultrasónico o flotante) para el depósito
- La bomba de agua o válvula solenoide se controla mediante RELAY (módulo relay 5V)
- El relay maneja 220V/12V de la bomba — SIEMPRE incluí diodo flyback (1N4007) en la bobina del relay
- Si el ESP32 es WiFi: incluí capacitor bulk (100µF) cerca del VCC del ESP32
- Incluí RTC (DS3231 I2C) para riego programado
- Opcionalmente: LCD I2C (20x4 o 16x2) para mostrar estado
- Power: la bomba va a 12V o 220V AC separado, el MCU a 5V USB o 7-12V DC → regulador 5V
- WARNING: nunca mezcles la tierra del circuito de control con la línea AC de la bomba

ASIGNACIÓN DE PINES ESP32 (OBLIGATORIO, sin conflictos):
- I2C SDA → U1.GPIO21 (exclusivo para RTC, LCD — NO asignar a otro periférico)
- I2C SCL → U1.GPIO22 (exclusivo para RTC, LCD — NO asignar a otro periférico)
- HC-SR04 TRIG → U1.GPIO5  (nunca GPIO21 o GPIO22)
- HC-SR04 ECHO → U1.GPIO18 (nunca GPIO21 o GPIO22)
- Relay control → U1.GPIO23
- FC-28 DATA (analógico) → U1.GPIO34
""",
    "domotics": """
DOMINIO: Domótica / Home Automation
- Relays para controlar cargas AC (luz, ventilador) — incluí diodo flyback + optoacoplador si es posible
- Sensor de temperatura y humedad (DHT22 o SHT31 I2C) para monitoreo ambiental
- PIR (HC-SR501) para detección de movimiento — pin de salida digital activo alto
- Incluí LED de estado (verde=online, rojo=alerta)
- Control remoto via WiFi/MQTT desde el ESP32
- Si incluís botones físicos: resistencias pull-up 10kΩ a VCC
- Power: 5V USB para el ESP32, relays alimentados con 5V o 12V según módulo
""",
    "motor": """
DOMINIO: Control de motores
- Driver de motor: L298N (hasta 2A/motor, 2 motores), DRV8825/A4988 (paso a paso), TB6600 (alta potencia)
- Pines de control: DIR, STEP/PWM, EN (enable activo bajo normalmente)
- Condensador de desacople bulk (470µF) entre VCC_MOTOR y GND — absorbe picos de corriente
- Diodos flyback (4× 1N5819 o puente rectificador) en cada bobina del motor DC
- Si usás encoder: pull-ups 10kΩ en líneas A y B
- Final de carrera (limit switch): pull-up 10kΩ, decoupling 100nF
- Separar la tierra del motor (GND_PWR) de la tierra digital (GND_DIG) — unilas en un solo punto
- Power: VCC_MOTOR separado de VCC_MCU (nunca alimentar el MCU desde el mismo rail que el motor)
""",
    "power_supply": """
DOMINIO: Fuente de alimentación / Convertidor
- Para linear regulators (LM317, LM7805): input > output + 3V dropout, cap entrada 100nF + cap salida 10µF
- Para switching (buck/boost): inductor apropiado (47µH típico), cap bulk en entrada y salida
- Incluí resistencia de carga mínima o enable pin
- Incluí fusible de protección en la entrada
- Si hay baterías LiPo: incluí TP4056 para carga, protección de sobrecorriente/sobredescarga (DW01)
""",
    "display": """
DOMINIO: Display / Interfaz visual
- OLED SSD1306 I2C: SDA→pin21 (ESP32) o A4 (Arduino), SCL→pin22 o A5, VCC→3.3V, pull-ups 4.7kΩ
- LCD I2C (PCF8574): mismas conexiones I2C, dirección por defecto 0x27
- NeoPixel WS2812B: resistencia 300Ω en línea DATA, capacitor 100µF entre VCC y GND del strip
- TFT (SPI): MOSI, CLK, CS, DC, RST — asegurate de usar nivel lógico 3.3V si el display lo requiere
""",
    "iot": """
DOMINIO: IoT / Conectividad WiFi-MQTT
- ESP32 necesita capacitor bulk 100µF + 100nF cerca del VCC para estabilidad WiFi
- Antena WiFi debe estar despejada (sin cobre debajo)
- Incluí LED heartbeat (parpado 1Hz) conectado a pin libre
- Si usás deep sleep: botón de reset externo con RC (10kΩ + 100nF) en EN
- MQTT broker local (Mosquitto) o cloud (HiveMQ, AWS IoT) — especificá en warnings
""",
    "industrial": """
DOMINIO: Sistema Industrial / Alta Tensión / Control de Cargas de Potencia
- SEGURIDAD ELÉCTRICA: separación galvánica OBLIGATORIA entre circuito de control (MCU 5V) y potencia (220VAC/48VDC)
- Usar módulos relay con optoacoplamiento integrado (5V IN, hasta 10A 250VAC OUT)
- Fusible en la entrada AC (según corriente total de las cargas)
- Varistor MOV (ej: S20K275) en paralelo con la entrada AC para protección de sobretensión
- Filtro EMI en la entrada: capacitor X2 (100nF/275VAC) + inductor de modo común

ETAPA DE ALIMENTACIÓN (220VAC → DC de control):
- Transformador 220VAC → 9-12VAC (o fuente SMPS 220VAC → 5V/12V)
- Si transformador: puente rectificador (ej: GBU4J 4A/600V o 4× 1N5408)
- Capacitor de filtro electrolítico (2200µF 25V mínimo)
- Regulador 7805 (LM7805) para los 5V del MCU: cap entrada 100nF, cap salida 10µF

ETAPA DE POTENCIA (conversión de voltaje principal, ej: 48VDC):
- Si se requiere 48VDC desde 220VAC: fuente SMPS dedicada (ej: Mean Well 48V)
- Incluir fusible en la salida DC (según corriente total de bombas)
- LED indicador de presencia de tensión (con resistencia limitadora)

CONTROL DE MÚLTIPLES CARGAS (cada bomba/motor):
- Relay individual por carga (ej: SRD-05VDC-SL-C, 5V bobina, 10A 250VAC contacto)
- Diodo flyback 1N4007 en paralelo con la bobina de cada relay
- Pin de control separado del MCU por relay
- Optoacoplador (PC817) entre MCU y relay si se requiere aislamiento adicional
- LED de estado por relay (con resistencia 470Ω)

ASIGNACIÓN DE PINES (Arduino Mega — hasta 8 relays):
- RELAY1: U1.D22  RELAY2: U1.D24  RELAY3: U1.D26  RELAY4: U1.D28
- RELAY5: U1.D30  RELAY6: U1.D32  RELAY7: U1.D34  RELAY8: U1.D36
- I2C: SDA=U1.D20, SCL=U1.D21 (para LCD, RTC, expansores)
- STATUS LED: U1.D13 (con resistencia 470Ω)
- E-STOP (paro de emergencia): U1.D2 (interrupt INT0, pull-up 10kΩ)
""",
    "default": "",
}


def _detect_domain(description: str) -> str:
    desc_lower = description.lower()
    scores = {domain: 0 for domain in DOMAIN_KEYWORDS}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                scores[domain] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "default"


# ──────────────────────────────────────────────────────────────────────────────
# F1.3 — LOAD COUNT EXTRACTOR
# Detects N from text ("5 bombas" → 5, "tres motores" → 3, "dos relays" → 2)
# ──────────────────────────────────────────────────────────────────────────────

_NUM_WORDS_ES = {
    "una": 1, "uno": 1, "un": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciséis": 16, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20,
}

_LOAD_NOUNS = (
    r"bombas?", r"motores?", r"motor", r"relays?", r"relés?", r"reles?",
    r"válvulas?", r"valvulas?", r"solenoides?",
    r"electroválvulas?", r"electrovalvulas?",
    r"contactores?", r"actuadores?", r"cargas?",
    r"luces?", r"lámparas?", r"lamparas?",
    r"ventiladores?", r"calefactores?",
    r"pumps?", r"motors?", r"valves?", r"loads?", r"lights?",
)


def _extract_load_count(description: str) -> int:
    """
    Detect explicit load count in description.
    Returns the maximum N found (so "5 bombas y 3 sensores" → 5).
    Returns 0 if no count found.
    """
    if not description:
        return 0
    text = description.lower()
    nouns = "(?:" + "|".join(_LOAD_NOUNS) + ")"
    counts: List[int] = []

    # Numeric digits: "5 bombas", "10 relays"
    for m in re.finditer(rf"(\d{{1,3}})\s+{nouns}\b", text):
        try:
            n = int(m.group(1))
            if 1 <= n <= 64:
                counts.append(n)
        except ValueError:
            pass

    # Spanish number words: "tres motores", "cinco bombas"
    word_pattern = "|".join(_NUM_WORDS_ES.keys())
    for m in re.finditer(rf"\b({word_pattern})\s+{nouns}\b", text):
        n = _NUM_WORDS_ES.get(m.group(1))
        if n:
            counts.append(n)

    return max(counts) if counts else 0


def _select_mcu(description: str, domain: str, user_mcu: str) -> str:
    """Return the best MCU for the circuit; prefer user choice if explicit."""
    explicit_mcus = ["esp32", "arduino", "stm32", "pico", "attiny", "esp8266",
                     "nano", "mega", "uno", "raspberry"]
    desc_lower = description.lower()
    for mcu in explicit_mcus:
        if mcu in desc_lower:
            return user_mcu  # user mentioned something specific
    return DOMAIN_MCU.get(domain, "Arduino Uno")


# ──────────────────────────────────────────────────────────────────────────────
# MCU PIN RULES — injected into prompt to prevent GPIO conflicts
# ──────────────────────────────────────────────────────────────────────────────

MCU_PIN_RULES: Dict[str, str] = {
    "Arduino Uno": """
PINES ARDUINO UNO (obligatorio respetar):
- Digital: D0-D13  (D0/D1 = UART — no usar si hay UART activo)
- Analógico: A0-A5 (ADC 10-bit)
- PWM disponible SOLO en: D3, D5, D6, D9, D10, D11
- I2C: SDA=A4, SCL=A5  (exclusivos — no asignar a otro periférico)
- SPI: MOSI=D11, MISO=D12, SCK=D13, SS=D10
- Límite: 40 mA por pin, 200 mA total MCU
""",
    "Arduino Nano": """
PINES ARDUINO NANO (obligatorio respetar):
- Digital: D0-D13  (D0/D1 = UART)
- Analógico: A0-A7  (A6/A7 solo lectura analógica, sin función digital)
- PWM disponible SOLO en: D3, D5, D6, D9, D10, D11
- I2C: SDA=A4, SCL=A5  (exclusivos)
- SPI: MOSI=D11, MISO=D12, SCK=D13, SS=D10
""",
    "Arduino Mega": """
PINES ARDUINO MEGA (obligatorio respetar):
- Digital: D0-D53
- Analógico: A0-A15
- PWM disponible en: D2-D13, D44-D46
- I2C: SDA=D20, SCL=D21  (exclusivos)
- SPI: MOSI=D51, MISO=D50, SCK=D52, SS=D53
- UART adicional: Serial1=D18/D19, Serial2=D16/D17, Serial3=D14/D15
""",
    "Raspberry Pi Pico": """
PINES RASPBERRY PI PICO (obligatorio respetar):
- GPIO: GP0-GP28  (máx 3.3V — NO tolera 5V)
- ADC: SOLO GP26(ADC0), GP27(ADC1), GP28(ADC2)
- I2C0: SDA=GP4, SCL=GP5  |  I2C1: SDA=GP6, SCL=GP7
- SPI0: MOSI=GP3, MISO=GP4, SCK=GP2  |  SPI1: MOSI=GP11, MISO=GP12, SCK=GP10
- PWM: todos los pines (pares GP0/GP1, GP2/GP3, ...)
- Sensor 5V → divisor resistivo o level shifter obligatorio
""",
    "ESP32": """
PINES ESP32 (obligatorio respetar — evitar conflictos):
- ADC seguro con WiFi: GPIO32-GPIO39  (evitar GPIO0/2/15 para ADC)
- Input-only (sin pull-up): GPIO34, GPIO35, GPIO36, GPIO39
- I2C (por defecto): SDA=GPIO21, SCL=GPIO22  (exclusivos)
- SPI (por defecto): MOSI=GPIO23, MISO=GPIO19, SCK=GPIO18, SS=GPIO5
- UART0 (USB): TX=GPIO1, RX=GPIO3  |  UART2: TX=GPIO17, RX=GPIO16
- DAC verdadero: GPIO25, GPIO26
- Máx 3.3V en entradas — sensor 5V → divisor de tensión obligatorio
""",
    "ESP8266": """
PINES ESP8266 (obligatorio respetar):
- GPIO disponibles: GPIO0, GPIO2, GPIO4, GPIO5, GPIO12-GPIO16
- GPIO0/2/15: estado en boot — no conectar a GND ni periféricos que los fuerzen
- ADC: solo A0 (0-1V, o 0-3.3V según módulo)
- I2C: SDA=GPIO4, SCL=GPIO5  (software I2C)
- SPI: MOSI=GPIO13, MISO=GPIO12, SCK=GPIO14, SS=GPIO15
- Máx 3.3V en entradas
""",
}


def _mcu_pin_rules(mcu: str) -> str:
    """Returns formatted pin constraint block for the given MCU string."""
    mcu_lower = mcu.lower()
    for key, rules in MCU_PIN_RULES.items():
        if key.lower() in mcu_lower or any(w in mcu_lower for w in key.lower().split()):
            return rules
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# SPEC EXTRACTION PROMPT — Stage 1 del pipeline de síntesis determinística.
# El LLM solo clasifica y extrae parámetros. Las CONEXIONES las decide el
# CircuitSynthesizer, no el LLM.
# ──────────────────────────────────────────────────────────────────────────────

CIRCUIT_SPEC_PROMPT = """Analiza la descripción de circuito y extrae un spec estructurado.
Tu único trabajo es CLASIFICAR y EXTRAER PARÁMETROS — NO generes conexiones ni nets.

DESCRIPCIÓN: {description}

Tipos de bloque disponibles:
- type "output", model "LED": LED conectado a un GPIO del MCU
- type "sensor", model "BMP280", interface "I2C": sensor BMP280 por I2C
- type "sensor", model "DHT22": sensor temperatura+humedad GPIO single-wire
- type "sensor", model "moisture_sensor": sensor humedad de suelo analógico (ADC)
- type "sensor", model "OLED", interface "I2C": display OLED I2C SSD1306
- type "relay": módulo relay para control de carga/bomba/válvula
- type "sensor", interface "I2C": cualquier sensor I2C genérico

Si la descripción no coincide con ningún bloque conocido, devolvé "blocks": [].

Responde ÚNICAMENTE con JSON válido, sin markdown:
{{
  "mcu": "<modelo exacto del MCU, ej: Arduino Uno, ESP32, etc.>",
  "vcc": <voltaje de alimentación como número, ej: 5.0>,
  "blocks": [
    {{
      "type": "<output|sensor>",
      "model": "<LED|BMP280|...>",
      "interface": "<I2C|SPI|GPIO — si aplica>",
      "gpio_pin": "<pin GPIO si aplica, ej: D9, GPIO2>",
      "vf": <tensión forward del LED si aplica, ej: 2.0>,
      "led_current_ma": <corriente LED en mA si aplica, ej: 20.0>,
      "color": "<color del LED si se menciona>",
      "sda_pin": "<pin SDA si aplica>",
      "scl_pin": "<pin SCL si aplica>",
      "i2c_address": "<dirección I2C si se menciona, ej: 0x76>"
    }}
  ]
}}"""

# ──────────────────────────────────────────────────────────────────────────────
# MAIN PROMPT
# ──────────────────────────────────────────────────────────────────────────────

CIRCUIT_PARSE_PROMPT = """Eres un ingeniero electrónico experto en diseño de circuitos. \
Genera una netlist JSON COMPLETA y DETALLADA para el siguiente circuito.

DESCRIPCIÓN DEL CIRCUITO:
{description}

MCU / Controlador: {mcu}
{load_count_hint}
{domain_hint}
{mcu_pin_rules}
{pinout_context}
═══════════════════════════════════════════════════════
REGLAS OBLIGATORIAS — aplica TODAS sin excepción:
═══════════════════════════════════════════════════════
COMPONENTES DE PROTECCIÓN (siempre incluir):
  • Cada LED → resistencia limitadora en serie (calcular: R=(Vcc-Vf)/If, típico 220Ω-1kΩ)
  • Cada relay → diodo flyback 1N4007 en la bobina (cátodo al VCC del relay)
  • Circuitos ESP32/WiFi → capacitor bulk 100µF + capacitor desacoplo 100nF en VCC
  • Buses I2C → pull-ups 4.7kΩ en SDA y en SCL (obligatorio para comunicación confiable)
  • Circuitos con 220VAC → fusible de entrada + varistor MOV + filtro EMI

NOMENCLATURA (respetar siempre):
  • MCUs e ICs: U1, U2, U3...
  • Resistencias: R1, R2, R3...  (valor en Ω, ej: "value":"10000", "unit":"Ω")
  • Capacitores: C1, C2, C3...   (valor en µF o nF, ej: "value":"100", "unit":"nF")
  • Diodos: D1, D2, D3...
  • Relays: RL1, RL2, RL3...  (NO U2/U3 — los relays SIEMPRE son RLn)
  • Inductores: L1, L2...
  • Conectores/terminales: J1, J2...
  • Módulos: MOD1, MOD2...

PINES DEL MCU:
  • Usar pines REALES según el MCU (ej: U1.GPIO21, U1.GND, U1.3V3, U1.VIN, U1.D7, U1.A0)
  • NO inventar nombres de pines

NETS:
  • Nombres descriptivos: VCC_5V, VCC_12V, VCC_48V, GND, AGND, RELAY1_CTRL, PUMP1_PWR...
  • CRÍTICO: cada nodo (ej: "U1.GND") debe aparecer en UN SOLO net — NUNCA repetido
  • Conectar TODOS los componentes en al menos un net (sin componentes flotantes)
  • GND compartido entre todas las secciones (separar AGND si hay señales analógicas)

═══════════════════════════════════════════════════════
REGLA CRÍTICA — N CARGAS / BOMBAS / MOTORES / RELAYS:
═══════════════════════════════════════════════════════
Si la descripción menciona N unidades (ej: "5 bombas", "3 motores", "4 relays", "tres válvulas"):

  • DEBES generar exactamente N componentes relay SEPARADOS: RL1, RL2, ..., RLN
    (NUNCA un único componente "Relay Module N-canales" agrupando las N cargas)

  • DEBES generar exactamente N diodos flyback separados: D_fly1, D_fly2, ..., D_flyN
    (cada diodo en paralelo con la bobina de SU relay correspondiente)

  • DEBES generar exactamente N resistencias de control: R1, R2, ..., RN (típico 470Ω-1kΩ)
    (entre cada pin del MCU y la entrada del relay correspondiente)

  • DEBES generar exactamente N nets de control separados:
    RELAY1_CTRL, RELAY2_CTRL, ..., RELAYn_CTRL
    (cada uno conecta U1.D## → Rn.1 → RLn.IN)

  • DEBES generar exactamente N nets de salida hacia las cargas:
    PUMP1_OUT/MOTOR1_OUT/LOAD1_OUT, PUMP2_OUT, ..., PUMPN_OUT
    (cada uno conecta RLn.NO al conector de salida correspondiente)

  • DEBES generar exactamente N conectores de salida: J2, J3, ..., J(N+1)
    (uno por carga; J1 reservado para entrada de alimentación)

  • PROHIBIDO: comprimir las N cargas en un solo módulo relay multi-canal
  • PROHIBIDO: omitir el flyback, la resistencia de control o el conector de cualquiera de las N cargas
  • PROHIBIDO: reusar el mismo net RELAY1_CTRL para varias cargas

═══════════════════════════════════════════════════════
CIRCUITOS DE ALTA TENSIÓN (220VAC, 110VAC) — OBLIGATORIO:
═══════════════════════════════════════════════════════
Si la descripción menciona red eléctrica (220VAC, 110VAC, 220V, "red", "alimentado desde"):
DEBES generar la etapa de conversión COMPLETA. NO asumas que viene de afuera.
Componentes OBLIGATORIOS (todos en el JSON):

  1. Conector de entrada AC: J1 (terminal_block 220VAC, pines L+N)
  2. Fusible: F1 (type:"fuse", típico 5×20mm 1-10A según carga)
  3. Varistor MOV: D6 (type:"varistor", S20K275 o S14K275 para 220VAC)
  4. UNO de estos dos paths para generar VCC del MCU:

     PATH A (con transformador):
       • T1 (type:"transformer", 220VAC→9-12VAC 50VA)
       • BR1 (type:"bridge_rectifier", GBU4J o KBP307 4A)
       • C1 (type:"capacitor_electrolytic", value:"2200", unit:"µF" — filtro)
       • U2 (type:"voltage_regulator", LM7805 — genera 5V del MCU)
       • C2 (type:"capacitor", value:"100", unit:"nF" — desacoplo)

     PATH B (con SMPS):
       • SMPS1 (type:"smps", entrada 220VAC, salida 5V o 12V)
       • C2 (type:"capacitor", value:"100", unit:"nF" — desacoplo MCU)

  5. Si la carga requiere otro voltaje (ej: 24V o 50V para válvulas/motores):
     • Una fuente DEDICADA: SMPS2 (type:"smps") o un segundo transformador
     • NO suponer que el voltaje de carga "ya está" — generarlo

PROHIBIDO en circuitos AC:
  • Omitir transformer/SMPS — el MCU no puede recibir 220VAC directo
  • Omitir el fusible o el varistor MOV
  • Generar nets como "VCC_5V" sin que ningún componente lo produzca
  • Conectar el MCU directamente a J1 (entrada 220VAC)

Separación galvánica obligatoria entre control (MCU) y potencia (AC):
  • Módulos relay con optoacoplamiento integrado, o PC817 explícito
  • Layout: zona AC física separada de zona MCU

COMPLETITUD:
  • Incluir TODOS los componentes necesarios para que el circuito funcione en producción
  • No omitir capacitores de desacoplo, resistencias de pull-up, diodos de protección
  • Incluir conectores/terminales de entrada y salida (input AC + output por carga)
  • Si hay múltiples voltajes, incluir el regulador/conversor correspondiente

═══════════════════════════════════════════════════════
Responde ÚNICAMENTE con JSON válido. SIN markdown, SIN explicaciones, SIN texto adicional.
Formato exacto requerido:
═══════════════════════════════════════════════════════
{{"name":"<nombre descriptivo del circuito>","description":"<descripción técnica>","components":[{{"id":"U1","name":"<nombre completo>","type":"<tipo>"}},{{"id":"R1","name":"<nombre>","type":"resistor","value":"<valor>","unit":"Ω"}}],"nets":[{{"name":"<NET_NAME>","nodes":["<U1.PIN>","<R1.1>"]}}],"power":"<descripción de alimentación>","warnings":[]}}"""


class CircuitAgent:
    def __init__(self):
        self.circuit_manager = CircuitDesignManager()
        self._synthesizer = CircuitSynthesizer()

    # ──────────────────────────────────────────────────────────────────────────
    # PIPELINE POR CAPAS
    # ──────────────────────────────────────────────────────────────────────────

    def _capa1_validate_spec(
        self, spec: Dict[str, Any]
    ) -> tuple:
        """
        CAPA 1 — Validación de spec antes del synthesizer.
        Verifica que cada bloque tenga handler conocido.
        Intenta resolver via BLOCK_TYPE_ALIASES si no mapea directamente.
        Retorna (spec_validado, n_mapeados, n_ignorados).
        """
        valid_blocks = []
        mapped = 0
        ignored = 0
        for block in spec.get("blocks", []):
            handler = self._synthesizer._find_handler(block)
            if handler is not None:
                valid_blocks.append(block)
            else:
                model_raw = block.get("model", "").lower().strip()
                alias = BLOCK_TYPE_ALIASES.get(model_raw)
                if alias:
                    # Remap block para que el synthesizer lo resuelva correctamente
                    remapped = {**block, "model": alias}
                    valid_blocks.append(remapped)
                    mapped += 1
                    logger.info(
                        "[CircuitAgent] CAPA1: bloque '%s' mapeado → '%s'",
                        model_raw, alias,
                    )
                else:
                    label = block.get("model", block.get("type", "desconocido"))
                    logger.warning(
                        "[CircuitAgent] CAPA1: bloque '%s' sin handler ni alias — ignorado",
                        label,
                    )
                    ignored += 1
        spec = {**spec, "blocks": valid_blocks}
        return spec, mapped, ignored

    def _capa2_drc_with_retry(
        self, circuit_data: Dict[str, Any]
    ) -> tuple:
        """
        CAPA 2 — DRC eléctrico con hasta 2 intentos de auto-fix.
        Retorna (circuit_data, drc_result, intentos_usados).
        """
        from tools.electrical_drc import run_drc
        from tools.mcu_pinout_validator import validate_pinout

        attempts = 0
        drc_result = {"errors": [], "warnings": [], "passed": True}
        for attempt in range(3):
            attempts = attempt + 1
            try:
                drc_result = run_drc(circuit_data)
            except Exception as e:
                logger.warning("[CircuitAgent] CAPA2: DRC falló (intento %d): %s", attempts, e)
                break
            if drc_result.get("passed"):
                break
            if attempt < 2:
                # Auto-fix: remueve nodos duplicados y conecta flotantes a GND
                self._validate_circuit(circuit_data)
                logger.info(
                    "[CircuitAgent] CAPA2: %d errores DRC — auto-fix intento %d",
                    len(drc_result.get("errors", [])), attempt + 1,
                )

        pinout_warnings = []
        try:
            pinout_warnings = validate_pinout(circuit_data)
        except Exception:
            pass

        circuit_data["drc"] = drc_result
        for pw in pinout_warnings:
            circuit_data.setdefault("warnings", []).append(pw)
        if not drc_result["passed"]:
            for err in drc_result.get("errors", []):
                circuit_data.setdefault("warnings", []).append(
                    f"[DRC] {err['code']}: {err['message']}"
                )
        return circuit_data, drc_result, attempts

    def _compute_schematic_score(
        self, circuit_data: Dict[str, Any], drc_result: Dict[str, Any]
    ) -> int:
        """CAPA 4 — Score esquemático 0-100."""
        score = 0
        components = circuit_data.get("components", [])
        nets = circuit_data.get("nets", [])

        # +30 si todos los comps caben en el viewBox (proxy: <= 50 componentes)
        if len(components) <= 50:
            score += 30

        # +30 si wire_count > 5 (nets con >1 nodo)
        wire_count = sum(1 for n in nets if len(n.get("nodes", [])) > 1)
        if wire_count > 5:
            score += 30

        # +20 si MCU tiene zona distinta al resto (siempre U1 en zona propia)
        has_mcu = any(
            (c.get("resolved_type") or c.get("type") or "").lower() in (
                "microcontroller", "arduino_uno", "arduino_nano", "arduino_mega",
                "esp32", "esp8266", "stm32",
            )
            for c in components
        )
        if has_mcu:
            score += 20

        # +20 si DRC passed
        if drc_result.get("passed"):
            score += 20

        return score

    def _compute_pcb_score(
        self, circuit_data: Dict[str, Any], drc_result: Dict[str, Any]
    ) -> int:
        """CAPA 4 — Score PCB 0-100."""
        score = 0
        components = circuit_data.get("components", [])

        # +40 si ocupación estimada > 35% (proxy: circuito con >= 4 componentes)
        if len(components) >= 4:
            score += 40

        # +30 si x_variance estimada > 20mm (proxy: múltiples zonas distintas)
        zone_types = set()
        for c in components:
            ctype = (c.get("resolved_type") or c.get("type") or "").lower()
            if ctype in ("microcontroller", "arduino_uno", "esp32", "esp8266"):
                zone_types.add("mcu")
            elif ctype in ("relay", "relay_module"):
                zone_types.add("relay")
            elif "sensor" in ctype:
                zone_types.add("sensor")
            elif ctype in ("led", "connector"):
                zone_types.add("output")
            else:
                zone_types.add("other")
        if len(zone_types) >= 2:
            score += 30

        # +30 si DRC passed
        if drc_result.get("passed"):
            score += 30

        return score

    def _extract_circuit_spec(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Stage 1 del pipeline de síntesis determinística.
        Llama al LLM con un prompt minimalista para extraer solo el template
        y los parámetros eléctricos — sin pedirle que genere conexiones.
        Devuelve el spec dict o None si el circuito no coincide con ningún template.
        """
        try:
            prompt = CIRCUIT_SPEC_PROMPT.format(description=description)
            response = call_llm_sync(
                [{"role": "user", "content": prompt}],
                model=LLM_MODEL_FAST,
                response_format={"type": "json_object"},
                timeout=15,
            )
            raw = response["choices"][0]["message"]["content"]
            spec = json.loads(raw)
            if not spec.get("blocks"):
                return None
            return spec
        except Exception as e:
            logger.debug(f"[CircuitAgent] spec extraction falló (fallback a LLM full): {e}")
            return None

    def _finalize_circuit(
        self,
        circuit_data: Dict[str, Any],
        pipeline_log: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Paso final del path de síntesis determinística.
        CAPA 2: DRC con hasta 2 reintentos de auto-fix.
        CAPA 4: calcula scores de calidad.
        Persiste en DB y anota design_id.
        """
        pipeline_log = pipeline_log or []

        # CAPA 2 — síntesis con retry DRC
        circuit_data, drc_result, attempts = self._capa2_drc_with_retry(circuit_data)
        n_comps = len(circuit_data.get("components", []))
        n_nets     = len(circuit_data.get("nets", []))
        drc_status = "DRC OK" if drc_result["passed"] else f"{len(drc_result['errors'])} errores"
        pipeline_log.append(
            f"⚙️ Sintetizando... → {n_comps} componentes, {n_nets} nets "
            f"({drc_status}, {attempts} intento{'s' if attempts > 1 else ''})"
        )

        # CAPA 3 — verificación esquemático
        sch_issues = []
        wire_count = sum(
            1 for n in circuit_data.get("nets", [])
            if len(n.get("nodes", [])) > 1
        )
        if len(circuit_data.get("components", [])) > 50:
            sch_issues.append("componentes > 50 — puede haber recorte en viewBox")
        if wire_count <= 5:
            sch_issues.append(f"wire_count={wire_count} (se esperan >5 wires visibles)")

        sch_score = self._compute_schematic_score(circuit_data, drc_result)
        sch_status = f"score {sch_score}/100"
        if sch_issues:
            sch_status += " — " + "; ".join(sch_issues)
        pipeline_log.append(f"📐 Esquemático... → {sch_status}")

        # CAPA 3 — verificación PCB
        pcb_score = self._compute_pcb_score(circuit_data, drc_result)
        pipeline_log.append(f"🗺️ PCB... → score {pcb_score}/100")

        # CAPA 4 — scores al circuito
        circuit_data["pipeline_scores"] = {"schematic": sch_score, "pcb": pcb_score}

        circuit_data.setdefault("detected_domain", "synthesized")
        circuit_data.setdefault("selected_mcu", "")

        design_id = self.circuit_manager.save_design(circuit_data)
        circuit_data["design_id"] = design_id
        pipeline_log.append(f"✅ Listo — Circuit ID {design_id}")
        circuit_data["pipeline_log"] = pipeline_log

        logger.info(
            f"[CircuitAgent] Circuito sintetizado '{circuit_data['name']}' "
            f"guardado con ID {design_id} — DRC {'OK' if drc_result['passed'] else 'FALLÓ'} "
            f"sch={sch_score}/100 pcb={pcb_score}/100"
        )
        return circuit_data

    def parse_circuit(self, description: str, mcu: str = "Arduino Uno") -> Optional[Dict[str, Any]]:
        """Parsea descripción NL → netlist JSON completo y correcto eléctricamente.

        Pipeline de dos etapas:
        1. Intenta síntesis determinística via CircuitSynthesizer (sin LLM para topología).
        2. Si el circuito no coincide con un template conocido, cae al flujo LLM completo.
        """
        try:
            pipeline_log: List[str] = []

            # ── Stage 1: síntesis determinística ─────────────────────────────
            spec = self._extract_circuit_spec(description)
            if spec:
                spec.setdefault("mcu", mcu)

                # CAPA 1 — validación de spec con alias resolution
                spec, capa1_mapped, capa1_ignored = self._capa1_validate_spec(spec)
                n_blocks = len(spec.get("blocks", []))
                pipeline_log.append(
                    f"🔍 Interpretando... → spec con {n_blocks} bloques"
                    + (f" ({capa1_mapped} mapeados)" if capa1_mapped else "")
                    + (f" ({capa1_ignored} ignorados)" if capa1_ignored else "")
                )

                synthesized = self._synthesizer.synthesize(spec)
                if synthesized is not None:
                    logger.info(
                        f"[CircuitAgent] Síntesis determinística OK — "
                        f"blocks={[b.get('model', b.get('type')) for b in spec.get('blocks', [])]} "
                        f"mcu={spec['mcu']} components={len(synthesized['components'])} "
                        f"nets={len(synthesized['nets'])}"
                    )
                    synthesized = self._finalize_circuit(synthesized, pipeline_log)
                    return synthesized

            logger.info("[CircuitAgent] Sin template match — usando flujo LLM completo")

            # ── Stage 2: flujo LLM completo (fallback) ───────────────────────
            # Detect domain and select best MCU
            domain = _detect_domain(description)
            best_mcu = _select_mcu(description, domain, mcu)
            domain_hint = DOMAIN_HINTS.get(domain, "")

            # Inject verified component pinouts BEFORE the LLM generates the netlist
            pinout_context = get_pinout_context_for_prompt([description])
            if pinout_context:
                logger.info(f"[CircuitAgent] Pinout context inyectado ({len(pinout_context)} chars)")

            # F1.3 — detect explicit N-load count and inject as hint
            load_count = _extract_load_count(description)
            if load_count >= 2:
                load_count_hint = (
                    f"\n═══════════════════════════════════════════════════════\n"
                    f"NÚMERO DE CARGAS DETECTADAS EN LA DESCRIPCIÓN: {load_count}\n"
                    f"═══════════════════════════════════════════════════════\n"
                    f"⚠ INSTRUCCIÓN OBLIGATORIA: el JSON DEBE contener exactamente "
                    f"{load_count} relays separados (RL1..RL{load_count}), "
                    f"{load_count} diodos flyback (D_fly1..D_fly{load_count}), "
                    f"{load_count} resistencias de control (R1..R{load_count}), "
                    f"{load_count} nets RELAY1_CTRL..RELAY{load_count}_CTRL, "
                    f"y {load_count} conectores de salida (J2..J{load_count + 1}).\n"
                    f"NUNCA agrupes las {load_count} cargas en un único módulo relay multi-canal.\n"
                )
            else:
                load_count_hint = ""

            prompt = CIRCUIT_PARSE_PROMPT.format(
                description=description,
                mcu=best_mcu,
                load_count_hint=load_count_hint,
                domain_hint=domain_hint,
                mcu_pin_rules=_mcu_pin_rules(best_mcu),
                pinout_context=pinout_context,
            )

            logger.info(
                f"[CircuitAgent] parse_circuit START — domain={domain} mcu={best_mcu} "
                f"load_count={load_count} model={LLM_MODEL_SMART!r} prompt_len={len(prompt)}"
            )

            messages = [{"role": "user", "content": prompt}]

            raw_content = None
            for attempt in range(2):
                try:
                    response = call_llm_sync(
                        messages,
                        model=LLM_MODEL_SMART,
                        response_format={"type": "json_object"} if attempt == 0 else None,
                        timeout=45,
                    )
                    raw_content = response["choices"][0]["message"]["content"]
                    logger.info(f"[CircuitAgent] LLM OK attempt={attempt} chars={len(raw_content)} preview={raw_content[:200]!r}")
                    break
                except Exception as llm_err:
                    logger.error(f"[CircuitAgent] LLM attempt {attempt+1} failed: {llm_err}")
                    if attempt == 1:
                        raise

            if not raw_content:
                logger.error("[CircuitAgent] LLM devolvió contenido vacío")
                return None

            content = self._clean_json_content(raw_content)
            circuit_data = json.loads(content)

            # Validate required keys
            for key in ["name", "description", "components", "nets"]:
                if key not in circuit_data:
                    logger.warning(f"Falta campo requerido '{key}' en respuesta del LLM.")
                    return None

            # Resolve component types
            for comp in circuit_data["components"]:
                resolved = resolve_component_type(comp.get("type"))
                comp["resolved_type"] = resolved or comp["type"]

            # Auto-complete missing values (resistors for LEDs, flyback diodes, etc.)
            self._calculate_missing_values(circuit_data)

            # Auto-complete AC→DC power stage if 220VAC mentioned but missing
            self._ensure_ac_dc_stage(circuit_data, description)

            # Domain-specific post-validation
            self._apply_domain_rules(circuit_data, domain)

            # Basic structural validation
            warnings = self._validate_circuit(circuit_data)
            if warnings:
                circuit_data.setdefault("warnings", []).extend(warnings)

            # DRC eléctrico
            from tools.electrical_drc import run_drc
            from tools.mcu_pinout_validator import validate_pinout
            try:
                drc_result = run_drc(circuit_data)
                pinout_warnings = validate_pinout(circuit_data)
            except Exception as drc_err:
                logger.warning(f"DRC/pinout falló: {drc_err}")
                drc_result = {"errors": [], "warnings": [], "passed": True}
                pinout_warnings = []

            # F1.1 — Review pass LLM si hay errors críticos o pinouts inválidos
            if drc_result["errors"] or pinout_warnings:
                reviewed = self._review_pass(
                    circuit_data, drc_result, pinout_warnings, best_mcu
                )
                if reviewed is not None:
                    circuit_data = reviewed
                    # Re-correr DRC + pinout sobre la versión revisada
                    try:
                        drc_result = run_drc(circuit_data)
                        pinout_warnings = validate_pinout(circuit_data)
                    except Exception as drc_err:
                        logger.warning(f"DRC/pinout post-review falló: {drc_err}")

            # Persist DRC + pinout
            circuit_data["drc"] = drc_result
            if not drc_result["passed"]:
                for err in drc_result["errors"]:
                    circuit_data.setdefault("warnings", []).append(
                        f"[DRC] {err['code']}: {err['message']}"
                    )
            for pw in pinout_warnings:
                circuit_data.setdefault("warnings", []).append(pw)

            # Annotate with detected domain and MCU
            circuit_data["detected_domain"] = domain
            circuit_data["selected_mcu"] = best_mcu

            # CAPA 4 — scores para el path LLM
            sch_score = self._compute_schematic_score(circuit_data, drc_result)
            pcb_score = self._compute_pcb_score(circuit_data, drc_result)
            circuit_data["pipeline_scores"] = {"schematic": sch_score, "pcb": pcb_score}

            n_comps = len(circuit_data.get("components", []))
            n_nets  = len(circuit_data.get("nets", []))
            llm_log = [
                f"🔍 Interpretando... → flujo LLM completo (dominio: {domain})",
                f"⚙️ Sintetizando... → {n_comps} componentes, {n_nets} nets",
                f"📐 Esquemático... → score {sch_score}/100",
                f"🗺️ PCB... → score {pcb_score}/100",
            ]

            # Save to DB
            design_id = self.circuit_manager.save_design(circuit_data)
            circuit_data["design_id"] = design_id
            llm_log.append(f"✅ Listo — Circuit ID {design_id}")
            circuit_data["pipeline_log"] = llm_log
            logger.info(f"Circuito '{circuit_data['name']}' guardado con ID {design_id} (dominio: {domain})")
            return circuit_data

        except json.JSONDecodeError as e:
            _preview = repr(content[:400]) if 'content' in locals() else 'N/A'
            logger.error(f"[CircuitAgent] JSONDecodeError: {e} | content={_preview}")
            return None
        except Exception as e:
            logger.exception(f"[CircuitAgent] Error parseando circuito: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _clean_json_content(self, content: str) -> str:
        match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
        if match:
            return match.group(1)
        # Fallback: find first { to last }
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            return content[start:end+1]
        return content

    def _calculate_missing_values(self, circuit_data: Dict[str, Any]) -> None:
        """Auto-agrega componentes de protección que el LLM omitió."""
        components = circuit_data["components"]
        nets = circuit_data.get("nets", [])
        warnings = circuit_data.setdefault("warnings", [])

        comp_ids = {c["id"] for c in components}
        types_by_id = {c["id"]: c.get("resolved_type", c.get("type", "")) for c in components}

        # 1. LEDs sin resistencia limitadora
        led_ids = [c["id"] for c in components if c.get("type") in ("led", "led_rgb")]
        resistor_ids = {c["id"] for c in components if c.get("type") == "resistor"}

        for led_id in led_ids:
            led_nets = [n for n in nets if any(led_id in node for node in n.get("nodes", []))]
            has_r = any(
                any(r_id in node for node in net.get("nodes", []))
                for net in led_nets for r_id in resistor_ids
            )
            if not has_r:
                new_id = f"R_auto_{led_id}"
                if new_id not in comp_ids:
                    components.append({
                        "id": new_id,
                        "name": f"Resistencia LED {led_id} 220Ω",
                        "type": "resistor", "resolved_type": "resistor",
                        "value": "220", "unit": "Ω", "auto_added": True,
                    })
                    comp_ids.add(new_id)
                    warnings.append(f"[Auto] Resistencia {new_id} (220Ω) agregada para {led_id} — verificá valor según Vcc y color del LED")

        # 2. Relays sin diodo flyback — UN flyback DEDICADO por relay (no reusar)
        relay_ids = [c["id"] for c in components
                     if c.get("resolved_type", c.get("type", "")) in ("relay", "relay_module", "ssr")
                     or c["id"].lower().startswith("rl")]
        # diode_ids se recalcula dentro del loop porque agregamos diodos nuevos
        used_diode_ids: set = set()  # diodos ya asignados a un relay en esta corrida

        for relay_id in relay_ids:
            diode_ids = {c["id"] for c in components
                         if c.get("resolved_type", c.get("type", "")) in ("diode", "1n4007")}
            relay_nets = [n for n in nets if any(relay_id in node for node in n.get("nodes", []))]
            has_flyback = (
                # Nivel 1: conectividad real (lógica actual)
                any(
                    any(d_id in node for node in net.get("nodes", []))
                    for net in relay_nets for d_id in diode_ids
                )
                or
                # Nivel 2: nombre contiene "flyback" o "fly"
                any(
                    "flyback" in c.get("name", "").lower()
                    or "fly" in c.get("id", "").lower()
                    for c in components if c["id"] in diode_ids
                )
                or
                # Nivel 3: existe algún diodo 1N4007 en el circuito y hay un relay
                any(
                    c.get("resolved_type", c.get("type", "")) == "1n4007"
                    for c in components
                )
            )
            if not has_flyback:
                # Crear un diodo NUEVO por cada relay (no reusar otros — un relay = un flyback)
                new_id = f"D_fly_{relay_id}"
                if new_id not in comp_ids:
                    components.append({
                        "id": new_id,
                        "name": f"Diodo flyback 1N4007 {relay_id}",
                        "type": "diode", "resolved_type": "diode",
                        "value": "1N4007", "auto_added": True,
                    })
                    comp_ids.add(new_id)
                used_diode_ids.add(new_id)
                warnings.append(f"[Auto] Diodo flyback {new_id} (1N4007) agregado para relay {relay_id}")

                # Conectar diodo: cátodo al net de control del relay, ánodo a GND
                ctrl_net = next(
                    (n for n in relay_nets
                     if any("ctrl" in n["name"].lower() or "coil" in n["name"].lower()
                            for _ in [1])),
                    relay_nets[0] if relay_nets else None,
                )
                gnd_net = next(
                    (n for n in nets if "gnd" in n["name"].lower()), None
                )
                if ctrl_net and f"{new_id}.cathode" not in ctrl_net["nodes"]:
                    ctrl_net["nodes"].append(f"{new_id}.cathode")
                if gnd_net and f"{new_id}.anode" not in gnd_net["nodes"]:
                    gnd_net["nodes"].append(f"{new_id}.anode")

    def _ensure_ac_dc_stage(self, circuit_data: Dict[str, Any], description: str) -> None:
        """
        Si la descripción menciona 220VAC/110VAC y el JSON no incluye una etapa
        de conversión AC→DC, agrega los componentes mínimos: F1, D6 (MOV), T1,
        BR1, C1, U2 (LM7805), C2 — junto con sus nets correspondientes.
        Solo se ejecuta cuando hay un MCU presente.
        """
        desc_l = (description or "").lower()
        ac_keywords = ("220vac", "220 vac", "220v", "110vac", "110 vac", "110v",
                       "red eléctrica", "red electrica", "alimentado desde red",
                       "corriente alterna", "230vac", "240vac")
        if not any(kw in desc_l for kw in ac_keywords):
            return

        components = circuit_data["components"]
        nets = circuit_data.setdefault("nets", [])
        warnings = circuit_data.setdefault("warnings", [])
        comp_ids = {c["id"] for c in components}
        types_present = {(c.get("resolved_type") or c.get("type") or "").lower() for c in components}

        # Si ya hay etapa de conversión, no hacer nada
        has_converter = any(t in types_present for t in
                            ("transformer", "smps", "bridge_rectifier"))
        if has_converter:
            return

        # No tiene sentido autocompletar si no hay MCU al cual alimentar
        has_mcu = any(t in types_present for t in
                      ("arduino_uno", "arduino_nano", "arduino_mega", "esp32",
                       "esp8266", "stm32", "pico", "rp2040", "mcu"))
        if not has_mcu:
            return

        # Construir IDs únicos sin pisar existentes
        def _new(prefix: str) -> str:
            i = 1
            while f"{prefix}{i}" in comp_ids:
                i += 1
            cid = f"{prefix}{i}"
            comp_ids.add(cid)
            return cid

        # Componentes a agregar (PATH A: transformer + bridge + 7805)
        added: List[Dict[str, Any]] = []
        if "fuse" not in types_present:
            fid = _new("F")
            added.append({"id": fid, "name": "Fusible AC 5A", "type": "fuse",
                          "resolved_type": "fuse", "value": "5", "unit": "A",
                          "auto_added": True})
        else:
            fid = next(c["id"] for c in components if (c.get("resolved_type") or c.get("type") or "").lower() == "fuse")

        if "varistor" not in types_present and "mov" not in types_present:
            mov_id = _new("D")
            added.append({"id": mov_id, "name": "Varistor MOV S20K275",
                          "type": "varistor", "resolved_type": "varistor",
                          "value": "S20K275", "auto_added": True})
        else:
            mov_id = None

        t_id = _new("T")
        added.append({"id": t_id, "name": "Transformador 220VAC/12VAC 50VA",
                      "type": "transformer", "resolved_type": "transformer",
                      "auto_added": True})

        br_id = _new("BR")
        added.append({"id": br_id, "name": "Puente rectificador GBU4J",
                      "type": "bridge_rectifier", "resolved_type": "bridge_rectifier",
                      "auto_added": True})

        cap_filter_id = _new("C")
        added.append({"id": cap_filter_id, "name": "Cap filtro 2200µF",
                      "type": "capacitor_electrolytic",
                      "resolved_type": "capacitor_electrolytic",
                      "value": "2200", "unit": "µF", "auto_added": True})

        reg_id = _new("U")
        added.append({"id": reg_id, "name": "LM7805 +5V",
                      "type": "voltage_regulator",
                      "resolved_type": "voltage_regulator",
                      "value": "LM7805", "auto_added": True})

        cap_dec_id = _new("C")
        added.append({"id": cap_dec_id, "name": "Cap desacoplo 100nF",
                      "type": "capacitor", "resolved_type": "capacitor",
                      "value": "100", "unit": "nF", "auto_added": True})

        # Conector de entrada AC si falta uno explícito de 220V
        ac_connector_id = None
        for c in components:
            n = (c.get("name", "") or "").lower()
            if (c.get("resolved_type") or c.get("type") or "").lower() == "connector" and (
                "220" in n or "110" in n or "ac" in n or "entrada" in n
            ):
                ac_connector_id = c["id"]
                break
        if not ac_connector_id:
            ac_connector_id = _new("J")
            added.append({"id": ac_connector_id, "name": "Entrada 220VAC",
                          "type": "connector", "resolved_type": "connector",
                          "auto_added": True})

        components.extend(added)

        # Nets nuevos / extender existentes
        def _get_or_create_net(name: str) -> Dict[str, Any]:
            for n in nets:
                if n["name"].upper() == name.upper():
                    return n
            new = {"name": name, "nodes": []}
            nets.append(new)
            return new

        # 220VAC L: J1.L → F1.1 → MOV.1
        n_l = _get_or_create_net("VCC_220VAC_L")
        for node in (f"{ac_connector_id}.L", f"{fid}.1", f"{mov_id}.1" if mov_id else None):
            if node and node not in n_l["nodes"]:
                n_l["nodes"].append(node)
        # 220VAC N: J1.N → T1.PRI_N
        n_n = _get_or_create_net("VCC_220VAC_N")
        for node in (f"{ac_connector_id}.N", f"{t_id}.PRI_N", f"{mov_id}.2" if mov_id else None):
            if node and node not in n_n["nodes"]:
                n_n["nodes"].append(node)
        # F1.2 → T1.PRI_L
        n_f = _get_or_create_net("VCC_220VAC_F")
        for node in (f"{fid}.2", f"{t_id}.PRI_L"):
            if node not in n_f["nodes"]:
                n_f["nodes"].append(node)
        # 12VAC sec: T1.SEC_A → BR1.AC1, T1.SEC_B → BR1.AC2
        for sec, ac_in in [("SEC_A", "AC1"), ("SEC_B", "AC2")]:
            n_sec = _get_or_create_net(f"VCC_12VAC_{sec[-1]}")
            for node in (f"{t_id}.{sec}", f"{br_id}.{ac_in}"):
                if node not in n_sec["nodes"]:
                    n_sec["nodes"].append(node)
        # Rectified: BR1.+ → C1.+ → U2.IN
        n_rec = _get_or_create_net("RECTIFIED_VCC")
        for node in (f"{br_id}.PLUS", f"{cap_filter_id}.PLUS", f"{reg_id}.IN"):
            if node not in n_rec["nodes"]:
                n_rec["nodes"].append(node)
        # GND
        n_gnd = next((n for n in nets if "gnd" in n["name"].lower() or "ground" in n["name"].lower()), None)
        if n_gnd is None:
            n_gnd = {"name": "GND", "nodes": []}
            nets.append(n_gnd)
        for node in (f"{br_id}.MINUS", f"{cap_filter_id}.MINUS",
                     f"{reg_id}.GND", f"{cap_dec_id}.2"):
            if node not in n_gnd["nodes"]:
                n_gnd["nodes"].append(node)
        # VCC_5V output (extender net existente si lo hay, o crear)
        n_5v = next((n for n in nets if any(v in n["name"].lower()
                                            for v in ("vcc_5v", "5v", "vcc"))), None)
        if n_5v is None:
            n_5v = {"name": "VCC_5V", "nodes": []}
            nets.append(n_5v)
        for node in (f"{reg_id}.OUT", f"{cap_dec_id}.1"):
            if node not in n_5v["nodes"]:
                n_5v["nodes"].append(node)

        warnings.append(
            f"[Auto-AC/DC] Etapa de conversión 220VAC→5VDC agregada automáticamente "
            f"(componentes: {fid}, {mov_id or 'sin MOV'}, {t_id}, {br_id}, "
            f"{cap_filter_id}, {reg_id}, {cap_dec_id}). El LLM la había omitido."
        )

    def _apply_domain_rules(self, circuit_data: Dict[str, Any], domain: str) -> None:
        """Validaciones extra por dominio."""
        warnings = circuit_data.setdefault("warnings", [])
        types = {c.get("resolved_type", c.get("type", "")) for c in circuit_data["components"]}

        if domain == "irrigation":
            if "relay" not in types and "relay_module" not in types:
                warnings.append("[Dominio] Sistema de riego sin relay — ¿cómo se controla la bomba?")
            if not any(t in types for t in ("sensor", "moisture_sensor")):
                warnings.append("[Dominio] Sistema de riego sin sensor de humedad del suelo")

        if domain == "motor":
            has_driver = any(t in types for t in ("motor_driver", "l298n", "drv8825", "a4988"))
            if not has_driver:
                warnings.append("[Dominio] Control de motor sin driver — conectar motor directamente al MCU puede dañarlo")

        if domain == "iot":
            has_wifi = any(t in types for t in ("esp32", "esp8266", "wifi_module"))
            if not has_wifi:
                warnings.append("[Dominio] Proyecto IoT sin módulo WiFi (ESP32 recomendado)")

    def _validate_circuit(self, circuit_data: Dict[str, Any]) -> List[str]:
        """
        F1.4 — validates AND auto-fixes the netlist:
          • Duplicate nodes → removed from the SECONDARY net (first occurrence wins)
          • Floating components → connected to GND if 2-terminal passive,
            or removed from JSON if no recovery is possible
        """
        warnings: List[str] = []
        nets = circuit_data.get("nets", [])
        components = circuit_data.get("components", [])

        # ── 1. Duplicate nodes — auto-fix by removing from secondary nets ──
        nodes_seen: Dict[str, str] = {}
        for net in nets:
            kept_nodes = []
            for node in net.get("nodes", []):
                if node in nodes_seen:
                    if nodes_seen[node] != net["name"]:
                        warnings.append(
                            f"[Auto-fix] Nodo duplicado {node} removido de net "
                            f"'{net['name']}' (ya estaba en '{nodes_seen[node]}')"
                        )
                    # drop from this net (keep first occurrence)
                else:
                    nodes_seen[node] = net["name"]
                    kept_nodes.append(node)
            net["nodes"] = kept_nodes

        # ── 2. Floating components — auto-fix by connecting to GND or removing ──
        connected = {node.split('.')[0] for net in nets for node in net.get("nodes", [])}
        gnd_net = next((n for n in nets if "gnd" in n["name"].lower() or "ground" in n["name"].lower()), None)

        # 2-terminal passives that are safe to ground if floating
        groundable_types = {
            "capacitor", "capacitor_ceramic", "capacitor_electrolytic",
            "resistor", "diode", "varistor", "fuse", "inductor",
        }

        components_to_remove: List[str] = []
        for comp in components:
            if comp["id"] in connected:
                continue

            ctype = (comp.get("resolved_type") or comp.get("type") or "").lower()

            # Strategy 1: groundable passive → connect 2nd pin to GND
            if gnd_net and ctype in groundable_types:
                gnd_node = f"{comp['id']}.2"
                if gnd_node not in gnd_net["nodes"]:
                    gnd_net["nodes"].append(gnd_node)
                    connected.add(comp["id"])
                    warnings.append(
                        f"[Auto-fix] Componente flotante {comp['id']} ({comp.get('name','')}) "
                        f"conectado a GND vía {gnd_node}"
                    )
                    continue

            # Strategy 2: not safely auto-connectable → mark for removal
            components_to_remove.append(comp["id"])
            warnings.append(
                f"[Auto-fix] Componente {comp['id']} ({comp.get('name','')}) "
                f"removido del JSON — no tenía nets y no es auto-conectable"
            )

        if components_to_remove:
            circuit_data["components"] = [
                c for c in components if c["id"] not in components_to_remove
            ]

        # ── 3. Sanity checks (informational) ──
        net_names = [n["name"].lower() for n in nets]
        has_vcc = any(v in name for name in net_names for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd"))
        has_gnd = any("gnd" in name or "ground" in name for name in net_names)
        if not has_vcc:
            warnings.append("No se detectó net de alimentación (VCC/5V/3V3)")
        if not has_gnd:
            warnings.append("No se detectó net de masa (GND)")

        # ── 4. N-load compliance check (post-LLM verification) ──
        desc = circuit_data.get("description", "") or ""
        expected_n = _extract_load_count(desc)
        if expected_n >= 2:
            relay_count = sum(
                1 for c in circuit_data["components"]
                if (c.get("resolved_type") or c.get("type") or "").lower()
                in ("relay", "relay_module", "ssr")
            )
            if relay_count < expected_n:
                warnings.append(
                    f"[N-load] Se esperaban {expected_n} relays separados "
                    f"pero el LLM generó {relay_count}. Revisar prompt o regenerar."
                )

        return warnings

    # ──────────────────────────────────────────────────────────────────────────
    # F1.1 — Review pass LLM
    # ──────────────────────────────────────────────────────────────────────────

    def _review_pass(
        self,
        circuit_data: Dict[str, Any],
        drc_result: Dict[str, Any],
        pinout_warnings: List[str],
        best_mcu: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Segundo pase LLM: audita el circuito generado y lo corrige.
        Acepta la versión revisada solo si:
          • Mantiene el MCU original (no lo borra ni lo cambia de tipo).
          • Reduce el número de errores DRC.
        Si no cumple, devuelve None y mantenemos la versión original.
        """
        from tools.electrical_drc import run_drc
        from tools.mcu_pinout_validator import validate_pinout

        original_errors = len(drc_result.get("errors", [])) + len(pinout_warnings)
        issues_summary = []
        for err in drc_result.get("errors", [])[:20]:
            issues_summary.append(f"- [DRC/{err['code']}] {err['message']}")
        for pw in pinout_warnings[:10]:
            issues_summary.append(f"- {pw}")

        if not issues_summary:
            return None

        # Identificar el MCU original (debe sobrevivir a la revisión)
        original_mcu_id = None
        for c in circuit_data.get("components", []):
            ctype = (c.get("resolved_type") or c.get("type") or "").lower()
            if any(m in ctype for m in ("arduino", "esp32", "esp8266", "stm32", "pico", "rp2040")):
                original_mcu_id = c.get("id")
                break

        circuit_json = json.dumps(circuit_data, ensure_ascii=False)
        # Limitar tamaño del prompt si el circuito es grande
        if len(circuit_json) > 12000:
            logger.info(f"[CircuitAgent.review] Circuito grande ({len(circuit_json)} chars), saltando review pass")
            return None

        prompt = f"""Sos un ingeniero electrónico senior auditando este diseño. Otro modelo \
generó el siguiente JSON pero tiene problemas detectados por validadores automáticos.

CIRCUITO GENERADO:
{circuit_json}

PROBLEMAS DETECTADOS:
{chr(10).join(issues_summary)}

MCU OBJETIVO: {best_mcu}

INSTRUCCIONES:
1. Resolvé TODOS los problemas listados manteniendo la intención original del circuito.
2. NO elimines el MCU principal ({original_mcu_id or 'el MCU declarado'}).
3. Si un pin es inválido (ej: D14 en Nano), reasignalo a un pin válido del MCU.
4. Si falta un componente de protección (flyback, fusible, pull-up), agregalo con valor estándar.
5. Si la polaridad de un diodo está invertida, corregila (cátodo en señal, ánodo a GND).
6. Mantené la nomenclatura existente (U1, R1, RL1, etc.) excepto cuando agregues componentes.

Respondé ÚNICAMENTE con el JSON corregido completo (mismo formato que el original).
SIN markdown, SIN explicaciones."""

        try:
            response = call_llm_sync(
                [{"role": "user", "content": prompt}],
                model=LLM_MODEL_SMART,
                response_format={"type": "json_object"},
                timeout=45,
            )
            raw = response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"[CircuitAgent.review] LLM falló: {e}")
            return None

        try:
            content = self._clean_json_content(raw)
            reviewed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"[CircuitAgent.review] JSON inválido: {e}")
            return None

        # Validar shape básico
        if not all(k in reviewed for k in ("components", "nets")):
            logger.warning("[CircuitAgent.review] Falta components o nets")
            return None

        # Re-resolver tipos de componentes
        for comp in reviewed["components"]:
            if "resolved_type" not in comp:
                comp["resolved_type"] = resolve_component_type(comp.get("type")) or comp.get("type")

        # Verificar que el MCU original sobreviva
        if original_mcu_id:
            survivor = next(
                (c for c in reviewed["components"] if c.get("id") == original_mcu_id),
                None,
            )
            if not survivor:
                logger.warning(f"[CircuitAgent.review] El auditor eliminó el MCU {original_mcu_id} — descartando")
                return None

        # Re-correr DRC sobre la versión revisada
        try:
            new_drc = run_drc(reviewed)
        except Exception as e:
            logger.warning(f"[CircuitAgent.review] DRC sobre revisión falló: {e}")
            return None

        new_pinout = validate_pinout(reviewed)
        new_errors = len(new_drc.get("errors", [])) + len(new_pinout)
        if new_errors >= original_errors:
            logger.info(
                f"[CircuitAgent.review] Revisión no mejora ({original_errors}→{new_errors} errors) — descartando"
            )
            return None

        logger.info(
            f"[CircuitAgent.review] Revisión aplicada: errors {original_errors}→{new_errors}"
        )
        # Preservar campos del original que el auditor no devuelve
        for k in ("name", "description", "power", "design_id"):
            if k not in reviewed and k in circuit_data:
                reviewed[k] = circuit_data[k]
        reviewed.setdefault("warnings", [])
        reviewed["warnings"].append(
            f"[Auto-review] Revisión LLM aplicada — errors DRC {original_errors}→{new_errors}"
        )
        return reviewed

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def get_circuit_by_id(self, design_id: int) -> Optional[Dict[str, Any]]:
        return self.circuit_manager.get_design(design_id)

    def list_all_circuits(self) -> List[Dict[str, Any]]:
        return self.circuit_manager.list_designs()
