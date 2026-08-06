"""DuckDuckGo Search MCP Server

提供免费的联网搜索能力，无需 API Key。

工具列表：
- web_search          — 通用网页搜索（使用 DuckDuckGo，完全免费、无需注册）
- web_search_suggest  — 搜索建议词

数据源：DuckDuckGo（duckduckgo-search 包），无需 API Key。
如网络无法访问 DuckDuckGo，返回 mock 搜索结果保证 Agent 流程不中断。

可选：通过环境变量 DDG_PROXY 配置代理（如 socks5://127.0.0.1:1080）。
"""

import functools
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载项目根目录 .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DDG_MCP_Server")

mcp = FastMCP("DuckDuckGoSearch")

# 可选代理（中国大陆访问 DuckDuckGo 可能需要）
_PROXY = os.getenv("DDG_PROXY", "").strip() or None


def log_tool_call(func):
    """装饰器：记录工具调用日志"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method_name = func.__name__
        logger.info(f"调用方法: {method_name}")
        if kwargs:
            try:
                params_str = json.dumps(kwargs, ensure_ascii=False)[:2000]
            except (TypeError, ValueError):
                params_str = str(kwargs)[:2000]
            logger.info(f"参数: {params_str}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"方法 {method_name} 执行成功")
            return result
        except Exception as e:
            logger.error(f"方法 {method_name} 执行失败: {e}")
            raise

    return wrapper


def _create_ddgs():
    """创建 DDGS 实例，支持可选代理"""
    from duckduckgo_search import DDGS

    kwargs: dict[str, Any] = {}
    if _PROXY:
        kwargs["proxy"] = _PROXY
    return DDGS(**kwargs)


# ============================================================
# 工具实现
# ============================================================


@mcp.tool()
@log_tool_call
def web_search(
    query: str,
    count: int = 10,
    region: str = "cn-zh",
) -> dict[str, Any]:
    """进行网页搜索，返回搜索结果的标题、链接和摘要。使用 DuckDuckGo，完全免费无需 API Key。

    Args:
        query: 搜索关键词（如 "LangChain 多Agent 教程"）
        count: 返回结果数量（1-20，默认10）
        region: 地区语言（默认 cn-zh 中国中文，可选 wt-wt 全球/us-en 美国英文等）

    Returns:
        搜索结果列表，每个结果包含 title、url、description 字段。
        网络不可达时返回 mock 结果。

    使用示例:
        # 搜索通用问题
        web_search(query="什么是 Kubernetes")

        # 限制数量
        web_search(query="LangGraph 状态图", count=5)
    """
    count = max(1, min(int(count), 20))

    try:
        ddgs = _create_ddgs()
        raw_results = ddgs.text(query, max_results=count, region=region)
        results = []
        for item in raw_results:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", item.get("url", "")),
                    "description": item.get("body", item.get("description", "")),
                }
            )

        if not results:
            logger.warning(f"DuckDuckGo 返回空结果，回退 mock（query={query}）")
            return _build_mock_search(query, count)

        return {
            "query": query,
            "total": len(results),
            "source": "duckduckgo",
            "results": results,
            "message": f"搜索到 {len(results)} 条结果",
        }
    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败（{e}），回退 mock 结果")
        return _build_mock_search(query, count)


@mcp.tool()
@log_tool_call
def web_search_suggest(query: str) -> dict[str, Any]:
    """获取搜索建议关键词。使用 DuckDuckGo 自动补全，完全免费。

    Args:
        query: 查询关键词

    Returns:
        建议词列表。网络不可达时返回 mock 建议。
    """
    try:
        ddgs = _create_ddgs()
        suggestions = list(ddgs.suggest(query))[:10]
        if not suggestions:
            return {"query": query, "source": "mock", "suggestions": _mock_suggestions(query)}
        return {"query": query, "source": "duckduckgo", "suggestions": suggestions}
    except Exception as e:
        logger.warning(f"DuckDuckGo 建议失败（{e}），回退 mock")
        return {"query": query, "source": "mock", "suggestions": _mock_suggestions(query)}


# ============================================================
# Mock 数据（网络不可达时使用）
# ============================================================


def _build_mock_search(query: str, count: int) -> dict[str, Any]:
    """构建 mock 搜索结果（DuckDuckGo 不可达时）

    按关键词匹配返回对应领域的 mock 新闻/技术资料，保证 Agent 流程可跑通。
    """
    q = query.lower()
    results = []

    if any(k in q for k in ["新闻", "news", "ai ", "ai新", "人工智能", "gpt", "大模型", "最新"]):
        results = [
            {
                "title": "OpenAI 推出最新一代大语言模型系列 GPT-5.6",
                "url": "https://www.jiqizhixin.com/articles/2026-ai-gpt56",
                "description": (
                    "OpenAI 推出 GPT-5.6 系列限量预览版，包含旗舰 Sol、平衡 Terra 和性价比 Luna 三款模型。"
                    "Sol 在编程、网络安全和生物学领域表现突出，新增 max 深度推理和 ultra 多 Agent 协同模式；"
                    "Terra 以 GPT-5.5 一半价格提供同等性能；Luna 主打轻量高速。"
                ),
            },
            {
                "title": "字节跳动推出原生全双工语音大模型 Seeduplex",
                "url": "https://www.bytedance.com/zh/seed/seeduplex",
                "description": (
                    "字节跳动 Seed 团队推出全双工语音大模型 Seeduplex，已在豆包 App 全量上线。"
                    "模型基于'边听边说'框架，实现听说同步，误回复率和抢话比例分别降低 50% 和 40%，"
                    "判停延迟减少 250ms，对话流畅度提升 12%。"
                ),
            },
            {
                "title": "DeepSeek 联合北大开源推测解码加速框架 DSpark",
                "url": "https://www.deepseek.com/research/dspark",
                "description": (
                    "DeepSeek 联合北京大学开源推测解码加速框架 DSpark，"
                    "在保持生成质量的前提下，将大模型推理速度提升 2-3 倍，"
                    "显著降低企业级部署的算力成本。"
                ),
            },
            {
                "title": "Claude 推出企业级托管 Agent 服务 Claude Managed Agents",
                "url": "https://www.anthropic.com/managed-agents",
                "description": (
                    "Anthropic 推出 Claude Managed Agents 企业级托管服务，"
                    "支持企业一键部署多 Agent 协作工作流，"
                    "Anthropic 年化收入已达 470 亿美元。"
                ),
            },
            {
                "title": "马斯克 xAI 开源 AI 编程智能体 Grok Build",
                "url": "https://www.it-home.com/archives/2026/ai/grok-build",
                "description": (
                    "马斯克旗下 xAI 宣布开源 AI 编程智能体工具 Grok Build，源码已发布至 GitHub。"
                    "工具覆盖规划、搜索、编码、测试到 Git 提交的全流程开发，"
                    "支持完全本地优先运行与自定义推理。"
                ),
            },
            {
                "title": "谷歌发布 Gemini 2.5 Flash Preview 混合推理模型",
                "url": "https://blog.google/gemini-25-flash",
                "description": (
                    "谷歌推出 Gemini 2.5 Flash Preview 预览模型，混合推理架构，"
                    "开发者可根据查询复杂程度灵活调整处理时间，"
                    "针对低延迟和降本优化，适合响应式虚拟助手和实时总结。"
                ),
            },
            {
                "title": "OpenAI 发布 Sora 2：AI 视频生成支持同步对话与音效",
                "url": "https://openai.com/sora-2",
                "description": (
                    "OpenAI 发布视频生成模型 Sora 2，具备同步对话和音效能力，"
                    "支持创作、二创和客串功能，已在 ChatGPT 开发者日亮相并开放预览版。"
                ),
            },
            {
                "title": "苹果收购 AI 初创公司 PromptAI，加码空间智能",
                "url": "https://www.reuters.com/apple-promptai",
                "description": (
                    "苹果从马斯克手中抢购了 AI 初创公司 PromptAI 的核心团队，"
                    "该公司由北大校友 Tete Xiao 联合创立，旗舰产品 Seemour "
                    "是具有空间感知的环境式 AI 系统。"
                ),
            },
            {
                "title": "面壁智能完成新一轮融资，端侧大模型估值超 200 亿",
                "url": "https://www.modelbest.cn/funding",
                "description": (
                    "端侧大模型独角兽面壁智能完成新一轮融资，估值超 200 亿元，"
                    "专注将大模型压缩至手机、车机等终端设备本地运行，"
                    "MiniCPM 系列已在多款消费设备落地。"
                ),
            },
            {
                "title": "我国已发布 1509 个人工智能大模型，数量居全球首位",
                "url": "https://cn.chinadaily.com.cn/a/2026/ai-large-models",
                "description": (
                    "截至统计日，我国已发布 1509 个人工智能大模型，"
                    "在全球已发布的 3755 个大模型中数量位居首位，"
                    "覆盖通用、行业、多模态、Agent 等多个方向。"
                ),
            },
        ]
    elif any(k in q for k in ["cpu", "内存", "memory", "性能", "performance"]):
        results = [
            {
                "title": "如何排查服务器 CPU 使用率过高问题",
                "url": "https://example.com/troubleshooting/cpu-high",
                "description": (
                    "CPU 使用率过高的常见原因：死循环、流量突增、定时任务重叠、数据库慢查询。"
                    "排查步骤：查看 top 进程、分析系统日志、检查慢查询。"
                ),
            },
            {
                "title": "JVM 内存泄漏排查指南",
                "url": "https://example.com/articles/jvm-leak",
                "description": "内存泄漏导致 Full GC 频繁。排查：dump 堆快照，用 MAT 分析大对象引用。",
            },
        ]
    elif any(k in q for k in ("agent", "langgraph", "多agent", "llm")):
        results = [
            {
                "title": "LangGraph Multi-Agent 协作架构详解",
                "url": "https://example.com/langgraph-multi-agent",
                "description": "Supervisor-Worker 模式：调度 Agent 负责任务分解和路由，专家 Agent 处理子任务。",
            },
        ]
    else:
        results = [
            {
                "title": f"「{query}」的搜索结果",
                "url": "https://example.com/search",
                "description": "DuckDuckGo 网络不可达，返回 mock 结果。请检查网络或配置 DDG_PROXY 环境变量。",
            }
        ]

    results = results[:count]
    return {
        "query": query,
        "total": len(results),
        "source": "mock",
        "results": results,
        "message": "DuckDuckGo 不可达，返回 mock 结果（可配置 DDG_PROXY 环境变量）",
    }


def _mock_suggestions(query: str) -> list[str]:
    """构建 mock 搜索建议"""
    return [f"{query} 教程", f"{query} 最佳实践", f"{query} 常见问题", f"{query} 优化"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8107)
