# agent/agent_controller.py

from agent.agent_state import AgentState
from memory.vector_memory import store_memory, search_memory
from memory.short_memory import ShortMemory
from memory.fact_extractor import extract_facts
from memory.graph_memory import graph_memory
from memory.graph_extractor import extract_relations
from database.sql_memory import SQLMemory
from core.prompt_builder import build_prompt
from agent.user_profiler import UserProfiler
from core.logger import logger
from agent.orchestrator import Orchestrator
from llm.openrouter_client import _call_llm
from llm.async_client import stream_llm_async


class AgentController:

    def __init__(self):
        self.state        = AgentState()
        self.short_memory = ShortMemory()
        self.sql_memory   = SQLMemory()
        self.orchestrator = Orchestrator(_call_llm)
        self.profiler     = UserProfiler(self.sql_memory)
        self._load_persisted_facts()
        self._init_knowledge_base()

    def _load_persisted_facts(self):
        try:
            facts = self.sql_memory.get_all_facts()
            for key, value in facts.items():
                self.state.set_user_fact(key, value)
            if facts:
                graph_memory.add_facts_from_dict(facts)
                logger.info(f"Memoria cargada: {len(facts)} hechos | "
                            f"Grafo: {graph_memory.stats()}")
        except Exception as e:
            logger.error(f"Error cargando memoria: {e}")

    def _init_knowledge_base(self):
        try:
            from knowledge.knowledge_base import index_knowledge_base
            result = index_knowledge_base(force=False)
            if result["files"] > 0:
                logger.info(f"Knowledge base: {result['files']} archivos nuevos, "
                            f"{result['chunks']} chunks indexados")
        except Exception as e:
            logger.error(f"Error inicializando knowledge base: {e}")

    async def process_input(self, user_input: str, on_token=None) -> dict:

        # 1. Guardar input + detectar plataforma
        self.state.add_message("user", user_input)
        self.short_memory.add(user_input)
        self._detect_and_set_platform(user_input)

        # 2. Extraer hechos y relaciones en paralelo (async, no bloquean)
        import asyncio
        new_facts, _ = await asyncio.gather(
            extract_facts(user_input),
            extract_relations(user_input),
            return_exceptions=True,
        )
        if isinstance(new_facts, dict):
            for key, value in new_facts.items():
                self.state.set_user_fact(key, value)
            if new_facts:
                graph_memory.add_facts_from_dict(new_facts)
                logger.info(f"Nuevos hechos: {new_facts}")

        # 3. Orquestador async
        orch_result = await self.orchestrator.run(
            query   = user_input,
            context = self._build_base_context(),
        )
        agents_used = orch_result["agents_used"]
        sub_context = orch_result["combined_context"]
        logger.info(f"Agentes usados: {agents_used}")

        # Circuit design: respuesta directa con card embebida
        circuit_result = orch_result["results"].get("circuit_design")
        if circuit_result and "circuit_design" in agents_used:
            design_id = circuit_result.get("design_id", 0)
            cname = circuit_result.get("name", "Circuito")
            cdesc = circuit_result.get("description", "")
            comps = circuit_result.get("components", [])
            nets  = circuit_result.get("nets", [])
            power = circuit_result.get("power", "")
            warns = circuit_result.get("warnings", [])
            drc   = circuit_result.get("drc", {})
            domain = circuit_result.get("detected_domain", "")
            mcu   = circuit_result.get("selected_mcu", "")
            drc_line = "✅ DRC pasado sin errores" if drc.get("passed", True) else \
                       f"⚠ DRC: {len(drc.get('errors', []))} errores — {drc.get('errors', [{}])[0].get('message','')}"

            hw_md = (
                f"## 🔌 {cname}\n"
                f"{cdesc}\n\n"
                f"**MCU:** {mcu} | **Alimentación:** {power} | **Dominio:** {domain}\n\n"
                f"**Componentes ({len(comps)}):**\n"
                + "".join(f"- `{c['id']}` {c['name']}" + (f" — {c.get('value','')}{c.get('unit','')}" if c.get('value') else '') + "\n"
                          for c in comps[:12])
                + (f"\n_… y {len(comps)-12} más_\n" if len(comps) > 12 else "")
                + f"\n**Nets ({len(nets)}):** " + ", ".join(f"`{n['name']}`" for n in nets[:8])
                + (f" … +{len(nets)-8}" if len(nets) > 8 else "")
                + f"\n\n**{drc_line}**"
                + (f"\n\n⚠ **Advertencias:** " + " · ".join(warns[:3]) if warns else "")
                + f"\n\n---\n"
                f"📐 **Circuito ID {design_id}** — disponible en:\n"
                f"- [Esquemático SVG](/api/circuits/{design_id}/schematic.svg)\n"
                f"- [KiCad .kicad_sch](/api/circuits/{design_id}/schematic.kicad_sch)\n"
                f"- [BOM CSV](/api/circuits/{design_id}/bom.csv)\n"
                f"- [Gerber ZIP](/api/circuits/{design_id}/gerber)\n"
                f"- [Ver en 3D](/api/circuits/viewer?id={design_id})\n"
            )
            self.state.add_message("assistant", hw_md)
            self._store_episode(user_input, hw_md)
            self.profiler.update_from_interaction(user_input, hw_md)
            if on_token:
                for char in hw_md:
                    await on_token(char)
            return {"text": hw_md, "circuit_design_id": design_id,
                    "circuit_name": cname, "agents_used": agents_used}

        # Si el hardware agent manejó el comando completamente, devolver directo
        # (evita que el LLM principal reescriba o contradiga la respuesta del agente)
        hw_result = orch_result["results"].get("hardware", "")
        if hw_result and agents_used == ["hardware"]:
            self.state.add_message("assistant", hw_result)
            self._store_episode(user_input, hw_result)
            self.profiler.update_from_interaction(user_input, hw_result)
            # Guardar firmware draft si la respuesta contiene código C++
            if "```cpp" in hw_result or "void setup()" in hw_result or "void loop()" in hw_result:
                import re
                code_blocks = re.findall(r'```(?:cpp|c|arduino)?\n(.*?)```', hw_result, re.DOTALL)
                if code_blocks:
                    self.state.set_firmware_draft(code_blocks[0])
            if on_token:
                for char in hw_result:
                    await on_token(char)
            return {"text": hw_result, "agents_used": agents_used}

        # 4. Obtener perfil activo de IA + contexto de fuentes
        ai_system_prompt = None
        source_context   = ""
        try:
            from database.intelligence import intelligence_db
            from memory.vector_memory import search_in_sources
            profile = intelligence_db.get_active_profile()
            if profile:
                ai_system_prompt = profile.get("system_prompt")
                active_sources   = profile.get("active_sources", [])
                if active_sources:
                    source_context = search_in_sources(user_input, active_sources)
        except Exception as e:
            logger.warning(f"[AgentController] No se pudo cargar perfil de IA: {e}")

        # 5. Búsqueda semántica en Qdrant — siempre, independiente del orquestador
        try:
            memories = await asyncio.to_thread(search_memory, user_input, 5)
        except Exception:
            memories = []

        # 6. Construir prompt final con perfil del usuario
        prompt = build_prompt(
            user_input           = user_input,
            history              = self.state.get_history(),
            memories             = memories,
            facts                = self.state.get_all_facts(),
            graph_context        = sub_context,
            user_profile_context = self.profiler.format_for_prompt(),
            system_prompt        = ai_system_prompt,
            source_context       = source_context,
        )

        # 7. Generar respuesta — streaming async o llamada directa
        messages = [{"role": "user", "content": prompt}]

        if on_token:
            # on_token ahora puede ser async o sync — lo normalizamos
            async def _on_token_async(token: str):
                if asyncio.iscoroutinefunction(on_token):
                    await on_token(token)
                else:
                    on_token(token)

            response = await stream_llm_async(
                messages   = messages,
                on_token   = _on_token_async,
                agent_id   = "agent-controller",
                agent_name = "AgentController",
            )
        else:
            raw      = await asyncio.to_thread(_call_llm, messages)
            response = raw["choices"][0]["message"].get("content", "")

        if not response:
            response = "No pude generar una respuesta."

        # 7. Persistir y actualizar perfil del usuario
        self.state.add_message("assistant", response)
        self._store_episode(user_input, response)
        self.profiler.update_from_interaction(user_input, response)

        # 8. Auto-fetch datasheets en background (no bloquea)
        asyncio.create_task(self._auto_fetch_datasheets(user_input + " " + response))

        return {"text": response, "agents_used": agents_used}

    async def _auto_fetch_datasheets(self, text: str):
        try:
            from tools.datasheet_fetcher import auto_fetch_and_index
            indexed = await asyncio.to_thread(auto_fetch_and_index, text)
            if indexed:
                logger.info(f"[AgentController] Datasheets indexados: {indexed}")
        except Exception as e:
            logger.warning(f"[AgentController] Error en auto_fetch_datasheets: {e}")

    def consolidate_on_exit(self):
        """
        Consolida memorias antiguas al cerrar la sesión.
        Llamar desde main.py en _exit_gracefully.
        """
        try:
            from memory.memory_consolidator import memory_consolidator
            result = memory_consolidator.consolidate_old_memories(days_threshold=7)
            stats  = memory_consolidator.stats()
            logger.info(
                f"[Consolidator] Sesión cerrada | "
                f"Contradicciones: {stats['contradictions_resolved']} | "
                f"Redundancias: {stats['redundancies_skipped']} | "
                f"Fusiones: {stats['memories_merged']}"
            )
            return result
        except Exception as e:
            logger.error(f"Error en consolidación al salir: {e}")
            return {}

    _PLATFORM_KEYWORDS = {
        "arduino": ["arduino ide", "arduino", ".ino", "#include <arduino"],
        "micropython": ["micropython", "from machine import", "import machine", "thonny"],
        "esp-idf": ["esp-idf", "idf.py", "menuconfig", "sdkconfig"],
        "platformio": ["platformio", "platform.ini", "pio run"],
    }

    def _detect_and_set_platform(self, text: str):
        t = text.lower()
        for platform, keywords in self._PLATFORM_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                if self.state.get_platform() != platform:
                    self.state.set_platform(platform)
                    logger.info(f"[AgentController] Plataforma detectada: {platform}")
                return

    def _build_base_context(self) -> str:
        parts = []
        facts = self.state.get_all_facts()
        if facts:
            parts.append("Hechos del usuario: " + ", ".join(f"{k}={v}" for k, v in facts.items()))
        try:
            project = self.sql_memory.get_active_project()
            if project:
                p_ctx = f"PROYECTO ACTIVO: {project['name']}"
                if project.get('mcu'):
                    p_ctx += f" | MCU: {project['mcu']}"
                if project.get('components'):
                    p_ctx += f" | Componentes: {project['components']}"
                if project.get('description'):
                    p_ctx += f" | Descripción: {project['description']}"
                parts.append(p_ctx)
        except Exception:
            pass

        # Plataforma detectada en sesión
        platform = self.state.get_platform()
        if platform:
            parts.append(f"PLATAFORMA DE SESIÓN: {platform} — usá esta plataforma por defecto para todo el código")

        # Firmware draft disponible
        draft = self.state.get_firmware_draft()
        if draft:
            preview = draft[:300].replace('\n', ' ')
            parts.append(f"FIRMWARE ACTUAL EN SESIÓN (primeras líneas): {preview}…")

        return "\n".join(parts)

    def _store_episode(self, user_input: str, response: str):
        try:
            memory_text = f"Usuario: {user_input} | Agente: {response}"
            store_memory(memory_text)
            self.sql_memory.store_message("user", user_input)
            self.sql_memory.store_message("assistant", response)
        except Exception as e:
            logger.error(f"Error guardando episodio: {e}")