# agent/agents/hardware_firmware.py — mixin de programación/compilación para HardwareAgent

import os
import httpx
from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger
from tools.hardware_detector import detect_devices
from tools.firmware_generator import generate_firmware
from tools.firmware_flasher import flash_firmware, compile_firmware, install_missing_libraries
from tools.serial_monitor import read_serial
from database.hardware_memory import hardware_memory


class _FirmwareMixin:

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
            # Sin dispositivo → asesoramiento técnico en vez de error genérico
            logger.info("[HardwareAgent] Sin dispositivo — derivando a design_consult")
            advice = self._design_consult(task, context)
            return (
                advice + "\n\n---\n"
                "*Si querés flashear el firmware, conectá el Arduino/ESP32 por USB y repetí el comando.*"
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

        if "circuito" in task.lower() and saved_circuit:
            full_context += f"\n\nGENERAR FIRMWARE PARA ESTE CIRCUITO EXACTO:\n{self._format_circuit_for_firmware(saved_circuit)}"

        firmware = generate_firmware(
            description=full_context,
            platform=device["platform"],
            device_name=device["name"],
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
            device_name=device["name"],
            task=task,
            code=firmware["code"],
            filename=firmware["filename"],
            success=True,
            serial_out=serial_output,
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

        circuit_context = {}
        device_name = ""
        try:
            from database.hardware_memory import hardware_memory as _hw
            device_name = self._extract_device_name(task) or ""
            if device_name:
                saved = _hw.get_circuit_context(device_name)
                if saved:
                    circuit_context = saved
        except Exception:
            pass

        result = call_bridge_sync("program", {
            "task":            task,
            "device_name":     device_name,
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

    def _fix_firmware(self, code: str, error: str, platform: str, task: str) -> str:
        try:
            response = httpx.post(
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
                timeout=180
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
