# infrastructure/embeddings.py

import threading
from core.config import EMBEDDING_MODEL
from core.logger import logger

# SentenceTransformer NO se importa aquí — cargarlo arrastra torch (~60-120s) y
# bloquearía el bind del socket de uvicorn antes del primer request.
# El import real ocurre dentro de _ensure_loaded(), al primer embed().


class EmbeddingModel:
    """
    Lazy-loading wrapper sobre SentenceTransformer.
    Tanto el import de sentence_transformers como la carga del modelo se hacen
    al primer embed(), no al importar el módulo.
    Esto garantiza que uvicorn bindee el puerto en <1s.
    Thread-safe: usa un lock para evitar doble carga.
    """

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer  # import lazy
                self._model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
                logger.info(f"[Embeddings] Modelo cargado desde cache: {EMBEDDING_MODEL}")
            except Exception:
                logger.info(f"[Embeddings] Cache miss — descargando: {EMBEDDING_MODEL}")
                try:
                    from sentence_transformers import SentenceTransformer  # import lazy
                    self._model = SentenceTransformer(EMBEDDING_MODEL)
                    logger.info(f"[Embeddings] Modelo descargado: {EMBEDDING_MODEL}")
                except Exception as e:
                    logger.error(f"[Embeddings] No se pudo cargar el modelo: {e}")
                    self._model = None

    def embed(self, text: str) -> list[float]:
        self._ensure_loaded()
        if self._model is None:
            return [0.0] * 384  # fallback vacío
        if isinstance(text, list):
            return self._model.encode(text).tolist()
        return self._model.encode([text])[0].tolist()


# instancia global reutilizable — liviana, no carga el modelo al importar
embedding_model = EmbeddingModel()
