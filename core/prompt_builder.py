# core/prompt_builder.py

from datetime import datetime


def _format_history(history: list[dict]) -> str:
    return "".join(
        f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content']}\n"
        for m in history
    )


def _format_memories(memories: list) -> str:
    if not memories:
        return ""
    return "Memorias relevantes:\n" + "".join(f"- {m}\n" for m in memories)


def _format_facts(facts: dict) -> str:
    if not facts:
        return ""
    return "Datos conocidos del usuario:\n" + "".join(
        f"- {k}: {v}\n" for k, v in facts.items()
    )


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

    fecha = datetime.now().strftime("%A %d de %B de %Y, %H:%M hs")
    base_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT) + f"\n\nHoy es {fecha}."

    sections = [
        base_prompt,
        source_context,
        user_profile_context,
        _format_facts(facts),
        graph_context,
        _format_memories(memories),
        f"Historial:\n{_format_history(history)}",
        f"Usuario: {user_input}\n\nAsistente:",
    ]

    return "\n\n".join(s for s in sections if s.strip())
