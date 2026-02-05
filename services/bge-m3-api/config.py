"""
BGE-M3 API Configuration
"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Model Configuration
    MODEL_NAME: str = "BAAI/bge-m3"
    MODEL_CACHE_DIR: str = "/models"
    USE_FP16: bool = True  # FP16 для экономии памяти (2-3GB вместо 4-6GB)

    # Performance Settings
    MAX_LENGTH: int = 2048  # Optimized for typical chunk size (was 8192)
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
