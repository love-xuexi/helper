from app.services.kb_api_service import KbApiService


def test_normalize_chunks_maps_platform_fields():
    raw = [
        {
            "id": "chunk-1",
            "content": "示例内容",
            "dataset_id": "kb-1",
            "document_id": "doc-1",
            "document_keyword": "runbook.pdf",
            "similarity": 0.87,
            "term_similarity": 0.8,
            "vector_similarity": 0.9,
        }
    ]

    chunks = KbApiService._normalize_chunks(raw)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["id"] == "chunk-1"
    assert chunk["content"] == "示例内容"
    assert chunk["document_name"] == "runbook.pdf"
    assert chunk["document_id"] == "doc-1"
    assert chunk["dataset_id"] == "kb-1"
    assert chunk["similarity"] == 0.87


def test_normalize_chunks_handles_missing_fields():
    chunks = KbApiService._normalize_chunks([{}])
    assert chunks[0]["id"] == ""
    assert chunks[0]["similarity"] == 0.0


def test_normalize_chunks_handles_empty_input():
    assert KbApiService._normalize_chunks([]) == []
