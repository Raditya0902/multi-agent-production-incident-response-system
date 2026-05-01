"""
Ingest past incident markdown files into ChromaDB.
Run once before starting the system:  python -m rag.ingestion
Safe to re-run — uses upsert semantics.
"""
import os
import glob

from rag.vectorstore import add_documents, CHROMA_PERSIST_DIR

INCIDENTS_DIR = os.path.join(os.path.dirname(__file__), "past_incidents")


def ingest_past_incidents(incidents_dir: str = INCIDENTS_DIR) -> int:
    pattern = os.path.join(incidents_dir, "*.md")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No markdown files found in {incidents_dir}")
        return 0

    documents = []
    for filepath in files:
        doc_id = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        documents.append({
            "id": doc_id,
            "content": content,
            "metadata": {"source": os.path.basename(filepath)},
        })

    add_documents(documents)
    return len(documents)


if __name__ == "__main__":
    count = ingest_past_incidents()
    print(f"Ingested {count} documents into ChromaDB at {CHROMA_PERSIST_DIR}")
