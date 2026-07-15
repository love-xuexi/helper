"""响应数据模型

定义 API 响应的 Pydantic 模型
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    """对话响应"""

    answer: str = Field(..., description="AI 回答")
    session_id: str = Field(..., description="会话 ID")


class Citation(BaseModel):
    """引用来源"""

    index: int = Field(..., description="引用编号")
    id: str = Field(..., description="片段 ID")
    document: str = Field(..., description="来源文档名称")
    similarity: float = Field(..., description="相似度")
    content_preview: str = Field("", description="内容预览")
    content: str = Field("", description="片段完整内容")


class ChatResultData(BaseModel):
    """对话返回数据（含引用来源）"""

    success: bool = Field(..., description="是否成功")
    answer: Optional[str] = Field(None, description="AI 回答")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="引用来源列表")
    message_id: Optional[str] = Field(None, description="消息 ID（用于反馈关联）")
    error_message: Optional[str] = Field(None, description="错误信息")


class SessionInfoResponse(BaseModel):
    """会话信息响应"""

    session_id: str = Field(..., description="会话 ID")
    message_count: int = Field(..., description="消息数量")
    history: List[Dict[str, str]] = Field(..., description="历史消息列表")


class ChatSessionSummary(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    last_message_preview: str = Field("", description="最后消息摘要")
    message_count: int = Field(0, description="消息数量")


class ChatSessionListResponse(BaseModel):
    total: int = Field(..., description="会话总数")
    limit: int = Field(..., description="每页数量")
    offset: int = Field(..., description="偏移量")
    sessions: List[ChatSessionSummary] = Field(default_factory=list, description="会话列表")


class ApiResponse(BaseModel):
    """通用 API 响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Any] = Field(None, description="数据")


class SimpleApiResponse(BaseModel):
    """简单 API 响应（data 可为任意结构）"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Any] = Field(None, description="数据")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(..., description="状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="版本号")


class FeedbackResponse(BaseModel):
    """反馈响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Dict[str, Any]] = Field(None, description="反馈数据")


class FeedbackListResponse(BaseModel):
    """反馈列表响应"""

    total: int = Field(..., description="反馈总数")
    limit: int = Field(..., description="每页数量")
    offset: int = Field(..., description="偏移量")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="反馈列表")


class FeedbackStatsResponse(BaseModel):
    """反馈统计响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Dict[str, Any]] = Field(None, description="统计数据")


class KnowledgeBaseInfo(BaseModel):
    """知识库信息"""

    id: str = Field(..., description="知识库 ID")
    name: str = Field(..., description="知识库名称")


class DocumentInfo(BaseModel):
    """文档信息"""

    id: str = Field(..., description="文档 ID")
    kb_id: str = Field(..., description="所属知识库 ID")
    name: str = Field(..., description="文档名称")
    create_date: str = Field("", description="创建时间")
    update_date: str = Field("", description="更新时间")


class BugListResponse(BaseModel):
    """Bug 列表响应"""

    total: int = Field(..., description="Bug 总数")
    limit: int = Field(..., description="每页数量")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Bug 列表")


class BugStatsResponse(BaseModel):
    """Bug 统计响应"""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Optional[Dict[str, Any]] = Field(None, description="统计数据")
