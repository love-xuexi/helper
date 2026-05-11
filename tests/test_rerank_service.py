from langchain_core.documents import Document

from app.services.rag_retrieval_service import RagRetrievalService
from app.services.rerank_service import LocalKeywordReranker, NvidiaRerankService


def test_local_keyword_reranker_prioritizes_query_overlap():
    documents = [
        Document(page_content="内存泄漏通常需要观察 RSS 和堆对象增长"),
        Document(page_content="CPU 使用率过高时先查看 top 进程和线程栈"),
        Document(page_content="磁盘写满需要清理日志和检查 inode"),
    ]

    reranked = LocalKeywordReranker().rerank("CPU 过高 如何 排查", documents, top_k=2)

    assert len(reranked) == 2
    assert reranked[0].page_content == "CPU 使用率过高时先查看 top 进程和线程栈"


def test_nvidia_reranker_orders_documents_by_response_index():
    documents = [
        Document(page_content="A 文档：磁盘处理流程", metadata={"source": "a"}),
        Document(page_content="B 文档：CPU 排查流程", metadata={"source": "b"}),
        Document(page_content="C 文档：内存处理流程", metadata={"source": "c"}),
    ]

    captured_payload = {}

    def fake_post_json(url, headers, payload, timeout):
        captured_payload["url"] = url
        captured_payload["headers"] = headers
        captured_payload["payload"] = payload
        captured_payload["timeout"] = timeout
        return {
            "rankings": [
                {"index": 1, "logit": 8.2},
                {"index": 2, "logit": 1.7},
                {"index": 0, "logit": -0.5},
            ]
        }

    service = NvidiaRerankService(
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
        model="nvidia/llama-3.2-nv-rerankqa-1b-v2",
        post_json=fake_post_json,
    )

    reranked = service.rerank("CPU 怎么排查", documents, top_k=2)

    assert [doc.metadata["source"] for doc in reranked] == ["b", "c"]
    assert (
        captured_payload["url"]
        == "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"
    )
    assert captured_payload["headers"]["Authorization"] == "Bearer test-key"
    assert captured_payload["payload"]["model"] == "nvidia/llama-3.2-nv-rerankqa-1b-v2"
    assert captured_payload["payload"]["query"]["text"] == "CPU 怎么排查"
    assert captured_payload["payload"]["passages"][1]["text"] == "B 文档：CPU 排查流程"


def test_nvidia_reranker_uses_hosted_endpoint_when_base_url_is_provider_root():
    captured_payload = {}

    def fake_post_json(url, headers, payload, timeout):
        captured_payload["url"] = url
        return {"rankings": [{"index": 0, "logit": 1.0}]}

    service = NvidiaRerankService(
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com",
        model="nvidia/llama-3.2-nv-rerankqa-1b-v2",
        post_json=fake_post_json,
    )

    service.rerank("CPU", [Document(page_content="CPU 排查")], top_k=1)

    assert (
        captured_payload["url"]
        == "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"
    )


def test_nvidia_reranker_keeps_explicit_ranking_endpoint():
    captured_payload = {}

    def fake_post_json(url, headers, payload, timeout):
        captured_payload["url"] = url
        return {"rankings": [{"index": 0, "logit": 1.0}]}

    service = NvidiaRerankService(
        api_key="test-key",
        base_url="http://localhost:8000/v1/ranking",
        post_json=fake_post_json,
    )

    service.rerank("CPU", [Document(page_content="CPU 排查")], top_k=1)

    assert captured_payload["url"] == "http://localhost:8000/v1/ranking"


def test_nvidia_reranker_accepts_list_response_shape():
    def fake_post_json(url, headers, payload, timeout):
        return [
            {"index": 1, "logit": 2.0},
            {"index": 0, "logit": 1.0},
        ]

    service = NvidiaRerankService(
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
        post_json=fake_post_json,
    )

    reranked = service.rerank(
        "CPU",
        [Document(page_content="磁盘"), Document(page_content="CPU")],
        top_k=2,
    )

    assert [doc.page_content for doc in reranked] == ["CPU", "磁盘"]


def test_nvidia_reranker_falls_back_when_api_fails():
    documents = [
        Document(page_content="内存泄漏通常需要观察 RSS 和堆对象增长"),
        Document(page_content="CPU 使用率过高时先查看 top 进程和线程栈"),
    ]

    def failing_post_json(url, headers, payload, timeout):
        raise RuntimeError("network failed")

    service = NvidiaRerankService(
        api_key="test-key",
        base_url="https://integrate.api.nvidia.com/v1",
        post_json=failing_post_json,
    )

    reranked = service.rerank("CPU 过高", documents, top_k=1)

    assert len(reranked) == 1
    assert reranked[0].page_content == "CPU 使用率过高时先查看 top 进程和线程栈"


def test_rag_retrieval_service_uses_candidate_recall_then_rerank():
    documents = [
        Document(page_content="A 文档"),
        Document(page_content="B 文档"),
        Document(page_content="C 文档"),
    ]

    class FakeRetriever:
        def invoke(self, query):
            return documents

    class FakeVectorStore:
        def __init__(self):
            self.search_kwargs = None

        def as_retriever(self, search_kwargs):
            self.search_kwargs = search_kwargs
            return FakeRetriever()

    class FakeVectorStoreManager:
        def __init__(self):
            self.vector_store = FakeVectorStore()

        def get_vector_store(self):
            return self.vector_store

    class FakeReranker:
        def __init__(self):
            self.received_top_k = None

        def rerank(self, query, documents, top_k):
            self.received_top_k = top_k
            return list(reversed(documents))[:top_k]

    manager = FakeVectorStoreManager()
    reranker = FakeReranker()
    service = RagRetrievalService(
        vector_store_manager=manager,
        reranker=reranker,
        candidate_top_k=20,
        final_top_k=2,
        rerank_enabled=True,
    )

    results = service.retrieve("CPU")

    assert manager.vector_store.search_kwargs == {"k": 20}
    assert reranker.received_top_k == 2
    assert [doc.page_content for doc in results] == ["C 文档", "B 文档"]
