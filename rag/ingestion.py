"""
Ingest past incident markdown files into ChromaDB.
Run once before starting the system:  python -m rag.ingestion
Safe to re-run — uses upsert semantics (same filename = same doc ID, won't re-ingest).
"""
import os
import glob

from rag.vectorstore import add_documents, CHROMA_PERSIST_DIR

INCIDENTS_DIR = os.path.join(os.path.dirname(__file__), "past_incidents")
REAL_INCIDENTS_DIR = os.path.join(INCIDENTS_DIR, "real")


def _load_docs_from_dir(directory: str, prefix: str = "") -> list[dict]:
    """Load all .md files from a directory as document dicts."""
    pattern = os.path.join(directory, "*.md")
    files = sorted(glob.glob(pattern))
    docs = []
    for filepath in files:
        stem = os.path.splitext(os.path.basename(filepath))[0]
        doc_id = f"{prefix}{stem}" if prefix else stem
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        docs.append({
            "id": doc_id,
            "content": content,
            "metadata": {"source": os.path.basename(filepath), "type": prefix or "synthetic"},
        })
    return docs


def ingest_past_incidents(incidents_dir: str = INCIDENTS_DIR) -> int:
    synthetic_docs = _load_docs_from_dir(incidents_dir)

    real_dir = os.path.join(incidents_dir, "real")
    real_docs = _load_docs_from_dir(real_dir, prefix="real_") if os.path.isdir(real_dir) else []

    all_docs = synthetic_docs + real_docs

    if not all_docs:
        print(f"No markdown files found in {incidents_dir}")
        return 0

    add_documents(all_docs)
    print(
        f"Ingested {len(synthetic_docs)} synthetic + {len(real_docs)} real documents "
        f"({len(all_docs)} total)"
    )
    return len(all_docs)


if __name__ == "__main__":
    count = ingest_past_incidents()
    print(f"Total documents in ChromaDB at {CHROMA_PERSIST_DIR}: {count}")
