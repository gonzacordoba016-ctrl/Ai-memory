# agent/agents/hardware_memory_ops.py — mixin de operaciones de memoria para HardwareAgent

import re
from datetime import datetime, timezone

from core.logger import logger
from database.hardware_memory import hardware_memory
from memory.vector_memory import store_memory, search_memory
from memory.graph_memory import graph_memory

from agent.agents.hardware_keywords import SAVE_DECISION_KEYWORDS


class _MemoryOpsMixin:

    # ======================
    # GUARDAR DECISIÓN
    # ======================

    def _save_decision(self, task: str) -> str:
        """Guarda el razonamiento detrás de una decisión de diseño."""
        from database.design_decisions import get_decisions_db

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

        # Extraer la decisión/razonamiento
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
        t = task.lower()
        match = re.search(r'\bpara\s+(.+?)(?:\s*$)', t)
        if match:
            name = match.group(1).strip().rstrip(".,!?")
            return name.title() if name else ""
        for keyword in ["arduino", "esp32", "esp8266", "pico", "nano", "mega", "uno"]:
            if keyword in t:
                return keyword.title()
        return ""

    # ======================
    # CONSULTAR MEMORIA
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

            circuit = hardware_memory.get_circuit_context(d["name"])
            if circuit:
                lines.append(f"  🔌 Circuito: {circuit['project_name'] or 'sin nombre'}")
                if circuit['components']:
                    comps = ", ".join(c.get('name', '?') for c in circuit['components'][:5])
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
    # VECTOR + GRAFO
    # ======================

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
