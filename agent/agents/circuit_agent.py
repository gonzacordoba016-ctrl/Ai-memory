# agent/agents/circuit_agent.py

import json
import re
from typing import Dict, Any, Optional, List
from core.logger import get_logger
from core.config import LLM_MODEL_SMART, LLM_MODEL_FAST
from database.circuit_design import CircuitDesignManager
from tools.hardware_detector import resolve_component_type
from llm.openrouter_client import _call_llm

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN DETECTION — fast pass before full parse
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_KEYWORDS = {
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
    "sensor_hub": ["sensor", "temperatura", "temperatura", "temperatura", "humedad",
                   "presión", "pressure", "gas", "co2", "calidad del aire", "air quality",
                   "dht", "bmp280", "mpu6050", "hx711", "balanza", "scale"],
    "iot":        ["wifi", "mqtt", "http", "api", "cloud", "iot", "internet",
                   "blynk", "thingspeak", "telegram", "web server", "ota"],
    "audio":      ["audio", "sonido", "sound", "speaker", "altavoz", "micrófono",
                   "buzzer", "piezo", "i2s", "amplificador", "amp", "max98357"],
}

# MCU recommendation by domain
DOMAIN_MCU = {
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
# MAIN PROMPT
# ──────────────────────────────────────────────────────────────────────────────

CIRCUIT_PARSE_PROMPT = """Eres un ingeniero electrónico senior especializado en diseño de circuitos embebidos.
Tu tarea es generar una netlist JSON completa, correcta eléctricamente y lista para fabricación.

Descripción del circuito: "{description}"
Microcontrolador principal: "{mcu}"
{domain_hint}

REGLAS OBLIGATORIAS — aplicá TODAS sin excepción:
1. ALIMENTACIÓN: incluí VCC y GND para cada componente activo. Los pines de alimentación deben estar en los nets correctos.
2. LEDs: SIEMPRE llevan resistencia limitadora en serie. R = (Vcc - Vled) / 20mA. Ejemplo: LED rojo con 5V → R = (5-2) / 0.02 = 150Ω → usá 150Ω o 220Ω.
3. CAPACITORES DE DESACOPLE: 100nF cerámico entre VCC y GND cerca de cada IC. Para ESP32/módulos WiFi: agrega también 100µF electrolítico.
4. I2C: resistencias pull-up 4.7kΩ a VCC en SDA y SCL cuando hay dispositivos I2C.
5. ONE-WIRE (DS18B20, DHT): pull-up 10kΩ en línea de datos.
6. RELAYS: diodo flyback 1N4007 en antiparalelo con la bobina (entre pines de la bobina).
7. MOTORES DC/PASO A PASO: capacitor bulk 470µF + 100nF entre VCC_MOTOR y GND_MOTOR.
8. NOMENCLATURA: U1-U99 (ICs/MCU), R1-R99 (resistencias), C1-C99 (caps), D1-D99 (LEDs/diodos), SW1+ (botones), MOD1+ (módulos), RL1+ (relays), Q1+ (transistores/MOSFET).
9. NETS descriptivos: VCC_5V, VCC_3V3, GND, SDA, SCL, DATA_SENS, RELAY_CTRL, PWM_MOTOR, etc.
10. PINES REALES: asigná pines concretos del MCU (ej: U1.GPIO4, U1.D13, U1.A0, U1.SDA). No uses "U1.pin1" genérico.
11. FUENTE DE ALIMENTACIÓN: especificá "power" con voltaje real (ej: "5V USB", "12V DC adapter", "7.4V LiPo + AMS1117-5V").
12. WARNINGS: incluí advertencias reales de riesgo (voltaje AC, alta corriente, mezcla de niveles 5V/3.3V, etc.).

Componentes que DEBES incluir cuando corresponde:
- Relay → diodo flyback 1N4007 (obligatorio)
- Motor DC → cap 470µF bulk + 4× diodo 1N5819 (puente flyback)
- ESP32 → cap 100µF + 100nF VCC
- Sensor I2C → pull-ups 4.7kΩ
- Batería → fusible de protección

Devuelve SOLO el JSON válido, sin texto antes ni después, sin bloques markdown:
{{
  "name": "nombre descriptivo del proyecto",
  "description": "descripción en 1-2 oraciones de qué hace el circuito",
  "components": [
    {{"id": "U1", "name": "{mcu}", "type": "arduino_uno"}},
    {{"id": "R1", "name": "Resistencia LED rojo 150Ω", "type": "resistor", "value": "150", "unit": "Ω"}},
    {{"id": "D1", "name": "LED Rojo indicador", "type": "led", "color": "red"}},
    {{"id": "C1", "name": "Cap desacople 100nF", "type": "capacitor", "value": "100n", "unit": "F"}},
    {{"id": "SW1", "name": "Pulsador reset", "type": "button"}}
  ],
  "nets": [
    {{"name": "VCC_5V",  "nodes": ["U1.5V", "R1.1", "C1.1"]}},
    {{"name": "GND",     "nodes": ["U1.GND", "D1.K", "C1.2"]}},
    {{"name": "LED_DRV", "nodes": ["U1.D13", "R1.2"]}},
    {{"name": "LED_A",   "nodes": ["R1.2", "D1.A"]}}
  ],
  "power": "5V USB",
  "warnings": []
}}"""


class CircuitAgent:
    def __init__(self):
        self.circuit_manager = CircuitDesignManager()

    def parse_circuit(self, description: str, mcu: str = "Arduino Uno") -> Optional[Dict[str, Any]]:
        """Parsea descripción NL → netlist JSON completo y correcto eléctricamente."""
        try:
            # Detect domain and select best MCU
            domain = _detect_domain(description)
            best_mcu = _select_mcu(description, domain, mcu)
            domain_hint = DOMAIN_HINTS.get(domain, "")

            prompt = CIRCUIT_PARSE_PROMPT.format(
                description=description,
                mcu=best_mcu,
                domain_hint=domain_hint,
            )

            messages = [{"role": "user", "content": prompt}]
            response = _call_llm(messages, model=LLM_MODEL_SMART)
            content = response["choices"][0]["message"]["content"]
            content = self._clean_json_content(content)

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

            # Domain-specific post-validation
            self._apply_domain_rules(circuit_data, domain)

            # Basic structural validation
            warnings = self._validate_circuit(circuit_data)
            if warnings:
                circuit_data.setdefault("warnings", []).extend(warnings)

            # DRC eléctrico
            try:
                from tools.electrical_drc import run_drc
                drc_result = run_drc(circuit_data)
                circuit_data["drc"] = drc_result
                if not drc_result["passed"]:
                    for err in drc_result["errors"]:
                        circuit_data.setdefault("warnings", []).append(
                            f"[DRC] {err['code']}: {err['message']}"
                        )
            except Exception as drc_err:
                logger.warning(f"DRC falló: {drc_err}")

            # Annotate with detected domain and MCU
            circuit_data["detected_domain"] = domain
            circuit_data["selected_mcu"] = best_mcu

            # Save to DB
            design_id = self.circuit_manager.save_design(circuit_data)
            circuit_data["design_id"] = design_id
            logger.info(f"Circuito '{circuit_data['name']}' guardado con ID {design_id} (dominio: {domain})")
            return circuit_data

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON del LLM: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error parseando circuito: {e}")
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

        # 2. Relays sin diodo flyback
        relay_ids = [c["id"] for c in components
                     if c.get("resolved_type", c.get("type", "")) in ("relay", "relay_module")]
        diode_ids = {c["id"] for c in components
                     if c.get("resolved_type", c.get("type", "")) in ("diode", "1n4007")}

        for relay_id in relay_ids:
            relay_nets = [n for n in nets if any(relay_id in node for node in n.get("nodes", []))]
            has_flyback = any(
                any(d_id in node for node in net.get("nodes", []))
                for net in relay_nets for d_id in diode_ids
            )
            if not has_flyback:
                new_id = f"D_fly_{relay_id}"
                if new_id not in comp_ids:
                    components.append({
                        "id": new_id,
                        "name": f"Diodo flyback 1N4007 {relay_id}",
                        "type": "diode", "resolved_type": "diode",
                        "value": "1N4007", "auto_added": True,
                    })
                    comp_ids.add(new_id)
                    warnings.append(f"[Auto] Diodo flyback {new_id} (1N4007) agregado para relay {relay_id}")

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
        warnings = []

        # Duplicate nodes
        nodes_used: Dict[str, str] = {}
        for net in circuit_data.get("nets", []):
            for node in net.get("nodes", []):
                if node in nodes_used:
                    warnings.append(f"Nodo duplicado: {node} en nets '{nodes_used[node]}' y '{net['name']}'")
                else:
                    nodes_used[node] = net["name"]

        # Disconnected components
        connected = {node.split('.')[0] for net in circuit_data.get("nets", [])
                     for node in net.get("nodes", [])}
        for comp in circuit_data.get("components", []):
            if comp["id"] not in connected:
                warnings.append(f"Componente {comp['id']} ({comp.get('name','')}) no tiene nets asignados")

        # No VCC/GND nets
        net_names = [n["name"].lower() for n in circuit_data.get("nets", [])]
        has_vcc = any(v in name for name in net_names for v in ("vcc", "5v", "3v3", "3.3v", "vin", "vdd"))
        has_gnd = any("gnd" in name or "ground" in name for name in net_names)
        if not has_vcc:
            warnings.append("No se detectó net de alimentación (VCC/5V/3V3)")
        if not has_gnd:
            warnings.append("No se detectó net de masa (GND)")

        return warnings

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def get_circuit_by_id(self, design_id: int) -> Optional[Dict[str, Any]]:
        return self.circuit_manager.get_design(design_id)

    def list_all_circuits(self) -> List[Dict[str, Any]]:
        return self.circuit_manager.list_designs()
