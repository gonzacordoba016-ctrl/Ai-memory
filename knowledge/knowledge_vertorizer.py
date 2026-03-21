# knowledge/knowledge_vectorizer.py

from infrastructure.embeddings import embedding_model
from infrastructure.vector_store import vector_store


def index_chunks(chunks):

    for chunk in chunks:

        text = chunk["content"]

        metadata = {
            "type": "knowledge",
            "source": chunk["source"]
        }

        vector_store.add_text(text, metadata)


def search_knowledge(query, limit=5):

    results = vector_store.search(query, limit)

    return results