# MinerU 与 LangChain 结合方案报告

> —— 面向知识库 RAG 系统的文档解析与切分能力升级

| 项目 | 内容 |
|------|------|
| 报告主题 | MinerU（文档解析）+ LangChain（文档切分）结合方案 |
| 目标读者 | 技术负责人 / 业务领导 |
| 编写日期 | 2026 年 7 月 |
| 关联系统 | 知行智能 Agent（super-biz-agent-py）RAG 知识库 |

---

## 一、摘要（Executive Summary）

当前知识库系统使用 MinerU 进行文档的解析与切分，但在实际使用中发现**语义切分效果不理想**——文档分块边界常常切断语义，导致向量检索召回质量受限。经调研，LangChain 拥有丰富且成熟的文档切分能力（含基于 Embedding 的语义切分），而 MinerU 的核心强项实为**文档结构化解析**而非语义切分。

**核心结论：MinerU 与 LangChain 并非竞争关系，而是 RAG 流水线中上下游的互补关系。**

- **MinerU = 文档解析层**：负责把 PDF / Word / PPT / 图片等非结构化文档"读懂"，还原版面、公式、表格，输出结构化 Markdown。
- **LangChain = 文档切分层**：负责把 Markdown 切成语义完整的分块（Chunk），再交给 Embedding 入库。

**推荐方案**：将 MinerU 作为前置解析层，LangChain 作为后置切分入库层，二者串联形成 `解析 → 切分 → 向量化 → 入库` 的完整流水线。这样既发挥 MinerU 的版面还原能力，又利用 LangChain 的语义切分优势，可显著提升知识库检索质量。现有代码库已具备 LangChain 切分基础设施，集成成本可控。

---

## 二、背景与问题陈述

### 2.1 现状

我司知识库 RAG 系统当前采用 MinerU 完成文档的解析与切分，整体链路为：

```
原始文档 → MinerU（解析 + 切分）→ Embedding → 向量库（Milvus）→ 检索问答
```

### 2.2 痛点

| 问题 | 表现 | 影响 |
|------|------|------|
| 语义切分效果不佳 | 分块边界常落在语义不完整处（如句中、表头与数据分离） | 检索到的 chunk 文意断裂，LLM 答非所问 |
| 切分策略单一 | 缺乏基于语义相似度的自适应切分 | 长短不一的段落被等长切割，语义聚散失真 |
| 文件类型受限 | 现有代码库上传仅支持 `.md` / `.txt` | PDF / Word / PPT 等办公文档无法直接入库 |

### 2.3 诉求

引入 LangChain 丰富的文档切分能力（尤其语义切分），与 MinerU 结合，全面提升知识库从"文档解析"到"分块入库"的全链路质量。

---

## 三、MinerU 技术解析

### 3.1 定位

MinerU 是**上海人工智能实验室（OpenDataLab）**开源的智能文档解析平台（GitHub Star 2.5 万+），核心能力是将 PDF、Word、PPT、Excel、图片、网页等**非结构化文档**转换为**结构化结果**，输出 Markdown 或元素级 JSON 两种形态。

> **关键认知：MinerU 在 RAG 链路中的正确定位是"结构化抽取层"——位于原始文档和切分器（Chunker）之间，为后续切片提供保留版面语义的输入。它解决的是"把文档读对"的问题，而非"把文档切好"的问题。**

### 3.2 核心能力

| 能力 | 说明 |
|------|------|
| 版面布局检测 | 使用 DocLayoutYOLO / LayoutLMv3 识别标题、正文、图片、表格、脚注等元素位置与阅读顺序 |
| 公式识别 | 基于 YOLOv8 公式检测 + UniMERNet 识别，将数学公式还原为可编译 LaTeX（`$E=mc^2$`） |
| 表格识别 | 还原跨页、合并单元格的表格为 HTML / Markdown 结构 |
| OCR 识别 | 支持扫描版 PDF、图片文档的文字识别，中英文等多语种 |
| 多栏重排 | 双栏 / 多栏文档按正确阅读顺序重排，避免文本流错乱 |
| 多格式输出 | Markdown（保留标题层级、公式、表格、列表）+ 元素级 JSON（含坐标与类型） |
| Office 直解析 | 原生支持 DOCX/PPTX/XLSX，保留修订痕迹、备注等元数据 |

### 3.3 两种解析后端

| 维度 | Pipeline 后端（传统流水线） | VLM 后端（视觉语言模型） |
|------|----------------------------|--------------------------|
| 原理 | CV 规则 + OCR 引擎组合 | 视觉语言大模型一体化理解 |
| 速度 | 2–5 秒/页 | 0.5–1 秒/页（需 sglang 加速） |
| 模型体积 | 多模型约 5GB | 单模型约 2GB |
| 最低配置 | CPU + 8GB 内存 | GPU 8GB + 16GB 内存 |
| 适用场景 | 扫描件、清晰度尚可的文档 | 复杂学术论文、古籍、杂志、多栏图文混排 |

### 3.4 输出示例

MinerU 解析 PDF 后输出目录结构：

```
demo.pdf
└── mineru_output/
    ├── demo.md            ← 完整 Markdown 输出（含标题层级、公式 LaTeX、表格 HTML）
    ├── demo.json          ← 元素级 JSON（含坐标、类型、内容）
    └── images/            ← 内嵌图片资源
```

同一份含公式和表格的技术报告 PDF，`pdfplumber` 抽取纯文本约 3,200 字符，MinerU 输出 Markdown 约 5,800 字符——多出的部分正是公式 LaTeX、表格 HTML 结构和栏顺序校正带来的内容，这些对向量检索至关重要。

### 3.5 行业评测表现

MinerU 2.5 Pro 在 OmniDocBench v1.6 上取得总体分数 95.69（基线 92.98），在公式识别（CDM 97.29）和表格识别（TEDS 93.42）两个对 RAG 召回影响最大的维度上均处于行业领先。

---

## 四、LangChain 文档切分技术解析

### 4.1 定位

LangChain 是当前最主流的 LLM 应用开发框架（GitHub Star 9 万+，月下载量 1 亿+），其 `langchain-text-splitters` 子包提供了业界最丰富的文档切分能力。它解决的是"把文档切好"的问题——在控制分块大小的同时，保证每个分块的语义完整性。

> **现有代码库已使用 LangChain 切分**：`app/services/document_splitter_service.py` 已采用 `MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter` 两阶段切分，但仅支持 `.md` / `.txt`，且未启用语义切分。

### 4.2 切分策略全景

LangChain 提供由浅入深的四层切分策略：

| 层级 | 策略 | 代表组件 | 原理 | 适用场景 |
|------|------|----------|------|----------|
| ① 基于长度 | 固定长度 / Token 切分 | `CharacterTextSplitter` | 按字符数或 Token 数硬切 | 最简单，基线方案 |
| ② 基于结构 | 递归字符切分 | `RecursiveCharacterTextSplitter` | 按分隔符优先级（段落→句→词）递归切分 | **最常用**，当前系统已采用 |
| ② 基于结构 | Markdown 标题切分 | `MarkdownHeaderTextSplitter` | 按 `#`/`##` 标题层级切分，保留标题元数据 | Markdown 文档，当前系统已采用 |
| ② 基于结构 | HTML / JSON / 代码切分 | `HTMLHeaderTextSplitter` / `RecursiveJsonSplitter` | 按文档格式语法结构切分 | 网页、JSON、代码 |
| ③ 基于语义 | 语义切分 | `SemanticChunker` | 基于 Embedding 相似度自适应切分 | **本次重点引入** |
| ④ 基于 Agent | 智能切分 | LLM 驱动切分 | 让 LLM 判断语义边界 | 高质量但成本高 |

### 4.3 SemanticChunker（语义切分器）详解

这是本次升级的关键武器，属于 LangChain 实验性组件（`langchain_experimental.text_splitter`）。

**工作原理**：

```
1. 按句子切分文本（正则 r"(?<=[.?!])\s+"）
2. 对相邻句子组计算 Embedding 向量
3. 计算相邻句子组的语义距离（余弦距离）
4. 当语义距离超过阈值时，在此处切分
5. 语义相近的句子合并为同一 chunk
```

**核心参数**：

| 参数 | 说明 | 取值 |
|------|------|------|
| `breakpoint_threshold_type` | 断点阈值类型 | `percentile`（默认，取距离分布的百分位）/ `standard_deviation`（均值+N倍标准差）/ `interquartile`（基于四分位距）/ `gradient`（基于距离梯度） |
| `breakpoint_threshold_amount` | 阈值数值 | percentile 默认 95，standard_deviation 默认 3，interquartile 默认 1.5 |
| `buffer_size` | 比较相似度时的句子窗口大小 | 默认 1 |
| `number_of_chunks` | 目标分块数（可选） | 设定后按数量切分 |
| `min_chunk_size` | 最小分块大小 | 避免过小碎片 |

**代码示例**：

```python
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

# 基于现有系统的 Embedding 服务初始化
embeddings = OpenAIEmbeddings(model=config.embedding_model)

semantic_splitter = SemanticChunker(
    embeddings,
    breakpoint_threshold_type="percentile",   # 按距离分布的95百分位作为切分点
    breakpoint_threshold_amount=95,
    buffer_size=1,
    min_chunk_size=300,
)

# MinerU 输出的 Markdown 文本喂给语义切分器
chunks = semantic_splitter.split_text(mineru_markdown_content)
```

### 4.4 切分效果对比

业界基准测试（3 篇 arXiv 论文，8 个 query）显示切分策略对召回率的影响：

| 切分策略 | Top-1 命中率 | Top-3 命中率 |
|----------|-------------|-------------|
| 朴素文本切分（pdfplumber + 递归字符） | 25.0% | 50.0% |
| Markdown-aware 切分（MinerU 输出 + 递归字符） | 50.0% | 75.0% |
| 元素级 JSON + 自定义切分 | 62.5% | 87.5% |

> 数据表明：解析质量（MinerU）与切分策略（LangChain）共同决定召回上限，二者缺一不可。

---

## 五、二者能力对比与互补定位

### 5.1 能力对比

| 维度 | MinerU | LangChain Text Splitters |
|------|--------|--------------------------|
| **核心职责** | 文档**解析**（非结构化 → 结构化） | 文档**切分**（长文本 → 语义块） |
| **输入** | PDF / Word / PPT / Excel / 图片 / 网页 | 文本 / Markdown / HTML / JSON |
| **输出** | Markdown / 元素级 JSON | `List[Document]`（含 page_content + metadata） |
| **技术侧重** | 版面检测、OCR、公式/表格识别 | 分块大小控制、语义边界识别、元数据保留 |
| **是否需要模型** | 是（布局/公式/OCR 模型，或 VLM） | 语义切分需 Embedding 模型；其余无需 |
| **在 RAG 中的环节** | 前置：解析层 | 中置：切分层 |
| **能否独立完成全链路** | 不能（切分能力弱） | 不能（无法解析 PDF 等） |

### 5.2 互补关系图

```
┌─────────────────────────────────────────────────────────────┐
│                     RAG 知识库构建流水线                       │
├──────────┬──────────────┬───────────────┬───────────────────┤
│  原始文档  │   MinerU     │   LangChain   │   Embedding+Milvus │
│ PDF/Word/ │  (解析层)     │   (切分层)     │   (向量化+入库)    │
│ PPT/图片  │              │               │                   │
│          │  版面还原     │  结构切分      │                   │
│          │  公式→LaTeX   │  语义切分      │                   │
│          │  表格→HTML    │  小片合并      │                   │
│          │  OCR 识别     │  Token预算控制  │                   │
└──────────┴──────────────┴───────────────┴───────────────────┘
   非结构化      结构化 Markdown       语义完整的 Chunk         向量索引
```

**一句话总结：MinerU 负责"把文档读对"，LangChain 负责"把文档切好"，二者分工明确，天然适配。**

---

## 六、结合方案设计

### 6.1 目标架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         文档入库流水线（升级后）                       │
└─────────────────────────────────────────────────────────────────────┘

  用户上传                  MinerU 解析层                  LangChain 切分层
 ┌──────────┐            ┌──────────────────┐          ┌────────────────────┐
 │ PDF      │            │  Pipeline / VLM  │          │ MarkdownHeader     │
 │ Word     │──上传──▶  │  版面布局检测     │──Markdown│ Splitter           │
 │ PPT      │            │  公式/表格识别    │          │ (按标题切分+元数据) │
 │ Excel    │            │  OCR             │          │        ↓           │
 │ 图片     │            │  多栏重排        │          │ SemanticChunker    │
 │ Markdown │──────┐     └──────────────────┘          │ (语义切分,可选)    │
 │ TXT      │      │              │                     │        ↓           │
 └──────────┘      │              │                     │ RecursiveCharacter │
                   │              │                     │ TextSplitter       │
                   │              │                     │ (大小控制+重叠)    │
                   │              │                     │        ↓           │
                   │              │                     │ 小片段合并+Token预算│
                   │(原有路径)     │                     └─────────┬──────────┘
                   │              │                               │
                   └──────────────┴───────────────────────────────▶│
                                                                  │
                                                    List[Document]│
                                                          ↓       │
                                              ┌───────────────────┐│
                                              │  Embedding 服务    ││
                                              │  (OpenAI 兼容)     ││
                                              └─────────┬─────────┘│
                                                        │          │
                                              ┌─────────▼─────────┐│
                                              │   Milvus 向量库     ││
                                              │  (biz collection)  ││
                                              └─────────────────────┘│
```

### 6.2 分层职责定义

| 层级 | 组件 | 职责 | 技术 |
|------|------|------|------|
| **L1 解析层** | MinerU | 非结构化文档 → 结构化 Markdown | Pipeline/VLM 后端，OCR，公式/表格识别 |
| **L2 切分层** | LangChain Text Splitters | Markdown → 语义完整的 Chunk | 标题切分 + 语义切分 + 递归切分 + 小片合并 |
| **L3 向量化层** | Embedding 服务 | Chunk → 向量 | OpenAI 兼容 Embedding API |
| **L4 存储层** | Milvus | 向量 + 元数据持久化 | langchain-milvus 集成 |

### 6.3 关键设计决策

**决策 1：MinerU 输出 Markdown，而非元素级 JSON**

- Markdown 输出可直接复用现有 `MarkdownHeaderTextSplitter`，改造成本最低
- Markdown 的 `#`/`##`/`$$`/`|---|` 天然提供语义段落边界
- 元素级 JSON 虽然更精细，但需自定义切分逻辑，开发量大，建议二期考虑

**决策 2：三阶段切分流水线（结构 → 语义 → 大小）**

```
阶段1: MarkdownHeaderTextSplitter   →  按标题切分，保留 h1/h2 元数据
阶段2: SemanticChunker              →  按语义相似度自适应切分（新增）
阶段3: RecursiveCharacterTextSplitter →  控制分块大小 + overlap
后处理: 小片段合并 + Token 预算控制    →  复用现有逻辑
```

**决策 3：语义切分作为可配置开关**

- 语义切分需调用 Embedding API，有额外开销
- 通过配置项 `CHUNK_USE_SEMANTIC=true|false` 控制是否启用
- 对长文档（如技术手册）启用，对短文档可关闭

---

## 七、与现有系统的集成路径

### 7.1 现有系统现状

现有代码库（`app/services/document_splitter_service.py`）已具备：

| 已有能力 | 实现方式 |
|----------|----------|
| Markdown 标题切分 | `MarkdownHeaderTextSplitter`（按 `#`/`##` 切分，保留 h1/h2 元数据） |
| 递归字符切分 | `RecursiveCharacterTextSplitter`（chunk_size 加倍，控制大小） |
| 小片段合并 | `_merge_small_chunks`（<300 字符合并到前一片） |
| Token 预算控制 | `_enforce_embedding_token_budget`（防超 Embedding 最大 Token） |
| 硬切兜底 | `_hard_split_document`（极端超长时逐字符切） |
| 向量入库 | `vector_store_manager.add_documents` → Milvus |

**缺口**：
1. ❌ 无 MinerU 解析层，不支持 PDF/Word/PPT/图片上传
2. ❌ 无语义切分（SemanticChunker）
3. ❌ 文件上传接口仅允许 `.txt` / `.md`

### 7.2 集成改造点

#### 改造点 1：新增 MinerU 解析服务

新增 `app/services/mineru_parser_service.py`：

```python
"""MinerU 文档解析服务 - 将非结构化文档解析为 Markdown"""

class MinerUParserService:
    """调用 MinerU（本地部署或 API）解析 PDF/Word/PPT/图片为 Markdown"""

    def parse_to_markdown(self, file_path: str) -> str:
        """
        解析文档为 Markdown 文本

        Args:
            file_path: 原始文档路径（pdf/docx/pptx/png 等）

        Returns:
            str: MinerU 输出的 Markdown 文本
        """
        # 方式一：调用 MinerU 官方 API（mineru.net）
        # 方式二：调用私有化部署的 MinerU 服务
        # 方式三：本地调用 magic-pdf CLI
        ...
```

#### 改造点 2：扩展文档分割服务

在 `document_splitter_service.py` 中新增语义切分支持：

```python
from langchain_experimental.text_splitter import SemanticChunker

class DocumentSplitterService:
    def __init__(self):
        # ... 现有初始化 ...
        self.use_semantic = config.chunk_use_semantic  # 新增配置项
        if self.use_semantic:
            self.semantic_splitter = SemanticChunker(
                embeddings=vector_embedding_service.embeddings,
                breakpoint_threshold_type="percentile",
                breakpoint_threshold_amount=95,
                min_chunk_size=300,
            )

    def split_markdown(self, content: str, file_path: str = "") -> List[Document]:
        # 阶段1: 标题切分（现有）
        md_docs = self.markdown_splitter.split_text(content)

        # 阶段2: 语义切分（新增，可选）
        if self.use_semantic:
            md_docs = self._semantic_split(md_docs)

        # 阶段3: 大小控制（现有）
        docs_after_split = self.text_splitter.split_documents(md_docs)

        # 后处理：小片合并 + Token 预算（现有）
        ...
```

#### 改造点 3：扩展文件上传接口

在 `app/api/file.py` 中放宽文件类型限制，对非 txt/md 文件先走 MinerU 解析：

```python
ALLOWED_EXTENSIONS = ["txt", "md", "pdf", "docx", "pptx", "xlsx", "png", "jpg"]

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ...
    if file_extension in ["pdf", "docx", "pptx", "xlsx", "png", "jpg"]:
        # 非 Markdown/TXT 文档：先经 MinerU 解析为 Markdown
        markdown_content = mineru_parser_service.parse_to_markdown(str(file_path))
        # 再走现有切分入库流程
        documents = document_splitter_service.split_markdown(markdown_content, str(file_path))
    else:
        # 原有 .md/.txt 路径不变
        content = file_path.read_text(encoding="utf-8")
        documents = document_splitter_service.split_document(content, str(file_path))
    ...
```

#### 改造点 4：新增配置项

在 `.env` 和 `config.py` 中新增：

```bash
# MinerU 配置
MINERU_MODE=api                    # api | local
MINERU_API_URL=https://mineru.net  # 或私有化部署地址
MINERU_API_TOKEN=your-token
MINERU_BACKEND=pipeline            # pipeline | vlm
MINERU_LANGUAGE=ch                 # ch | en

# 语义切分配置
CHUNK_USE_SEMANTIC=true            # 是否启用语义切分
CHUNK_SEMANTIC_THRESHOLD=percentile
CHUNK_SEMANTIC_PERCENTILE=95
```

### 7.3 改造影响评估

| 改造项 | 影响范围 | 风险 | 兼容性 |
|--------|----------|------|--------|
| 新增 MinerU 解析服务 | 新文件，不影响现有 | 低 | 100% 兼容现有 |
| 扩展分割服务 | `document_splitter_service.py` 增加分支 | 低 | 配置开关控制，默认可关闭 |
| 扩展上传接口 | `file.py` 增加文件类型 | 低 | 原 .md/.txt 路径不变 |
| 新增配置项 | `.env` + `config.py` | 低 | 提供合理默认值 |

> **核心原则：所有改造均向后兼容，通过配置开关控制，不破坏现有 .md/.txt 的处理链路。**

---

## 八、实施路线图

### 阶段一：MinerU 解析层接入（1–2 周）

| 任务 | 产出 | 验收标准 |
|------|------|----------|
| MinerU 部署/接入 | API 或本地服务可用 | 能将测试 PDF 解析为 Markdown |
| 新增 `MinerUParserService` | 解析服务代码 | 单元测试通过 |
| 扩展上传接口 | 支持 PDF/Word 上传 | PDF 上传后成功入库 |
| 端到端联调 | 完整链路跑通 | PDF → Markdown → 切分 → 入库 → 检索 |

### 阶段二：语义切分增强（1 周）

| 任务 | 产出 | 验收标准 |
|------|------|----------|
| 引入 SemanticChunker | 语义切分代码 | 配置开关生效 |
| 切分流水线调优 | 阈值参数 | 对测试文档切分质量优于纯字符切分 |
| 对比评测 | 评测报告 | 语义切分 Top-K 召回率提升 |

### 阶段三：优化与评估（1 周）

| 任务 | 产出 | 验收标准 |
|------|------|----------|
| 批量文档评测 | 召回率对比报告 | 召回率较升级前提升 |
| 大文件处理优化 | 分页解析策略 | 50+ 页 PDF 不 OOM |
| 增量更新策略 | 文件哈希去重 | 重复入库不产生冗余分片 |

### 里程碑

```
第1-2周 ████████████  MinerU 解析层接入
第3周   ██████        语义切分增强
第4周   ██████        优化与评估
        ↓
     全链路上线
```

---

## 九、预期收益

### 9.1 检索质量提升

| 指标 | 当前（预估） | 升级后（预期） | 提升幅度 |
|------|-------------|---------------|----------|
| Top-1 召回命中率 | ~50% | ~75%+ | +25 个百分点 |
| Top-3 召回命中率 | ~70% | ~87%+ | +17 个百分点 |
| 公式/表格类查询命中 | 低 | 显著提升 | 公式 LaTeX 保留可被精确检索 |

### 9.2 能力扩展

| 能力 | 升级前 | 升级后 |
|------|--------|--------|
| 支持文件类型 | `.md` / `.txt` | PDF / Word / PPT / Excel / 图片 / Markdown / TXT |
| 切分策略 | 标题切分 + 字符切分 | 标题切分 + **语义切分** + 字符切分 |
| 版面还原 | 无 | 双栏重排、表格结构、公式 LaTeX |
| 扫描件支持 | 无 | OCR 识别 |

### 9.3 业务价值

1. **知识库覆盖面扩大**：可直接沉淀 PDF 运维手册、Word 操作规程、PPT 培训材料，无需人工转 Markdown
2. **问答准确率提升**：语义切分保证 chunk 语义完整，减少"答非所问"
3. **专业文档可检索**：含公式、表格的技术文档可被精准检索（LaTeX / HTML 结构保留）
4. **降低运维成本**：减少人工文档预处理工作量

---

## 十、风险与注意事项

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| MinerU 大文件 OOM | 50+ 页 PDF 内存峰值高 | 采用 `split_pages=True` 分页解析；flash 模式限 20 页内单次处理 |
| 扫描件 OCR 精度 | 低 DPI 扫描件识别率下降 | 检测无文本层 PDF 时自动切换 precision + OCR 模式 |
| 语义切分额外开销 | 每次 Cut 需调 Embedding API | 配置开关控制；仅对长文档启用；缓存句子 Embedding |
| MinerU 依赖体积 | 本地部署需下载模型（~2–5GB） | 优先使用官方 API；私有化部署时统一规划 GPU 资源 |
| 增量更新元数据漂移 | 文档版本迭代后旧分片残留 | 基于文件哈希（SHA256）判断是否需重新入库；按 `_source` 精确清理旧分片（现有逻辑已支持） |
| Markdown 切分兼容性 | MinerU Markdown 格式与手写 Markdown 略有差异 | 验证 `MarkdownHeaderTextSplitter` 对 MinerU 输出的兼容性；必要时做格式归一化 |

---

## 十一、结论与建议

### 11.1 核心结论

1. **MinerU 与 LangChain 是互补而非竞争关系**。MinerU 擅长文档解析（版面/公式/表格还原），LangChain 擅长文档切分（含语义切分），二者分别处于 RAG 流水线的不同环节。

2. **当前"MinerU 既解析又切分"的用法未发挥各自长项**。MinerU 的切分能力偏弱（主要按页/按元素），而 LangChain 拥有业界最丰富的切分策略（含基于 Embedding 的 SemanticChunker）。

3. **推荐采用"MinerU 解析 + LangChain 切分"的串联架构**。MinerU 输出的 Markdown 天然适配 LangChain 的 `MarkdownHeaderTextSplitter`，集成改造成本低，且现有代码库已具备 LangChain 切分基础设施。

### 11.2 实施建议

| 优先级 | 建议 |
|--------|------|
| ★★★ 高 | 优先接入 MinerU 解析层，扩展 PDF/Word 文件支持，解决"无文档可切"问题 |
| ★★★ 高 | 引入 SemanticChunker 语义切分，解决"切分语义不完整"核心痛点 |
| ★★☆ 中 | 建立召回率评测基准，量化验证升级效果 |
| ★☆☆ 低 | 二期考虑元素级 JSON + 自定义切分，追求极致召回 |

### 11.3 总结

> 本方案以最小改造成本，将 MinerU 的文档解析能力与 LangChain 的语义切分能力结合，在"向后兼容现有系统"的前提下，系统性地解决当前知识库"文件类型受限"与"语义切分不佳"两大痛点。预期可使 Top-1 召回率提升约 25 个百分点，并显著扩展知识库可消化的文档类型范围。

---

## 十二、多模态数据处理深度解析（图片 / 表格 / 公式）

> 前述章节聚焦文本流的解析与切分。但知识库文档（尤其 PDF / PPT）常包含**图片、表格、公式**等多模态元素，这些元素的处理流程与纯文本有本质区别。本章专门阐述多模态数据的完整处理链路。

### 12.1 多模态数据为何是 RAG 的难点

纯文本 RAG 的流程清晰：`文本 → 切分 → 文本 Embedding → 向量库 → 检索 → LLM 生成`。但一旦文档中出现图片、表格、公式，就会遇到三个核心挑战：

| 挑战 | 说明 |
|------|------|
| ① 图片无法直接文本切分 | 图片是二进制像素数据，不能用 `RecursiveCharacterTextSplitter` 按字符切 |
| ② 表格被字符切分会"断裂" | 朴素按字符长度切分，会把表格从中间切开，表头与数据分离，语义全毁 |
| ③ 文本 Embedding 模型无法嵌入图片 | 当前系统使用的 OpenAI 兼容文本 Embedding 只接受字符串输入 |

**因此，多模态数据需要一套独立的处理策略，而非简单地"一刀切"。**

### 12.2 MinerU 如何解析处理多模态元素

MinerU 的核心价值正是精准剥离并结构化这些多模态元素。解析完成后，所有元素统一沉淀在一个输出目录中。

#### 12.2.1 MinerU 输出目录结构

```
processed/{job-id}/{document-name}/auto/
├── {document-name}.md              ← 主 Markdown 文档（含文本 + 图片引用 + 表格 + 公式）
├── {document-name}_content_list.json   ← 内容列表元数据（元素级，含类型/坐标）
├── {document-name}_middle.json     ← 中间处理结果
├── {document-name}_model.json      ← 模型输出数据
├── {document-name}_layout.pdf      ← 布局分析可视化（调试用）
├── {document-name}_span.pdf        ← Span 信息可视化
├── {document-name}_origin.pdf      ← 原始 PDF 备份
└── images/                         ← 提取的所有图片（SHA256 哈希命名）
    ├── 129c1105fc166bb5.jpg
    ├── 13ab640c16d9358e.jpg
    └── 20974eda45b12f07.jpg
```

#### 12.2.2 各多模态元素的输出形态

**① 图片 → 独立文件 + Markdown 引用**

- 图片被**物理抽取**到 `images/` 目录，以 SHA256 哈希前 16 位命名（避免重复和冲突）
- 在 Markdown 中以标准图片语法引用：

```markdown
![图表描述](images/129c1105fc166bb5.jpg)
```

- 图片与正文上下文关联被保留（MinerU 会"精准剥离图文并保留上下文关联"）

**② 表格 → HTML 结构（默认）**

- 表格被还原为 HTML 格式，保留行列结构、合并单元格：

```html
<table>
  <tr>
    <th>指标</th><th>Q1</th><th>Q2</th>
  </tr>
  <tr>
    <td>营收</td><td>1.2亿</td><td>1.5亿</td>
  </tr>
</table>
```

- 同时支持输出 CSV / Markdown 表格格式，可按需选择
- HTML 格式对 LLM 最友好（结构完整，LLM 能理解行列关系）

**③ 公式 → LaTeX 代码**

- 行内公式：`$E = mc^2$`
- 行间公式：

```latex
$$
L_{CE} = -\sum_{i=1}^{C} y_i \log \hat{y}_i
$$
```

- 复杂公式（含矩阵、积分、上下标）均可精准还原为可编译 LaTeX

**④ 文本 → 保留结构的 Markdown**

- 标题层级（`#` / `##` / `###`）保留
- 段落、列表、缩进保留
- 多栏排版按正确阅读顺序重排

#### 12.2.3 content_list.json 元素级结构

除了 Markdown，MinerU 还输出 `content_list.json`，将文档拆解为有序的元素列表：

```json
[
  {"type": "text",    "text": "# 概述\n本报告...", "page_idx": 0},
  {"type": "image",   "img_path": "images/129c1105fc166bb5.jpg", "img_caption": "图1 架构图", "page_idx": 0},
  {"type": "table",   "html": "<table>...</table>", "table_caption": "表1 季度数据", "page_idx": 1},
  {"type": "equation","latex": "$$L_{CE}=...$$", "page_idx": 1},
  {"type": "text",    "text": "如上表所示...", "page_idx": 1}
]
```

> **关键认知：MinerU 的 `content_list.json` 是多模态处理的"黄金输入"——它把文档拆成了带类型标签的元素序列，下游可以按类型分别处理。**

### 12.3 MinerU 输出后，LangChain 如何切分含图片表格的数据

这是本方案的核心技术点。MinerU 输出的 Markdown 中**混合了文本、图片引用、HTML 表格、LaTeX 公式**，直接用 `RecursiveCharacterTextSplitter` 会有两个问题：

1. **表格被切碎**：字符切分可能在表格中间断开
2. **图片引用与上下文分离**：图片 `![]()` 可能被切到一个 chunk，而它的说明文字在另一个 chunk

#### 12.3.1 推荐方案：MultiVectorRetriever（多向量检索器）

LangChain 官方推荐使用 **`MultiVectorRetriever`** 处理半结构化（表格）和多模态（图片）数据。其核心思想是：

> **解耦"检索依据"与"返回内容"——用摘要/描述做向量检索，但返回原始完整内容给 LLM。**

```
┌─────────────────────────────────────────────────────────────┐
│              MultiVectorRetriever 工作机制                    │
└─────────────────────────────────────────────────────────────┘

  原始文档元素                检索依据(存向量库)           返回内容(存DocStore)
 ┌──────────────┐          ┌──────────────┐           ┌──────────────┐
 │ 文本段落      │──嵌入──▶ │ 文本向量      │           │ 文本段落      │
 ├──────────────┤          ├──────────────┤           ├──────────────┤
 │ HTML 表格     │──LLM摘要 │ 表格摘要向量  │  检索命中  │ 完整HTML表格  │
 │              │──嵌入──▶ │              │───返回──▶ │              │
 ├──────────────┤          ├──────────────┤           ├──────────────┤
 │ 图片          │──LLM摘要 │ 图片描述向量  │           │ 原始图片/引用 │
 │              │──嵌入──▶ │              │           │              │
 └──────────────┘          └──────────────┘           └──────────────┘
        │                         │                          │
        │                         │                          │
        └───── 通过 doc_id 关联 ──┴──────────────────────────┘

  检索流程: 用户Query → 向量相似搜索(在摘要向量中) → 得到doc_id → 从DocStore取原始内容 → 喂给LLM
```

**为什么这样设计？**
- 表格和图片用文本摘要做检索，命中率远高于直接嵌入（文本 Embedding 对自然语言查询更敏感）
- 但生成答案时，把**完整表格/原始图片**喂给 LLM，保证信息无损

#### 12.3.2 三种多模态处理策略

LangChain 提供三种处理图片的策略，按检索与生成方式区分：

| 策略 | 检索方式 | 生成方式 | 适用场景 |
|------|----------|----------|----------|
| **策略 A：多模态 Embedding** | 用 CLIP / Gemini Embedding 等多模态模型同时嵌入文本和图片 | 把原始图片+文本传给多模态 LLM | 有多模态 Embedding 服务，且需图文混合检索 |
| **策略 B：图片转文本摘要（纯文本RAG）** | 用多模态 LLM（GPT-4V/LLaVA）生成图片文字描述，用文本 Embedding 检索 | 只返回文本，图片不参与生成 | 无多模态 LLM，或图片不重要只需检索 |
| **策略 C：图片摘要 + 原图（混合，推荐）** | 用多模态 LLM 生成图片描述，用文本 Embedding 检索摘要，但关联原始图片 | 把原始图片+文本传给多模态 LLM | 兼顾检索精度与生成质量，**推荐** |

**三种策略对比**：

```
策略A: 图片 --CLIP嵌入--> 向量库 --检索--> 原图 --> 多模态LLM生成
策略B: 图片 --LLM摘要--> 文本嵌入 --> 向量库 --检索--> 文本 --> 文本LLM生成
策略C: 图片 --LLM摘要--> 文本嵌入 --> 向量库 --检索(关联doc_id)--> 原图 --> 多模态LLM生成
```

#### 12.3.3 表格的专门处理

表格采用"摘要检索 + 原表返回"模式：

```python
# 伪代码：表格处理流程
for table_element in content_list.tables:
    html = table_element.html  # MinerU 输出的 HTML 表格

    # 1. 用 LLM 生成表格的自然语言摘要
    summary = llm.invoke(f"请用一段话总结这个表格的内容：\n{html}")

    # 2. 摘要做向量化（用于检索）
    summary_vector = embeddings.embed(summary)

    # 3. 存入 MultiVectorRetriever
    #    - 向量库存：summary_vector + doc_id
    #    - DocStore 存：doc_id -> 原始 HTML 表格
    retriever.add(summary_vector, doc_id=table_element.id, content=html)
```

**效果**：用户问"Q2 营收多少？"，向量检索命中表格摘要 → 返回完整 HTML 表格 → LLM 从表中精确提取"1.5亿"。

### 12.4 完整多模态处理流水线（MinerU + LangChain）

结合 MinerU 解析与 LangChain 切分，完整的多模态处理流程如下：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                  多模态文档入库完整流水线                                   │
└──────────────────────────────────────────────────────────────────────────┘

 PDF/Word/PPT
      │
      ▼
 ┌─────────────────────┐
 │  MinerU 解析层       │
 │  - 版面布局检测      │
 │  - 图片抽取→images/ │
 │  - 表格→HTML        │
 │  - 公式→LaTeX       │
 │  - OCR文字识别       │
 └──────────┬──────────┘
            │
            ▼ content_list.json (元素级) + .md (Markdown)
 ┌─────────────────────┐
 │  元素分类器(新增)    │
 │  按type分发处理:     │
 │  - text → 文本切分   │
 │  - table → 摘要+存表 │
 │  - image → 描述+存图 │
 │  - equation→ 保留    │
 └──────┬───┬───┬──────┘
        │   │   │
   ┌────┘   │   └────┐
   ▼        ▼        ▼
 文本流    表格流    图片流
 ┌────┐  ┌────┐   ┌────┐
 │标题│  │LLM │   │LLM │
 │切分│  │摘要│   │描述│
 │语义│  │    │   │生成│
 │切分│  │    │   │    │
 │大小│  │    │   │    │
 │控制│  │    │   │    │
 └─┬──┘  └─┬──┘   └─┬──┘
   │       │        │
   ▼       ▼        ▼
 文本Embed  摘要Embed 描述Embed
   │       │        │
   └───────┼────────┘
           ▼
 ┌─────────────────────┐     ┌─────────────────────┐
 │  向量库(Milvus)      │     │  DocStore(文档存储)   │
 │  存: 向量 + doc_id   │◀───│  存: doc_id → 原始内容│
 │  + metadata(类型)    │     │  (文本/HTML表格/图片) │
 └─────────────────────┘     └─────────────────────┘
           │
           ▼ 检索时
 ┌─────────────────────┐
 │  Query向量          │
 │  → 相似搜索         │
 │  → 得到doc_id列表   │
 │  → 从DocStore取原文 │
 └──────────┬──────────┘
            │
            ▼
 ┌─────────────────────┐
 │  LLM生成(多模态)     │
 │  输入: Query + 文本  │
 │       + HTML表格     │
 │       + 原始图片     │
 │  输出: 图文混排回答   │
 └─────────────────────┘
```

### 12.5 核心代码实现示例

以下为多模态处理的关键代码骨架，展示如何在现有系统中扩展：

```python
"""多模态文档处理服务 - 处理含图片/表格/公式的文档"""

from langchain_core.documents import Document
from langchain_core.stores import InMemoryStore
from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.output_parsers import StrOutputParser

class MultimodalDocumentProcessor:
    """多模态文档处理器"""

    def __init__(self, embeddings, multimodal_llm, vectorstore):
        self.embeddings = embeddings
        self.multimodal_llm = multimodal_llm  # GPT-4V / LLaVA 等
        self.vectorstore = vectorstore

        # MultiVectorRetriever: 向量库存检索依据，DocStore存原始内容
        self.docstore = InMemoryStore()
        self.retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=self.docstore,
            id_key="doc_id",
        )

        # 文本切分器（复用现有逻辑）
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, chunk_overlap=100
        )

    def process_document(self, content_list_json: list, source: str):
        """
        处理 MinerU 输出的 content_list.json

        Args:
            content_list_json: MinerU 元素级输出
            source: 原始文件路径（用于 metadata）
        """
        for idx, element in enumerate(content_list_json):
            doc_id = f"{source}_{idx}"
            elem_type = element["type"]

            if elem_type == "text":
                self._process_text(element["text"], doc_id, source)
            elif elem_type == "table":
                self._process_table(element["html"], doc_id, source, element.get("table_caption"))
            elif elem_type == "image":
                self._process_image(element["img_path"], doc_id, source, element.get("img_caption"))
            elif elem_type == "equation":
                # 公式作为文本处理，LaTeX 本身可被文本 Embedding
                self._process_text(element["latex"], doc_id, source)

    def _process_text(self, text: str, doc_id: str, source: str):
        """文本：常规切分 + 直接嵌入"""
        chunks = self.text_splitter.create_documents(
            [text], metadatas=[{"doc_id": doc_id, "type": "text", "_source": source}]
        )
        self.vectorstore.add_documents(chunks)
        self.docstore.mset([(doc_id, chunks[0])])

    def _process_table(self, html: str, doc_id: str, source: str, caption: str = ""):
        """表格：LLM生成摘要 → 摘要嵌入向量库 → 原HTML存DocStore"""
        # 1. 多模态LLM生成表格摘要
        summary_prompt = f"请用一段话总结以下表格的要点，便于检索：\n表格标题:{caption}\n表格内容:\n{html}"
        summary = (self.multimodal_llm | StrOutputParser()).invoke(summary_prompt)

        # 2. 摘要作为 Document 存入向量库（带 doc_id）
        summary_doc = Document(
            page_content=summary,
            metadata={"doc_id": doc_id, "type": "table_summary", "_source": source}
        )
        self.vectorstore.add_documents([summary_doc])

        # 3. 原始 HTML 表格存入 DocStore（检索时返回这个）
        self.docstore.mset([(doc_id, Document(page_content=html, metadata={"type": "table", "_source": source}))])

    def _process_image(self, img_path: str, doc_id: str, source: str, caption: str = ""):
        """图片：多模态LLM生成描述 → 描述嵌入向量库 → 图片路径存DocStore"""
        # 1. 多模态LLM看图生成文字描述
        description = self.multimodal_llm.invoke([
            {"type": "text", "text": f"请描述这张图片的内容。图片标题:{caption}"},
            {"type": "image_url", "image_url": {"url": f"file://{img_path}"}},
        ])
        description = description.content if hasattr(description, 'content') else str(description)

        # 2. 描述存入向量库
        desc_doc = Document(
            page_content=description,
            metadata={"doc_id": doc_id, "type": "image_description", "_source": source}
        )
        self.vectorstore.add_documents([desc_doc])

        # 3. 原始图片路径存入 DocStore
        self.docstore.mset([(doc_id, Document(
            page_content=f"![{caption}]({img_path})",
            metadata={"type": "image", "img_path": img_path, "_source": source}
        ))])

    def retrieve(self, query: str, k: int = 5):
        """检索：向量搜索摘要 → 返回原始内容"""
        return self.retriever.invoke(query)[:k]
```

### 12.6 若仅用 LangChain（无 MinerU）处理多模态

若不引入 MinerU，纯靠 LangChain 也能处理多模态，但解析能力受限。流程如下：

```
PDF/图片 → Unstructured库分区 → 元素(text/table/image) → MultiVectorRetriever → ...
```

**LangChain 纯净方案（无 MinerU）**：

| 环节 | 工具 | 能力 | 局限 |
|------|------|------|------|
| 文档解析 | `Unstructured` 库 | 用 YOLOX 布局模型提取 text/table/image 元素 | 中文支持弱；复杂表格还原差；无公式识别 |
| 图片提取 | `Unstructured` partition_image | 抽取内嵌图片 | 扫描件 OCR 精度低 |
| 表格还原 | `Unstructured` partition_pdf | 输出 HTML 表格 | 跨页表格、合并单元格处理弱 |
| 公式处理 | ❌ 不支持 | 无公式识别能力 | 公式直接丢失或变乱码 |
| 切分入库 | `MultiVectorRetriever` | 摘要+原文模式 | 同上 |
| 多模态生成 | GPT-4V / LLaVA | 图片理解+生成 | 需多模态 LLM |

**纯 LangChain 代码示例**：

```python
from langchain_community.document_loaders import UnstructuredPDFLoader

# 用 Unstructured 解析 PDF，按元素分区
loader = UnstructuredPDFLoader("doc.pdf", strategy="hi_res")
docs = loader.load()

# 后续走 MultiVectorRetriever（同 12.5 节代码）
```

**结论**：纯 LangChain 方案**能用但效果差**——缺乏 MinerU 的版面检测、公式识别、表格结构化能力，尤其对中文 PDF 和含公式的技术文档表现不佳。**因此强烈推荐 MinerU 做解析层，LangChain 做切分入库层。**

### 12.7 与现有系统的适配建议

结合现有代码库（`super-biz-agent-py`），多模态处理的适配建议如下：

| 现状 | 升级建议 | 优先级 |
|------|----------|--------|
| 仅支持 `.md`/`.txt` 文本切分 | 新增 `MultimodalDocumentProcessor`，处理 MinerU 的 `content_list.json` | ★★★ |
| 无 MultiVectorRetriever | 引入 `MultiVectorRetriever` + `InMemoryStore`（或扩展为 Milvus 的 KV 字段） | ★★★ |
| 无多模态 LLM | 接入 GPT-4V / 通义千问 VL / LLaVA，用于图片描述和表格摘要 | ★★☆ |
| Milvus 仅存文本向量 | metadata 增加 `type` 字段（text/table_summary/image_desc），区分元素类型 | ★★☆ |
| 检索返回纯文本 | 检索命中后从 DocStore 取原始 HTML 表格 / 图片路径，拼入 Prompt | ★★★ |
| 前端仅展示文本 | 前端支持渲染 HTML 表格和图片（Markdown 已支持 `![]()` 和 `<table>`） | ★☆☆ |

### 12.8 多模态处理的取舍建议

| 场景 | 推荐策略 | 理由 |
|------|----------|------|
| 文档以文字为主，图片少 | 策略 B（图片转文本摘要） | 成本低，无需多模态 LLM 生成 |
| 文档含关键图表（架构图、流程图） | 策略 C（摘要+原图） | 检索准 + 生成时能展示原图 |
| 有多模态 Embedding 服务 | 策略 A（CLIP 多模态嵌入） | 图文统一向量空间，检索最自然 |
| 表格密集（财务报表、数据手册） | 表格摘要 + 原表返回 | 避免表格被切碎，保证数据完整 |
| 公式密集（学术论文） | LaTeX 直接文本嵌入 | LaTeX 符号可被文本 Embedding 捕获语义 |

### 12.9 小结

> 多模态数据处理的核心思路是**"分类处理 + 摘要检索 + 原文返回"**：
> - MinerU 负责把图片、表格、公式精准**剥离并结构化**（这是它的强项）
> - LangChain 的 `MultiVectorRetriever` 负责**按元素类型分别处理**：文本直接切分嵌入，表格和图片用 LLM 生成摘要做检索、原始内容存 DocStore 供生成
> - 生成阶段把检索到的**原始 HTML 表格、图片、文本**一起喂给多模态 LLM，实现图文混排的精准问答
>
> 这套方案在保留现有文本处理链路的同时，增量式扩展多模态能力，是知识库从"纯文本 RAG"迈向"多模态 RAG"的关键升级。

---

## 附录 A：技术依赖清单

```bash
# 现有依赖（已在 pyproject.toml 中）
langchain>=0.1.0
langchain-text-splitters>=1.1.0
langchain-milvus>=0.3.3
langchain-openai>=1.1.0

# 需新增依赖
langchain-experimental>=0.3.0     # SemanticChunker 所在包
langchain-mineru>=0.1.0           # MinerU 的 LangChain 集成（可选）
unstructured[hi-res]>=0.15.0      # 纯 LangChain 方案的多模态文档解析（可选，无 MinerU 时使用）
```

### 多模态处理相关组件

| 组件 | 用途 | 来源 |
|------|------|------|
| `MultiVectorRetriever` | 多模态检索（摘要检索+原文返回） | `langchain.retrievers.multi_vector` |
| `InMemoryStore` / `BaseStore` | 存储原始表格/图片内容 | `langchain_core.stores` |
| 多模态 LLM | 图片描述、表格摘要生成 | GPT-4V / 通义千问 VL / LLaVA / FUYU-8b |
| 多模态 Embedding（可选） | 图文统一向量空间 | CLIP / Gemini Embedding / Jina CLIP |

## 附录 B：参考资料

| 资料 | 链接 |
|------|------|
| MinerU 官方仓库 | https://github.com/opendatalab/MinerU |
| MinerU 官网 | https://mineru.net |
| LangChain Text Splitters 文档 | https://docs.langchain.com/oss/python/integrations/splitters |
| LangChain SemanticChunker API | langchain_experimental.text_splitter.SemanticChunker |
| LangChain MultiVectorRetriever 文档 | https://python.langchain.com/docs/how_to/multi_vector/ |
| LangChain 多模态 RAG Cookbook | https://github.com/langchain-ai/langchain/blob/master/cookbook/Semi_structured_and_multi_modal_RAG.ipynb |
| LangChain 半结构化/多模态 RAG 博客 | https://www.langchain.com/blog/semi-structured-multi-modal-rag |
| MinerU + RAG 集成实战 | https://cloud.tencent.com/developer/article/2662542 |
| MinerU + AWS Serverless 企业级 RAG 平台 | https://aws.amazon.com/cn/blogs/china/building-enterprise-rag-document-processing-platform-based-on-mineru-and-aws-serverless |

---

*报告完*
