# agent/orchestrator.py

import json
import asyncio
from core.logger import logger
from core.config import LLM_MODEL_FAST
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
- circuit_design: DISEÑAR un circuito nuevo desde cero (generar netlist, esquemático, PCB, BOM) cuando el usuario pide que SE CREE/DISEÑE/GENERE un circuito completo
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
- Si pide DISEÑAR/CREAR/GENERAR/ARMAR un circuito, esquemático o PCB nuevo → circuit_design
- Si menciona Arduino, ESP32, microcontrolador, LED, sensor, pin, firmware, circuito eléctrico, PLC, ladder, automatización, variador, transformador, potencia, relay, contactor, decisión de diseño → hardware
- Si es saludo, opinión o pregunta general de conocimiento → direct

Consulta: "{query}"

JSON:"""


# Keywords que indican EXPLÍCITAMENTE un cálculo eléctrico.
# Solo si uno de estos aparece se intenta ElectricalCalcAgent.
# Evita que consultas de firmware/circuitos sean mal clasificadas.
ELECTRICAL_CALC_KEYWORDS = [
    "calculá la resistencia", "calcular resistencia", "resistencia para led",
    "resistencia limitadora", "cuánta resistencia", "cuanta resistencia",
    "calculá el capacitor", "calcular capacitor", "qué capacitor", "que capacitor",
    "calculá el inductor", "calcular inductor",
    "divisor de tensión", "divisor resistivo", "divisor de tension",
    "filtro paso bajo", "filtro paso alto", "filtro rc", "filtro lc",
    "filtro pasa bajo", "filtro pasa alto",
    "constante de tiempo rc", "tiempo de carga",
    "autonomía de batería", "autonomia de bateria", "cuánto dura la batería",
    "fusible para", "qué fusible", "que fusible",
    "disipador térmico", "heatsink", "heat sink",
    "convertidor buck", "convertidor boost", "buck converter", "boost converter",
    "relación de transformación", "transformador",
    "ganancia del amplificador", "amplificador inversor", "amplificador no inversor",
    "frecuencia vfd", "frecuencia para rpm", "torque del motor",
    "ley de ohm", "caída de tensión", "caida de tension",
    "potencia disipada", "eficiencia energética", "eficiencia energetica",
    "dimensioná", "dimensionar",
]

CIRCUIT_DESIGN_KEYWORDS = [
    "diseñame un circuito", "diseña un circuito", "crea un circuito",
    "genera un circuito", "generame un circuito", "armame un circuito",
    "quiero un circuito", "haceme un circuito", "necesito un circuito",
    "diseñame el esquemático", "crea el esquemático", "genera el esquemático",
    "diseñame un esquema", "diseñame una pcb", "crea una pcb", "genera una pcb",
    "make a circuit", "design a circuit", "create a circuit", "generate a circuit",
    "design me a", "create schematic", "generate schematic",
    "diseñame el sistema de riego", "diseñame el sistema de domótica",
    "diseñame el control", "diseñame la fuente", "diseñame el driver",
    "arma el circuito", "crea el circuito completo",
    "parsea un circuito", "parsea el circuito", "parsea este circuito",
    "parse a circuit", "parse circuit",
    "generá el esquemático", "generá un circuito", "generá la netlist",
    "generar circuito", "generar esquemático", "generar netlist",
    # Follow-up requests for schematics/PCB
    "generame los esquemas", "generame el esquema", "genera los esquemas",
    "dame el esquematico", "dame el esquemático", "dame el pcb", "dame la pcb",
    "dame los esquemas", "dame el diseño", "dame los diseños",
    "el esquematico y pcb", "esquematico y pcb", "esquemático y pcb",
    "generate the schematic", "give me the schematic", "give me the pcb",
    "generame el pcb", "generame la pcb", "generame el diseño",
    # F1.1 — variantes naturales en español argentino
    "diseña el pcb y esquematico", "diseña el esquematico y pcb",
    "diseña el pcb y esquemático", "diseña el esquemático y pcb",
    "diseña el pcb", "diseña el esquematico", "diseña el esquemático",
    "diseñá el pcb", "diseñá el esquematico", "diseñá el esquemático",
    "diseñá el pcb y esquematico", "diseñá el esquematico y pcb",
    "haceme el pcb", "haceme el esquematico", "haceme el esquemático",
    "haceme el circuito", "haceme la pcb",
    "quiero el pcb", "quiero la pcb", "quiero el esquematico",
    "quiero el esquemático", "quiero ver el circuito", "quiero ver la pcb",
    "crear el esquematico", "crear el esquemático", "crear el pcb",
    "crear la pcb", "crear el circuito",
    "diseña el circuito completo", "diseñá el circuito completo",
    "generar el pcb", "generar la pcb",
    "generar el esquematico", "generar el esquemático",
    "hace el esquematico", "hace el pcb", "hace el circuito",
    "hacé el esquematico", "hacé el pcb", "hacé el circuito",
    "muestrame el esquematico", "muestrame el pcb",
    "mostrame el esquematico", "mostrame el pcb", "mostrame el circuito",
    "armar el pcb", "armar el esquematico", "armar el circuito",
    "armame el pcb", "armame el esquematico",
]

KEYWORD_ROUTES = {
    "circuit_design": CIRCUIT_DESIGN_KEYWORDS,
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
        # Cálculos de ingeniería eléctrica (ElectricalCalcAgent)
        "calculá la resistencia", "calcular resistencia",
        "calculá el capacitor", "calcular capacitor",
        "calculá el inductor", "calcular inductor",
        "dimensioná", "dimensionar", "dimensionamiento",
        "resistencia para led", "resistencia limitadora",
        "divisor de tensión", "divisor resistivo",
        "filtro paso bajo", "filtro paso alto", "filtro lc",
        "buck", "boost", "flyback", "convertidor dc",
        "fuente conmutada", "switching",
        "constante de tiempo rc", "tiempo de carga",
        "autonomía de batería", "batería dura",
        "fusible para", "qué fusible",
        "disipador", "heatsink", "heat sink",
        "eficiencia energética", "pérdidas",
        "ganancia del amplificador", "ganancia opamp",
        "frecuencia del vfd", "frecuencia para rpm",
        "torque del motor", "potencia del motor",
        "ley de ohm", "caída de tensión",
        "relación de transformación",
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

    # Regex laxo para circuit_design — fix v4.14.1 bug #2:
    # "Diseñá un circuito controlador para 7 electroválvulas..." no matcheaba
    # ningún literal exacto y caía a 'hardware' (que tiene "circuito" en su lista)
    # → terminaba en LLM general que solo explicaba sin generar el circuito.
    _CIRCUIT_REGEX = None  # se compila lazy en _keyword_route

    def _keyword_route(self, query: str) -> list[str] | None:
        """Heurística estática — sin overhead LLM. Siempre se intenta primero.
        Prioridades:
          1) Literal en CIRCUIT_DESIGN_KEYWORDS → circuit_design
          2) Regex laxo verbo-de-creación + sustantivo-de-circuito → circuit_design
          3) Cualquier otro KEYWORD_ROUTES en orden (hardware, research, …)
        """
        q = query.lower()

        # 1) Literal de circuit_design tiene prioridad absoluta
        if any(kw in q for kw in KEYWORD_ROUTES["circuit_design"]):
            return ["circuit_design"]

        # 2) Regex laxo de circuit_design ANTES que hardware/research
        if self._CIRCUIT_REGEX is None:
            import re as _re
            type(self)._CIRCUIT_REGEX = _re.compile(
                r"\b(diseñ[aá]|crea|cre[aá]me|gener[aá]|gener[aá]me|"
                r"arm[aá]|arm[aá]me|hac[eé]|hac[eé]me|necesito|quiero|"
                r"construy[eé]|construime|"
                r"design|create|generate|build|make)\b"
                r"[\w\s,.;:¿?¡!()-]{0,80}?"
                r"\b(circuito|esquem[aá]tico|pcb|netlist|schematic|board|"
                r"controlador|driver|fuente|amplificador|regulador|"
                r"sistema\s+de)\b"
            )
        if self._CIRCUIT_REGEX.search(q):
            return ["circuit_design"]

        # 3) Resto de routes en orden
        for agent, keywords in KEYWORD_ROUTES.items():
            if agent == "circuit_design":
                continue  # ya evaluado arriba
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

    async def run(self, query: str, context: str = "", history: list = None,
                  on_phase=None) -> dict:
        """
        Ejecuta los agentes necesarios de forma async.
        Los agentes síncronos legacy (research, code, memory) se envuelven
        en asyncio.to_thread() para no bloquear el event loop.

        on_phase: callback opcional async(phase_name) para emitir progreso.
        """
        async def _phase(name: str):
            if on_phase:
                try:
                    await on_phase(name)
                except Exception:
                    pass

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

        if "circuit_design" in agents_to_run:
            try:
                await _phase("generating_circuit")
                from agent.agents.circuit_agent import CircuitAgent
                ca = CircuitAgent()

                # Detect MCU from query first, then fallback to history
                mcu = "Arduino Uno"
                q_l = query.lower()
                if "esp32" in q_l:     mcu = "ESP32"
                elif "esp8266" in q_l: mcu = "ESP8266"
                elif "nano" in q_l:    mcu = "Arduino Nano"
                elif "mega" in q_l:    mcu = "Arduino Mega"
                elif "pico" in q_l:    mcu = "Raspberry Pi Pico"
                elif "stm32" in q_l:   mcu = "STM32"

                # Detect if this is a short follow-up that lacks actual circuit context
                _circuit_content_words = [
                    "circuito", "regulador", "sistema", "bomba", "motor", "fuente",
                    "sensor", "voltaje", "corriente", "convertidor", "transformador",
                    "circuit", "regulator", "power", "control", "driver", "pump",
                    "220v", "48v", "12v", "5v", "relay", "arduino", "esp32",
                    "pic", "stm32", "automatizar", "automatización", "control",
                    "hidráulica", "hidraulica", "neumático", "plc", "variador",
                ]
                is_followup = (
                    len(query.strip()) < 120
                    and not any(kw in q_l for kw in _circuit_content_words)
                )

                description = query
                if is_followup and history:
                    # Enrich description with conversation history (last user messages)
                    user_msgs = [
                        m["content"] for m in history
                        if m.get("role") == "user" and m.get("content", "").strip()
                    ]
                    # Exclude the current message (already is query)
                    prev_msgs = [m for m in user_msgs if m.strip() != query.strip()]
                    if prev_msgs:
                        prev_text = "\n".join(f"- {m}" for m in prev_msgs[-5:])
                        description = (
                            f"Historial de conversación previa (mensajes del usuario):\n"
                            f"{prev_text}\n\n"
                            f"Petición actual del usuario: {query}\n\n"
                            f"Genera el circuito completo y detallado basándote en la "
                            f"descripción del historial. La petición actual es un seguimiento "
                            f"de la conversación anterior."
                        )
                        logger.info(
                            f"[Orchestrator] CircuitAgent — follow-up enriquecido con "
                            f"{len(prev_msgs)} mensajes previos"
                        )

                # If MCU not found in query, also scan history
                if mcu == "Arduino Uno" and history:
                    hist_text = " ".join(
                        m.get("content", "") for m in history if m.get("role") == "user"
                    ).lower()
                    if "esp32" in hist_text:     mcu = "ESP32"
                    elif "esp8266" in hist_text: mcu = "ESP8266"
                    elif "nano" in hist_text:    mcu = "Arduino Nano"
                    elif "mega" in hist_text:    mcu = "Arduino Mega"
                    elif "pico" in hist_text:    mcu = "Raspberry Pi Pico"
                    elif "stm32" in hist_text:   mcu = "STM32"

                circuit = await asyncio.to_thread(ca.parse_circuit, description, mcu)
                if circuit:
                    await _phase("validating")
                    results["circuit_design"] = circuit
                    # Build rich context for LLM explanation
                    comp_list = ", ".join(
                        f"{c['id']} {c['name']}" for c in circuit.get("components", [])[:8]
                    )
                    net_list = ", ".join(n["name"] for n in circuit.get("nets", [])[:6])
                    drc = circuit.get("drc", {})
                    drc_status = "✅ DRC OK" if drc.get("passed", True) else f"⚠ DRC: {len(drc.get('errors',[]))} errores"
                    context_parts.append(
                        f"[Circuito Generado — ID {circuit['design_id']}]\n"
                        f"Nombre: {circuit['name']}\n"
                        f"Descripción: {circuit['description']}\n"
                        f"MCU: {circuit.get('selected_mcu','')}\n"
                        f"Componentes ({len(circuit['components'])}): {comp_list}\n"
                        f"Nets ({len(circuit['nets'])}): {net_list}\n"
                        f"Alimentación: {circuit.get('power','')}\n"
                        f"DRC: {drc_status}\n"
                        f"Dominio detectado: {circuit.get('detected_domain','')}\n"
                        f"Advertencias: {len(circuit.get('warnings',[]))} — {'; '.join(circuit.get('warnings',[])[:2])}"
                    )
                    logger.info(f"[Orchestrator] CircuitAgent → ID {circuit['design_id']}")
                    await _phase("rendering")
                else:
                    context_parts.append("[Circuito] No se pudo generar el circuito — verificá la descripción")
            except Exception as e:
                logger.error(f"[Orchestrator] CircuitAgent falló: {e}")
                context_parts.append(f"[Circuito] Error generando circuito: {e}")

        if "hardware" in agents_to_run:
            q_lower = query.lower()
            # Solo intentar ElectricalCalcAgent si la consulta contiene keywords
            # de cálculo explícito — evita que firmware/circuitos sean mal ruteados.
            is_calc_query = any(kw in q_lower for kw in ELECTRICAL_CALC_KEYWORDS)
            ec_handled = False

            if is_calc_query:
                try:
                    from agent.agents.electrical_calc_agent import get_electrical_calc_agent
                    from database.component_stock import get_stock_db
                    ec_agent  = get_electrical_calc_agent()
                    ec_result = await ec_agent.run(query, stock_db=get_stock_db())
                    if ec_result:
                        results["hardware"] = ec_result
                        context_parts.append(f"[Cálculo Eléctrico]\n{ec_result}")
                        logger.info("[Orchestrator] ElectricalCalcAgent manejó la consulta")
                        ec_handled = True
                except Exception as e:
                    logger.warning(f"[Orchestrator] ElectricalCalcAgent falló: {e}")

            if not ec_handled:
                # HardwareAgent para firmware, circuitos, dispositivos, etc.
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