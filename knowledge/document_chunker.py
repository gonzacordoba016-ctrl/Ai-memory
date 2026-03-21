# knowledge/document_chunker.py


def chunk_text(text, chunk_size=500, overlap=50):

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def chunk_documents(documents):

    all_chunks = []

    for doc in documents:

        text = doc["content"]
        source = doc["source"]

        chunks = chunk_text(text)

        for chunk in chunks:

            all_chunks.append({
                "source": source,
                "content": chunk
            })

    return all_chunks