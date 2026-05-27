# SuperBizAgent 项目推进计划

## 目标

先完成对现有 Agent 项目的理解与架构梳理，建立后续功能完善时可持续更新的文档沉淀目录。

## 阶段计划

| 阶段 | 状态 | 说明 |
|---|---|---|
| 1. 梳理项目结构、依赖与启动方式 | 已完成 | 已读取 README、pyproject、目录结构、启动脚本说明和核心入口 |
| 2. 理解核心 Agent 链路与数据流 | 已完成 | 已分析 RAG Agent、AIOps Agent、MCP 工具、向量检索和前端请求链路 |
| 3. 建立项目文档沉淀 | 已完成 | 已在 `project-docs/` 下维护计划、发现、进度与架构概览 |
| 4. 提出后续完善方向 | 已完成 | 已在 `project_overview.md` 中整理风险点和后续演进路线 |
| 5. 增加 RAG 重排序能力 | 已完成 | 已接入 OpenAI-compatible / NVIDIA Rerank，形成候选召回、重排序、失败降级的检索流水线 |
| 6. 修复 Windows 一键启动脚本 | 已完成 | 已将批处理脚本改为英文 ASCII + CRLF，补齐 `.python-version` 和 pip 兜底，验证启动/停止命令可用 |
| 7. 重构模型服务配置 | 已完成 | 已将 Chat、Embedding、Rerank 拆分为独立 OpenAI-compatible 配置，并保留旧 DashScope / NVIDIA 配置兜底 |
| 8. 处理 Embedding 输入 token 限制 | 已完成 | 已在检索 query 阶段新增智能压缩，并在知识库入库阶段通过文档继续切分控制 512 token 限制 |
| 9. PostgreSQL 会话持久化 | 已完成 | 已增加 `SESSION_CHECKPOINT_BACKEND=memory|postgres`、PostgreSQL checkpointer、会话索引表和前端服务端历史列表加载 |

## 当前判断

项目是一个 FastAPI + LangChain/LangGraph + OpenAI-compatible 模型接口 + Milvus + MCP 的智能业务代理系统，主要包含两条 Agent 链路：

- RAG Chat Agent：面向普通知识库问答，支持非流式与 SSE 流式输出。
- AIOps Agent：面向智能运维诊断，采用 Plan-Execute-Replan 工作流。

本轮项目理解已完成，并已完成 RAG 重排序增强、Windows 一键启动脚本修复、OpenAI-compatible 模型配置重构、Embedding 输入 token 限制处理和 PostgreSQL 会话持久化。完整概览见 `project-docs/project_overview.md`。

## 后续维护约定

- `findings.md`：记录代码阅读、架构理解、风险点与关键发现。
- `progress.md`：记录每次会话做了什么、改了什么、验证了什么。
- `project_overview.md`：沉淀项目整体架构、模块职责与数据流。
