"""Validation query sets for trace validation runs.

Imports from existing test fixtures + manual edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationQuery:
    """Single validation query."""

    text: str
    source: str  # smoke | eval | manual
    difficulty: str  # easy | medium | hard
    collection: str  # legal_documents | contextual_bulgaria_voyage | any
    expect_rewrite: bool = False


# Bulgarian property queries (from tests/smoke/queries.py, skip CHITCHAT)
PROPERTY_QUERIES: list[ValidationQuery] = [
    # SIMPLE (6)
    ValidationQuery("Сколько стоит квартира?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Какая цена на студию?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Сколько стоит дом?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Какая цена аренды?", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Двухкомнатная квартира", "smoke", "easy", "contextual_bulgaria_voyage"),
    ValidationQuery("Трёхкомнатная квартира", "smoke", "easy", "contextual_bulgaria_voyage"),
    # COMPLEX (8)
    ValidationQuery(
        "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро с видом на море",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Квартиры в комплексе Harmony Suites корпус 3 с мебелью",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Сравни цены на студии в Несебре и Равде",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Апартаменты с двумя спальнями рядом с пляжем, первая линия",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Что лучше: Sunny Beach или Sveti Vlas для инвестиций?",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Новостройки с рассрочкой платежа на 2 года",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Квартира с паркингом и кладовой в закрытом комплексе",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
    ValidationQuery(
        "Покажи варианты до 70000 евро с ремонтом под ключ",
        "smoke",
        "hard",
        "contextual_bulgaria_voyage",
    ),
]

# Criminal Code queries (subset from src/evaluation/smoke_test.py)
LEGAL_QUERIES: list[ValidationQuery] = [
    # HARD (5)
    ValidationQuery(
        "что регулирует первая статья УК Украины о правовом обеспечении",
        "eval",
        "hard",
        "legal_documents",
    ),
    ValidationQuery(
        "как учитывается иностранный приговор при рецидиве на территории Украины?",
        "eval",
        "hard",
        "legal_documents",
    ),
    ValidationQuery(
        "какая уголовная ответственность за отказ от дальнейшего совершения преступления",
        "eval",
        "hard",
        "legal_documents",
    ),
    ValidationQuery(
        "как определяется неосторожность: предвидел или не предвидел последствия действий",
        "eval",
        "hard",
        "legal_documents",
    ),
    ValidationQuery(
        "как квалифицировать два разных преступления, совершённые одним лицом одновременно",
        "eval",
        "hard",
        "legal_documents",
    ),
    # MEDIUM (5)
    ValidationQuery(
        "какие цели и задачи ставит перед собой уголовный кодекс Украины",
        "eval",
        "medium",
        "legal_documents",
    ),
    ValidationQuery(
        "статья 1 Уголовного кодекса Украины задачи",
        "eval",
        "easy",
        "legal_documents",
    ),
    ValidationQuery(
        "стаття 115 КК України",
        "eval",
        "easy",
        "legal_documents",
    ),
    ValidationQuery(
        "відповідальність за крадіжку",
        "eval",
        "medium",
        "legal_documents",
    ),
    ValidationQuery(
        "покарання за шахрайство",
        "eval",
        "medium",
        "legal_documents",
    ),
]

# Bulgarian property queries with BGE-M3 embeddings (gdrive_documents_bge)
GDRIVE_BGE_QUERIES: list[ValidationQuery] = [
    # EASY (10)
    ValidationQuery("квартира в Несебре", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("студия на Солнечном берегу", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("цена дома в Равде", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("аренда апартаментов", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("однокомнатная квартира цена", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("недвижимость в Болгарии", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("жильё у моря", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("купить квартиру Бургас", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("сколько стоит студия", "smoke", "easy", "gdrive_documents_bge"),
    ValidationQuery("квартира первая линия", "smoke", "easy", "gdrive_documents_bge"),
    # MEDIUM (10)
    ValidationQuery(
        "квартира до 50000 евро с мебелью",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "двухкомнатная с видом на море",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "новостройка с рассрочкой",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "комплекс с бассейном и паркингом",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "квартира с ремонтом под ключ",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "апартаменты рядом с пляжем до 40000",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "студия в закрытом комплексе",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "жильё для сдачи в аренду инвестиции",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "квартира с балконом и кондиционером",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "дом с участком в пригороде",
        "smoke",
        "medium",
        "gdrive_documents_bge",
    ),
    # HARD (10)
    ValidationQuery(
        "сравни цены Солнечный берег vs Святой Влас 2024",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "что лучше купить студию или однокомнатную для инвестиций",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "комплексы с управляющей компанией и гарантированной арендой",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "найди все варианты с рассрочкой на 2-3 года без первого взноса",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "какой район в Бургасской области самый перспективный для покупки",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "апартаменты с двумя спальнями в Harmony Suites или Tarsis Club",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "покупка через юрлицо vs физлицо налоги",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "квартира с документами для ВНЖ в Болгарии",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "самые дешёвые варианты на первой линии с мебелью",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
    ValidationQuery(
        "что включает цена под ключ: мебель, техника, ремонт",
        "smoke",
        "hard",
        "gdrive_documents_bge",
    ),
]

# Manual edge cases
EDGE_CASE_QUERIES: list[ValidationQuery] = [
    # Should trigger rewrite (nonsensical → low relevance → rewrite)
    ValidationQuery(
        "фиолетовые документы с перламутровыми пуговицами",
        "manual",
        "hard",
        "any",
        expect_rewrite=True,
    ),
    # Should return empty or low results
    ValidationQuery(
        "quantum computing applications in molecular biology",
        "manual",
        "hard",
        "any",
    ),
    # Simple, should be fast
    ValidationQuery(
        "цена",
        "manual",
        "easy",
        "any",
    ),
]


def get_queries_for_collection(collection: str) -> list[ValidationQuery]:
    """Get queries applicable to a specific collection."""
    result: list[ValidationQuery] = []
    if collection == "legal_documents":
        result.extend(LEGAL_QUERIES)
    elif collection == "contextual_bulgaria_voyage":
        result.extend(PROPERTY_QUERIES)
    elif collection == "gdrive_documents_bge":
        result.extend(GDRIVE_BGE_QUERIES)
    # Edge cases apply to any collection
    result.extend(EDGE_CASE_QUERIES)
    return result


def get_warmup_queries(collection: str, count: int = 3) -> list[ValidationQuery]:
    """Get warmup queries (subset of main queries)."""
    queries = get_queries_for_collection(collection)
    return queries[:count]


def get_cache_hit_queries(
    cold_queries: list[ValidationQuery],
    count: int = 5,
) -> list[ValidationQuery]:
    """Select queries to repeat for cache-hit testing."""
    # Pick a mix: some easy (likely cached) + some hard
    easy = [q for q in cold_queries if q.difficulty == "easy"][:2]
    hard = [q for q in cold_queries if q.difficulty == "hard"][:3]
    return (easy + hard)[:count]
