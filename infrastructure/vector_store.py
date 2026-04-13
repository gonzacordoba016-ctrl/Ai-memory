# infrastructure/vector_store.py
#
# VectorStore usa lazy initialization: QdrantClient se crea en el primer
# store()/search(), NO al importar el módulo. Esto evita que qdrant-client
# (y su inicialización de storage embebido) bloquee el startup de uvicorn.

import os
import logging
from infrastructure.embeddings import embedding_model
from core.config import VECTOR_DB_PATH, VECTOR_COLLECTION, QDRANT_URL
import uuid as uuid_lib

logger = logging.getLogger(__name__)


class VectorStore:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._connect_attempted = False
            cls._instance.client = None
        return cls._instance

    def __init__(self):
        # Lightweight init — no conectar a Qdrant aquí.
        # La conexión se hace en _ensure_connected() al primer uso.
        if not hasattr(self, 'collection'):
            self.collection = VECTOR_COLLECTION

    def _ensure_connected(self):
        """Conecta a Qdrant la primera vez que se necesita (lazy)."""
        if self._connect_attempted:
            return
        self._connect_attempted = True
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            if QDRANT_URL:
                qdrant_api_key = os.getenv("QDRANT_API_KEY") or None
                self.client = QdrantClient(url=QDRANT_URL, api_key=qdrant_api_key)
            else:
                os.makedirs(VECTOR_DB_PATH, exist_ok=True)
                self.client = QdrantClient(path=VECTOR_DB_PATH)
            self._init_collection()
            self._initialized = True
            logger.info(f"[VectorStore] Qdrant inicializado | path={VECTOR_DB_PATH or QDRANT_URL}")
        except Exception as e:
            logger.warning(f"[VectorStore] No se pudo inicializar Qdrant: {e}. Búsqueda vectorial deshabilitada.")
            self._initialized = False

    def _init_collection(self):
        from qdrant_client.models import Distance, VectorParams
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def store(self, text: str, metadata: dict = {}):
        self._ensure_connected()
        if not self.client:
            return
        from qdrant_client.models import PointStruct
        vector = embedding_model.embed(text)
        point  = PointStruct(
            id=str(uuid_lib.uuid4()),
            vector=vector,
            payload={"text": text, **metadata}
        )
        self.client.upsert(collection_name=self.collection, points=[point])

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        self._ensure_connected()
        if not self.client:
            return []
        vector  = embedding_model.embed(query)
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        output = []
        for r in results:
            payload = dict(r.payload or {})
            text    = payload.pop("text", "")
            output.append({
                "text":     text,
                "score":    r.score,
                "metadata": payload,
            })
        return output

    def clear(self):
        """Borra y recrea la colección. Úsalo solo en tests."""
        self._ensure_connected()
        if self.client:
            self.client.delete_collection(self.collection)
            self._init_collection()


vector_store = VectorStore()