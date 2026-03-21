# memory/graph_extractor.py

import json
from memory.graph_memory import graph_memory
from core.logger import logger
from llm.async_client import call_llm_text

RELATION_PROMPT = """Analizá el siguiente mensaje y extraé relaciones entre entidades.

Devolvé ÚNICAMENTE un JSON con una lista de relaciones. Cada relación tiene:
- subject: entidad origen (siempre en minúsculas)
- predicate: tipo de relación (verbo corto, en minúsculas)
- object: entidad destino (en minúsculas)

Ejemplos de relaciones válidas:
- "Me llamo Juan y trabajo en Acme" → [{{"subject":"usuario","predicate":"se_llama","object":"juan"}},{{"subject":"usuario","predicate":"trabaja_en","object":"acme"}}]
- "Acme usa Python para sus backends" → [{{"subject":"acme","predicate":"usa","object":"python"}},{{"subject":"python","predicate":"se_usa_para","object":"backends"}}]
- "Hola, ¿cómo estás?" → []

Si no hay relaciones claras, devolvé [].

Mensaje: "{message}"

Respondé solo con el JSON array, sin explicaciones ni markdown."""

MIN_LENGTH    = 20
SKIP_KEYWORDS = ["/help", "/memory", "/history", "/search", "/exit", "/pdf", "/system"]


async def extract_relations(text: str) -> list[dict]:
    """
    Extrae relaciones del texto usando el LLM de forma async
    y las persiste en el grafo.
    """
    if len(text) < MIN_LENGTH:
        return []
    if any(text.startswith(kw) for kw in SKIP_KEYWORDS):
        return []

    try:
        content = await call_llm_text(
            messages=[{
                "role":    "user",
                "content": RELATION_PROMPT.format(message=text),
            }],
            temperature=0,
            timeout=30,
            agent_id="graph-extractor",
            agent_name="GraphExtractor",
        )

        if not content:
            return []

        content   = content.replace("```json", "").replace("```", "").strip()
        relations = json.loads(content)

        if not isinstance(relations, list):
            return []

        for rel in relations:
            s = rel.get("subject", "").strip()
            p = rel.get("predicate", "").strip()
            o = rel.get("object", "").strip()
            if s and p and o:
                graph_memory.add_relation(s, p, o, source="conversation")

        if relations:
            logger.info(f"Grafo: {len(relations)} relaciones extraídas")

        return relations

    except Exception as e:
        logger.error(f"Error extrayendo relaciones para el grafo: {e}")
        return []