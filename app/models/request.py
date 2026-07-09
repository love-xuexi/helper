"""请求数据模型

定义 API 请求的 Pydantic 模型
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求"""

    id: str = Field(..., description="会话 ID", alias="Id")
    question: str = Field(..., description="用户问题", alias="Question")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "Id": "session-123",
                "Question": "什么是向量数据库？"
            }
        }


class ClearRequest(BaseModel):
    """清空会话请求"""

    session_id: str = Field(..., description="会话 ID", alias="sessionId")

    class Config:
        populate_by_name = True


class FeedbackRequest(BaseModel):
    """反馈评价请求"""

    session_id: str = Field(..., description="会话 ID", alias="sessionId")
    message_id: str = Field(..., description="消息 ID", alias="messageId")
    rating: str = Field(..., description="评价: like / dislike", alias="rating")
    question: Optional[str] = Field("", description="用户原始提问", alias="question")
    answer: Optional[str] = Field("", description="AI 回答内容", alias="answer")
    feedback_tags: Optional[List[str]] = Field(None, description="负反馈标签列表", alias="feedbackTags")
    feedback_description: Optional[str] = Field("", description="详细描述", alias="feedbackDescription")
    chunk_ids: Optional[List[str]] = Field(None, description="关联知识片段 ID 列表", alias="chunkIds")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "sessionId": "session-123",
                "messageId": "msg-456",
                "rating": "dislike",
                "question": "寿险投保规则是什么？",
                "answer": "根据参考资料...",
                "feedbackTags": ["回答不准确", "逻辑不清晰"],
                "feedbackDescription": "回答中提到的体检标准和实际不符",
                "chunkIds": ["859cffd18e948c98"]
            }
        }


class UploadUrlRequest(BaseModel):
    """通过 URL 上传文档请求"""

    kb_id: str = Field(..., description="目标知识库 ID", alias="kbId")
    file_url: str = Field(..., description="文件 URL", alias="fileUrl")
    auto_parse: bool = Field(True, description="是否自动解析", alias="autoParse")

    class Config:
        populate_by_name = True
