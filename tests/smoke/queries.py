# tests/smoke/queries.py
"""Smoke test query definitions by type.

Distribution: 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX = 20 total
"""

from dataclasses import dataclass
from enum import Enum


class ExpectedQueryType(Enum):
    """Expected query classification."""

    CHITCHAT = "CHITCHAT"
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


@dataclass
class SmokeQuery:
    """Smoke test query with expected behavior."""

    text: str
    expected_type: ExpectedQueryType
    expect_cache_write: bool = False
    expect_rerank: bool = False


# 20 queries: 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX (STRICT)
SMOKE_QUERIES: list[SmokeQuery] = [
    # === CHITCHAT (6) - skip RAG entirely ===
    SmokeQuery("Привет!", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Добрый день", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Спасибо за помощь", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Кто ты?", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Что ты умеешь?", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Пока, до свидания", ExpectedQueryType.CHITCHAT),
    # === SIMPLE (6) - light RAG, skip rerank ===
    # These match SIMPLE_PATTERNS in query_router.py
    SmokeQuery("Сколько стоит квартира?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Какая цена на студию?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Сколько стоит дом?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Какая цена аренды?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Двухкомнатная квартира", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Трёхкомнатная квартира", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    # === COMPLEX (8) - full RAG + rerank + quantization A/B ===
    SmokeQuery(
        "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро с видом на море",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Квартиры в комплексе Harmony Suites корпус 3 с мебелью",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Сравни цены на студии в Несебре и Равде",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Апартаменты с двумя спальнями рядом с пляжем, первая линия",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Что лучше: Sunny Beach или Sveti Vlas для инвестиций?",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Новостройки с рассрочкой платежа на 2 года",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Квартира с паркингом и кладовой в закрытом комплексе",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Покажи варианты до 70000 евро с ремонтом под ключ",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
]


def get_queries_by_type(query_type: ExpectedQueryType) -> list[SmokeQuery]:
    """Get queries filtered by type."""
    return [q for q in SMOKE_QUERIES if q.expected_type == query_type]


def validate_distribution():
    """Validate 6/6/8 distribution."""
    chitchat = len(get_queries_by_type(ExpectedQueryType.CHITCHAT))
    simple = len(get_queries_by_type(ExpectedQueryType.SIMPLE))
    complex_ = len(get_queries_by_type(ExpectedQueryType.COMPLEX))

    assert chitchat == 6, f"CHITCHAT should be 6, got {chitchat}"
    assert simple == 6, f"SIMPLE should be 6, got {simple}"
    assert complex_ == 8, f"COMPLEX should be 8, got {complex_}"
    assert len(SMOKE_QUERIES) == 20, f"Total should be 20, got {len(SMOKE_QUERIES)}"


# Validate on import
validate_distribution()
