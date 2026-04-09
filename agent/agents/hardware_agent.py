# agent/agents/hardware_agent.py

import json as _json
import requests
import os
from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger
from tools.hardware_detector import detect_devices
from tools.firmware_generator import generate_firmware
from tools.firmware_flasher import flash_firmware, compile_firmware, install_platform, install_missing_libraries
from tools.serial_monitor import read_serial
from tools.signal_reader import signal_reader, SIGNAL_FIRMWARE
from database.hardware_memory import hardware_memory
from memory.vector_memory import store_memory, search_memory
from memory.graph_memory import graph_memory
from datetime import datetime, timezone


INTENT_PROMPT = """Clasificá esta consulta de hardware en UNA sola palabra:

- save_circuit: guardar, asociar o registrar un circuito/foto para un dispositivo
- query:        consultar información sobre dispositivos registrados, firmware actual, historial de flashes, qué tiene programado, qué componentes tiene
- program:      programar, flashear, cargar código, hacer parpadear, encender, controlar, subir firmware
- signal:       leer señal analógica, voltaje, osciloscopio, monitorear pin
- debug:        corregir error, algo no funciona, falla, arreglar, diagnosticar, el código da error

Consulta: "{task}"

Respondé SOLO con una de estas 5 palabras: save_circuit, query, program, signal, debug"""


# ── KEYWORDS exhaustivas por categoría ───────────────────────────────────────

SAVE_DECISION_KEYWORDS = [
    "guardá la decisión", "guarda la decisión",
    "guardá el razonamiento", "guarda el razonamiento",
    "guardá por qué", "guarda por qué",
    "registrá la decisión", "registra la decisión",
    "guardá la razón", "guarda la razón",
    "anotá que", "anota que",
]

SAVE_CIRCUIT_KEYWORDS = [
    "guardá el circuito", "guarda el circuito",
    "guardá este circuito", "guarda este circuito",
    "asociá el circuito", "asocia el circuito",
    "guardá la foto", "guarda la foto",
    "registrá el circuito", "registra el circuito",
    "guardá el esquema", "guarda el esquema",
]

QUERY_KEYWORDS = [
    # Consultas directas de memoria
    "qué tiene", "que tiene", "qué tenía", "que tenia",
    "qué tengo", "que tengo", "qué había", "que habia",
    "qué programé", "que programe", "qué cargué", "que cargue",
    "qué subí", "que subi", "qué flasheé", "que flashee",
    "tenía programado", "tenia programado", "había cargado",
    # Historial
    "historial", "versiones", "versión anterior", "último firmware",
    "ultimo firmware", "última versión", "ultima version",
    "cuántas veces", "cuantas veces", "cuántos flashes", "cuantos flashes",
    "registro de", "log de", "actividad de",
    # Dispositivos
    "dispositivos", "registrados", "conocidos", "conectados",
    "qué dispositivos", "que dispositivos", "cuáles dispositivos",
    "mis dispositivos", "mis arduinos", "mis esp",
    # Info general
    "firmware actual", "código actual", "qué tiene cargado",
    "que tiene cargado", "qué sabe", "que sabe",
    "información sobre", "info sobre", "detalles de",
    "estado del", "estado de",
    # Biblioteca
    "proyectos guardados", "biblioteca", "proyectos disponibles",
    "qué proyectos", "que proyectos",
    # Circuito
    "circuito", "componentes", "conexiones del",
    "qué componentes", "que componentes",
    "esquema", "diagrama",
]

SIGNAL_KEYWORDS = [
    "señal", "senal", "señales", "senales",
    "analógica", "analogica", "analógico", "analogico",
    "voltaje", "voltage", "volt", "volts",
    "osciloscopio", "osciloscopo", "oscilloscope",
    "leer pin", "leer a0", "leer a1", "leer a2",
    "monitorear señal", "monitorear senal",
    "capturar señal", "medir voltaje", "medir corriente",
    "sensor analógico", "sensor analogico",
    "adc", "pwm output", "frecuencia",
]

DEBUG_KEYWORDS = [
    # Errores genéricos
    "error", "errores", "falla", "fallas", "fallo",
    "no funciona", "no anda", "no compila",
    "no flashea", "no sube", "upload failed",
    "no responde", "se colgó", "se congela", "se reinicia",
    # Acciones de debug
    "arreglá", "arregla", "arreglame", "corregí", "corrige",
    "corregime", "arreglar", "corregir", "reparar",
    "debug", "debuggear", "depurar", "diagnosticar",
    "revisar", "verificar el código",
    # Síntomas hardware
    "no enciende", "no prende", "no parpadea", "no se mueve",
    "no lee", "no detecta", "no envía", "no envia",
    "no conecta", "no responde al serial",
    "led apagado", "pin no funciona",
    # Síntomas código
    "el código falla", "codigo falla", "código da error",
    "syntax error", "compilation error", "linker error",
    "undefined reference", "not declared",
    "loop infinito", "crash", "exception",
]

PROGRAM_KEYWORDS = [
    # Acciones de programación
    "programá", "programa", "programar", "flashear", "flasheá",
    "cargá", "carga", "cargar", "subí", "subi", "subir",
    "instalá", "instala", "instalar",
    # Control de hardware
    "hacer parpadear", "que parpadee", "que encienda", "que apague",
    "que lea", "que mida", "que envíe", "que muestre",
    "controlar", "manejar", "activar", "desactivar",
    "encender", "apagar", "toggle",
    # Proyectos
    "blink", "servo", "motor", "pantalla", "display",
    "sensor de temperatura", "sensor de humedad",
    "comunicación serial", "wifi", "bluetooth", "mqtt",
    "leer sensor", "escribir pin",
]


class HardwareAgent:

    name        = "HardwareAgent"
    description = "Programá hardware conectado: Arduino, ESP32, ESP8266 y más"

    def run(self, task: str, context: str = "") -> str:
        intent = self._classify_intent(task)
        logger.info(f"[HardwareAgent] Intent: {intent} | Tarea: {task[:60]}")

        if intent == "save_decision": return self._save_decision(task)
        if intent == "save_circuit": return self._save_circuit(task)
        if intent == "query":        return self._query_memory(task)
        if intent == "signal":       return self._start_signal_mode(task)
        if intent == "debug":        return self._debug_mode(task)
        return self._program_device(task, context)

    # ======================
    # CLASIFICACIÓN
    # ======================

    def _classify_intent(self, task: str) -> str:
        """Usa el LLM para clasificar la intención. Fallback a keywords si falla."""
        try:
            response = requests.post(
                LLM_API,
                headers=get_llm_headers("hardware-agent", "HardwareAgent"),
                json={
                    "model":       LLM_MODEL,
                    "messages":    [{"role": "user", "content": INTENT_PROMPT.format(task=task)}],
                    "temperature": 0,
                },
                timeout=15
            )
            response.raise_for_status()
            intent = response.json()["choices"][0]["message"]["content"].strip().lower()
            for valid in ("query", "program", "signal", "debug"):
                if valid in intent:
                    return valid
        except Exception as e:
            logger.error(f"[HardwareAgent] Error clasificando intent: {e}")

        return self._classify_by_keywords(task)

    def _classify_by_keywords(self, task: str) -> str:
        """Fallback exhaustivo por keywords cuando el LLM no responde."""
        t = task.lower()

        if any(kw in t for kw in SAVE_DECISION_KEYWORDS):
            return "save_decision"

        if any(kw in t for kw in SAVE_CIRCUIT_KEYWORDS):
            return "save_circuit"

        # Debug tiene prioridad sobre program (errores antes que programar)
        if any(kw in t for kw in DEBUG_KEYWORDS):
            return "debug"

        if any(kw in t for kw in QUERY_KEYWORDS):
            return "query"

        if any(kw in t for kw in SIGNAL_KEYWORDS):
            return "signal"

        if any(kw in t for kw in PROGRAM_KEYWORDS):
            return "program"

        # Default: si mencionan hardware sin contexto claro, asumir programar
        return "program"

    # ======================
    # GUARDAR DECISIÓN
    # ======================

    def _save_decision(self, task: str) -> str:
        """Guarda el razonamiento detrás de una decisión de diseño."""
        import re
        from database.design_decisions import get_decisions_db

        # Extraer proyecto (opcional) y decisión del texto
        # Ej: "guardá la decisión: elegí el LM317 porque necesitaba regulación lineal"
        # Ej: "guardá que en el proyecto fuente_dc usé LM317 porque tiene bajo ruido"
        t = task

        # Detectar proyecto
        project = "general"
        m_proj = re.search(r'(?:en el proyecto|proyecto)\s+(["\w\s]+?)(?:\s+usé|\s+elegí|\s*:)', t, re.IGNORECASE)
        if m_proj:
            project = m_proj.group(1).strip().strip('"')

        # Detectar componente
        component = None
        m_comp = re.search(r'(?:elegí|usé|use|elegi)\s+(?:el\s+|la\s+|un\s+|una\s+)?(\w+)', t, re.IGNORECASE)
        if m_comp:
            component = m_comp.group(1)

        # Extraer la decisión/razonamiento después de ":" o "porque" o directamente
        decision = ""
        reasoning = ""
        if ":" in t:
            parts = t.split(":", 1)
            reasoning = parts[1].strip()
            decision  = reasoning[:80]
        elif "porque" in t.lower():
            idx = t.lower().index("porque")
            reasoning = t[idx:].strip()
            decision  = t[:idx].strip()
            # Limpiar keywords de guardado del inicio
            for kw in SAVE_DECISION_KEYWORDS:
                decision = decision.replace(kw, "").strip()
        else:
            reasoning = t
            decision  = t[:80]

        if not reasoning.strip():
            return (
                "No entendí el razonamiento. Probá con:\n"
                "*\"guardá la decisión: elegí el LM317 porque necesitaba regulación lineal con bajo ruido\"*"
            )

        try:
            decision_id = get_decisions_db().save(
                project=project,
                decision=decision,
                reasoning=reasoning,
                component=component,
            )
            # También guardar en memoria vectorial para búsqueda semántica
            store_memory(f"Decisión de diseño [{project}]: {reasoning}", metadata={"type": "decision", "project": project})

            return (
                f"✓ Decisión guardada (ID {decision_id})\n\n"
                f"**Proyecto:** {project}\n"
                f"**Componente:** {component or 'no especificado'}\n"
                f"**Razonamiento:** {reasoning[:200]}"
            )
        except Exception as e:
            logger.error(f"[HardwareAgent] Error guardando decisión: {e}")
            return f"No pude guardar la decisión: {e}"

    # ======================
    # GUARDAR CIRCUITO
    # ======================

    def _save_circuit(self, task: str) -> str:
        """Asocia el último circuito analizado por VisionAgent a un dispositivo."""
        from agent.agents.vision_agent import vision_agent

        circuit = getattr(vision_agent, "_last_circuit", {})
        if not circuit:
            # Intentar recuperar desde DB (sobrevive reloads del servidor)
            try:
                from database.sql_memory import _default as _sql
                import json as _j
                raw = _sql.get_all_facts().get("__last_vision_circuit", "")
                if raw:
                    circuit = _j.loads(raw)
                    vision_agent._last_circuit = circuit
            except Exception:
                pass
        if not circuit:
            return (
                "No tengo ningún circuito reciente para guardar. "
                "Primero sacale una foto al componente con el botón de cámara."
            )

        # Extraer el nombre del dispositivo del texto (ej: "guardá el circuito para Arduino")
        device_name = self._extract_device_name(task)
        if not device_name:
            return (
                "¿Para qué dispositivo querés guardar el circuito? "
                "Decime por ejemplo: *\"guardá el circuito para Arduino UNO\"*"
            )

        saved = hardware_memory.save_circuit_context(device_name, circuit)
        if not saved:
            return f"No pude guardar el circuito para {device_name}."

        components = circuit.get("components", [])
        comp_names = ", ".join(c.get("name", "?") for c in components[:5])
        logger.info(f"[HardwareAgent] Circuito guardado para {device_name} | {len(components)} componentes")

        return (
            f"✓ Circuito guardado para **{device_name}**\n\n"
            f"Componentes registrados ({len(components)}): {comp_names}\n"
            f"La próxima vez que programes {device_name} voy a usar esta información automáticamente."
        )

    def _extract_device_name(self, task: str) -> str:
        """Extrae el nombre del dispositivo de frases como 'guardá el circuito para Arduino'."""
        import re
        t = task.lower()
        # Buscar "para X" al final
        match = re.search(r'\bpara\s+(.+?)(?:\s*$)', t)
        if match:
            name = match.group(1).strip().rstrip(".,!?")
            return name.title() if name else ""
        # Buscar nombre de dispositivo conocido
        for keyword in ["arduino", "esp32", "esp8266", "pico", "nano", "mega", "uno"]:
            if keyword in t:
                return keyword.title()
        return ""

    # ======================
    # PASO 1 — PROGRAMAR
    # ======================

    def _program_device(self, task: str, context: str = "") -> str:
        logger.info(f"[HardwareAgent] Programando: {task[:80]}...")

        # ── Hardware Bridge (programación remota) ─────────────────────────────
        try:
            from api.routers.hardware_bridge import is_bridge_connected, call_bridge_sync
            if is_bridge_connected():
                logger.info("[HardwareAgent] Bridge conectado — ejecutando remotamente")
                return self._program_via_bridge(task, context, call_bridge_sync)
        except ImportError:
            pass  # No disponible en entornos sin el router cargado

        devices = detect_devices()
        if not devices:
            return (
                "No detecté ningún dispositivo conectado. "
                "Conectá tu Arduino/ESP32 por USB y volvé a intentarlo."
            )

        device = next((d for d in devices if d["platform"]), devices[0])
        if not device["platform"]:
            return (
                f"Detecté un dispositivo en {device['port']} pero no pude identificarlo. "
                f"Descripción: {device['description']}."
            )

        logger.info(f"[HardwareAgent] Dispositivo: {device['name']} en {device['port']}")
        hardware_memory.register_device(device)

        # Contexto del circuito (componentes, conexiones, pines)
        circuit_context = hardware_memory.format_circuit_for_prompt(device["name"])
        if circuit_context:
            logger.info("[HardwareAgent] Inyectando contexto de circuito en prompt")

        # Verificar si hay un circuito guardado para este dispositivo
        saved_circuit = hardware_memory.get_circuit_context(device["name"])
        if saved_circuit and not circuit_context:
            # Si hay circuito pero no contexto formateado, crearlo
            circuit_context = hardware_memory.format_circuit_for_prompt(device["name"])
            
        similar = hardware_memory.get_similar_firmware(task[:30])
        memory_context = ""
        if similar:
            memory_context = f"\nFirmware similar anterior ({similar[0]['device']}):\n{similar[0]['code'][:300]}"
            logger.info("[HardwareAgent] Encontré firmware similar en memoria")

        # Componentes en stock del ingeniero
        stock_context = ""
        try:
            from database.component_stock import get_stock_db
            in_stock = get_stock_db().get_all(in_stock_only=True)
            if in_stock:
                stock_lines = [
                    f"  - {c['name']} ({c['value'] or ''}) {('pkg:' + c['package']) if c['package'] else ''} × {c['quantity']}"
                    for c in in_stock[:20]
                ]
                stock_context = "\n\n--- COMPONENTES EN STOCK (priorizar estos) ---\n" + "\n".join(stock_lines)
                logger.info(f"[HardwareAgent] {len(in_stock)} componentes en stock inyectados al prompt")
        except Exception as e:
            logger.debug(f"[HardwareAgent] Stock no disponible: {e}")

        # Combinar todo el contexto disponible
        full_context = task
        if circuit_context:
            full_context += f"\n\n--- CIRCUITO DEL DISPOSITIVO ---\n{circuit_context}"
        if memory_context:
            full_context += memory_context
        if stock_context:
            full_context += stock_context

        # Si el usuario dice algo como "programá el Arduino con el circuito guardado"
        if "circuito" in task.lower() and saved_circuit:
            full_context += f"\n\nGENERAR FIRMWARE PARA ESTE CIRCUITO EXACTO:\n{self._format_circuit_for_firmware(saved_circuit)}"


        firmware = generate_firmware(
            description = full_context,
            platform    = device["platform"],
            device_name = device["name"],
        )

        if "error" in firmware:
            return f"Error generando el firmware: {firmware['error']}"

        compile_result = compile_firmware(firmware["dir"], device["fqbn"])
        if not compile_result["success"]:

            # ── PASO 1: Auto-instalar librerías faltantes ────────────────────
            lib_result = install_missing_libraries(compile_result["error"])
            if lib_result["any_installed"]:
                logger.info(
                    f"[HardwareAgent] Librerías instaladas: {lib_result['installed']}. "
                    "Reintentando compilación..."
                )
                compile_result = compile_firmware(firmware["dir"], device["fqbn"])

            # ── PASO 2: Si aún falla, pedir corrección al LLM ───────────────
            if not compile_result["success"]:
                corrected = self._fix_firmware(
                    firmware["code"], compile_result["error"], device["platform"], task
                )
                if corrected:
                    with open(firmware["path"], "w") as f:
                        f.write(corrected)
                    firmware["code"] = corrected
                    compile_result   = compile_firmware(firmware["dir"], device["fqbn"])

            # ── PASO 3: Rendirse e informar al usuario ───────────────────────
            if not compile_result["success"]:
                libs_msg = ""
                if lib_result["failed"]:
                    libs_msg = (
                        f"\nLibrerías no instaladas automáticamente: "
                        f"{', '.join(lib_result['failed'])}. "
                        f"Instalálas manualmente con: "
                        f"`arduino-cli lib install \"<nombre>\"`"
                    )
                hardware_memory.save_firmware(
                    device["name"], task, firmware["code"],
                    success=False, notes=compile_result["error"][:200]
                )
                return (
                    f"No pude compilar el firmware.\n"
                    f"Error: {compile_result['error'][:300]}\n"
                    f"{libs_msg}\n"
                    f"```cpp\n{firmware['code'][:400]}\n```"
                )

        flash_result = flash_firmware(firmware["dir"], device["fqbn"], device["port"])
        if not flash_result["success"]:
            hardware_memory.save_firmware(
                device["name"], task, firmware["code"],
                success=False, notes=flash_result["error"][:200]
            )
            return (
                f"Compiló pero no pude flashear.\n"
                f"Error: {flash_result['error'][:300]}"
            )

        serial_output = read_serial(device["port"], duration=4)

        hardware_memory.save_firmware(
            device_name = device["name"],
            task        = task,
            code        = firmware["code"],
            filename    = firmware["filename"],
            success     = True,
            serial_out  = serial_output,
        )
        self._store_in_vector_memory(task, device, firmware["code"])
        self._update_graph(task, device)

        decision_hint = (
            "\n\n💡 *¿Querés guardar el razonamiento de este diseño? "
            "Decime por ejemplo: \"guardá la decisión: elegí el LM317 porque...\"*"
        )

        return (
            f"✓ Firmware subido a {device['name']} en {device['port']}\n\n"
            f"```cpp\n{firmware['code'][:600]}\n```\n\n"
            f"Monitor serial:\n{serial_output}"
            f"{decision_hint}"
        )

    def _program_via_bridge(self, task: str, context: str, call_bridge_sync) -> str:
        """Delega la programación al Hardware Bridge Client en la PC del usuario."""
        logger.info("[HardwareAgent] Enviando job 'program' al bridge client")

        # Obtener contexto del circuito si lo hay (el bridge lo necesita para generate_firmware)
        circuit_context = {}
        try:
            from database.hardware_memory import hardware_memory as _hw
            # Buscar dispositivo por contexto o nombre en el task
            device_name = self._extract_device_name(task) or ""
            if device_name:
                saved = _hw.get_circuit_context(device_name)
                if saved:
                    circuit_context = saved
        except Exception:
            pass

        result = call_bridge_sync("program", {
            "task":            task,
            "device_name":     device_name if "device_name" in dir() else "",
            "circuit_context": circuit_context,
        }, timeout=180)

        if not result.get("success"):
            err = result.get("error", "Error desconocido")
            return f"Error en programación remota: {err}"

        code       = result.get("code", "")
        port       = result.get("port", "?")
        device_out = result.get("device_name", "dispositivo remoto")
        serial_out = result.get("serial_output", result.get("output", ""))

        return (
            f"✓ Firmware subido remotamente a {device_out} en {port}\n\n"
            f"```cpp\n{code[:600]}\n```\n\n"
            + (f"Monitor serial:\n{serial_out}" if serial_out else "")
        )

    # ======================
    # PASO 2 — MEMORIA
    # ======================

    def _query_memory(self, task: str) -> str:
        logger.info("[HardwareAgent] Consultando memoria de hardware")

        devices = hardware_memory.get_all_devices()
        stats   = hardware_memory.get_stats()

        if not devices:
            return "No tengo registro de ningún dispositivo programado todavía."

        vector_results = search_memory("hardware firmware arduino esp32", top_k=3)

        lines = [f"Dispositivos conocidos ({stats['devices']} total, {stats['total_flashes']} flashes):\n"]

        for d in devices:
            current = hardware_memory.get_current_firmware(d["name"])
            lines.append(f"**{d['name']}**")
            lines.append(f"  Puerto: {d['port'] or 'desconocido'}")
            lines.append(f"  Visto por última vez: {d['last_seen']}")
            if current:
                lines.append(f"  Último firmware: {current['task']}")
                lines.append(f"  Fecha: {current['timestamp']}")
                lines.append(f"  Código:\n  ```cpp\n  {current['code'][:200]}\n  ```")
            else:
                lines.append("  Sin firmware registrado")

            # Mostrar contexto del circuito si existe
            circuit = hardware_memory.get_circuit_context(d["name"])
            if circuit:
                lines.append(f"  🔌 Circuito: {circuit['project_name'] or 'sin nombre'}")
                if circuit['components']:
                    comps = ", ".join(c.get('name','?') for c in circuit['components'][:5])
                    lines.append(f"  Componentes: {comps}")
                if circuit['power']:
                    lines.append(f"  Alimentación: {circuit['power']}")
            lines.append("")

        if vector_results:
            hw_memories = [r for r in vector_results
                          if "hardware" in r.lower() or "arduino" in r.lower()]
            if hw_memories:
                lines.append("Memorias relacionadas:")
                for r in hw_memories:
                    lines.append(f"- {r[:100]}")

        return "\n".join(lines)

    # ======================
    # PASO 3 — SEÑAL
    # ======================

    def _start_signal_mode(self, task: str) -> str:
        devices = detect_devices()
        if not devices:
            return "No detecté dispositivos. Conectá el Arduino para leer señales."

        device  = next((d for d in devices if d["platform"]), devices[0])
        current = hardware_memory.get_current_firmware(device["name"])
        needs_firmware = not current or "telemetría" not in (current.get("task") or "").lower()

        if needs_firmware:
            return (
                f"Para leer señales necesito cargar el firmware de telemetría en {device['name']}.\n"
                f"Decime 'cargá el firmware de señal' y lo instalo automáticamente.\n\n"
                f"El firmware lee A0, A1, A2 y envía los valores cada 100ms via Serial."
            )

        signal_reader.start(device["port"])
        return (
            f"✓ Leyendo señales de {device['name']} en {device['port']}\n"
            f"Abrí el visualizador en http://localhost:8000/static/graph3d.html"
        )

    # ======================
    # PASO 4 — DEBUGGING
    # ======================

    def _debug_mode(self, task: str) -> str:
        logger.info(f"[HardwareAgent] Modo debug: {task[:60]}")

        devices = detect_devices()
        if not devices:
            return "No detecté dispositivos para debuggear."

        device  = next((d for d in devices if d["platform"]), devices[0])
        current = hardware_memory.get_current_firmware(device["name"])

        if not current:
            return f"No tengo registro del firmware actual de {device['name']}."

        serial_output = read_serial(device["port"], duration=5)

        # Contexto del circuito para diagnóstico más preciso
        circuit_context = hardware_memory.format_circuit_for_prompt(device["name"])
        circuit_section = f"\n\nCircuito:\n{circuit_context}" if circuit_context else ""

        try:
            response = requests.post(
                LLM_API,
                headers=get_llm_headers("hardware-agent", "HardwareAgent"),
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Eres un experto en debugging de microcontroladores. "
                                "Analizá el código y el output serial para identificar el problema. "
                                "Si hay info del circuito, usala para verificar pines y conexiones. "
                                "Devolvé un JSON: {\"diagnosis\": str, \"fixed_code\": str}"
                            )
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Dispositivo: {device['name']}\n"
                                f"Tarea original: {current['task']}\n"
                                f"Código actual:\n{current['code'][:600]}\n\n"
                                f"Output serial:\n{serial_output}\n\n"
                                f"Problema reportado: {task}"
                                f"{circuit_section}"
                            )
                        }
                    ],
                    "temperature": 0.2,
                },
                timeout=60
            )
            response.raise_for_status()
            content      = response.json()["choices"][0]["message"]["content"].strip()
            content      = content.replace("```json", "").replace("```", "").strip()
            debug_result = _json.loads(content)

            diagnosis  = debug_result.get("diagnosis", "No pude diagnosticar")
            fixed_code = debug_result.get("fixed_code", "")

            if not fixed_code:
                return f"Diagnóstico: {diagnosis}\n\nNo pude generar código corregido."

            firmware_path = f"./agent_files/firmware/firmware_{device['name'].lower().replace(' ','_')}"
            os.makedirs(firmware_path, exist_ok=True)
            filename = f"firmware_{device['name'].lower().replace(' ','_')}.ino"
            with open(os.path.join(firmware_path, filename), "w") as f:
                f.write(fixed_code)

            compile_result = compile_firmware(firmware_path, device["fqbn"])
            if not compile_result["success"]:
                return f"Diagnóstico: {diagnosis}\n\nEl código corregido no compila: {compile_result['error'][:200]}"

            flash_result = flash_firmware(firmware_path, device["fqbn"], device["port"])
            if not flash_result["success"]:
                return f"Diagnóstico: {diagnosis}\n\nNo pude flashear el código corregido."

            hardware_memory.save_firmware(
                device["name"],
                f"[DEBUG] {current['task']}",
                fixed_code, filename, True,
                notes=f"Corregido: {diagnosis[:100]}"
            )

            new_serial = read_serial(device["port"], duration=3)

            return (
                f"**Diagnóstico**: {diagnosis}\n\n"
                f"**Código corregido y flasheado** ✓\n\n"
                f"```cpp\n{fixed_code[:500]}\n```\n\n"
                f"Monitor serial:\n{new_serial}"
            )

        except Exception as e:
            logger.error(f"[HardwareAgent] Error en debug: {e}")
            return f"Error en debugging: {e}\nOutput serial: {serial_output}"

    # ======================
    # UTILIDADES
    # ======================

    def _fix_firmware(self, code: str, error: str, platform: str, task: str) -> str:
        try:
            response = requests.post(
                LLM_API,
                headers=get_llm_headers("hardware-agent", "HardwareAgent"),
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Corregí el código con errores de compilación. Devolvé SOLO el código, sin markdown."
                        },
                        {
                            "role": "user",
                            "content": f"Código:\n{code}\n\nError:\n{error}\n\nTarea: {task}"
                        }
                    ],
                    "temperature": 0.1,
                },
                timeout=60
            )
            response.raise_for_status()
            fixed = response.json()["choices"][0]["message"]["content"].strip()
            return "\n".join(
                l for l in fixed.split("\n")
                if not l.strip().startswith("```")
            ).strip()
        except Exception as e:
            logger.error(f"[HardwareAgent] Error corrigiendo: {e}")
            return ""

    def _store_in_vector_memory(self, task: str, device: dict, code: str):
        try:
            fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            store_memory(
                f"[Hardware - {fecha}] Programé {device['name']} en {device['port']}. Tarea: {task}.",
                metadata={"type": "hardware", "device": device["name"], "port": device["port"]}
            )
        except Exception as e:
            logger.error(f"[HardwareAgent] Error en vector memory: {e}")

    def _update_graph(self, task: str, device: dict):
        try:
            graph_memory.add_relation(
                "usuario", "programó", device["name"].lower(), source="hardware"
            )
            graph_memory.add_relation(
                device["name"].lower(), "conectado_en", device["port"].lower(), source="hardware"
            )
        except Exception as e:
            logger.error(f"[HardwareAgent] Error en grafo: {e}")

    def _format_circuit_for_firmware(self, circuit: dict) -> str:
        """Formatea un circuito para generar firmware específico."""
        if not circuit:
            return ""
            
        lines = [f"PROYECTO: {circuit.get('project_name', 'Sin nombre')}"]
        
        if circuit.get('description'):
            lines.append(f"DESCRIPCIÓN: {circuit['description']}")
            
        if circuit.get('components'):
            lines.append("COMPONENTES:")
            for comp in circuit['components']:
                line = f"  - {comp.get('name', '?')} ({comp.get('type', '?')})"
                if comp.get('pin'):
                    line += f" en pin {comp['pin']}"
                if comp.get('value'):
                    line += f" valor {comp['value']}{comp.get('unit', '')}"
                lines.append(line)
                
        if circuit.get('connections'):
            lines.append("CONEXIONES:")
            for conn in circuit['connections']:
                lines.append(f"  - {conn.get('from', '?')} → {conn.get('to', '?')}")
                
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────
# Una sola instancia compartida para todo el proceso.
# El Orchestrator importa esta instancia en lugar de crear HardwareAgent() por request.
_hardware_agent_instance: HardwareAgent | None = None

def get_hardware_agent() -> HardwareAgent:
    """Retorna la instancia singleton del HardwareAgent."""
    global _hardware_agent_instance
    if _hardware_agent_instance is None:
        _hardware_agent_instance = HardwareAgent()
    return _hardware_agent_instance

