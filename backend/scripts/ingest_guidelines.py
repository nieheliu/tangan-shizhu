"""把本机指南 PDF 写入 Chroma。PDF 不进入 Git。

在 backend 目录执行：

    .\\.venv\\Scripts\\python scripts\\ingest_guidelines.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.rag.embeddings import embed_texts
from app.rag.ingest import ingest_pdf, reset_collection
from app.rag.vectorstore import open_client

PDF_NAME = "adult-diabetes-dietary-guide-2023.pdf"


def chroma_dir() -> Path:
    configured = Path(get_settings().chroma_path)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[1] / configured


def guideline_pdf() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "raw" / PDF_NAME


def main() -> None:
    pdf = guideline_pdf()
    if not pdf.is_file():
        raise SystemExit(f"找不到 {pdf}。请把指南放在 data/raw，不要提交进 Git。")
    directory = chroma_dir()
    directory.mkdir(parents=True, exist_ok=True)
    collection = reset_collection(open_client(str(directory)))
    chunks = ingest_pdf(pdf, collection, embed_texts)
    print(f"chunks={len(chunks)} chroma={directory}")


if __name__ == "__main__":
    main()
