"""LLM 工厂类.

按 provider 路由创建 Chat 模型：

- 有专用 LangChain 接口的模型走专用接口：
  - ``deepseek`` -> ``langchain_deepseek.ChatDeepSeek``
  - ``qwen``     -> ``langchain_qwq.ChatQwen``
- 没有专用接口时回退到 OpenAI 兼容接口 ``langchain_openai.ChatOpenAI``。

provider 由 ``settings.effective_chat_provider`` 决定（显式配置 ``CHAT_PROVIDER``，
或根据 ``CHAT_BASE_URL`` / ``CHAT_MODEL`` 自动推断，无法识别时兜底 ``openai``）。
三种接口都继承自 ``BaseChatOpenAI``，因此 ``with_structured_output`` / ``bind_tools`` /
流式输出等能力一致，调用方无需区分。
"""

from enum import Enum

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config


class ChatProvider(str, Enum):
    """支持的 Chat 模型接口类型。"""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"


class LLMFactory:
    """LLM 工厂类 - OpenAI 兼容兜底 + 专用模型接口路由。"""

    def __init__(self, settings=None):
        self.settings = settings or config

    def _resolve_provider(self, provider: str | None) -> ChatProvider:
        name = (provider or self.settings.effective_chat_provider or "openai").strip().lower()
        try:
            return ChatProvider(name)
        except ValueError:
            logger.warning(f"未知的 chat provider '{name}'，回退到 OpenAI 兼容模式")
            return ChatProvider.OPENAI

    def create_chat_model(
        self,
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
    ) -> BaseChatModel:
        chat_provider = self._resolve_provider(provider)

        # effective_* 已按 provider 处理默认值：DeepSeek 用官方地址/deepseek-chat，
        # openai/qwen 沿用 DashScope 旧配置兜底，从而保持向后兼容。
        model = model or self.settings.effective_chat_model
        base_url = base_url or self.settings.effective_chat_base_url
        api_key = api_key or self.settings.effective_chat_api_key

        if chat_provider is ChatProvider.DEEPSEEK:
            # ChatDeepSeek 的 base_url 字段别名为 api_base。
            return ChatDeepSeek(
                model=model,
                temperature=temperature,
                streaming=streaming,
                base_url=base_url,
                api_key=api_key,
            )

        if chat_provider is ChatProvider.QWEN:
            return ChatQwen(
                model=model,
                temperature=temperature,
                streaming=streaming,
                api_base=base_url,
                api_key=api_key,
            )

        # 兜底：OpenAI 兼容接口
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
        )


# 全局 LLM 工厂实例
llm_factory = LLMFactory()
