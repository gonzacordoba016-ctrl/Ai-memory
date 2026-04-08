# infrastructure/vector_store.py

import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from infrastructure.embeddings import embedding_model
from core.config import VECTOR_DB_PATH, VECTOR_COLLECTION, QDRANT_URL
import uuid as uuid_lib


class VectorStore:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        if QDRANT_URL:
            qdrant_api_key = os.getenv("QDRANT_API_KEY") or None
            self.client = QdrantClient(url=QDRANT_URL, api_key=qdrant_api_key)
        else:
            self.client = QdrantClient(path=VECTOR_DB_PATH)
        self.collection = VECTOR_COLLECTION
        self._init_collection()
        self._initialized = True

    def _init_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def store(self, text: str, metadata: dict = {}):
        vector = embedding_model.embed(text)
        point  = PointStruct(
            id=str(uuid_lib.uuid4()),
            vector=vector,
            payload={"text": text, **metadata}
        )
        self.client.upsert(collection_name=self.collection, points=[point])

    def search(self, query: str, top_k: int = 5) -> list[dict]:
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
        self.client.delete_collection(self.collection)
        self._init_collection()


vector_store = VectorStore()