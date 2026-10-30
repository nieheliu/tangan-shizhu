"""从指南索引里取片段。结果带 chunk_id、文件名和页码。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    page: int
    text: str


def retrieve(
    collection: Any,
    embedding: list[float],
    *,
    limit: int = 5,
) -> tuple[RetrievedChunk, ...]:
    if limit <= 0:
        return ()
    count = int(collection.count())
    if count == 0:
        return ()
    found = collection.query(
        query_embeddings=[embedding],
        n_results=min(limit, count),
        include=["documents", "metadatas"],
    )
    ids = (found.get("ids") or [[]])[0]
    documents = (found.get("documents") or [[]])[0]
    metadatas = (found.get("metadatas") or [[]])[0]
    rows: list[RetrievedChunk] = []
    for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=False):
        meta = metadata or {}
        page = meta.get("page")
        rows.append(
            RetrievedChunk(
                chunk_id=str(meta.get("chunk_id") or chunk_id),
                source=str(meta.get("source") or ""),
                page=int(page) if page is not None else 0,
                text=document or "",
            )
        )
    return tuple(rows)


def search_guidelines(
    question: str,
    collection: Any,
    embedder: Embedder,
    *,
    limit: int = 5,
) -> tuple[RetrievedChunk, ...]:
    vectors = embedder([question])
    if len(vectors) != 1:
        raise ValueError("问题只能对应一条向量")
    return retrieve(collection, vectors[0], limit=limit)
