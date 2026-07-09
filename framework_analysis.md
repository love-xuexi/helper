# 知行智能Agent (super-biz-agent-py) 整体框架分析

## 1. 项目整体定位
`super-biz-agent-py` 是一个企业级的智能对话和运维助手系统。它融合了 **RAG (检索增强生成)** 知识库问答和 **AIOps (智能运维)** 自动化故障诊断。该系统不局限于简单的 LLM 对话，而是通过 LangGraph 构建了具备规划、执行、反思能力的 Agent 生态，并利用 MCP (Model Context Protocol) 协议接入了外部监控和日志等基础设施。

## 2. 核心技术栈
项目的技术选型体现了现代化、企业级 AI 应用的特征：
- **Web 框架**: **FastAPI** (高性能，支持异步和流式响应 SSE)
- **AI / 编排框架**: **LangChain** + **LangGraph** (构建复杂的工作流和有状态的 Agent)
- **向量数据库**: **Milvus** (用于 RAG 系统的文档向量存储与高维检索)
- **大模型生态**: OpenAI 兼容接口支持 (可无缝对接 DashScope、OpenAI 等)，同时集成了 **NVIDIA Rerank / BAAI bge-reranker** 用于检索重排序。
- **状态存储**: **PostgreSQL** (用于 LangGraph 的 Checkpoint 持久化，实现会话中断恢复)
- **工具集成协议**: **MCP (Model Context Protocol)** (解耦了 Agent 和底层监控/日志工具，如 CLS 和 Monitor)

## 3. 分层架构解析
项目在 `app/` 目录下采用了清晰的模块化分层架构：

### 3.1 接入层 (`app/api/`)
基于 FastAPI 暴露 RESTful API 和 SSE 流式接口：
- `chat.py`: 提供普通对话和流式对话 (`/api/chat`, `/api/chat_stream`)。
- `aiops.py`: 暴露故障诊断流程触发接口。
- `file.py`: 处理文档上传和向量化入口 (`/api/upload`)。

### 3.2 代理逻辑层 (`app/agent/` & `app/services/`)
这是系统的“大脑”，主要分为两类核心智能体：
1. **RAG Agent (`rag_agent_service.py`)**: 
   - 负责知识问答。结合了多轮对话上下文。
2. **AIOps Agent (`app/agent/aiops/`)**: 
   - 采用 **Plan-Execute-Replan** 架构。
   - `planner.py`: 分析问题，制定 4-6 步的诊断计划。
   - `executor.py`: 根据计划调用相应的 MCP 工具 (查询日志、看监控指标)。
   - `replanner.py`: 评估工具返回结果，决定是继续下一步、调整计划还是输出最终根因报告。

### 3.3 业务服务层 (`app/services/`)
提供 Agent 运行所需的专业能力封装：
- **检索与排序**: `rag_retrieval_service.py` 和 `rerank_service.py` 负责从 Milvus 召回粗排结果，并通过重排序模型 (Rerank) 提升精确度。
- **向量化与预处理**: `document_splitter_service.py` 处理文档分块 (Chunking)；`vector_embedding_service.py` 和 `embedding_input_guard.py` 负责文本向量化及 Token 预算控制 (防溢出截断)。
- **存储管理**: `vector_store_manager.py` 和 `vector_index_service.py` 封装对 Milvus 的索引和存储操作。

### 3.4 基础设施与核心层 (`app/core/`, `app/models/`, `app/tools/`)
- **Core 组件**: `llm_factory.py` (模型实例化)、`milvus_client.py` (数据库连接)、`session_persistence.py` (PostgreSQL 状态管理)。
- **工具组件**: Agent 可调用的工具集，通过 `mcp_client.py` 动态加载外部 MCP 提供的能力。
- **数据模型**: 基于 Pydantic 定义的 API 请求响应及内部传递数据结构 (`app/models/`)。

## 4. 外部子系统集成
- **MCP Servers (`mcp_servers/`)**: 项目不仅有主服务，还独立包含了符合 MCP 规范的服务端（如 `cls_server.py`, `monitor_server.py`），它们负责与真实运维环境对接获取数据。主服务通过 MCP 客户端与它们交互。
- **Web 前端 (`static/`)**: 提供了原生的纯前端 HTML/JS/CSS 实现，支持对话交互、流式打字机效果及功能切换。

## 5. 核心工作流总结

### A. RAG 知识库问答工作流
1. **文档摄入**: 用户上传 Markdown (`/api/upload`) -> 文本分块 (Chunking) -> 调用 Embedding 模型 -> 写入 Milvus 向量库。
2. **问答检索**: 用户提问 -> Query 向量化 -> Milvus 召回 Top-K 候选 (Candidate Top-K=20) -> 调用 Rerank 模型精排 (Top-K=3) -> 拼装 Prompt -> LLM 生成回答并流式返回。

### B. AIOps 智能诊断工作流
1. **触发诊断**: 用户提交报错/问题描述。
2. **规划 (Plan)**: AIOps Planner LLM 生成初步诊断步骤。
3. **执行 (Execute)**: 系统遍历步骤，Executor LLM 决定需要使用哪些 MCP 工具（如调用 `cls_server` 查日志）。
4. **反思与重规划 (Replan)**: Replanner 根据工具执行结果更新状态，如果获取到足够信息则总结 Root Cause（根因），否则继续调整步骤执行。

## 6. 架构亮点
1. **先进的 Agent 架构设计**: 使用 LangGraph 将 AIOps 的复杂分析过程拆解为状态图 (State Graph)，增强了系统的可控性和调试性。
2. **企业级的容错与管控**: 
   - 实现了 Embedding `Token 预算估算与截断`（`embedding_input_guard.py`），防止长文本超出模型上下文限制。
   - `PostgreSQL 会话持久化` 支持 Agent 的跨服务重启状态保留。
   - `Rerank 降级策略`，在重排序服务超时时能自动回退。
3. **高扩展的工具协议**: 引入 MCP 规范，使得后续接入新的内部系统 (如 CMDB、工单系统) 只需要编写独立的 MCP Server，无需改动核心 Agent 代码。
