# agent/agents/hardware_agent.py

import requests
from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger
from tools.hardware_detector import detect_devices
from tools.signal_reader import signal_reader
from database.hardware_memory import hardware_memory

from agent.agents.hardware_keywords import (
    INTENT_PROMPT, _normalize,
    SAVE_DECISION_KEYWORDS, SAVE_CIRCUIT_KEYWORDS, QUERY_KEYWORDS,
    SIGNAL_KEYWORDS, DEBUG_KEYWORDS, PROGRAM_KEYWORDS, DESIGN_KEYWORDS, MODIFY_KEYWORDS,
)
from agent.agents.hardware_firmware import _FirmwareMixin
from agent.agents.hardware_memory_ops import _MemoryOpsMixin
from agent.agents.hardware_design import _DesignMixin
from agent.agents.hardware_diff import _DiffMixin


class HardwareAgent(_FirmwareMixin, _MemoryOpsMixin, _DesignMixin, _DiffMixin):

    name        = "HardwareAgent"
    description = "Programá hardware conectado: Arduino, ESP32, ESP8266 y más"

    def run(self, task: str, context: str = "") -> str:
        intent = self._classify_intent(task)
        logger.info(f"[HardwareAgent] Intent: {intent} | Tarea: {task[:60]}")

        if intent == "save_decision": return self._save_decision(task)
        if intent == "save_circuit":  return self._save_circuit(task)
        if intent == "query":         return self._query_memory(task)
        if intent == "signal":        return self._start_signal_mode(task)
        if intent == "debug":         return self._debug_mode(task)
        if intent == "design":        return self._design_consult(task, context)
        if intent == "modify":        return self._modify_firmware(task, context)
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
            for valid in ("save_decision", "save_circuit", "query", "program", "signal", "debug", "design"):
                if valid in intent:
                    return valid
        except Exception as e:
            logger.error(f"[HardwareAgent] Error clasificando intent: {e}")

        return self._classify_by_keywords(task)

    def _classify_by_keywords(self, task: str) -> str:
        """Fallback exhaustivo por keywords cuando el LLM no responde."""
        t = _normalize(task.lower())

        if any(_normalize(kw) in t for kw in SAVE_DECISION_KEYWORDS):
            return "save_decision"
        if any(_normalize(kw) in t for kw in SAVE_CIRCUIT_KEYWORDS):
            return "save_circuit"
        # Debug tiene prioridad sobre program (errores antes que programar)
        if any(_normalize(kw) in t for kw in DEBUG_KEYWORDS):
            return "debug"
        if any(_normalize(kw) in t for kw in QUERY_KEYWORDS):
            return "query"
        if any(_normalize(kw) in t for kw in SIGNAL_KEYWORDS):
            return "signal"
        if any(_normalize(kw) in t for kw in DESIGN_KEYWORDS):
            return "design"
        if any(_normalize(kw) in t for kw in MODIFY_KEYWORDS):
            return "modify"
        if any(_normalize(kw) in t for kw in PROGRAM_KEYWORDS):
            return "program"
        # Default: si mencionan hardware sin contexto claro, consulta de diseño
        return "design"

    # ======================
    # SEÑAL
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


# ── Singleton ─────────────────────────────────────────────────────────────────
_hardware_agent_instance: HardwareAgent | None = None


def get_hardware_agent() -> HardwareAgent:
    """Retorna la instancia singleton del HardwareAgent."""
    global _hardware_agent_instance
    if _hardware_agent_instance is None:
        _hardware_agent_instance = HardwareAgent()
    return _hardware_agent_instance
