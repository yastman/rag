"""Vulture whitelist — intentional false positives (#3011).

Each name silences a Vulture finding that is NOT dead code.
See comments for rationale.

  exc_val, exc_tb  — __aexit__ protocol params (scripts/e2e/telegram_client.py)
  lf               — no-op Langfuse shim param (#2844); kept for API compat
  backend          — no-op stub param (src/observability/scores.py)
"""

exc_tb  # unused variable (scripts/e2e/telegram_client.py:190)
exc_val  # unused variable (scripts/e2e/telegram_client.py:190)
lf  # unused variable (src/observability/scores.py:14)
backend  # unused variable (src/observability/scores.py:28)
