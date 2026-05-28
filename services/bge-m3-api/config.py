"""
BGE-M3 API Configuration
"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Model Configuration
    MODEL_NAME: str = "BAAI/bge-m3"  # HuggingFace model ID (tokenizer only with ONNX)
    MODEL_CACHE_DIR: str = "/models"
    USE_FP16: bool = True  # FP16 for CPU memory savings (legacy; ONNX INT8 ignores this)

    # ONNX Runtime Configuration
    ONNX_MODEL_DIR: str = os.getenv(
        "ONNX_MODEL_DIR", "/models/onnx"
    )  # Directory containing model.int8.onnx + model.int8.onnx.data

    # Performance Settings
    MAX_LENGTH: int = 2048  # For documents (typical chunk size)
    QUERY_MAX_LENGTH: int = 256  # For short queries (10-50 tokens)
    BATCH_SIZE: int = 12
    NUM_THREADS: int = int(os.getenv("OMP_NUM_THREADS", "4"))

    # API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000  # Внутренний порт контейнера (8001 на хосте)
    WORKERS: int = 1  # Один worker для экономии памяти

    # Rerank limits
    RERANK_MAX_DOCS: int = 30
    RERANK_MAX_LENGTH: int = 512
    RERANK_DEFAULT_TOP_K: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
