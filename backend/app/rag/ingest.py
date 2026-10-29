from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.rag.indexer import GuidelineChunk, build_chunks
from app.rag.loader import pages_from_pdf
from app.rag.vectorstore import get_chunk, upsert_chunks

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
