"""反馈评价服务 - 精细化反馈与评价系统.

- 点赞 / 不喜欢 两种评价
- 不喜欢时收集结构化标签（回答不准确 / 文档已过时 / 逻辑不清晰 / 未解决实际问题）+ 补充描述
- 反馈数据（原始提问、AI 回答、评价标签、详细描述、关联知识片段 ID）统一入库

存储策略：
- 本地 SQLite 兜底存储（无外部依赖，服务可独立运行）
- 若配置 FEEDBACK_API_URL，则同时转发到内网反馈入库接口（尽力而为，失败只记日志）

预留（知识库自进化闭环，后续实现）：
- LLM 初步逻辑校验与差异摘要，判断是否为有效纠错
- 高赞问答自动沉淀、知识盲区预警工单
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.config import Settings, config

# 结构化负反馈标签（前端弹窗选项与此保持一致）
FEEDBACK_TAGS = [
    "回答不准确",
    "文档已过时",
    "逻辑不清晰",
    "未解决实际问题",
    "引用来源错误",
    "其他",
]

RATING_LIKE = "like"
RATING_DISLIKE = "dislike"


class FeedbackService:
    """反馈评价服务（SQLite 本地存储 + 可选内网接口转发）."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or config
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def db_path(self) -> Path:
        return Path(self.settings.feedback_db_path)

    def initialize(self) -> None:
        """建库建表（幂等）."""
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        message_id TEXT NOT NULL DEFAULT '',
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        rating TEXT NOT NULL,
                        tags TEXT NOT NULL DEFAULT '[]',
                        comment TEXT NOT NULL DEFAULT '',
                        chunk_ids TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feedback_session
                    ON feedback (session_id, created_at)
                    """
                )
            self._initialized = True
            logger.info(f"[Feedback] 反馈数据库初始化完成: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def save_feedback(
        self,
        session_id: str,
        question: str,
        answer: str,
        rating: str,
        message_id: str = "",
        tags: list[str] | None = None,
        comment: str = "",
        chunk_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """保存一条反馈记录，返回入库后的记录."""
        if rating not in (RATING_LIKE, RATING_DISLIKE):
            raise ValueError(f"无效的评价类型: {rating}")

        self.initialize()
        record = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "message_id": message_id,
            "question": question,
            "answer": answer,
            "rating": rating,
            "tags": tags or [],
            "comment": comment,
            "chunk_ids": chunk_ids or [],
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback (
                    id, session_id, message_id, question, answer,
                    rating, tags, comment, chunk_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["session_id"],
                    record["message_id"],
                    record["question"],
                    record["answer"],
                    record["rating"],
                    json.dumps(record["tags"], ensure_ascii=False),
                    record["comment"],
                    json.dumps(record["chunk_ids"], ensure_ascii=False),
                    record["created_at"],
                ),
            )
        logger.info(
            f"[Feedback] 反馈已入库: session={session_id}, rating={rating}, tags={record['tags']}"
        )
        return record

    async def forward_feedback(self, record: dict[str, Any]) -> None:
        """转发反馈到内网入库接口（配置了 FEEDBACK_API_URL 时生效）."""
        url = self.settings.feedback_api_url
        if not url:
            return
        try:
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.settings.kb_api_token}"},
                timeout=self.settings.kb_timeout_seconds,
            ) as client:
                response = await client.post(url, json=record)
                response.raise_for_status()
                logger.info(f"[Feedback] 反馈已转发到内网接口: {record['id']}")
        except Exception as e:
            logger.warning(f"[Feedback] 反馈转发失败（本地已入库）: {e}")

    def list_feedback(self, limit: int = 100, rating: str | None = None) -> list[dict[str, Any]]:
        """查询反馈记录（供后台审核 / 知识修正使用）."""
        self.initialize()
        sql = (
            "SELECT id, session_id, message_id, question, answer, rating, tags, comment, "
            "chunk_ids, created_at FROM feedback"
        )
        params: list[Any] = []
        if rating:
            sql += " WHERE rating = ?"
            params.append(rating)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "message_id": row[2],
                "question": row[3],
                "answer": row[4],
                "rating": row[5],
                "tags": json.loads(row[6]),
                "comment": row[7],
                "chunk_ids": json.loads(row[8]),
                "created_at": row[9],
            }
            for row in rows
        ]

    def get_stats(self) -> dict[str, int]:
        """反馈统计（点赞/不喜欢数量），供后续知识盲区预警使用."""
        self.initialize()
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating").fetchall()
        stats = {RATING_LIKE: 0, RATING_DISLIKE: 0}
        for rating, count in rows:
            stats[rating] = count
        return stats


feedback_service = FeedbackService()
