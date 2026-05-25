"""Shared LangGraph kernel — runtime-level package.

First slice of the runtime migration tracked under #1948 / #2045 / #2049.
Hosts the LangGraph state schema and the initial-state factory so
``src/api`` and ``mini_app`` no longer have to reach back into
``telegram_bot/`` for them.
"""
