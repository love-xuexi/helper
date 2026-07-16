"""
MCP 客户端管理
提供全局单例的 MCP 客户端，避免重复初始化

这个文件负责创建和管理 MCP Client。
MCP 可以理解成“给大模型/Agent 使用的外部工具协议”：
- Agent 不直接调用外部服务
- Agent 通过 MCP Client 获取工具列表
- 当模型决定调用某个工具时，MCP Client 负责把请求发给对应 MCP Server

在本项目中，rag_agent_service.py 会调用 get_mcp_client_with_retry()，
拿到 MultiServerMCPClient 后再执行 get_tools()，
最终把 MCP 工具注册到 LangChain Agent 中。
"""

import asyncio
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from loguru import logger
from mcp.types import CallToolResult, TextContent

# 全局 MCP 客户端（延迟初始化）
# 初始值为 None，只有第一次调用 get_mcp_client(...) 时才真正创建。
# 这样可以避免应用启动时就连接所有 MCP Server，也避免重复创建客户端。
_mcp_client: MultiServerMCPClient | None = None


async def retry_interceptor(
    request: MCPToolCallRequest,
    handler,
    max_retries: int = 3,
    delay: float = 1.0,
):
    """MCP 工具调用重试拦截器

    当工具调用失败时，使用指数退避策略自动重试。
    如果所有重试都失败，返回包含错误信息的结果而不是抛出异常。

    MCPToolCallRequest 结构：
    - name: str - 工具名称
    - args: dict[str, Any] - 工具参数
    - server_name: str - 服务器名称

    Args:
        request: MCP 工具调用请求
        handler: 实际的工具调用处理器
        max_retries: 最大重试次数（默认3次）
        delay: 初始延迟时间（秒，默认1秒）

    Returns:
        CallToolResult: 工具调用结果或错误信息

    成功时，最终返回 handler(request) 的结果，通常是 CallToolResult，例如：
    CallToolResult(
        content=[TextContent(type="text", text="工具返回的文本内容")],
        isError=False
    )

    失败且重试耗尽时，不抛异常，而是返回：
    CallToolResult(
        content=[TextContent(type="text", text="工具 xxx 在 3 次重试后仍然失败: ...")],
        isError=True
    )

    这样做的效果是：
    工具失败会被包装成“工具结果”返回给 Agent，
    而不是直接让整个 Agent 调用链路崩掉。
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(
                f"调用 MCP 工具: {request.name} "
                f"(服务器: {request.server_name}, 第 {attempt + 1}/{max_retries} 次尝试)"
            )
            # handler(request) 才是真正执行 MCP 工具调用的地方。
            # retry_interceptor 本身不实现工具逻辑，只是在外面包一层重试。
            result = await handler(request)
            logger.info(f"MCP 工具 {request.name} 调用成功")
            return result

        except Exception as e:
            last_error = e
            logger.warning(
                f"MCP 工具 {request.name} 调用失败 (第 {attempt + 1}/{max_retries} 次): {str(e)}"
            )

            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                # 指数退避：
                # 第 1 次失败后等 1 秒
                # 第 2 次失败后等 2 秒
                # 第 3 次失败后如果还有重试，会等 4 秒
                # 这样可以避免外部服务短暂抖动时被立即连续打爆
                wait_time = delay * (2**attempt)  # 指数退避
                logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)

    # 所有重试都失败，返回错误结果而不是抛出异常
    error_msg = f"工具 {request.name} 在 {max_retries} 次重试后仍然失败: {str(last_error)}"
    logger.error(error_msg)
    return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=True)


# 从配置文件读取 MCP 服务器配置
from app.config import config

# 使用配置文件中定义的完整 MCP 服务器配置
# DEFAULT_MCP_SERVERS 大概长这样：
# {
#     "server_name": {
#         "transport": "sse",
#         "url": "http://localhost:xxxx/sse"
#     }
# }
# 具体内容来自 app.config.config.mcp_servers。
DEFAULT_MCP_SERVERS = config.mcp_servers


async def get_mcp_client(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """
    获取或初始化 MCP 客户端（不带重试拦截器）

    这是一个单例模式，确保整个应用只有一个 MCP 客户端实例（除非 force_new=True）

    从 langchain-mcp-adapters 0.1.0 开始，MultiServerMCPClient 不再支持作为上下文管理器使用。
    直接创建实例即可使用。

    Args:
        servers: MCP 服务器配置，默认使用 DEFAULT_MCP_SERVERS
        tool_interceptors: 自定义工具拦截器列表
        force_new: 是否强制创建新实例（用于特殊场景，如需要不同配置）

    Returns:
        MultiServerMCPClient: MCP 客户端实例

    最终返回的是一个 MultiServerMCPClient 对象。
    它不是工具调用结果，而是“工具客户端/工具管理器”。

    典型用法：
    client = await get_mcp_client()
    tools = await client.get_tools()

    tools 返回的是 LangChain 可用的工具列表，
    后续会传给 create_agent(..., tools=tools)。
    """
    global _mcp_client

    # 如果请求新实例，直接创建并返回（不缓存）
    # force_new=True 适合测试或临时使用不同 servers 配置。
    # 注意：这种情况下不会写入全局 _mcp_client。
    if force_new:
        logger.info("创建新的 MCP 客户端实例（非单例）")
        client = _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)
        # 不再需要 __aenter__()，直接返回即可
        return client

    # 单例模式：如果已存在，直接返回
    # 第一次调用会创建；后续调用复用同一个 _mcp_client。
    # 这样可以避免多个 Agent/请求重复初始化 MCP 连接和工具列表。
    if _mcp_client is None:
        logger.info("初始化全局 MCP 客户端...")
        _mcp_client = _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)
        # 不再需要 __aenter__()，直接使用即可
        logger.info("全局 MCP 客户端初始化完成")

    return _mcp_client


async def get_mcp_client_with_retry(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """
    获取或初始化带重试功能的 MCP 客户端

    这是一个单例模式，确保整个应用只有一个 MCP 客户端实例（除非 force_new=True）
    重试拦截器会自动添加到拦截器列表的开头

    Args:
        servers: MCP 服务器配置，默认使用 DEFAULT_MCP_SERVERS
        tool_interceptors: 自定义工具拦截器列表（会在重试拦截器之后添加）
        force_new: 是否强制创建新实例（用于特殊场景，如需要不同配置）

    Returns:
        MultiServerMCPClient: 带重试功能的 MCP 客户端实例

    和 get_mcp_client(...) 的区别：
    - get_mcp_client(...) 默认不加 retry_interceptor
    - get_mcp_client_with_retry(...) 会自动把 retry_interceptor 放到拦截器列表最前面

    所以通过这个函数拿到的 MCP Client，
    后续每次工具调用失败时都会自动重试，最多 3 次。
    """
    # 构建拦截器列表：重试拦截器在最前面
    # 拦截器可以理解成工具调用前后的“中间件”。
    # retry_interceptor 放在最前面，保证它能包住后续所有工具调用。
    interceptors = [retry_interceptor]
    if tool_interceptors:
        # 如果调用方还传入了其它拦截器，就接在 retry_interceptor 后面。
        interceptors.extend(tool_interceptors)

    # 复用 get_mcp_client(...) 的单例创建逻辑，只是额外传入了 tool_interceptors。
    return await get_mcp_client(
        servers=servers, tool_interceptors=interceptors, force_new=force_new
    )


def _create_mcp_client(
    servers: dict[str, dict[str, str]], tool_interceptors: list | None = None
) -> MultiServerMCPClient:
    """
    创建 MCP 客户端实例

    Args:
        servers: MCP 服务器配置
        tool_interceptors: 工具拦截器列表

    Returns:
        MultiServerMCPClient: 未初始化的客户端实例

    最终返回示例不是普通 dict，而是：
    MultiServerMCPClient(...)

    这个对象内部保存了多个 MCP Server 的连接配置。
    后续调用 client.get_tools() 时，它会根据 servers 配置去加载各个 MCP Server 暴露的工具。
    """
    # MultiServerMCPClient 的第一个参数直接接收 servers 配置字典
    # 格式: {server_name: {"transport": "...", "url": "..."}}
    kwargs: dict[str, Any] = {}

    if tool_interceptors:
        # tool_interceptors 会应用到通过这个 client 发起的工具调用上。
        # 例如 retry_interceptor 可以在工具调用失败时自动重试。
        kwargs["tool_interceptors"] = tool_interceptors

    # 第一个参数是 servers 配置，直接传递
    # 返回的是 MCP 客户端实例，不会立即返回工具执行结果。
    return MultiServerMCPClient(servers, **kwargs)  # type: ignore[arg-type]
