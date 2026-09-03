"""Service factory for PropertyBot DI/test seam (#2948).

``build_services`` constructs all long-lived collaborators that
``PropertyBot.__init__`` used to inline. Tests can call it with a
minimal ``BotConfig`` stub and swap individual services without wiring
the full bot stack.

Only stdlib + already-installed deps here — no heavy imports at module
scope so that contract tests can import this module without qdrant_client,
langgraph, or aiogram being fully importable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:  # pragma: no cover
    from .config import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class Services:
    """Holds all eagerly-constructed collaborators for PropertyBot.

    Fields that are initialised lazily (pg_pool, user_service, …) are
    not included here — they remain ``None`` attributes on the bot until
    ``start()`` runs the ``_setup_*`` lifecycle methods.
    """

    graph_config: Any
    cache: Any
    hybrid: Any
    embeddings: Any  # alias → hybrid
    sparse: Any
    qdrant: Any
    qdrant_apartments: Any
    apartments_service: Any
    reranker: Any
    llm: Any
    apartment_pipeline: Any
    redis_monitor: Any
    i18n_hub: Any = field(default=None)


def build_services(config: BotConfig) -> Services:
    """Construct all eagerly-initialised PropertyBot collaborators.

    Importing heavy runtime modules is deferred to this function body so
    ``_bot_services`` itself has no heavy module-scope side-effects.
    """
    from src.runtime.config import GraphConfig
    from src.runtime.integrations.cache import CacheLayerManager
    from src.runtime.integrations.embeddings import BGEM3HybridEmbeddings, BGEM3SparseEmbeddings
    from src.runtime.services.qdrant import QdrantService
    from telegram_bot.services.apartment.apartments_service import ApartmentsService
    from telegram_bot.services.observability.redis_monitor import RedisHealthMonitor

    graph_config = GraphConfig(
        llm_base_url=config.llm_base_url,
        llm_api_key=config.llm_api_key,
        llm_model=config.llm_model,
        bge_m3_url=config.bge_m3_url,
        qdrant_url=config.qdrant_url,
        qdrant_collection=config.qdrant_collection,
        search_top_k=config.search_top_k,
        redis_url=config.redis_url,
        domain=config.domain,
        domain_language=config.domain_language,
    )

    cache = CacheLayerManager(redis_url=config.redis_url)

    hybrid = BGEM3HybridEmbeddings(
        base_url=config.bge_m3_url,
        timeout=graph_config.bge_m3_timeout,
    )
    sparse = BGEM3SparseEmbeddings(
        base_url=config.bge_m3_url,
        timeout=graph_config.bge_m3_timeout,
    )
    qdrant = QdrantService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name=config.qdrant_collection,
        quantization_mode=config.qdrant_quantization_mode,
        timeout=config.qdrant_timeout,
    )
    qdrant_apartments = QdrantService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name="apartments",
    )
    apartments_service = ApartmentsService(qdrant=qdrant_apartments)

    reranker = None
    if config.rerank_provider == "colbert":
        logger.info("Reranking via server-side Qdrant ColBERT path")
    elif config.rerank_provider == "none":
        logger.info("Reranking disabled")

    llm = graph_config.create_llm()

    from telegram_bot.services.apartment.apartment_extraction_pipeline import (
        ApartmentExtractionPipeline,
    )
    from telegram_bot.services.apartment.apartment_filter_extractor import ApartmentFilterExtractor

    _apt_llm = None
    try:
        from telegram_bot.services.apartment.apartment_llm_extractor import ApartmentLlmExtractor

        _apt_llm = ApartmentLlmExtractor(llm=llm, model=config.apartment_extraction_model)
    except (ImportError, ModuleNotFoundError):
        logger.warning(
            "ApartmentLlmExtractor unavailable, falling back to regex-only extraction",
            exc_info=True,
        )

    apartment_pipeline = ApartmentExtractionPipeline(
        regex_extractor=ApartmentFilterExtractor(),
        llm_extractor=_apt_llm,
        redis=cache.redis,
    )

    redis_monitor = RedisHealthMonitor(redis_url=config.redis_url)

    i18n_hub = None
    try:
        from .middlewares.i18n import create_translator_hub

        i18n_hub = create_translator_hub()
    except Exception:
        logger.warning(
            "Failed to initialize i18n hub during startup preflight; "
            "falling back to RU-only menu filters",
            exc_info=True,
        )

    return Services(
        graph_config=graph_config,
        cache=cache,
        hybrid=hybrid,
        embeddings=hybrid,
        sparse=sparse,
        qdrant=qdrant,
        qdrant_apartments=qdrant_apartments,
        apartments_service=apartments_service,
        reranker=reranker,
        llm=llm,
        apartment_pipeline=apartment_pipeline,
        redis_monitor=redis_monitor,
        i18n_hub=i18n_hub,
    )
