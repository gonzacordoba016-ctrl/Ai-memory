# tools/datasheet_fetcher.py
# Descarga y cachea datasheets de componentes electrónicos.
# Fuente: búsqueda DuckDuckGo → PDF/TXT de fabricante

import os
import re
import httpx
from pathlib import Path
from core.logger import logger

CACHE_DIR = Path("./agent_files/datasheets")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ICs comunes con URLs directas para evitar búsqueda
_DIRECT_URLS: dict[str, str] = {
    "lm317":   "https://www.ti.com/lit/ds/symlink/lm317.pdf",
    "lm7805":  "https://www.ti.com/lit/ds/symlink/lm7805.pdf",
    "lm35":    "https://www.ti.com/lit/ds/symlink/lm35.pdf",
    "ne555":   "https://www.ti.com/lit/ds/symlink/ne555.pdf",
    "uln2003": "https://www.ti.com/lit/ds/symlink/uln2003a.pdf",
    "l298n":   "https://www.st.com/resource/en/datasheet/l298.pdf",
    "ina219":  "https://www.ti.com/lit/ds/symlink/ina219.pdf",
    "mcp3208": "https://ww1.microchip.com/downloads/en/DeviceDoc/21298e.pdf",
}

# Regex para detectar nombres de CIs en texto
_IC_PATTERN = re.compile(
    r'\b(lm\d{3,4}[a-z]?|ne\d{3}|l\d{3,4}n?|irf\d{3,4}|tip\d{3}|bc\d{3}|'
    r'mcp\d{4}|ina\d{3}|uln\d{4}|esp\d{2,4}|stm\d{2}|pic\d{2}[a-z]\d+|'
    r'atmega\d+|attiny\d+|74[hls]+\d+|lm\d+|max\d{4}|ads\d{4}|dac\d{4})\b',
    re.IGNORECASE,
)


def extract_ic_names(text: str) -> list[str]:
    """Detecta nombres de CIs en un texto."""
    found = _IC_PATTERN.findall(text.lower())
    return list(set(found))


def get_cached_path(ic_name: str) -> Path:
    return CACHE_DIR / f"{ic_name.lower()}.txt"


def is_cached(ic_name: str) -> bool:
    return get_cached_path(ic_name).exists()


def fetch_datasheet_text(ic_name: str) -> str | None:
    """
    Busca y devuelve el texto del datasheet del CI.
    Primero revisa caché local, luego intenta descarga directa, luego búsqueda web.
    """
    ic = ic_name.lower().strip()
    cache_path = get_cached_path(ic)

    if cache_path.exists():
        logger.info(f"[Datasheet] Cache hit: {ic}")
        return cache_path.read_text(encoding="utf-8", errors="ignore")

    # Intentar URL directa conocida
    if ic in _DIRECT_URLS:
        text = _fetch_pdf_text(_DIRECT_URLS[ic])
        if text:
            cache_path.write_text(text, encoding="utf-8")
            logger.info(f"[Datasheet] Descargado via URL directa: {ic}")
            return text

    # Fallback: búsqueda DuckDuckGo para encontrar el datasheet
    try:
        from tools.web_search import web_search
        results = web_search(f"{ic} datasheet filetype:pdf site:ti.com OR site:st.com OR site:microchip.com", max_results=3)
        for r in results:
            url = r.get("url", "")
            if url.endswith(".pdf") or "datasheet" in url.lower():
                text = _fetch_pdf_text(url)
                if text:
                    cache_path.write_text(text, encoding="utf-8")
                    logger.info(f"[Datasheet] Descargado via búsqueda: {ic} — {url}")
                    return text
    except Exception as e:
        logger.warning(f"[Datasheet] Búsqueda fallida para {ic}: {e}")

    # Fallback final: resumen del conocimiento interno del LLM
    logger.info(f"[Datasheet] No se encontró datasheet para {ic}, usando resumen LLM")
    return _generate_summary(ic)


def _fetch_pdf_text(url: str) -> str | None:
    """Descarga un PDF y extrae texto."""
    try:
        r = httpx.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        if r.status_code != 200:
            return None
        content_type = r.headers.get("content-type", "")
        if "pdf" in content_type:
            try:
                import pdfplumber
                import io
                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                    pages = []
                    for page in pdf.pages[:8]:  # primeras 8 páginas
                        t = page.extract_text()
                        if t:
                            pages.append(t)
                    return "\n".join(pages)[:8000]
            except Exception:
                return None
        elif "text" in content_type:
            return r.text[:8000]
    except Exception as e:
        logger.warning(f"[Datasheet] Error descargando {url}: {e}")
    return None


def _generate_summary(ic_name: str) -> str:
    """Genera un resumen técnico del CI usando el LLM como fallback."""
    try:
        from core.config import LLM_API, LLM_MODEL, get_llm_headers
        r = httpx.post(
            LLM_API,
            headers=get_llm_headers("datasheet-fetcher", "DatasheetFetcher"),
            json={
                "model": LLM_MODEL,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Generá un resumen técnico del componente electrónico {ic_name.upper()} "
                        f"con: descripción, voltaje de operación, corriente máxima, pinout típico, "
                        f"aplicaciones principales, notas de seguridad. Sé conciso y técnico."
                    ),
                }],
                "temperature": 0.1,
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        # Cachear el resumen también
        get_cached_path(ic_name).write_text(f"[Resumen LLM — no es el datasheet oficial]\n\n{text}", encoding="utf-8")
        return text
    except Exception as e:
        logger.error(f"[Datasheet] Error generando resumen LLM para {ic_name}: {e}")
        return ""


def auto_fetch_and_index(text: str) -> list[str]:
    """
    Detecta CIs en un texto, descarga sus datasheets y los indexa en la KB.
    Retorna lista de CIs indexados.
    """
    ics = extract_ic_names(text)
    indexed = []
    for ic in ics:
        if is_cached(ic):
            continue
        content = fetch_datasheet_text(ic)
        if content:
            try:
                from knowledge.knowledge_base import index_knowledge_base
                # Escribir a knowledge dir para que se indexe
                from pathlib import Path
                kb_path = Path("./agent_files/knowledge") / f"datasheet_{ic}.txt"
                kb_path.write_text(f"# Datasheet: {ic.upper()}\n\n{content}", encoding="utf-8")
                index_knowledge_base(force=False)
                indexed.append(ic)
                logger.info(f"[Datasheet] Indexado en KB: {ic}")
            except Exception as e:
                logger.warning(f"[Datasheet] Error indexando {ic}: {e}")
    return indexed
