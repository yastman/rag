"""Re-export of src.observability_sentry for backward-compatible imports.

Keep ``telegram_bot.observability_sentry`` importable so future bot-side
helpers can ``from telegram_bot.observability_sentry import initialize_sentry``
without dipping into ``src.*`` directly.
"""

from src.observability_sentry import initialize_sentry


__all__ = ["initialize_sentry"]
