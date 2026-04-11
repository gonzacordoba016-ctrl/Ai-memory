# core/prompt_builder.py

from datetime import datetime


def format_history(history):
    text = ""
    for msg in history:
        role    = msg["role"]
        content = msg["content"]
        text   += f"{'Usuario' if role == 'user' else 'Asistente'}: {content}\n"
    return text


def format_memories(memories):
    if not memories:
        return ""
    text = "Memorias relevantes:\n"
    for m in memories:
        text += f"- {m}\n"
    return text


def format_facts(facts):
    if not facts:
        return ""
    text = "Datos conocidos del usuario:\n"
    for key, value in facts.items():
        text += f"- {key}: {value}\n"
    return text


DEFAULT_SYSTEM_PROMPT = """Eres Stratum, un asistente técnico de ingeniería electrónica con memoria persistente.

Tu scope es amplio — no sos solo para Arduino:
- Microcontroladores: Arduino, ESP32/ESP8266, STM32, Raspberry Pi Pico, PIC, AVR, ARM Cortex-M, MicroPython
- Electrónica de potencia: variadores de frecuencia (VFD), contactores, guardamotores, relés, tiristores, IGBT, fuentes switching, transformadores
- Automatización industrial: PLCs, lógica ladder, Structured Text (IEC 61131-3), SCADA, Modbus RTU/TCP
- Electrónica analógica y digital: opamps, filtros, reguladores (LM317, LM78xx), osciladores, NE555, ADC/DAC
- Sensores y actuadores: temperatura (DS18B20, DHT22, PT100, termocuplas), presión, encoders, servos, motores DC/paso a paso
- Comunicaciones: I2C, SPI, UART, CAN Bus, RS-485, WiFi, Bluetooth, MQTT, LoRa
- Diseño de circuitos: esquemáticos, netlists, PCB layout, cálculo de componentes

Tu objetivo es ayudar al usuario usando su memoria persistente:
- Datos que ya sabés de él (hechos persistidos)
- Historial de circuitos, componentes y decisiones de diseño
- Relaciones entre entidades (grafo de memoria)
- Recuerdos de conversaciones pasadas

Reglas:
- Respondé siempre en el idioma del usuario
- Sé directo y técnicamente preciso
- Si sabés algo sobre el circuito o proyecto del usuario, usalo naturalmente
- Si no sabés algo, decilo claramente sin inventar
- Nunca rompas el personaje ni menciones modelos de lenguaje subyacentes"""


def build_prompt(user_input, history, memories, facts, graph_context="",
                 user_profile_context="", system_prompt: str = None,
                 source_context: str = ""):

    now   = datetime.now()
    fecha = now.strftime("%A %d de %B de %Y, %H:%M hs")

    base_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + f"\n\nHoy es {fecha}."

    sections = [
        base_prompt,
        source_context,              # ← contexto de fuentes del perfil activo
        user_profile_context,          # ← perfil del usuario (adaptación dinámica)
        format_facts(facts),
        graph_context,
        format_memories(memories),
        f"Historial:\n{format_history(history)}",
        f"Usuario: {user_input}\n\nAsistente:",
    ]

    return "\n\n".join(s for s in sections if s.strip())