"""Canonical PropertyBot test builder with explicit service injection (#3345).

One helper owns the default injected ``Services`` bundle for
handler/presentation tests. It constructs an explicit
:class:`telegram_bot.lifecycle.services.Services` value with ``MagicMock``
collaborators and hands it to ``PropertyBot`` through the ``_services`` DI
seam, so tests never patch service constructors
(``GraphConfig.create_llm``, Qdrant, embeddings, cache, Telegram ``Bot``).

Default service construction itself is tested in
``tests/unit/test_bot_initialization.py``, which stays on the real
``PropertyBot(config)`` path on purpose.
"""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import MagicMock

from telegram_bot.bot import PropertyBot
from telegram_bot.config import BotConfig
from telegram_bot.lifecycle.services import Services
from tests.unit._bot_config_factory import make_full_bot_config


def make_property_bot(
    config: BotConfig | None = None,
    *,
    service_overrides: Mapping[str, object] | None = None,
) -> PropertyBot:
    """Return a ``PropertyBot`` built on an explicit mocked ``Services`` bundle.

    ``service_overrides`` may replace individual ``Services`` fields by name;
    unknown field names are rejected. ``reranker`` and ``i18n_hub`` default to
    ``None`` — the production values for a ``rerank_provider="none"`` config
    without a translator hub — and every other field is a fresh ``MagicMock``
    (``embeddings`` aliases ``hybrid``, matching :func:`build_services`).
    """
    hybrid = MagicMock(name="hybrid_embeddings")
    defaults: dict[str, object] = {
        "graph_config": MagicMock(name="graph_config"),
        "cache": MagicMock(name="cache"),
        "hybrid": hybrid,
        "embeddings": hybrid,
        "sparse": MagicMock(name="sparse_embeddings"),
        "qdrant": MagicMock(name="qdrant"),
        "qdrant_apartments": MagicMock(name="qdrant_apartments"),
        "apartments_service": MagicMock(name="apartments_service"),
        "reranker": None,
        "llm": MagicMock(name="llm"),
        "apartment_pipeline": MagicMock(name="apartment_pipeline"),
        "redis_monitor": MagicMock(name="redis_monitor"),
        "i18n_hub": None,
    }

    overrides = dict(service_overrides or {})
    unknown = set(overrides) - set(defaults)
    if unknown:
        raise ValueError(
            f"Unknown Services field(s) in service_overrides: {sorted(unknown)}; "
            f"valid fields: {sorted(defaults)}"
        )
    defaults.update(overrides)

    services = Services(**defaults)
    return PropertyBot(config or make_full_bot_config(), _services=services)
