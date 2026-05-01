#!/bin/bash
set -e

echo "Ingesting RAG documents into ChromaDB..."
python -m rag.ingestion

echo "Starting Streamlit on port 8501..."
exec streamlit run frontend/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none
