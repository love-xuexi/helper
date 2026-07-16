from app.config import config
from app.services.document_splitter_service import DocumentSplitterService
from app.services.embedding_input_guard import estimate_tokens


def test_markdown_splitter_keeps_each_document_chunk_within_embedding_token_budget():
    splitter = DocumentSplitterService()
    content = (
        "# CPU 故障处理\n\n" + "服务 CPU 使用率过高，需要排查日志、指标、线程池和下游依赖。" * 200
    )
    budget = max(1, config.embedding_max_tokens - config.embedding_token_safety_margin)

    documents = splitter.split_markdown(content, "aiops-docs/cpu_high_usage.md")

    assert documents
    assert all(estimate_tokens(document.page_content) <= budget for document in documents)
    assert "服务 CPU 使用率过高" in "".join(document.page_content for document in documents)
