"""配置管理模块.

使用 Pydantic Settings 实现类型安全的配置管理
"""

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "SuperBizAgent"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"  # nosec B104 - 服务默认监听所有网卡，可用 HOST 环境变量覆盖
    port: int = 9900

    # Chat 模型配置
    # chat_provider 决定使用哪种 LangChain 接口：
    #   deepseek -> langchain_deepseek.ChatDeepSeek
    #   qwen     -> langchain_qwq.ChatQwen
    #   openai   -> langchain_openai.ChatOpenAI（OpenAI 兼容，兜底）
    # 留空则根据 base_url / model 自动推断，无法识别时回退到 openai 兼容模式。
    chat_provider: str = ""
    chat_api_key: str = ""
    chat_base_url: str = ""
    chat_model: str = ""

    # DashScope 旧配置
    dashscope_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    dashscope_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-max"

    # 知识库平台 API 配置（内网）
    # 知识库的建立/解析/向量化/混合检索/重排均由知识库平台完成，本服务只调用其接口
    kb_api_token: str = ""  # Bearer Token，形如 kbmp-xxxx
    kb_doc_base_url: str = "http://10.8.192.79:5353"  # 文档检索 / 上传
    kb_mgmt_base_url: str = "http://10.8.192.79:5354"  # 知识库管理（列表/文档/指定检索）
    kb_faq_base_url: str = "http://10.8.192.79:6000"  # FAQ 问答库检索
    kb_botcode: str = ""  # 机器人编码
    kb_faq_channel: str = ""  # FAQ 渠道
    kb_upload_kb_id: str = ""  # 文件上传的默认目标知识库 ID（留空则取知识库列表第一个）
    kb_timeout_seconds: float = 30.0
    kb_max_chunks: int = 5  # 传给 LLM 的最相关片段数量（3-5）
    kb_min_similarity: float = 0.0  # 相似度过滤阈值（0 表示不过滤）

    # 反馈评价系统配置
    feedback_db_path: str = "data/feedback.db"  # 本地 SQLite 存储
    feedback_api_url: str = ""  # 可选：内网反馈入库接口，配置后反馈会同步转发

    # 会话持久化配置
    session_checkpoint_backend: str = "memory"
    postgres_dsn: str = ""
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    postgres_connect_timeout_seconds: float = 10.0

    # RAG 配置
    rag_model: str = ""  # 使用快速响应模型，不带扩展思考

    # MCP 服务配置
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"

    @property
    def is_postgres_checkpoint_enabled(self) -> bool:
        return self.session_checkpoint_backend.lower() == "postgres"

    @property
    def mcp_servers(self) -> dict[str, dict[str, Any]]:
        """获取完整的 MCP 服务器配置."""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            },
        }

    @property
    def effective_chat_provider(self) -> str:
        """返回 chat 模型接口类型；未显式配置时根据 base_url / model 推断，兜底 openai。"""
        if self.chat_provider:
            return self.chat_provider.strip().lower()
        haystack = f"{self.chat_base_url} {self.chat_model}".lower()
        if "deepseek" in haystack:
            return "deepseek"
        if "dashscope" in haystack or "aliyuncs" in haystack or "qwen" in haystack:
            return "qwen"
        return "openai"

    @property
    def effective_chat_api_key(self) -> str:
        return self.chat_api_key or self.dashscope_api_key

    @property
    def effective_chat_base_url(self) -> str:
        # 显式配置优先；DeepSeek 用官方地址，其余（openai/qwen）沿用 DashScope 旧配置兜底
        if self.chat_base_url:
            return self.chat_base_url
        if self.effective_chat_provider == "deepseek":
            return "https://api.deepseek.com/v1"
        return self.dashscope_api_base

    @property
    def effective_chat_model(self) -> str:
        # 显式配置优先；DeepSeek 默认 deepseek-chat，其余（openai/qwen）沿用 DashScope 旧配置兜底
        if self.chat_model or self.rag_model:
            return self.chat_model or self.rag_model
        if self.effective_chat_provider == "deepseek":
            return "deepseek-chat"
        return self.dashscope_model


# 全局配置实例
config = Settings()
