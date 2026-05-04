FROM python:3.11.9-slim

WORKDIR /app

# Deps de sistema para sentence-transformers y compilación de paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Fijar la ruta del cache de HuggingFace a una ruta determinista.
# Esto garantiza que el modelo descargado en el build sea encontrado en runtime,
# independientemente de la variable HOME que Railway pueda inyectar.
ENV HF_HOME=/app/.cache/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers

# Instalar dependencias Python.
# --index-url (primario) = CPU wheel index → garantiza torch CPU, no CUDA.
# --extra-index-url PyPI = fallback para todos los paquetes que no están en el CPU index.
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    -r requirements.txt

# Pre-descargar el modelo de embeddings durante el build (evita cold-start lento).
# || true → no falla el build si hay problema de red; el modelo se descarga al primer embed().
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" || echo "WARNING: model download failed, will download on first embed()"

# Copiar código fuente
COPY . .

# Crear directorios necesarios
RUN mkdir -p database memory_db agent_files/knowledge agent_files/firmware api/static tools/plugins

EXPOSE 8000

RUN adduser --disabled-password --gecos "" appuser
USER appuser

# Railway inyecta PORT como variable de entorno
CMD ["python", "run.py", "serve", "--no-reload"]
