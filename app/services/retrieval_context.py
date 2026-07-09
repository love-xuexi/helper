"""检索上下文 - 记录一次问答过程中命中的知识片段.

Agent 在回答过程中可能调用 retrieve_knowledge 工具，
工具命中的知识片段需要随答案一起返回给前端（引用来源展示、反馈入库关联 chunk ID）。

通过 contextvars 传递：查询开始时 begin()，工具内 record()，查询结束后 collect()。
async 任务会继承创建时的 context，因此 LangGraph 的工具节点也能拿到同一份列表。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_retrieved_chunks: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "retrieved_chunks", default=None
)


def begin() -> None:
    """开始一次问答，重置片段列表."""
    _retrieved_chunks.set([])


def record(chunks: list[dict[str, Any]]) -> None:
    """记录本次问答命中的知识片段（工具内调用）."""
    bucket = _retrieved_chunks.get()
    if bucket is not None:
        bucket.extend(chunks)


def collect() -> list[dict[str, Any]]:
    """获取本次问答命中的全部知识片段."""
    return list(_retrieved_chunks.get() or [])
