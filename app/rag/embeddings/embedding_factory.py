# app/rag/embeddings/embedding_factory.py
import logging
from langchain_core.embeddings import Embeddings
from app.config import RAGConfig

logger = logging.getLogger(__name__)

def get_embedding_model(config: RAGConfig) -> Embeddings:
    """
    创建和返回一个基于配置的embedding模型
    Args:
        config: RAGConfig
    Returns:
        Embeddings: HuggingFaceEmbeddings
    """
    from langchain_huggingface import HuggingFaceEmbeddings
    logger.info(f"Initializing local embedding model: {config.embedding.model_name}")
    return HuggingFaceEmbeddings(
        model_name=config.embedding.model_name,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
