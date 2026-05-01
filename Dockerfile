FROM python:3.11-slim

WORKDIR /app

# System deps needed to build some Python packages (e.g. chromadb, torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first (much smaller than the GPU default)
RUN pip install --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (respects .dockerignore)
COPY . .

# Create persistent-data directories so volumes mount cleanly
RUN mkdir -p rag/chroma_db data_storage

EXPOSE 8501

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
