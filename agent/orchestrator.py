# agent/orchestrator.py

import json
from core.logger import logger
from llm.async_client import call_llm_text

from agent.agents.research_agent import ResearchAgent
from agent.agents.code_agent import CodeAgent
from agent.agents.memory_agent import MemoryAgent


ROUTING_PROMPT = """Analizá la siguiente consulta del usuario y decidí qué agentes invocar.

Agentes disponibles:
- research: buscar información web, noticias, datos actuales, clima, precios, deportes
- code: ejecutar código Python, cálculos matemáticos, leer/escribir archivos
- memory: consultar memoria del usuario, historial, hechos conocidos sobre el usuario
- hardware: programar Arduino/ESP32/ESP8266/PIC/STM32, consultar dispositivos, historial de firmware, guardar decisiones de diseño, circuitos de potencia, PLCs, automatización
- direct: responder directamente sin sub-agentes (saludos, opiniones, conversación general)

Devolvé ÚNICAMENTE un JSON con:
{{
  "agents": ["lista", "de", "agentes"],
  "reason": "por qué elegiste estos agentes"
}}

Reglas estrictas:
- Si pregunta por eventos actuales, noticias, precios, resultados deportivos → research
- Si pregunta por cálculos, código Python, archivos → code
- Si pregunta por datos del usuario, historial de conversación → memory
- Si menciona Arduino, ESP32, microcontrolador, LED, sensor, pin, firmware, circuito eléctrico, PLC, ladder, automatización, variador, transformador, potencia, relay, contactor, decisión de diseño → hardware
- Si es saludo, opinión o pregunta general de conocimiento → direct

Consulta: "{query}"

JSON:"""


KEYWORD_ROUTES = {
    "hardware": [
        "arduino", "esp32", "esp8266", "pico", "led", "sensor",
        "pin", "flashear", "programar hardware", "micropython", "serial",
        "parpadee", "enciende el led", "apaga el led", "humedad",
        "servo", "motor", "buzzer", "pantalla", "lcd", "i2c",
        "pwm", "analogico", "digital", "interrupt", "timer",
        "wifi esp", "bluetooth", "mqtt", "firmware", "microcontrolador",
        "guardá el circuito", "guarda el circuito", "guardá este circuito",
        "asociá el circuito", "registrá el circuito",
        "guardá la decisión", "guarda la decisión", "guardá el razonamiento",
        "guarda el razonamiento", "guardá por qué", "guarda por qué",
        "registrá la decisión", "anotá que", "anota que",
        "conecté", "conecte el arduino", "conecte el esp",
        "dispositivos registrados", "qué dispositivos", "que dispositivos",
        "historial de hardware", "último firmware", "ultimo firmware",
        "qué programé", "que programe", "qué tiene cargado",
        "que tiene cargado", "cuántas veces flasheé", "cuantas veces",
        "qué cargué", "que cargue",
        # Electrónica general
        "circuito", "esquemático", "esquema eléctrico", "netlist",
        "resistencia", "capacitor", "inductor", "transistor", "mosfet",
        "regulador", "fuente de alimentación", "transformador", "relay",
        "contactor", "variador", "inversor", "plc", "ladder", "automatización",
        "lm317", "ne555", "555", "opamp", "amplificador operacional",
        "corriente", "voltaje", "tensión", "potencia eléctrica",
        "kicad", "ltspice", "eagle", "esquemático",
        "decisión de diseño", "elegí el", "usé el",
    ],
    "research": [
        "busca", "buscar", "precio", "noticias", "hoy", "actual", "clima",
        "quién ganó", "qué pasó", "cuándo fue", "champions", "campeon",
        "resultado", "partido", "cotización", "dólar", "euro", "bitcoin",
        "presidente", "elecciones", "pronóstico",
    ],
    "code": [
        "calculá", "calcula", "cuánto es", "cuanto es", "ejecuta", "código python",
        "script", "ordená", "convertí", "porcentaje",
        "promedio", "suma", "multiplica", "%", "√", "raíz",
    ],
    "memory": [
        "recuerdas", "recuerdo", "me llamo", "mi nombre", "dijiste",
        "antes dijiste", "qué sé", "qué sabes de mí", "historial",
        "cómo me llamo", "cuántos años tengo", "dónde vivo",
    ],
}


class Orchestrator:

    def __init__(self, client_fn):
        self.client_fn      = client_fn
        self.research_agent = ResearchAgent(client_fn)
        self.code_agent     = CodeAgent(client_fn)
        self.memory_agent   = MemoryAgent(client_fn)

    def _keyword_route(self, query: str) -> list[str] | None:
        """Heurística estática — sin overhead LLM. Siempre se intenta primero."""
        q = query.lower()
        for agent, keywords in KEYWORD_ROUTES.items():
            if any(kw in q for kw in keywords):
                return [agent]
        return None

    async def route(self, query: str) -> list[str]:
        """
        Determina qué agentes invocar.
        1. Intenta keywords estáticos (zero-LLM, sin latencia)
        2. Si no matchea, consulta al LLM async
        3. Fallback a 'direct' si falla todo
        """
        # Paso 1: keywords estáticos (prioridad, sin LLM)
        kw = self._keyword_route(query)
        if kw:
            logger.info(f"[Orchestrator] Keyword route → {kw}")
            return kw

        # Paso 2: LLM async para casos ambiguos
        try:
            from core.config import LLM_MODEL_FAST
            content = await call_llm_text(
                messages=[{
                    "role":    "user",
                    "content": ROUTING_PROMPT.format(query=query),
                }],
                model=LLM_MODEL_FAST,
                temperature=0,
                timeout=30,
                agent_id="orchestrator",
                agent_name="Orchestrator",
            )

            if not content:
                return ["direct"]

            content = content.replace("```json", "").replace("```", "").strip()
            data    = json.loads(content)
            agents  = data.get("agents", ["direct"])

            logger.info(f"[Orchestrator] LLM route → {agents} | {data.get('reason', '')}")
            return agents

        except Exception as e:
            logger.error(f"[Orchestrator] Error en routing LLM: {e}")
            return ["direct"]

    async def run(self, query: str, context: str = "") -> dict:
        """
        Ejecuta los agentes necesarios de forma async.
        Los agentes síncronos legacy (research, code, memory) se envuelven
        en asyncio.to_thread() para no bloquear el event loop.
        """
        import asyncio

        agents_to_run = await self.route(query)
        results       = {}
        context_parts = []

        if "memory" in agents_to_run:
            result = await asyncio.to_thread(self.memory_agent.run, query, context)
            results["memory"] = result
            if result and "No se encontró" not in result:
                context_parts.append(f"[Memoria]\n{result}")

        if "research" in agents_to_run:
            result = await asyncio.to_thread(self.research_agent.run, query, context)
            results["research"] = result
            if result:
                context_parts.append(f"[Investigación web]\n{result}")

        if "code" in agents_to_run:
            result = await asyncio.to_thread(self.code_agent.run, query, context)
            results["code"] = result
            if result:
                context_parts.append(f"[Código/Archivos]\n{result}")

        if "hardware" in agents_to_run:
            from agent.agents.hardware_agent import get_hardware_agent
            hw_agent = get_hardware_agent()
            result = await asyncio.to_thread(hw_agent.run, query, context)
            results["hardware"] = result
            if result:
                context_parts.append(f"[Hardware]\n{result}")

        return {
            "agents_used":      agents_to_run,
            "results":          results,
            "combined_context": "\n\n---\n\n".join(context_parts),
        }