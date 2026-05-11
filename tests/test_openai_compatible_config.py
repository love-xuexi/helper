import pytest
from langchain_core.documents import Document

from app.config import Settings
from app.core.llm_factory import LLMFactory
from app.services.embedding_input_guard import estimate_tokens
from app.services.rerank_service import RerankProvider, RerankService
from app.services.vector_embedding_service import OpenAICompatibleEmbeddings


def make_settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_settings_support_independent_openai_compatible_model_configs():
    settings = make_settings(
        chat_api_key="chat-key",
        chat_base_url="https://chat.example.com/v1",
        chat_model="chat-model",
        embedding_api_key="embedding-key",
        embedding_base_url="https://embedding.example.com/v1",
        embedding_model="embedding-model",
        embedding_dimensions=768,
        rerank_api_key="rerank-key",
        rerank_base_url="https://rerank.example.com/v1",
        rerank_model="rerank-model",
        rerank_provider="openai_compatible",
    )

    assert settings.chat_api_key == "chat-key"
    assert settings.chat_base_url == "https://chat.example.com/v1"
    assert settings.chat_model == "chat-model"
    assert settings.embedding_api_key == "embedding-key"
    assert settings.embedding_base_url == "https://embedding.example.com/v1"
    assert settings.embedding_model == "embedding-model"
    assert settings.embedding_dimensions == 768
    assert settings.rerank_api_key == "rerank-key"
    assert settings.rerank_base_url == "https://rerank.example.com/v1"
    assert settings.rerank_model == "rerank-model"
    assert settings.rerank_provider == "openai_compatible"


def test_settings_keep_legacy_dashscope_values_as_chat_and_embedding_fallbacks():
    settings = make_settings(
        dashscope_api_key="legacy-key",
        dashscope_api_base="https://legacy.example.com/v1",
        dashscope_model="legacy-chat-model",
        dashscope_embedding_model="legacy-embedding-model",
    )

    assert settings.effective_chat_api_key == "legacy-key"
    assert settings.effective_chat_base_url == "https://legacy.example.com/v1"
    assert settings.effective_chat_model == "legacy-chat-model"
    assert settings.effective_embedding_api_key == "legacy-key"
    assert settings.effective_embedding_base_url == "https://legacy.example.com/v1"
    assert settings.effective_embedding_model == "legacy-embedding-model"


def test_llm_factory_uses_default_chat_config_from_settings():
    settings = make_settings(
        chat_api_key="chat-key",
        chat_base_url="https://chat.example.com/v1",
        chat_model="chat-model",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert llm.model_name == "chat-model"
    assert str(llm.openai_api_base).rstrip("/") == "https://chat.example.com/v1"
    assert llm.openai_api_key.get_secret_value() == "chat-key"


def test_embedding_service_uses_independent_base_url_and_key():
    captured_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    embeddings = OpenAICompatibleEmbeddings(
        api_key="embedding-key",
        base_url="https://embedding.example.com/v1",
        model="embedding-model",
        dimensions=768,
        client_factory=FakeOpenAI,
    )

    assert captured_kwargs == {
        "api_key": "embedding-key",
        "base_url": "https://embedding.example.com/v1",
    }
    assert embeddings.model == "embedding-model"
    assert embeddings.dimensions == 768


def test_embedding_service_compresses_long_query_before_api_call():
    captured_request = {}

    class FakeEmbeddingsClient:
        def create(self, **kwargs):
            captured_request.update(kwargs)

            class Response:
                data = [type("EmbeddingItem", (), {"embedding": [0.1, 0.2]})()]

            return Response()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddingsClient()

    embeddings = OpenAICompatibleEmbeddings(
        api_key="embedding-key",
        base_url="https://embedding.example.com/v1",
        model="embedding-model",
        dimensions=2,
        max_tokens=80,
        token_safety_margin=10,
        client_factory=FakeOpenAI,
    )
    long_query = (
        "普通上下文" * 500
        + " 服务 order-api CPU 99% timeout HTTP 503 service unavailable 错误码 E5002"
    )

    result = embeddings.embed_query(long_query)

    assert result == [0.1, 0.2]
    assert len(captured_request["input"]) < len(long_query)
    assert "order-api" in captured_request["input"]
    assert "CPU" in captured_request["input"]
    assert "503" in captured_request["input"]


def test_embedding_service_sends_document_embeddings_one_at_a_time_under_token_limit():
    captured_inputs = []

    class FakeEmbeddingsClient:
        def create(self, **kwargs):
            captured_inputs.append(kwargs["input"])

            class Response:
                data = [type("EmbeddingItem", (), {"embedding": [float(len(captured_inputs))]})()]

            return Response()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddingsClient()

    embeddings = OpenAICompatibleEmbeddings(
        api_key="embedding-key",
        base_url="https://embedding.example.com/v1",
        model="embedding-model",
        dimensions=1,
        max_tokens=64,
        token_safety_margin=8,
        client_factory=FakeOpenAI,
    )
    texts = ["CPU 使用率持续 99%，服务 order-api timeout HTTP 503。"] * 3

    result = embeddings.embed_documents(texts)

    assert result == [[1.0], [2.0], [3.0]]
    assert len(captured_inputs) == len(texts)
    assert all(isinstance(input_text, str) for input_text in captured_inputs)
    assert all(estimate_tokens(input_text) <= 56 for input_text in captured_inputs)


def test_embedding_service_rejects_oversized_document_text_without_truncating():
    captured_inputs = []

    class FakeEmbeddingsClient:
        def create(self, **kwargs):
            captured_inputs.append(kwargs["input"])

            class Response:
                data = [type("EmbeddingItem", (), {"embedding": [0.1]})()]

            return Response()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddingsClient()

    embeddings = OpenAICompatibleEmbeddings(
        api_key="embedding-key",
        base_url="https://embedding.example.com/v1",
        model="embedding-model",
        dimensions=1,
        max_tokens=64,
        token_safety_margin=8,
        client_factory=FakeOpenAI,
    )

    with pytest.raises(ValueError, match="文档片段超过 Embedding token 预算"):
        embeddings.embed_documents(["CPU 使用率持续 99%，服务 order-api timeout HTTP 503。" * 20])

    assert captured_inputs == []


def test_rerank_service_openai_compatible_provider_uses_generic_rerank_endpoint():
    captured_payload = {}

    def fake_post_json(url, headers, payload, timeout):
        captured_payload["url"] = url
        captured_payload["headers"] = headers
        captured_payload["payload"] = payload
        captured_payload["timeout"] = timeout
        return {"results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}]}

    service = RerankService(
        api_key="rerank-key",
        base_url="https://rerank.example.com/v1",
        model="rerank-model",
        provider=RerankProvider.OPENAI_COMPATIBLE,
        post_json=fake_post_json,
    )

    documents = [
        Document(page_content="磁盘"),
        Document(page_content="CPU"),
    ]
    reranked = service.rerank("CPU", documents, top_k=2)

    assert captured_payload["url"] == "https://rerank.example.com/v1/rerank"
    assert captured_payload["headers"]["Authorization"] == "Bearer rerank-key"
    assert captured_payload["payload"] == {
        "model": "rerank-model",
        "query": "CPU",
        "documents": ["磁盘", "CPU"],
        "top_n": 2,
    }
    assert [doc.page_content for doc in reranked] == ["CPU", "磁盘"]
