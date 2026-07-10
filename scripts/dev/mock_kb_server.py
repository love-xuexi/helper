"""本地联调用：模拟内网知识库平台（文档检索 + 管理接口），监听 127.0.0.1:5353。

用法见 docs/local-dev-guide.md。
"""

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()

CHUNKS = [
    {
        "id": "chunk-001",
        "content": "排查 CPU 飙高问题时，第一步应使用 top 命令查看占用最高的进程，"
        "随后用 top -Hp <pid> 定位具体线程，并结合 jstack 导出线程栈分析热点代码。",
        "document_id": "doc-ops-01",
        "document_keyword": "运维手册-CPU问题排查.pdf",
        "dataset_id": "kb-ops",
        "similarity": 0.92,
    },
    {
        "id": "chunk-002",
        "content": "若 CPU 高由 GC 频繁引起，可通过 jstat -gcutil 观察 GC 情况，" "必要时调整堆大小或排查内存泄漏。",
        "document_id": "doc-ops-02",
        "document_keyword": "JVM调优指南.docx",
        "dataset_id": "kb-ops",
        "similarity": 0.85,
    },
]


@app.post("/v1/doc/retrieval/")
async def retrieval(request: Request):
    body = await request.json()
    print("KB retrieval called, query =", body.get("query"))
    return {"code": 0, "message": "success", "data": {"chunks": CHUNKS}}


@app.get("/api/v1/kbs/listkbs")
async def list_kbs():
    return {"code": 0, "data": [{"id": "kb-ops", "name": "运维知识库"}]}


@app.get("/api/v1/kbs/{kb_id}/docs")
async def list_docs(kb_id: str):
    return {
        "code": 0,
        "data": [
            {"id": "doc-ops-01", "name": "运维手册-CPU问题排查.pdf"},
            {"id": "doc-ops-02", "name": "JVM调优指南.docx"},
        ],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5353)
