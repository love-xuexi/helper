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
    port: int = 9983

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

    # ---- 知识库 API 配置（内网接口，RAG 检索直接调用） ----
    # 文档检索/上传地址（端口 5353）
    kb_retrieval_base_url: str = "http://10.8.192.79:5353"
    # 知识库管理地址（端口 5354）
    kb_management_base_url: str = "http://10.8.192.79:5354"
    # FAQ 检索地址（端口 6000）
    kb_faq_base_url: str = "http://10.8.192.79:6000"
    # 统一鉴权 Token
    kb_api_token: str = "kbmp-i94DZSu3_pUMxcA0seYAe-Hcod3_EJRf"
    # 文档检索用的 botcode
    kb_botcode: str = "25d4c12e46834cc39bc211b84a9b2462"
    # FAQ 检索用的 botcode
    kb_faq_botcode: str = "a2a45e52569f48ac9a2a2ca1d1e2718c"
    # FAQ 渠道
    kb_faq_channel: str = "1"
    # 默认检索的知识库 ID 列表（逗号分隔，留空则使用 botcode 关联的默认库）
    kb_default_kb_ids: str = ""
    # 检索返回的片段数量上限
    kb_top_k: int = 5
    # 检索相似度阈值（低于此值的片段将被过滤）
    kb_similarity_threshold: float = 0.3
    # KB API 请求超时（秒）
    kb_timeout_seconds: float = 30.0

    # ---- 反馈系统配置 ----
    # 反馈数据库路径（SQLite）
    feedback_db_path: str = "./data/feedback.db"
    # 可选：反馈数据外部推送 API（留空则仅本地存储）
    feedback_external_api_url: str = ""
    feedback_external_api_token: str = ""

    # ---- Bug 上报系统配置 ----
    # Bug 数据库路径（SQLite）
    bug_db_path: str = "./data/bug.db"
    # Bug 附件存储目录
    bug_upload_dir: str = "./data/uploads"

    # RAG 配置（保留兼容旧配置，实际检索改用 KB API）
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
    def kb_default_kb_id_list(self) -> list[str]:
        """将 kb_default_kb_ids 字符串解析为列表。"""
        if not self.kb_default_kb_ids.strip():
            return []
        return [s.strip() for s in self.kb_default_kb_ids.split(",") if s.strip()]

    @property
    def kb_auth_header(self) -> dict[str, str]:
        """获取知识库 API 鉴权请求头。"""
        return {"Authorization": f"Bearer {self.kb_api_token}"}

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
