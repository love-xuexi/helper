"""配置管理模块

使用 Pydantic Settings 实现类型安全的配置管理
"""

from typing import Any, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

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
    host: str = "0.0.0.0"
    port: int = 9900

    # OpenAI 兼容模型配置
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
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        """获取完整的 MCP 服务器配置"""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            }
        }

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
