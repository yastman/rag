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

    # Claude Judge
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    judge_model: str = "claude-sonnet-4-20250514"

    # Thresholds
    pass_score: float = 6.0

    # Qdrant test collection
    test_collection: str = "contextual_bulgaria_test"

    # Reports
    reports_dir: str = "reports"

    # Observability validation (Langfuse)
    validate_langfuse: bool = field(
        default_factory=lambda: (
            os.getenv("E2E_VALIDATE_LANGFUSE", "0").lower() in {"1", "true", "yes"}
        )
    )

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.telegram_api_id:
            errors.append("TELEGRAM_API_ID not set")
        if not self.telegram_api_hash:
            errors.append("TELEGRAM_API_HASH not set")
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY not set")
        return errors
