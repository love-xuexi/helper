"""反馈评价服务 - SQLite 存储 + 可选外部推送

功能：
1. 存储用户对 AI 回答的点赞/不喜欢评价
2. 收集结构化负反馈（回答不准确/文档已过时/逻辑不清晰/未解决实际问题 + 详细描述）
3. 关联知识片段 ID，便于后续追溯
4. 可选推送至外部 API（配置 FEEDBACK_EXTERNAL_API_URL）

数据表 feedback:
  id, session_id, message_id, question, answer, rating,
  feedback_tags (JSON), feedback_description, chunk_ids (JSON),
  created_at, updated_at
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from app.config import config


# 预设的负反馈选项
NEGATIVE_FEEDBACK_TAGS = [
    "回答不准确",
    "文档已过时",
    "逻辑不清晰",
    "未解决实际问题",
    "信息不完整",
    "引用来源错误",
]


class FeedbackStore:
    """SQLite 反馈数据存储"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        """创建数据库表（幂等）。"""
        if self._initialized:
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    rating TEXT NOT NULL CHECK(rating IN ('like', 'dislike')),
                    feedback_tags TEXT NOT NULL DEFAULT '[]',
                    feedback_description TEXT NOT NULL DEFAULT '',
                    chunk_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC)"
            )
        self._initialized = True
        logger.info(f"[FeedbackStore] 数据库初始化完成: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def submit_feedback(
        self,
        session_id: str,
        message_id: str,
        rating: str,
        question: str = "",
        answer: str = "",
        feedback_tags: list[str] | None = None,
        feedback_description: str = "",
        chunk_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """提交一条反馈。"""
        if rating not in ("like", "dislike"):
            raise ValueError("rating 必须是 'like' 或 'dislike'")

        now = datetime.now().isoformat()
        tags_json = json.dumps(feedback_tags or [], ensure_ascii=False)
        chunks_json = json.dumps(chunk_ids or [], ensure_ascii=False)

        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feedback (
                    session_id, message_id, question, answer, rating,
                    feedback_tags, feedback_description, chunk_ids,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, message_id, question, answer, rating,
                    tags_json, feedback_description, chunks_json,
                    now, now,
                ),
            )
            feedback_id = cursor.lastrowid
            conn.commit()

        logger.info(f"[FeedbackStore] 反馈已存储: id={feedback_id}, rating={rating}, message_id={message_id}")
        return self.get_feedback(feedback_id)

    def get_feedback(self, feedback_id: int) -> dict[str, Any] | None:
        """获取单条反馈。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM feedback WHERE id = ?", (feedback_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_feedback(
        self,
        limit: int = 50,
        offset: int = 0,
        rating: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出反馈（按时间倒序）。"""
        query = "SELECT * FROM feedback"
        params: list[Any] = []
        if rating:
            query += " WHERE rating = ?"
            params.append(rating)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_feedback_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """根据 message_id 获取反馈（用于前端查已评价状态）。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM feedback WHERE message_id = ? ORDER BY id DESC LIMIT 1",
                (message_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_stats(self) -> dict[str, Any]:
        """获取反馈统计。"""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            likes = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='like'").fetchone()[0]
            dislikes = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='dislike'").fetchone()[0]

            # 统计负反馈标签分布
            tag_counts: dict[str, int] = {}
            dislike_rows = conn.execute(
                "SELECT feedback_tags FROM feedback WHERE rating='dislike'"
            ).fetchall()
            for row in dislike_rows:
                tags = json.loads(row["feedback_tags"])
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "total": total,
            "likes": likes,
            "dislikes": dislikes,
            "like_rate": round(likes / total, 4) if total > 0 else 0.0,
            "tag_distribution": tag_counts,
        }

    def delete_feedback(self, feedback_id: int) -> bool:
        """删除一条反馈。"""
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "message_id": row["message_id"],
            "question": row["question"],
            "answer": row["answer"],
            "rating": row["rating"],
            "feedback_tags": json.loads(row["feedback_tags"]),
            "feedback_description": row["feedback_description"],
            "chunk_ids": json.loads(row["chunk_ids"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class FeedbackService:
    """反馈评价服务 - 存储管理 + 可选外部推送"""

    def __init__(self) -> None:
        self.store = FeedbackStore(config.feedback_db_path)

    def initialize(self) -> None:
        self.store.initialize()

    async def submit_feedback(
        self,
        session_id: str,
        message_id: str,
        rating: str,
        question: str = "",
        answer: str = "",
        feedback_tags: list[str] | None = None,
        feedback_description: str = "",
        chunk_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """提交反馈并（可选）推送到外部 API。"""
        result = self.store.submit_feedback(
            session_id=session_id,
            message_id=message_id,
            rating=rating,
            question=question,
            answer=answer,
            feedback_tags=feedback_tags,
            feedback_description=feedback_description,
            chunk_ids=chunk_ids,
        )

        # 可选：推送到外部 API
        await self._push_to_external(result)

        return result

    def get_feedback(self, feedback_id: int) -> dict[str, Any] | None:
        return self.store.get_feedback(feedback_id)

    def get_feedback_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        return self.store.get_feedback_by_message_id(message_id)

    def list_feedback(
        self, limit: int = 50, offset: int = 0, rating: str | None = None
    ) -> list[dict[str, Any]]:
        return self.store.list_feedback(limit=limit, offset=offset, rating=rating)

    def get_stats(self) -> dict[str, Any]:
        return self.store.get_stats()

    async def _push_to_external(self, feedback: dict[str, Any]) -> None:
        """如果配置了外部 API，推送反馈数据。"""
        url = config.feedback_external_api_url.strip()
        if not url:
            return

        token = config.feedback_external_api_token.strip()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=feedback, headers=headers)
                if response.status_code < 400:
                    logger.info(f"[FeedbackService] 反馈已推送至外部 API: {url}")
                else:
                    logger.warning(
                        f"[FeedbackService] 外部 API 推送失败: HTTP {response.status_code}, {response.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"[FeedbackService] 外部 API 推送异常: {e}")


# 全局单例
feedback_service = FeedbackService()
