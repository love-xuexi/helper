from app.services.embedding_input_guard import (
    compress_query_for_embedding,
    estimate_tokens,
    truncate_to_token_budget,
)


def test_compress_query_keeps_high_signal_incident_details_within_budget():
    long_context = "无关背景说明" * 700
    query = (
        f"{long_context}\n"
        "服务 order-api 在 10:30 开始出现 CPU 99%，日志包含 timeout，"
        "HTTP 503 service unavailable，错误码 E5002，请检索相关排查方案。"
    )

    compressed = compress_query_for_embedding(query, max_tokens=120)

    assert estimate_tokens(compressed) <= 120
    assert "order-api" in compressed
    assert "CPU" in compressed
    assert "timeout" in compressed
    assert "503" in compressed
    assert "E5002" in compressed


def test_compress_query_falls_back_to_tail_when_text_has_no_high_signal_parts():
    prefix = "早期上下文" * 500
    tail = "最后的问题需要被保留下来"
    query = f"{prefix}{tail}"

    compressed = compress_query_for_embedding(query, max_tokens=40)

    assert estimate_tokens(compressed) <= 40
    assert compressed.endswith(tail)


def test_truncate_to_token_budget_keeps_tail_by_default():
    text = "A" * 300 + "重要结尾"

    truncated = truncate_to_token_budget(text, max_tokens=30)

    assert estimate_tokens(truncated) <= 30
    assert truncated.endswith("重要结尾")


def test_estimate_tokens_is_conservative_for_long_ascii_sequences():
    assert estimate_tokens("A" * 600) >= 600
