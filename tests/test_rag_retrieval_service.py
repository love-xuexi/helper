from langchain_core.documents import Document

from app.config import config
from app.services.embedding_input_guard import estimate_tokens
from app.services.rag_retrieval_service import RagRetrievalService


class FakeRetriever:
    def __init__(self):
        self.query = None

    def invoke(self, query):
        self.query = query
        return [Document(page_content="CPU 排查文档")]


class FakeVectorStore:
    def __init__(self, retriever):
        self.retriever = retriever
        self.search_kwargs = None

    def as_retriever(self, search_kwargs):
        self.search_kwargs = search_kwargs
        return self.retriever


class FakeVectorStoreManager:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def get_vector_store(self):
        return self.vector_store


class FakeReranker:
    def __init__(self):
        self.query = None

    def rerank(self, query, documents, top_k):
        self.query = query
        return documents[:top_k]


def test_rag_retrieval_uses_compressed_query_for_vector_recall_and_rerank(monkeypatch):
    monkeypatch.setattr(config, "embedding_max_tokens", 512)
    monkeypatch.setattr(config, "embedding_token_safety_margin", 32)
    retriever = FakeRetriever()
    vector_store = FakeVectorStore(retriever)
    reranker = FakeReranker()
    service = RagRetrievalService(
        vector_store_manager=FakeVectorStoreManager(vector_store),
        reranker=reranker,
        candidate_top_k=5,
        final_top_k=1,
        rerank_enabled=True,
    )
    long_query = (
        "普通上下文" * 800
        + " 服务 order-api CPU 99% timeout HTTP 503 service unavailable 错误码 E5002"
    )

    docs = service.retrieve(long_query)

    assert [doc.page_content for doc in docs] == ["CPU 排查文档"]
    assert retriever.query == reranker.query
    assert retriever.query != long_query
    assert estimate_tokens(retriever.query) <= 480
    assert "order-api" in retriever.query
    assert "CPU" in retriever.query
    assert "503" in retriever.query
