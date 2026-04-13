# infrastructure/embeddings.py

import threading
from sentence_transformers import SentenceTransformer
from core.config import EMBEDDING_MODEL
from core.logger import logger


class EmbeddingModel:
    """
    Lazy-loading wrapper sobre SentenceTransformer.
    El modelo se carga en el primer embed(), no al importar el módulo.
    Esto permite que uvicorn bindee el puerto antes de que el modelo esté listo.
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
                self._model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
                logger.info(f"[Embeddings] Modelo cargado desde cache: {EMBEDDING_MODEL}")
            except Exception:
                logger.info(f"[Embeddings] Cache miss — descargando: {EMBEDDING_MODEL}")
                try:
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
