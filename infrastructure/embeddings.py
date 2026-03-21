# infrastructure/embeddings.py

from sentence_transformers import SentenceTransformer
from core.config import EMBEDDING_MODEL


class EmbeddingModel:

    def __init__(self):
        self.model = SentenceTransformer(EMBEDDING_MODEL)

    def embed(self, text: str) -> list[float]:
        if isinstance(text, list):
            return self.model.encode(text).tolist()
        return self.model.encode([text])[0].tolist()


# instancia global reutilizable
embedding_model = EmbeddingModel()