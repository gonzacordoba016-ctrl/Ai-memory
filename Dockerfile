FROM python:3.11-slim

WORKDIR /app

# Deps de sistema para sentence-transformers y compilación de paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-instalar PyTorch versión CPU para evitar descargar 2.5GB de binarios CUDA (que causa timeouts en la nube)
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Instalar dependencias Python (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar el modelo de embeddings durante el build (evita cold-start lento)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copiar código fuente
COPY . .

# Crear directorios necesarios
RUN mkdir -p database memory_db agent_files/knowledge agent_files/firmware api/static tools/plugins

EXPOSE 8000

# Railway inyecta PORT como variable de entorno
CMD ["python", "run.py", "serve", "--no-reload"]
