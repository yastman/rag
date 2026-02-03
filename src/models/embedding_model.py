"""Singleton BGE-M3 model manager to prevent duplicate loading.

Loading BGE-M3 multiple times wastes 4-6GB RAM per instance.
This module ensures only ONE model instance exists in memory.
"""

import logging

from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)

# Global singleton instances
_bge_m3_model: BGEM3FlagModel | None = None
_sentence_transformer: SentenceTransformer | None = None


def get_bge_m3_model(use_fp16: bool = True, device: str | None = None) -> BGEM3FlagModel:
    """
    Get singleton BGE-M3 model instance (FlagEmbedding version).

    Used for multi-vector search with dense, sparse, and ColBERT vectors.
    Loading once saves 4-6GB RAM compared to multiple instances.

    Args:
        use_fp16: Use FP16 precision (faster, less memory)
        device: Device to use ('cuda', 'cpu', or None for auto)

    Returns:
        Shared BGEM3FlagModel instance
    """
    global _bge_m3_model

    if _bge_m3_model is None:
        logger.info("Loading BGE-M3 model (FlagEmbedding) - first initialization")
        _bge_m3_model = BGEM3FlagModel(
            "BAAI/bge-m3",
            use_fp16=use_fp16,
            device=device,
        )
        logger.info("BGE-M3 model loaded successfully (singleton)")
    else:
        logger.debug("Using existing BGE-M3 model instance (singleton)")

    return _bge_m3_model


def get_sentence_transformer(model_name: str = "BAAI/bge-m3") -> SentenceTransformer:
    """
    Get singleton SentenceTransformer instance.

    Used for simple dense-only embeddings (telegram bot, simple search).
    Loading once saves 2-3GB RAM.

    Args:
        model_name: Model identifier (default: BAAI/bge-m3)

    Returns:
        Shared SentenceTransformer instance
    """
    global _sentence_transformer

    if _sentence_transformer is None:
        logger.info(f"Loading SentenceTransformer ({model_name}) - first initialization")
        _sentence_transformer = SentenceTransformer(model_name)
        logger.info("SentenceTransformer loaded successfully (singleton)")
    else:
        logger.debug("Using existing SentenceTransformer instance (singleton)")

    return _sentence_transformer


def clear_models():
    """
    Clear model instances from memory.

    Use for testing or when you need to free GPU/RAM.
    """
    global _bge_m3_model, _sentence_transformer

    if _bge_m3_model is not None:
        logger.info("Clearing BGE-M3 model from memory")
        del _bge_m3_model
        _bge_m3_model = None

    if _sentence_transformer is not None:
        logger.info("Clearing SentenceTransformer from memory")
        del _sentence_transformer
        _sentence_transformer = None

    # Force garbage collection
    import gc

    gc.collect()
