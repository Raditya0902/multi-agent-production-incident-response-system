import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./rag/chroma_db")

_client = None
_collection = None
_embedding_model = None


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name="past_incidents",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def add_documents(documents: List[dict]) -> None:
    """Add or update documents in the vector store.

    Each document dict must have: id (str), content (str), metadata (dict, optional).
    """
    collection = _get_collection()
    model = get_embedding_model()

    ids = [doc["id"] for doc in documents]
    contents = [doc["content"] for doc in documents]
    metadatas = [doc.get("metadata", {}) for doc in documents]
    embeddings = model.encode(contents).tolist()

    collection.upsert(
        ids=ids,
        documents=contents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def retrieve_context(query: str, top_k: int = 3) -> List[str]:
    """Return top_k past-incident documents most similar to the query."""
    collection = _get_collection()
    model = get_embedding_model()

    if collection.count() == 0:
        return []

    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
    )
    return results["documents"][0] if results["documents"] else []


def retrieve_context_with_scores(query: str, top_k: int = 3) -> List[tuple]:
    """Return (document, distance) tuples; distance is cosine distance (0=identical, 2=opposite)."""
    collection = _get_collection()
    model = get_embedding_model()

    if collection.count() == 0:
        return []

    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "distances"],
    )
    docs = results["documents"][0] if results["documents"] else []
    distances = results["distances"][0] if results["distances"] else []
    return list(zip(docs, distances))
