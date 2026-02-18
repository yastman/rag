"""LLM Guard API Configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Model
    MODEL_NAME: str = "protectai/deberta-v3-base-prompt-injection-v2"
    THRESHOLD: float = 0.85
    USE_ONNX: bool = True

    # API
    HOST: str = "0.0.0.0"
    PORT: int = 8100
    WORKERS: int = 1

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
