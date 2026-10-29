from pathlib import Path

from app.rag.indexer import build_chunks, chunk_text
from app.rag.ingest import fetch_chunk, ingest_pdf
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
