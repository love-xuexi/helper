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

## 当前判断

项目是一个 FastAPI + LangChain/LangGraph + DashScope + Milvus + MCP 的智能业务代理系统，主要包含两条 Agent 链路：

- RAG Chat Agent：面向普通知识库问答，支持非流式与 SSE 流式输出。
- AIOps Agent：面向智能运维诊断，采用 Plan-Execute-Replan 工作流。

本轮项目理解已完成，完整概览见 `project-docs/project_overview.md`。

## 后续维护约定

- `findings.md`：记录代码阅读、架构理解、风险点与关键发现。
- `progress.md`：记录每次会话做了什么、改了什么、验证了什么。
- `project_overview.md`：沉淀项目整体架构、模块职责与数据流。
