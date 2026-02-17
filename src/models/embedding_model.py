"""Singleton BGE-M3 model manager to prevent duplicate loading.

Loading BGE-M3 multiple times wastes 4-6GB RAM per instance.
This module ensures only ONE model instance exists in memory.

NOTE: FlagEmbedding and sentence_transformers are imported lazily to avoid
pulling torch at import time. Install with: uv sync --extra ml-local
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from FlagEmbedding import BGEM3FlagModel
    from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)

# Global singleton instances (typed as Any to avoid import at module level)
_bge_m3_model: Any | None = None
_sentence_transformer: Any | None = None

_INSTALL_HINT = "Install ml-local extra: uv sync --extra ml-local"


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

    Raises:
        ImportError: If FlagEmbedding is not installed
    """
    global _bge_m3_model

    if _bge_m3_model is None:
        try:
            from FlagEmbedding import BGEM3FlagModel as _BGEM3
        except ImportError as e:
            raise ImportError(f"FlagEmbedding is not installed. {_INSTALL_HINT}") from e

        logger.info("Loading BGE-M3 model (FlagEmbedding) - first initialization")
        _bge_m3_model = _BGEM3(
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

    Raises:
        ImportError: If sentence_transformers is not installed
    """
    global _sentence_transformer

    if _sentence_transformer is None:
        try:
            from sentence_transformers import SentenceTransformer as _ST
        except ImportError as e:
            raise ImportError(f"sentence_transformers is not installed. {_INSTALL_HINT}") from e

        logger.info(f"Loading SentenceTransformer ({model_name}) - first initialization")
        _sentence_transformer = _ST(model_name)
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
