from typing import Any

import chromadb

from app.rag.indexer import GuidelineChunk

COLLECTION_NAME = "guidelines"


def open_client(path: str | None = None) -> Any:
    if path is None:
        return chromadb.EphemeralClient()
    return chromadb.PersistentClient(path=path)


def get_collection(client: Any) -> Any:
    return client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def upsert_chunks(
    collection: Any, chunks: list[GuidelineChunk], embeddings: list[list[float]]
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("片段数量和向量数量不一致")
    if not chunks:
        return
    collection.upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {"source": chunk.source, "page": chunk.page, "chunk_id": chunk.chunk_id}
            for chunk in chunks
        ],
        embeddings=embeddings,
    )


def get_chunk(collection: Any, chunk_id: str) -> dict[str, Any] | None:
    found = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    ids = found.get("ids") or []
    if not ids:
        return None
    metadata = (found.get("metadatas") or [{}])[0] or {}
    document = (found.get("documents") or [""])[0] or ""
    return {
        "chunk_id": ids[0],
        "source": metadata.get("source"),
        "page": metadata.get("page"),
        "text": document,
    }
