# agent/agents/memory_agent.py
#
# Especialista en consultar y sintetizar la memoria del sistema.
# No escribe en memoria (eso lo hace el AgentController), solo lee.

from agent.agents.base_agent import BaseAgent
from memory.vector_memory import search_memory, search_memory_with_scores
from memory.graph_memory import graph_memory
from database.sql_memory import _default as sql_db
from core.logger import logger


class MemoryAgent(BaseAgent):

    name        = "MemoryAgent"
    description = "Consulta memoria vectorial, grafo de relaciones y hechos del usuario"
    system_prompt = """Eres un agente especialista en memoria y contexto del usuario.

Tu función es recuperar y sintetizar información relevante de la memoria del sistema.

Reglas:
- Combiná hechos estructurados, memorias semánticas y relaciones del grafo
- Presentá la información de forma organizada
- Indicá la fuente de cada dato (SQLite, Qdrant, grafo)
- Si no hay información, decilo claramente"""

    def __init__(self, client_fn):
        # MemoryAgent no usa herramientas del tool_registry
        # opera directamente sobre los módulos de memoria
        super().__init__(client_fn, [], lambda name, args: "")

    def run(self, task: str, context: str = "") -> str:
        """Override: consulta memoria directamente sin loop ReAct."""
        try:
            facts    = sql_db.get_all_facts()
            memories = search_memory_with_scores(task, top_k=5)
            graph_ctx = graph_memory.get_context_for_query(task)

            parts = []

            if facts:
                facts_text = "\n".join(f"  {k}: {v}" for k, v in facts.items())
                parts.append(f"Hechos conocidos (SQLite):\n{facts_text}")

            if memories:
                mem_lines = "\n".join(
                    f"  [{m['score']:.2f}] {m['text'][:100]}"
                    for m in memories
                )
                parts.append(f"Memorias relevantes (Qdrant):\n{mem_lines}")

            if graph_ctx:
                parts.append(f"Relaciones (Grafo):\n{graph_ctx}")

            if not parts:
                return "No se encontró información relevante en memoria."

            summary = "\n\n".join(parts)
            logger.info(f"[MemoryAgent] Recuperadas {len(memories)} memorias, "
                        f"{len(facts)} hechos")
            return summary

        except Exception as e:
            logger.error(f"[MemoryAgent] Error: {e}")
            return f"Error consultando memoria: {e}"