"""transcribe_node — back-compat re-export.

The canonical implementation moved to :mod:`src.runtime.graph.nodes.transcribe`
as part of the reverse-layering Slice B (#2049 / #1948). This module
remains so that existing ``from telegram_bot.graph.nodes.transcribe import …``
imports across ``telegram_bot/``, ``tests/``, and the rest of the repo
continue to work unchanged.
"""

from src.runtime.graph.nodes.transcribe import make_transcribe_node  # noqa: I001

__all__ = ["make_transcribe_node"]
