"""Bug 上报服务 - SQLite 存储

功能：
1. 存储用户上报的 Bug（分类、标题、描述、附件）
2. 关联会话 ID、当时的用户问题和 AI 回答，便于追溯
3. 支持 Bug 状态管理（待处理/处理中/已解决/已关闭）
4. 提供统计信息（总数、各状态数量）

数据表 bugs:
  id, reporter, category, title, content, session_id, query, answer,
  status, attachment_path, created_at, updated_at
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import config


# 预设的 Bug 分类
BUG_CATEGORIES = [
    "检索问题",
    "生成问题",
    "模型配置问题",
    "其他",
]

# 预设的 Bug 状态
BUG_STATUSES = [
    "待处理",
    "处理中",
    "已解决",
    "已关闭",
]


class BugStore:
    """SQLite Bug 数据存储"""

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
                CREATE TABLE IF NOT EXISTS bugs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter TEXT NOT NULL DEFAULT 'anonymous',
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    query TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '待处理',
                    attachment_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bugs_category ON bugs(category)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bugs_session ON bugs(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bugs_created ON bugs(created_at DESC)"
            )
        self._initialized = True
        logger.info(f"[BugStore] 数据库初始化完成: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_bug(
        self,
        reporter: str,
        category: str,
        title: str,
        content: str,
        session_id: str = "",
        query: str = "",
        answer: str = "",
        attachment_path: str = "",
    ) -> dict[str, Any]:
        """创建一条 Bug 记录。"""
        now = datetime.now().isoformat()
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO bugs (
                    reporter, category, title, content,
                    session_id, query, answer, status, attachment_path,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reporter or "anonymous", category, title, content,
                    session_id, query, answer, "待处理", attachment_path,
                    now, now,
                ),
            )
            bug_id = cursor.lastrowid
            conn.commit()

        logger.info(f"[BugStore] Bug 已存储: id={bug_id}, category={category}, title={title}")
        return self.get_bug(bug_id)

    def get_bug(self, bug_id: int) -> dict[str, Any] | None:
        """获取单条 Bug。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM bugs WHERE id = ?", (bug_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_bugs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出 Bug（按时间倒序）。"""
        query = "SELECT * FROM bugs WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count_bugs(
        self,
        status: str | None = None,
        category: str | None = None,
    ) -> int:
        """统计 Bug 总数（可按状态/分类过滤）。"""
        query = "SELECT COUNT(*) FROM bugs WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        with self._get_conn() as conn:
            return conn.execute(query, params).fetchone()[0]

    def update_status(self, bug_id: int, status: str) -> dict[str, Any] | None:
        """更新 Bug 状态。"""
        if status not in BUG_STATUSES:
            raise ValueError(f"status 必须是以下之一: {', '.join(BUG_STATUSES)}")
        now = datetime.now().isoformat()
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE bugs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, bug_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self.get_bug(bug_id)

    def get_stats(self) -> dict[str, Any]:
        """获取 Bug 统计数据。"""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM bugs").fetchone()[0]
            status_counts: dict[str, int] = {}
            for s in BUG_STATUSES:
                status_counts[s] = conn.execute(
                    "SELECT COUNT(*) FROM bugs WHERE status = ?", (s,)
                ).fetchone()[0]
            category_counts: dict[str, int] = {}
            for c in BUG_CATEGORIES:
                category_counts[c] = conn.execute(
                    "SELECT COUNT(*) FROM bugs WHERE category = ?", (c,)
                ).fetchone()[0]
        return {
            "total": total,
            "status_distribution": status_counts,
            "category_distribution": category_counts,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "reporter": row["reporter"],
            "category": row["category"],
            "title": row["title"],
            "content": row["content"],
            "session_id": row["session_id"],
            "query": row["query"],
            "answer": row["answer"],
            "status": row["status"],
            "attachment_path": row["attachment_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class BugService:
    """Bug 上报服务"""

    def __init__(self) -> None:
        self.store = BugStore(config.bug_db_path)
        self.upload_dir = Path(config.bug_upload_dir)

    def initialize(self) -> None:
        self.store.initialize()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def report_bug(
        self,
        reporter: str,
        category: str,
        title: str,
        content: str,
        session_id: str = "",
        query: str = "",
        answer: str = "",
        attachment_path: str = "",
    ) -> dict[str, Any]:
        """上报 Bug。"""
        if category not in BUG_CATEGORIES:
            raise ValueError(f"category 必须是以下之一: {', '.join(BUG_CATEGORIES)}")
        if not title.strip():
            raise ValueError("Bug 标题不能为空")
        if not content.strip():
            raise ValueError("Bug 描述不能为空")
        return self.store.create_bug(
            reporter=reporter,
            category=category,
            title=title,
            content=content,
            session_id=session_id,
            query=query,
            answer=answer,
            attachment_path=attachment_path,
        )

    def get_bug(self, bug_id: int) -> dict[str, Any] | None:
        return self.store.get_bug(bug_id)

    def list_bugs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.store.list_bugs(
            limit=limit, offset=offset, status=status, category=category
        )

    def count_bugs(
        self, status: str | None = None, category: str | None = None
    ) -> int:
        return self.store.count_bugs(status=status, category=category)

    def update_status(self, bug_id: int, status: str) -> dict[str, Any] | None:
        return self.store.update_status(bug_id, status)

    def get_stats(self) -> dict[str, Any]:
        return self.store.get_stats()


# 全局单例
bug_service = BugService()
