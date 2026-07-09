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
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 1024
    embedding_encoding_format: str = "float"
    embedding_max_tokens: int = 8192
    embedding_token_safety_margin: int = 128

    # DashScope 旧配置
    dashscope_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    dashscope_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"  # v4 支持多种维度（默认 1024）

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # 会话持久化配置
    session_checkpoint_backend: str = "memory"
    postgres_dsn: str = ""
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    postgres_connect_timeout_seconds: float = 10.0

    # RAG 配置
    rag_top_k: int = 3
    rag_candidate_top_k: int = 20
    rag_model: str = ""  # 使用快速响应模型，不带扩展思考

    # Rerank 配置
    rerank_enabled: bool = True
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_provider: str = ""
    rerank_timeout_seconds: float = 30.0
    nvidia_api_key: str = ""
    nvidia_base_url: str = ""

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

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
        return self.chat_base_url or self.dashscope_api_base

    @property
    def effective_chat_model(self) -> str:
        return self.chat_model or self.rag_model or self.dashscope_model

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.dashscope_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.dashscope_api_base

    @property
    def effective_embedding_model(self) -> str:
        return self.embedding_model or self.dashscope_embedding_model

    @property
    def effective_embedding_dimensions(self) -> int | None:
        return self.embedding_dimensions if self.embedding_dimensions > 0 else None

    @property
    def effective_rerank_api_key(self) -> str:
        return self.rerank_api_key or self.nvidia_api_key

    @property
    def effective_rerank_base_url(self) -> str:
        return self.rerank_base_url or self.nvidia_base_url

    @property
    def effective_rerank_provider(self) -> str:
        if self.rerank_provider:
            return self.rerank_provider
        if self.rerank_base_url or self.rerank_api_key:
            return "openai_compatible"
        if self.nvidia_base_url or self.nvidia_api_key:
            return "nvidia"
        return "openai_compatible"


# 全局配置实例
config = Settings()
