"""用本机 Ollama 的 bge-m3 生成向量。不调用对话模型。"""

from typing import Any

from openai import OpenAI

from app.core.config import Settings, get_settings

_BATCH = 8


def embedding_client(settings: Settings | None = None) -> OpenAI:
    settings = settings or get_settings()
    return OpenAI(api_key="ollama", base_url=settings.ollama_base_url, timeout=120)


def embed_texts(
    texts: list[str],
    *,
    client: Any | None = None,
    model: str | None = None,
    batch_size: int = _BATCH,
) -> list[list[float]]:
    if not texts:
        return []
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    if client is None or model is None:
        settings = get_settings()
        client = client or embedding_client(settings)
        model = model or settings.embedding_model
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(batch):
            raise RuntimeError("向量数量和文本数量不一致")
        vectors.extend(list(item.embedding) for item in ordered)
    return vectors
