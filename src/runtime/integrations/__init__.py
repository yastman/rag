"""Shared runtime integrations package.

Hosts ``src/`` modules that wrap external services (BGE-M3 embeddings,
Redis cache, Qdrant vector store, etc.) so ``src/api`` and ``mini_app``
can use them without reaching back into ``telegram_bot/``.

Tracked under #1948 / #2045 / #2049.
"""
