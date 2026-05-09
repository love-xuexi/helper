"""向量嵌入服务模块 - 基于 LangChain Embeddings 标准接口"""

from typing import List

from langchain_core.embeddings import Embeddings
from openai import OpenAI
from loguru import logger

from app.config import config


class DashScopeEmbeddings(Embeddings):
    """阿里云 DashScope Text Embedding (OpenAI 兼容模式)
    
    实现 LangChain 标准 Embeddings 接口:
    - embed_documents(texts: List[str]) → List[List[float]]: 批量嵌入文档
    - embed_query(text: str) → List[float]: 嵌入单个查询

    这个类的作用是把“自然语言文本”转换成“向量”。
    向量可以理解成一串浮点数，模型会把语义相近的文本转换成距离更近的向量。

    例如输入：
    "CPU 使用率过高如何排查"

    最终输出大概长这样：
    [0.0123, -0.0876, 0.0345, ..., 0.0098]

    当前 dimensions=1024，所以每段文本最终会变成一个长度为 1024 的 float 列表。
    后续 Milvus 存储和相似度搜索时，比较的就是这些向量之间的距离。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v4",
        dimensions: int = 1024,
    ):
        """
        初始化 DashScope Embeddings

        初始化本身不会生成向量，只是创建一个 OpenAI SDK Client。
        这里虽然使用 OpenAI 这个 Python 包，但 base_url 指向的是阿里云 DashScope
        的 OpenAI 兼容接口，所以实际请求发给 DashScope。
        
        Args:
            api_key: DashScope API Key
            model: 嵌入模型名称
            dimensions: 向量维度
        """
        if not api_key or api_key == "your-api-key-here":
            raise ValueError("请设置环境变量 DASHSCOPE_API_KEY")
        
        # 创建 OpenAI 兼容客户端
        # 后续 self.client.embeddings.create(...) 会请求 DashScope embedding 接口
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = model
        self.dimensions = dimensions
        
        # 打印初始化信息
        masked_key = self._mask_api_key(api_key)
        logger.info(
            f"DashScope Embeddings 初始化完成 - "
            f"模型: {model}, 维度: {dimensions}, API Key: {masked_key}"
        )

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        """掩码 API Key 用于日志"""
        if len(api_key) > 8:
            return f"{api_key[:8]}...{api_key[-4:]}"
        return "***"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档列表 (LangChain 标准接口)

        这个方法通常由 LangChain Milvus VectorStore 自动调用。
        比如 vector_store_manager.add_documents(documents) 写入文档时，
        LangChain 会取出每个 Document.page_content，组成 texts 列表传进来。

        输入示例：
        [
            "第一段故障处理文本...",
            "第二段日志排查文本..."
        ]

        返回示例：
        [
            [0.01, -0.02, 0.03, ..., 0.04],
            [-0.05, 0.06, -0.01, ..., 0.02]
        ]

        返回值外层列表长度等于输入文本数量；
        内层每个列表就是一段文本的 embedding 向量，长度是 self.dimensions。
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 嵌入向量列表
        """
        if not texts:
            return []
        
        try:
            logger.info(f"批量嵌入 {len(texts)} 个文档")
            
            # 批量调用 API
            # input=texts 表示一次请求把多个文本块一起送给 embedding 模型
            # dimensions=self.dimensions 表示要求模型返回指定维度的向量
            # encoding_format="float" 表示返回 Python 可直接使用的 float 数组
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float"
            )
            
            # DashScope 返回的 response.data 中，每个 item 对应一个输入文本
            # item.embedding 就是这个文本的向量
            embeddings = [item.embedding for item in response.data]
            logger.debug(f"批量嵌入完成, 维度: {len(embeddings[0])}")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"批量嵌入失败: {e}")
            raise RuntimeError(f"批量嵌入失败: {e}") from e

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询文本 (LangChain 标准接口)

        这个方法通常在“用户检索”时被调用。
        例如用户问：
        "服务 CPU 飙高怎么办？"

        系统会先把这个 query 转成一个向量：
        [0.02, -0.01, 0.08, ..., -0.03]

        然后 Milvus 用这个 query 向量去和库里的文档向量做相似度搜索，
        找出语义最接近的几个文档分片。
        
        Args:
            text: 查询文本
            
        Returns:
            List[float]: 嵌入向量
        """
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")
        
        try:
            logger.debug(f"嵌入查询, 长度: {len(text)} 字符")
            
            # 单条查询也走同一个 embedding 接口
            # 区别是 input 传入的是一个字符串，而不是字符串列表
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
                encoding_format="float"
            )
            
            # 单条查询只会返回一个 embedding，所以取 response.data[0]
            embedding = response.data[0].embedding
            logger.debug(f"查询嵌入完成, 维度: {len(embedding)}")
            
            return embedding
            
        except Exception as e:
            logger.error(f"查询嵌入失败: {e}")
            raise RuntimeError(f"查询嵌入失败: {e}") from e


# 全局单例
# 项目其他地方会直接 import vector_embedding_service 使用同一个 embedding 服务实例。
# 例如 vector_store_manager 初始化 Milvus VectorStore 时，会把它作为 embedding_function 传进去。
vector_embedding_service = DashScopeEmbeddings(
    api_key=config.dashscope_api_key,
    model=config.dashscope_embedding_model,
    dimensions=1024
)
