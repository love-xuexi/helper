"""LLM 工厂类.

使用 LangChain 官方的 DeepSeek 接口 (langchain_deepseek.ChatDeepSeek) 调用 DeepSeek 模型。

ChatDeepSeek 继承自 BaseChatOpenAI，兼容 with_structured_output / bind_tools / 流式输出，
同时针对 DeepSeek API 做了专门适配（如 reasoning_content、tool 消息格式等）。

默认接入 DeepSeek 官方服务：
- Base URL: https://api.deepseek.com/v1
- 常用模型: deepseek-chat（对话）、deepseek-reasoner（推理）

如需接入自建或第三方兼容 DeepSeek 的服务，只需通过配置修改 base_url / api_key。
"""

from langchain_deepseek import ChatDeepSeek

from app.config import config


class LLMFactory:
    """LLM 工厂类 - 使用 LangChain 官方 DeepSeek 接口"""

    # DeepSeek 官方 API 默认值
    DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
    DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

    def __init__(self, settings=None):
        self.settings = settings or config

    def create_chat_model(
        self,
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatDeepSeek:
        model = model or self.settings.effective_chat_model or LLMFactory.DEEPSEEK_DEFAULT_MODEL
        base_url = base_url or self.settings.effective_chat_base_url or LLMFactory.DEEPSEEK_BASE_URL
        api_key = api_key or self.settings.effective_chat_api_key

        # ChatDeepSeek 的 base_url 字段别名为 api_base，这里用 base_url 传入即可。
        llm = ChatDeepSeek(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
        )

        return llm


# 全局 LLM 工厂实例
llm_factory = LLMFactory()
