"""
AIOps 智能运维接口
"""

import json

from fastapi import APIRouter
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.models.aiops import AIOpsRequest
from app.services.aiops_service import aiops_service
from app.services.multi_agent_service import multi_agent_service

router = APIRouter()


@router.post("/aiops")
async def diagnose_stream(request: AIOpsRequest):
    """
    AIOps 故障诊断接口（流式 SSE）

    **功能说明：**
    - 自动获取当前系统的活动告警
    - 使用 Plan-Execute-Replan 模式进行智能诊断
    - 流式返回诊断过程和结果

    **SSE 事件类型：**

    1. `status` - 状态更新
       ```json
       {
         "type": "status",
         "stage": "fetching_alerts",
         "message": "正在获取系统告警信息..."
       }
       ```

    2. `plan` - 诊断计划制定完成
       ```json
       {
         "type": "plan",
         "stage": "plan_created",
         "message": "诊断计划已制定，共 6 个步骤",
         "target_alert": {...},
         "plan": ["步骤1: ...", "步骤2: ..."]
       }
       ```

    3. `step_complete` - 步骤执行完成
       ```json
       {
         "type": "step_complete",
         "stage": "step_executed",
         "message": "步骤执行完成 (2/6)",
         "current_step": "查询系统日志",
         "result_preview": "...",
         "remaining_steps": 4
       }
       ```

    4. `report` - 最终诊断报告
       ```json
       {
         "type": "report",
         "stage": "final_report",
         "message": "最终诊断报告已生成",
         "report": "# 故障诊断报告\\n...",
         "evidence": {...}
       }
       ```

    5. `complete` - 诊断完成
       ```json
       {
         "type": "complete",
         "stage": "diagnosis_complete",
         "message": "诊断流程完成",
         "diagnosis": {...}
       }
       ```

    6. `error` - 错误信息
       ```json
       {
         "type": "error",
         "stage": "error",
         "message": "诊断过程发生错误: ..."
       }
       ```

    **使用示例：**
    ```bash
    curl -X POST "http://localhost:9983/api/aiops" \\
      -H "Content-Type: application/json" \\
      -d '{"session_id": "session-123"}' \\
      --no-buffer
    ```

    **前端使用示例：**
    ```javascript
    const eventSource = new EventSource('/api/aiops');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'plan') {
        console.log('诊断计划:', data.plan);
      } else if (data.type === 'step_complete') {
        console.log('步骤完成:', data.current_step);
      } else if (data.type === 'report') {
        console.log('最终报告:', data.report);
      } else if (data.type === 'complete') {
        console.log('诊断完成');
        eventSource.close();
      }
    };
    ```

    Args:
        request: AIOps 诊断请求

    Returns:
        SSE 事件流
    """
    session_id = request.session_id or "default"
    task = (request.task or "").strip()
    use_multi_agent = request.multi_agent
    logger.info(
        f"[会话 {session_id}] 收到 AIOps 请求（流式），"
        f"task={'自定义任务' if task else '默认诊断'}，"
        f"mode={'多Agent' if use_multi_agent else '单Agent'}"
    )

    async def event_generator():
        try:
            if use_multi_agent:
                # 多 Agent 协作模式：直接由 multi_agent_service 执行用户任务
                async for event in multi_agent_service.execute(
                    task or "分析当前系统告警并生成诊断报告", session_id=session_id
                ):
                    yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
                    if event.get("type") in ["complete", "error"]:
                        break
            elif task:
                # 单 Agent 模式：自定义任务
                async for event in aiops_service.execute(task, session_id=session_id):
                    yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
                    if event.get("type") in ["complete", "error"]:
                        break
            else:
                # 单 Agent 模式：默认诊断
                async for event in aiops_service.diagnose(session_id=session_id):
                    yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
                    if event.get("type") in ["complete", "error"]:
                        break

            logger.info(f"[会话 {session_id}] AIOps 流式响应完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] AIOps 诊断流式响应异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "error", "stage": "exception", "message": f"诊断异常: {str(e)}"},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())
