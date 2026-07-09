"""请求数据模型.

定义 API 请求的 Pydantic 模型
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求."""

    id: str = Field(..., description="会话 ID", alias="Id")
    question: str = Field(..., description="用户问题", alias="Question")

    class Config:
        populate_by_name = True
        json_schema_extra = {"example": {"Id": "session-123", "Question": "什么是向量数据库？"}}


class FeedbackRequest(BaseModel):
    """反馈评价请求."""

    session_id: str = Field(..., description="会话 ID", alias="sessionId")
    question: str = Field(..., description="用户原始提问")
    answer: str = Field(..., description="AI 回答")
    rating: str = Field(..., description="评价类型: like / dislike")
    message_id: str = Field("", description="消息 ID（前端生成，用于关联）", alias="messageId")
    tags: list[str] = Field(default_factory=list, description="结构化负反馈标签")
    comment: str = Field("", description="补充描述")
    chunk_ids: list[str] = Field(default_factory=list, description="关联的知识片段 ID", alias="chunkIds")

    class Config:
        populate_by_name = True


class ClearRequest(BaseModel):
    """清空会话请求."""

    session_id: str = Field(..., description="会话 ID", alias="sessionId")

    class Config:
        populate_by_name = True
