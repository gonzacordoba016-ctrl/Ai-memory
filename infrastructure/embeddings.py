# infrastructure/embeddings.py

from sentence_transformers import SentenceTransformer
from core.config import EMBEDDING_MODEL
from core.logger import logger


class EmbeddingModel:

    def __init__(self):
        try:
            # Intentar desde cache local sin tocar la red
            self.model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
            logger.info(f"[Embeddings] Modelo cargado desde cache: {EMBEDDING_MODEL}")
        except Exception:
            # No está en cache — descargar (solo ocurre la primera vez)
            logger.info(f"[Embeddings] Descargando modelo: {EMBEDDING_MODEL}")
            self.model = SentenceTransformer(EMBEDDING_MODEL)

    def embed(self, text: str) -> list[float]:
        if isinstance(text, list):
            return self.model.encode(text).tolist()
        return self.model.encode([text])[0].tolist()


# instancia global reutilizable
embedding_model = EmbeddingModel()