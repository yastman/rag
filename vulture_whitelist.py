"""Vulture whitelist — intentional false positives (#3011).

Each name silences a Vulture finding that is NOT dead code.
See comments for rationale.

  exc_val, exc_tb  — __aexit__ protocol params (scripts/e2e/telegram_client.py)
"""

exc_tb  # unused variable (scripts/e2e/telegram_client.py:190)
exc_val  # unused variable (scripts/e2e/telegram_client.py:190)
