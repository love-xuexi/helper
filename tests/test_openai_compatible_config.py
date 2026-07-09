from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen

from app.config import Settings
from app.core.llm_factory import LLMFactory


def make_settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_settings_support_independent_chat_model_config():
    settings = make_settings(
        chat_api_key="chat-key",
        chat_base_url="https://chat.example.com/v1",
        chat_model="chat-model",
    )

    assert settings.chat_api_key == "chat-key"
    assert settings.chat_base_url == "https://chat.example.com/v1"
    assert settings.chat_model == "chat-model"


def test_settings_keep_legacy_dashscope_values_as_chat_fallbacks():
    settings = make_settings(
        dashscope_api_key="legacy-key",
        dashscope_api_base="https://legacy.example.com/v1",
        dashscope_model="legacy-chat-model",
    )

    assert settings.effective_chat_api_key == "legacy-key"
    assert settings.effective_chat_base_url == "https://legacy.example.com/v1"
    assert settings.effective_chat_model == "legacy-chat-model"


def test_llm_factory_falls_back_to_openai_compatible_for_generic_config():
    # 未指定 provider 且 base_url/model 无法识别 -> OpenAI 兼容兜底
    settings = make_settings(
        chat_api_key="chat-key",
        chat_base_url="https://chat.example.com/v1",
        chat_model="chat-model",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "chat-model"
    assert str(llm.openai_api_base).rstrip("/") == "https://chat.example.com/v1"
    assert llm.openai_api_key.get_secret_value() == "chat-key"


def test_llm_factory_routes_to_deepseek_when_provider_configured():
    settings = make_settings(chat_provider="deepseek", chat_api_key="chat-key")

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatDeepSeek)
    assert llm.model_name == "deepseek-chat"
    assert str(llm.api_base).rstrip("/") == "https://api.deepseek.com/v1"
    assert llm.api_key.get_secret_value() == "chat-key"


def test_llm_factory_infers_deepseek_from_base_url():
    settings = make_settings(
        chat_api_key="chat-key",
        chat_base_url="https://api.deepseek.com/v1",
        chat_model="deepseek-reasoner",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatDeepSeek)
    assert llm.model_name == "deepseek-reasoner"


def test_llm_factory_honors_legacy_dashscope_config_via_openai_fallback():
    # 仅配置旧版 DASHSCOPE_* 的用户应继续走 OpenAI 兼容并使用其自定义 model/endpoint
    settings = make_settings(
        dashscope_api_key="legacy-key",
        dashscope_api_base="https://legacy.example.com/v1",
        dashscope_model="qwen-legacy",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "qwen-legacy"
    assert str(llm.openai_api_base).rstrip("/") == "https://legacy.example.com/v1"
    assert llm.openai_api_key.get_secret_value() == "legacy-key"


def test_llm_factory_routes_to_qwen_when_provider_configured():
    settings = make_settings(
        chat_provider="qwen",
        chat_api_key="chat-key",
        chat_model="qwen-plus",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatQwen)
    assert llm.model_name == "qwen-plus"
    assert llm.api_key.get_secret_value() == "chat-key"


def test_llm_factory_unknown_provider_falls_back_to_openai():
    settings = make_settings(
        chat_provider="some-unknown-vendor",
        chat_api_key="chat-key",
        chat_base_url="https://chat.example.com/v1",
        chat_model="chat-model",
    )

    llm = LLMFactory(settings=settings).create_chat_model(streaming=False)

    assert isinstance(llm, ChatOpenAI)
