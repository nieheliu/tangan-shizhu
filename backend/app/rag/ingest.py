from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.rag.indexer import GuidelineChunk, build_chunks
from app.rag.loader import pages_from_pdf
from app.rag.vectorstore import (
    COLLECTION_NAME,
    get_chunk,
    get_collection,
    upsert_chunks,
)

Embedder = Callable[[list[str]], list[list[float]]]


def ingest_pdf(path: Path, collection: Any, embedder: Embedder) -> list[GuidelineChunk]:
    chunks = build_chunks(path.name, pages_from_pdf(path))
    if not chunks:
        return []
    embeddings = embedder([chunk.text for chunk in chunks])
    upsert_chunks(collection, chunks, embeddings)
    return chunks


def fetch_chunk(collection: Any, chunk_id: str) -> dict[str, Any] | None:
    return get_chunk(collection, chunk_id)


def reset_collection(client: Any) -> Any:
    names: list[str] = []
    for item in client.list_collections():
        name = item if isinstance(item, str) else getattr(item, "name", None)
        if name:
            names.append(name)
    if COLLECTION_NAME in names:
        client.delete_collection(COLLECTION_NAME)
    return get_collection(client)
