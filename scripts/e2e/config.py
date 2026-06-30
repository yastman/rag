"""E2E testing configuration."""

import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class E2EConfig(BaseSettings):
    """Configuration for E2E testing."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Telegram Userbot (from my.telegram.org)
    telegram_api_id: int = Field(default=0, alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    telegram_session: str = "e2e_tester"

    # Target bot
    bot_username: str = Field(default="@test_your_bot", alias="E2E_BOT_USERNAME")

    # Timeouts
    response_timeout: int = 60  # Streaming can be slow
    between_tests_delay: float = 2.0  # Rate limiting

    # Judge provider and credentials
    judge_provider: str = Field(default="litellm", alias="E2E_JUDGE_PROVIDER")
    judge_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("E2E_JUDGE_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"),
    )
    judge_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("E2E_JUDGE_BASE_URL", "LLM_BASE_URL"),
    )
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    judge_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("E2E_JUDGE_MODEL", "LLM_MODEL"),
    )

    # Thresholds
    pass_score: float = 6.0

    # Canonical Qdrant collection for current corpus
    test_collection: str = Field(default="gdrive_documents_bge", alias="E2E_COLLECTION_NAME")

    # Qdrant preflight configuration
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_doc_collection: str = Field(
        default="gdrive_documents_bge", alias="E2E_QDRANT_DOC_COLLECTION"
    )
    qdrant_apartment_collection: str = Field(
        default="apartments", alias="E2E_QDRANT_APARTMENT_COLLECTION"
    )
    qdrant_min_doc_points: int = Field(default=1, alias="E2E_QDRANT_MIN_DOC_POINTS")
    qdrant_min_apartment_points: int = Field(default=1, alias="E2E_QDRANT_MIN_APARTMENT_POINTS")
    qdrant_doc_vectors: str = Field(default="dense,colbert", alias="E2E_QDRANT_DOC_VECTORS")
    qdrant_apartment_vectors: str = Field(
        default="dense,colbert", alias="E2E_QDRANT_APARTMENT_VECTORS"
    )

    # Reports
    reports_dir: str = "reports"

    # Voice note fixture path for voice delivery scenarios
    voice_note_path: str = Field(default="", alias="E2E_VOICE_NOTE_PATH")

    def validate(self, *, judge_required: bool = True) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.telegram_api_id:
            errors.append("TELEGRAM_API_ID not set")
        if not self.telegram_api_hash:
            errors.append("TELEGRAM_API_HASH not set")
        if not judge_required:
            return errors

        provider = (self.judge_provider or "").strip().lower()
        if provider in {"", "litellm"}:
            if not any(
                os.getenv(key)
                for key in ("CEREBRAS_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")
            ):
                errors.append(
                    "At least one LLM provider key is required for judge provider 'litellm'"
                )
        elif provider in {"openai-compatible", "openai"}:
            if not self.judge_api_key:
                errors.append("E2E_JUDGE_API_KEY not set for OpenAI-compatible judge provider")
            if not self.judge_base_url:
                errors.append("E2E_JUDGE_BASE_URL not set for OpenAI-compatible judge provider")
        elif provider == "anthropic-direct":
            if not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY not set for judge provider 'anthropic-direct'")
        else:
            errors.append(
                f"Unsupported E2E_JUDGE_PROVIDER '{self.judge_provider}'. "
                "Use 'litellm' or 'anthropic-direct'."
            )
        return errors
