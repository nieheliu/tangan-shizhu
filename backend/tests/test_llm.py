from app.core.config import Settings
from app.core.llm import (
    DEEPSEEK_BASE_URL,
    QWEN_BASE_URL,
    generate,
    resolve_cloud_base_url,
)

MESSAGES = [{"role": "user", "content": "解释这道菜"}]


def test_recommend_does_not_call_ollama_when_cloud_fails() -> None:
    called: list[str] = []

    def cloud(_messages: list[dict[str, str]]) -> str:
        raise TimeoutError("cloud down")

    def ollama(_messages: list[dict[str, str]]) -> str:
        called.append("ollama")
        return "local"

    try:
        generate(
            MESSAGES, purpose="recommend", cloud_complete=cloud, ollama_complete=ollama
        )
        raised = False
    except TimeoutError:
        raised = True

    assert raised
    assert called == []


def test_chat_retries_ollama_when_cloud_fails() -> None:
    called: list[str] = []

    def cloud(_messages: list[dict[str, str]]) -> str:
        called.append("cloud")
        raise TimeoutError("cloud down")

    def ollama(_messages: list[dict[str, str]]) -> str:
        called.append("ollama")
        return "local"

    text = generate(
        MESSAGES, purpose="chat", cloud_complete=cloud, ollama_complete=ollama
    )

    assert text == "local"
    assert called == ["cloud", "ollama"]


def test_provider_urls_and_model_come_from_settings(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            captured["model"] = str(kwargs["model"])
            message = type("Message", (), {"content": "ok"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["base_url"] = str(kwargs["base_url"])

        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("app.core.llm.OpenAI", FakeOpenAI)
    settings = Settings(
        llm_provider="qwen", llm_api_key="test-key", llm_model="qwen-plus"
    )

    assert (
        resolve_cloud_base_url(Settings(llm_provider="deepseek")) == DEEPSEEK_BASE_URL
    )
    assert resolve_cloud_base_url(settings) == QWEN_BASE_URL
    assert generate(MESSAGES, purpose="recommend", settings=settings) == "ok"
    assert captured["base_url"] == QWEN_BASE_URL
    assert captured["model"] == "qwen-plus"
