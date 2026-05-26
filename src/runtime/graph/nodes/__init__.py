"""LangGraph node implementations — runtime-level package.

Second slice of the runtime migration tracked under #1948 / #2049.
Hosts low-coupling graph node implementations so ``src/runtime``
no longer has to reach back into ``telegram_bot/`` for them.
"""
