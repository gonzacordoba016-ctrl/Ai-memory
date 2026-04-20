# agent/agents/hardware_diff.py — mixin para modificación incremental de firmware con diff

import difflib
import os
import requests

from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger


class _DiffMixin:

    def _modify_firmware(self, task: str, context: str = "") -> str:
        """Modifica el firmware actual de la sesión según el pedido del usuario y muestra un diff."""

        # Obtener el draft actual — viene inyectado en context por agent_controller
        current_code = None
        if context and "FIRMWARE ACTUAL EN SESIÓN" in context:
            # Extraer el código del contexto de sesión via state (referencia al controller)
            pass

        # Fallback: buscar en context directo
        try:
            from api.app_state import agent_controller
            current_code = agent_controller.state.get_firmware_draft()
        except Exception:
            pass

        if not current_code:
            return (
                "No tengo un firmware previo en esta sesión para modificar. "
                "Primero pedime que escriba el firmware y luego puedo modificarlo."
            )

        system_prompt = (
            "Sos un ingeniero de firmware senior. "
            "Te doy el código actual y una instrucción de modificación. "
            "Devolvé ÚNICAMENTE el código completo modificado, sin explicaciones, "
            "dentro de un bloque ```cpp ... ```. "
            "Mantené el estilo y la estructura del código original. "
            "Usá C++ con Arduino IDE salvo que el código original use otra plataforma."
        )

        user_content = (
            f"Código actual:\n```cpp\n{current_code}\n```\n\n"
            f"Modificación solicitada: {task}"
        )

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
                    "temperature": 0.2,
                },
                timeout=120,
            )
            response.raise_for_status()
            new_code_raw = response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[HardwareAgent] Error modificando firmware: {e}")
            return f"Error modificando el firmware: {e}"

        # Extraer código del bloque
        import re
        code_blocks = re.findall(r'```(?:cpp|c|arduino)?\n(.*?)```', new_code_raw, re.DOTALL)
        new_code = code_blocks[0].strip() if code_blocks else new_code_raw.strip()

        # Generar diff coloreado (formato GitHub-style para el frontend)
        diff_lines = list(difflib.unified_diff(
            current_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile="firmware_anterior",
            tofile="firmware_nuevo",
            lineterm="",
        ))

        diff_text = "".join(diff_lines) if diff_lines else "(sin cambios detectados)"

        # Guardar nuevo draft
        try:
            from api.app_state import agent_controller
            agent_controller.state.set_firmware_draft(new_code)
        except Exception:
            pass

        return (
            f"Firmware modificado. Cambios:\n\n"
            f"```diff\n{diff_text}\n```\n\n"
            f"Código completo actualizado:\n\n"
            f"```cpp\n{new_code}\n```"
        )
