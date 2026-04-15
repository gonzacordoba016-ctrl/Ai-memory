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

    async def process_input(self, user_input: str, on_token=None) -> str:

        # 1. Guardar input
        self.state.add_message("user", user_input)
        self.short_memory.add(user_input)

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

        # Si el hardware agent manejó el comando completamente, devolver directo
        # (evita que el LLM principal reescriba o contradiga la respuesta del agente)
        hw_result = orch_result["results"].get("hardware", "")
        if hw_result and agents_used == ["hardware"]:
            self.state.add_message("assistant", hw_result)
            self._store_episode(user_input, hw_result)
            self.profiler.update_from_interaction(user_input, hw_result)
            if on_token:
                for char in hw_result:
                    await on_token(char)
            return hw_result

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

        return response

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

    def _build_base_context(self) -> str:
        facts = self.state.get_all_facts()
        if not facts:
            return ""
        return "Hechos del usuario: " + ", ".join(f"{k}={v}" for k, v in facts.items())

    def _store_episode(self, user_input: str, response: str):
        try:
            memory_text = f"Usuario: {user_input} | Agente: {response}"
            store_memory(memory_text)
            self.sql_memory.store_message("user", user_input)
            self.sql_memory.store_message("assistant", response)
        except Exception as e:
            logger.error(f"Error guardando episodio: {e}")