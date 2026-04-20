# agent/agents/hardware_design.py — mixin de diseño, debug y formateo para HardwareAgent

import json as _json
import os
import requests

from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger
from tools.hardware_detector import detect_devices
from tools.firmware_flasher import compile_firmware, flash_firmware
from tools.serial_monitor import read_serial
from database.hardware_memory import hardware_memory
from memory.vector_memory import store_memory


class _DesignMixin:

    # ======================
    # DISEÑO / CONSULTA TÉCNICA
    # ======================

    def _design_consult(self, task: str, context: str = "") -> str:
        """Asesoramiento técnico de ingeniería eléctrica/electrónica sin necesidad de dispositivo."""
        logger.info(f"[HardwareAgent] Consulta de diseño: {task[:60]}")

        stock_context = ""
        try:
            from database.component_stock import get_stock_db
            in_stock = get_stock_db().get_all(in_stock_only=True)
            if in_stock:
                stock_lines = [
                    f"  - {c['name']} ({c['value'] or ''}) {('pkg:'+c['package']) if c['package'] else ''} × {c['quantity']}"
                    for c in in_stock[:20]
                ]
                stock_context = "\n\nComponentes en stock del ingeniero (priorizalos):\n" + "\n".join(stock_lines)
        except Exception:
            pass

        decisions_context = ""
        try:
            from database.design_decisions import get_decisions_db
            recent = get_decisions_db().get_all(limit=5)
            if recent:
                lines = [f"  - [{d['project']}] {d['decision']}" for d in recent]
                decisions_context = "\n\nDecisiones de diseño previas:\n" + "\n".join(lines)
        except Exception:
            pass

        # Determinar plataforma de la sesión si está disponible en context
        platform_hint = ""
        if context and "PLATAFORMA DE SESIÓN:" in context:
            for line in context.splitlines():
                if "PLATAFORMA DE SESIÓN:" in line:
                    platform_hint = line.split("PLATAFORMA DE SESIÓN:")[-1].strip()
                    break

        if not platform_hint:
            platform_hint = "arduino"  # default: C++/Arduino IDE

        platform_instruction = (
            f"Para ejemplos de código usá **C++ con Arduino IDE** (setup/loop, #include, Serial.begin) "
            f"salvo que el usuario pida explícitamente MicroPython, ESP-IDF u otra plataforma."
            if platform_hint == "arduino"
            else f"Para ejemplos de código usá la plataforma **{platform_hint}** según el contexto de sesión."
        )

        system_prompt = (
            "Sos un ingeniero electrónico y eléctrico senior especializado en circuitos de potencia, "
            "automatización industrial, microcontroladores y electrónica embebida. "
            "Respondé en español, de forma técnica y concisa. "
            "Incluí: componentes recomendados con valores, normas de seguridad relevantes, "
            "esquema de conexiones si aplica, y código de control si el usuario lo necesita. "
            f"{platform_instruction} "
            "Si el diseño involucra alta tensión o alta potencia, siempre mencioná las consideraciones de seguridad."
        )

        user_content = task
        if stock_context:
            user_content += stock_context
        if decisions_context:
            user_content += decisions_context
        if context:
            user_content += f"\n\nContexto adicional:\n{context}"

        try:
            response = requests.post(
                LLM_API,
                headers=get_llm_headers("hardware-agent", "HardwareAgent"),
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    "temperature": 0.3,
                },
                timeout=180
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()

            try:
                store_memory(
                    f"[Diseño] {task[:120]}",
                    metadata={"type": "design_consult"}
                )
            except Exception:
                pass

            return answer

        except Exception as e:
            logger.error(f"[HardwareAgent] Error en design_consult: {e}")
            return f"No pude procesar la consulta de diseño: {e}"

    # ======================
    # DEBUGGING
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

        serial_output   = read_serial(device["port"], duration=5)
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
                timeout=180
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
    # FORMATO FIRMWARE
    # ======================

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
