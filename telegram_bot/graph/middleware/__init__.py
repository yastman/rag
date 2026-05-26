"""SDK-native middleware for the LangChain ``create_agent`` pipeline.

Companion to ``telegram_bot.graph.nodes.*`` while the voice and text paths
migrate from the bespoke StateGraph to ``create_agent`` (umbrella #1535).
The legacy node modules stay in place; new code lives here.
"""

from telegram_bot.graph.middleware.guard import GuardMiddleware


__all__ = ["GuardMiddleware"]
