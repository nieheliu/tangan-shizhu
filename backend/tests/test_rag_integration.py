from pathlib import Path

import pytest
from openai import OpenAIError

from app.rag.embeddings import embed_texts
from app.rag.ingest import ingest_pdf, reset_collection
from app.rag.retrieve import search_guidelines
from app.rag.vectorstore import open_client
from scripts.ingest_guidelines import PDF_NAME, guideline_pdf

pytestmark = pytest.mark.integration


def test_staple_amount_question_retrieves_guideline_passages(tmp_path: Path) -> None:
    pdf = guideline_pdf()
    if not pdf.is_file():
        pytest.skip("指南 PDF 不在本机")
    try:
        embed_texts(["主食定量"])
    except (OSError, OpenAIError):
        pytest.skip("bge-m3 不可用")

    collection = reset_collection(open_client(str(tmp_path)))
    chunks = ingest_pdf(pdf, collection, embed_texts)
    assert chunks
    assert all(chunk.chunk_id and chunk.page >= 1 for chunk in chunks)
    assert pdf.name == PDF_NAME

    hits = search_guidelines("糖尿病每天主食吃多少", collection, embed_texts, limit=5)
    assert hits
    assert all(hit.chunk_id and hit.page >= 1 and hit.source == pdf.name for hit in hits)
    text = "\n".join(hit.text for hit in hits)
    assert "主食" in text
    assert any(token in text for token in ("200", "300", "1/3", "碳水化合物", "全谷物"))
