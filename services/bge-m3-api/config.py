"""
BGE-M3 API Configuration
"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    ***REMOVED*** Model Configuration
    MODEL_NAME: str = "BAAI/bge-m3"
    MODEL_CACHE_DIR: str = "/models"
    USE_FP16: bool = True  ***REMOVED*** FP16 для экономии памяти (2-3GB вместо 4-6GB)

    ***REMOVED*** Performance Settings
    MAX_LENGTH: int = 2048  ***REMOVED*** Optimized for typical chunk size (was 8192)
    BATCH_SIZE: int = 12
    NUM_THREADS: int = int(os.getenv("OMP_NUM_THREADS", "4"))

    ***REMOVED*** API Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000  ***REMOVED*** Внутренний порт контейнера (8001 на хосте)
    WORKERS: int = 1  ***REMOVED*** Один worker для экономии памяти

    ***REMOVED*** Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
