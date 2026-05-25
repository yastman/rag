"""Shared runtime services package.

Hosts ``src/`` modules that wrap external services (Qdrant client,
metrics aggregation, etc.) so ``src/api`` and ``mini_app`` can use them
without reaching back into ``telegram_bot/``.

Tracked under #1948 / #2047 / #2049.
"""
