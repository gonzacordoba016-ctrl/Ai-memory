# tools/web_search.py

from duckduckgo_search import DDGS
from core.logger import logger


def web_search(query: str, max_results: int = 4) -> str:
    """Busca en la web usando DuckDuckGo y retorna resultados como texto."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"- {r['title']}: {r['body']}")

        if not results:
            return "No se encontraron resultados."

        return "\n".join(results)

    except Exception as e:
        logger.error(f"Error en búsqueda web: {e}")
        return f"Error al buscar: {e}"