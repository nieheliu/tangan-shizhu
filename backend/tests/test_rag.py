from pathlib import Path

import pytest

from app.rag.embeddings import embed_texts
from app.rag.indexer import build_chunks, chunk_text
from app.rag.ingest import fetch_chunk, ingest_pdf, reset_collection
from app.rag.retrieve import search_guidelines
from app.rag.vectorstore import get_collection, open_client


def test_chunk_ids_keep_source_and_page() -> None:
    chunks = build_chunks("guide.pdf", [(3, "糖尿病主食宜定量。")])
    assert chunks[0].chunk_id == "guide.pdf:3:0"
    assert chunks[0].source == "guide.pdf"
    assert chunks[0].page == 3


def test_chunk_text_overlaps_long_pages() -> None:
    pieces = chunk_text("甲" * 20, size=10, overlap=4)
    assert pieces[0] == "甲" * 10
    assert pieces[1][:4] == pieces[0][-4:]


def test_ingest_can_be_fetched_by_chunk_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rag.ingest.pages_from_pdf",
        lambda _path: [(1, "每天主食要定量，并搭配蔬菜。")],
    )
    collection = get_collection(open_client())

    chunks = ingest_pdf(
        Path("guide.pdf"),
        collection,
        lambda texts: [[0.1, 0.2, 0.3] for _ in texts],
    )

    found = fetch_chunk(collection, chunks[0].chunk_id)
    assert found is not None
    assert found["chunk_id"] == "guide.pdf:1:0"
    assert found["source"] == "guide.pdf"
    assert found["page"] == 1
    assert "主食" in found["text"]


def _embed(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        if "主食" in text:
            vectors.append([1.0, 0.0])
        else:
            vectors.append([0.0, 1.0])
    return vectors


def test_search_returns_chunk_id_and_page_for_the_closer_passage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.rag.ingest.pages_from_pdf",
        lambda _path: [
            (4, "每天主食要定量，碳水化合物大约 200 到 300 克。"),
            (8, "运动可以改善胰岛素敏感性。"),
        ],
    )
    collection = reset_collection(open_client())
    ingest_pdf(Path("guide.pdf"), collection, _embed)
    hits = search_guidelines("糖尿病每天主食吃多少", collection, _embed, limit=2)
    assert hits[0].chunk_id == "guide.pdf:4:0"
    assert hits[0].source == "guide.pdf"
    assert hits[0].page == 4
    assert "主食" in hits[0].text
    assert "运动" not in hits[0].text


def test_embedder_uses_bge_m3_not_the_chat_model() -> None:
    class _Item:
        def __init__(self, index: int) -> None:
            self.index = index
            self.embedding = [float(index), 1.0]

    class _Response:
        def __init__(self, count: int) -> None:
            self.data = [_Item(index) for index in range(count)]

    class _Embeddings:
        def __init__(self) -> None:
            self.models: list[str] = []

        def create(self, *, model: str, input: list[str]) -> _Response:
            self.models.append(model)
            return _Response(len(input))

    class _Client:
        def __init__(self) -> None:
            self.embeddings = _Embeddings()

    client = _Client()
    vectors = embed_texts(["甲", "乙"], client=client, model="bge-m3")
    assert client.embeddings.models == ["bge-m3"]
    assert vectors == [[0.0, 1.0], [1.0, 1.0]]
