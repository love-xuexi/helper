"""文档分割服务模块 - 基于 LangChain 的智能文档分割"""

from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from loguru import logger

from app.config import config
from app.services.embedding_input_guard import estimate_tokens


class DocumentSplitterService:
    """
    文档分割服务 - 使用 LangChain 的分割器

    这个服务的最终结果不是直接写数据库，而是把一整篇文档切成多个 LangChain Document。
    每个 Document 可以理解成一个“可被向量化和检索的文本块”，结构大概长这样：
    Document(
        page_content="这一段是真正要参与 embedding 的文本内容...",
        metadata={
            "_source": "/abs/path/uploads/a.md",
            "_extension": ".md",
            "_file_name": "a.md",
            "h1": "一级标题",
            "h2": "二级标题"
        }
    )

    上游 vector_index_service 会拿到这里返回的 List[Document]，
    再调用 vector_store_manager.add_documents(...) 把这些文本块转成向量并写入 Milvus。
    """

    def __init__(self):
        """初始化文档分割服务"""
        self.chunk_size = config.chunk_max_size
        self.chunk_overlap = config.chunk_overlap
        self.embedding_token_budget = max(
            1, config.embedding_max_tokens - config.embedding_token_safety_margin
        )

        # Markdown 标题分割器 (只按一级和二级标题分割，减少分片数)
        # 例如 Markdown 内容：
        # # 故障处理
        # ## CPU 过高
        # xxx
        # 分割后 Document.metadata 里会带上 {"h1": "故障处理", "h2": "CPU 过高"}
        # 这些标题元数据后续会和正文一起存入 Milvus，方便知道分片来自哪个章节
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                # 不再按三级标题分割，避免过度碎片化
            ],
            strip_headers=False,  # 保留标题在内容中
        )

        # 递归字符分割器 (用于二次分割，使用更大的chunk_size)
        # 它负责控制每个分片不要太长：
        # - chunk_size 表示单个分片的目标最大字符数
        # - chunk_overlap 表示相邻分片之间保留一小段重叠文本，避免语义被硬切断
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size * 2,  # 加倍chunk_size，减少分片数
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        self.embedding_budget_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.embedding_token_budget,
            chunk_overlap=min(self.chunk_overlap, max(0, self.embedding_token_budget // 5)),
            length_function=estimate_tokens,
            is_separator_regex=False,
        )

        logger.info(
            f"文档分割服务初始化完成, chunk_size={self.chunk_size}, "
            f"secondary_chunk_size={self.chunk_size * 2}, "
            f"overlap={self.chunk_overlap}"
        )

    def split_markdown(self, content: str, file_path: str = "") -> list[Document]:
        """
        分割 Markdown 文档 (两阶段分割 + 合并小片段)

        最终返回 List[Document]，例如：
        [
            Document(
                page_content="# 故障处理\n\n## CPU 过高\n\n排查 top、日志、线程池...",
                metadata={
                    "h1": "故障处理",
                    "h2": "CPU 过高",
                    "_source": "/abs/path/runbook.md",
                    "_extension": ".md",
                    "_file_name": "runbook.md"
                }
            ),
            Document(...)
        ]

        Args:
            content: Markdown 内容
            file_path: 文件路径 (用于元数据)

        Returns:
            List[Document]: 文档分片列表
        """
        if not content or not content.strip():
            logger.warning(f"Markdown 文档内容为空: {file_path}")
            return []

        try:
            # 第一阶段: 按标题分割
            # 输出仍然是 List[Document]，但此时主要依据 # / ## 章节边界切分
            # 每个 Document.page_content 是某个标题下的正文，metadata 中带 h1/h2
            md_docs = self.markdown_splitter.split_text(content)

            # 第二阶段: 按大小进一步分割
            # 如果某个标题章节内容太长，会继续按 chunk_size * 2 的长度切成更小分片
            # 这样可以避免单个 chunk 太大，导致 embedding 或检索效果变差
            docs_after_split = self.text_splitter.split_documents(md_docs)

            # 第三阶段: 合并太小的分片 (< 300字符)
            # 标题切分可能产生很短的碎片；太短的 chunk 语义信息不足，检索时容易不准
            # 所以这里会尝试把小片段合并到前一个片段中
            final_docs = self._merge_small_chunks(docs_after_split, min_size=300)
            final_docs = self._enforce_embedding_token_budget(final_docs)

            # 添加文件路径元数据
            # 这些字段用于后续：
            # - 删除旧索引：根据 _source 找到同一个文件的旧分片
            # - 检索展示：知道命中的文本块来自哪个文件
            # - 过滤查询：可以按文件名/后缀筛选
            for doc in final_docs:
                doc.metadata["_source"] = file_path
                doc.metadata["_extension"] = ".md"
                doc.metadata["_file_name"] = Path(file_path).name

            logger.info(f"Markdown 分割完成: {file_path} -> {len(final_docs)} 个分片")
            return final_docs

        except Exception as e:
            logger.error(f"Markdown 分割失败: {file_path}, 错误: {e}")
            raise

    def split_text(self, content: str, file_path: str = "") -> list[Document]:
        """
        分割普通文本文档

        普通 txt 没有 Markdown 标题层级，所以不会产生 h1/h2 元数据。
        最终返回 List[Document]，例如：
        [
            Document(
                page_content="第一段文本内容...",
                metadata={
                    "_source": "/abs/path/a.txt",
                    "_extension": ".txt",
                    "_file_name": "a.txt"
                }
            ),
            Document(
                page_content="第二段文本内容...",
                metadata={...}
            )
        ]

        Args:
            content: 文本内容
            file_path: 文件路径 (用于元数据)

        Returns:
            List[Document]: 文档分片列表
        """
        if not content or not content.strip():
            logger.warning(f"文本文档内容为空: {file_path}")
            return []

        try:
            # 直接使用递归字符分割器
            # create_documents 会把 texts 中的完整字符串切成多个 Document
            # metadatas 只有一份，但 LangChain 会把这份 metadata 复制到每一个切出来的 Document 上
            docs = self.text_splitter.create_documents(
                texts=[content],
                metadatas=[
                    {
                        "_source": file_path,
                        "_extension": Path(file_path).suffix,
                        "_file_name": Path(file_path).name,
                    }
                ],
            )
            docs = self._enforce_embedding_token_budget(docs)

            logger.info(f"文本分割完成: {file_path} -> {len(docs)} 个分片")
            return docs

        except Exception as e:
            logger.error(f"文本分割失败: {file_path}, 错误: {e}")
            raise

    def split_document(self, content: str, file_path: str = "") -> list[Document]:
        """
        智能分割文档 (根据文件类型选择分割器)

        这是对外最常用的入口：
        - 如果 file_path 以 .md 结尾，走 split_markdown(...)
        - 否则统一当普通文本处理，走 split_text(...)

        Args:
            content: 文档内容
            file_path: 文件路径

        Returns:
            List[Document]: 文档分片列表
        """
        if file_path.endswith(".md"):
            return self.split_markdown(content, file_path)
        else:
            return self.split_text(content, file_path)

    def _merge_small_chunks(self, documents: list[Document], min_size: int = 300) -> list[Document]:
        """
        合并太小的分片

        输入是已经切好的 Document 列表，输出还是 Document 列表。
        它不会创建向量，也不会写 Milvus，只是减少过短 chunk 的数量。

        示例：
        输入：
        [
            Document(page_content="很长的第一段...", metadata={"h1": "A"}),
            Document(page_content="太短", metadata={"h1": "A"}),
            Document(page_content="新的长段落...", metadata={"h1": "B"})
        ]
        输出可能变成：
        [
            Document(page_content="很长的第一段...\n\n太短", metadata={"h1": "A"}),
            Document(page_content="新的长段落...", metadata={"h1": "B"})
        ]

        Args:
            documents: 文档列表
            min_size: 最小分片大小 (字符数)

        Returns:
            List[Document]: 合并后的文档列表
        """
        if not documents:
            return []

        merged_docs = []
        current_doc = None

        for doc in documents:
            doc_size = len(doc.page_content)

            if current_doc is None:
                # 第一个文档
                current_doc = doc
            elif doc_size < min_size and len(current_doc.page_content) < self.chunk_size * 2:
                # 当前文档太小且合并后不会太大，则合并
                current_doc.page_content += "\n\n" + doc.page_content
                # 保留主文档的元数据
            else:
                # 保存当前文档，开始新文档
                merged_docs.append(current_doc)
                current_doc = doc

        # 添加最后一个文档
        if current_doc is not None:
            merged_docs.append(current_doc)

        return merged_docs

    def _enforce_embedding_token_budget(self, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        safe_docs: list[Document] = []
        oversized_count = 0

        for doc in documents:
            if estimate_tokens(doc.page_content) <= self.embedding_token_budget:
                safe_docs.append(doc)
                continue

            oversized_count += 1
            split_docs = self.embedding_budget_splitter.split_documents([doc])
            for split_doc in split_docs:
                if estimate_tokens(split_doc.page_content) <= self.embedding_token_budget:
                    safe_docs.append(split_doc)
                else:
                    safe_docs.extend(self._hard_split_document(split_doc))

        if oversized_count:
            logger.warning(
                f"文档分片超过 Embedding token 预算，已继续切分: "
                f"oversized_chunks={oversized_count}, "
                f"before={len(documents)}, after={len(safe_docs)}, "
                f"max_tokens={self.embedding_token_budget}"
            )

        return safe_docs

    def _hard_split_document(self, document: Document) -> list[Document]:
        chunks: list[Document] = []
        current = ""

        for char in document.page_content:
            candidate = current + char
            if current and estimate_tokens(candidate) > self.embedding_token_budget:
                chunks.append(
                    Document(page_content=current.strip(), metadata=dict(document.metadata))
                )
                current = char
            else:
                current = candidate

        if current.strip():
            chunks.append(Document(page_content=current.strip(), metadata=dict(document.metadata)))

        return chunks


# 全局单例
document_splitter_service = DocumentSplitterService()
