# agent/agents/research_agent.py

import httpx
from agent.agents.base_agent import BaseAgent
from tools.tool_registry import TOOL_DEFINITIONS, execute_tool
from knowledge.knowledge_base import search_knowledge
from core.config import LLM_API, LLM_MODEL, get_llm_headers
from core.logger import logger

_TOOLS = [t for t in TOOL_DEFINITIONS
          if t["function"]["name"] in ("web_search", "get_datetime")]


class ResearchAgent(BaseAgent):

    name         = "ResearchAgent"
    description  = "Busca información en knowledge base local y en internet"
    system_prompt = (
        "Eres un agente especialista en investigacion y busqueda de informacion.\n"
        "Primero consultás la knowledge base local. "
        "Si no encontrás informacion suficiente, buscás en internet.\n"
        "Reglas:\n"
        "- Siempre indicá la fuente de la informacion\n"
        "- Si la knowledge base tiene la respuesta, no busques en web\n"
        "- Sintetizá los resultados de forma clara y concisa\n"
        "- No inventes datos"
    )

    def __init__(self, client_fn):
        super().__init__(client_fn, _TOOLS, execute_tool)

    def run(self, task: str, context: str = "") -> str:

        # 1. Buscar en knowledge base primero
        kb_results = search_knowledge(task, top_k=3)

        if kb_results:
            logger.info(f"[ResearchAgent] Knowledge base: {len(kb_results)} resultados")
            kb_text = "\n".join(kb_results)

            # Respuesta directa desde knowledge base sin entrar al loop ReAct
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Eres un agente de investigacion. "
                        "Tenés la siguiente informacion disponible de la knowledge base local. "
                        "USALA para responder sin buscar en internet ni leer archivos:\n\n"
                        f"{kb_text}"
                    )
                },
                {"role": "user", "content": task}
            ]

            try:
                response = httpx.post(
                    LLM_API,
                    headers=get_llm_headers(
                        agent_id="research-agent",
                        agent_name="ResearchAgent"
                    ),
                    json={
                        "model":       LLM_MODEL,
                        "messages":    messages,
                        "temperature": 0.3,
                    },
                    timeout=30
                )
                response.raise_for_status()
                answer = response.json()["choices"][0]["message"].get("content", "")
                if answer:
                    logger.info("[ResearchAgent] Respondió desde knowledge base")
                    return answer
            except Exception as e:
                logger.error(f"[ResearchAgent] Error respuesta directa: {e}")

        # 2. Sin resultados locales → loop ReAct con web_search
        logger.info("[ResearchAgent] Sin resultados locales, buscando en web")
        return super().run(task, context)