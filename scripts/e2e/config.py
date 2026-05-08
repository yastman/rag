"""E2E testing configuration."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


load_dotenv()


@dataclass
class E2EConfig:
    """Configuration for E2E testing."""

    # Telegram Userbot (from my.telegram.org)
    telegram_api_id: int = field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0")))
    telegram_api_hash: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    telegram_session: str = "e2e_tester"

    # Target bot
    bot_username: str = field(
        default_factory=lambda: os.getenv("E2E_BOT_USERNAME", "@test_nika_homes_bot")
    )

    # Timeouts
    response_timeout: int = 60  # Streaming can be slow
    between_tests_delay: float = 2.0  # Rate limiting

    # Judge provider and credentials
    judge_provider: str = field(default_factory=lambda: os.getenv("E2E_JUDGE_PROVIDER", "litellm"))
    judge_api_key: str = field(
        default_factory=lambda: os.getenv(
            "E2E_JUDGE_API_KEY",
            os.getenv(
                "LLM_API_KEY", os.getenv("OPENAI_API_KEY", os.getenv("LITELLM_MASTER_KEY", ""))
            ),
        )
    )
    judge_base_url: str = field(
        default_factory=lambda: os.getenv(
            "E2E_JUDGE_BASE_URL", os.getenv("LLM_BASE_URL", "http://localhost:4000/v1")
        )
    )
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    judge_model: str = field(
        default_factory=lambda: os.getenv("E2E_JUDGE_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    )

    # Thresholds
    pass_score: float = 6.0

    # Canonical Qdrant collection for current corpus
    test_collection: str = field(
        default_factory=lambda: os.getenv("E2E_COLLECTION_NAME", "gdrive_documents_bge")
    )

    # Reports
    reports_dir: str = "reports"

    # Observability validation (Langfuse)
    validate_langfuse: bool = field(
        default_factory=lambda: (
            os.getenv("E2E_VALIDATE_LANGFUSE", "0").lower() in {"1", "true", "yes"}
        )
    )

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
        if provider in {"", "litellm", "openai-compatible", "openai"}:
            if not self.judge_api_key:
                errors.append("E2E_JUDGE_API_KEY not set for judge provider 'litellm'")
            if not self.judge_base_url:
                errors.append("E2E_JUDGE_BASE_URL not set for judge provider 'litellm'")
        elif provider == "anthropic-direct":
            if not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY not set for judge provider 'anthropic-direct'")
        else:
            errors.append(
                f"Unsupported E2E_JUDGE_PROVIDER '{self.judge_provider}'. "
                "Use 'litellm' or 'anthropic-direct'."
            )
        return errors
