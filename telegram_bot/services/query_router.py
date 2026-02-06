"""Query router for RAG pipeline optimization.

2026 best practice: Skip RAG for simple queries (chit-chat, greetings)
to reduce latency and cost. Only invoke full pipeline for actual search queries.
"""

import logging
import re
from enum import Enum

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Query classification for routing decisions."""

    CHITCHAT = "chitchat"  # Simple greetings, thanks - no RAG needed
    SIMPLE = "simple"  # Simple factual questions - light RAG
    COMPLEX = "complex"  # Complex search queries - full RAG + rerank
    OFF_TOPIC = "off_topic"  # Non-real-estate queries - politely redirect


# Patterns for chit-chat detection (no RAG needed)
CHITCHAT_PATTERNS = [
    # Greetings (Russian)
    r"^привет\b",
    r"^здравствуй",
    r"^добр(ый|ое|ая)\s+(день|утро|вечер)",
    r"^хай\b",
    r"^хелло\b",
    r"^салют\b",
    # Greetings (English)
    r"^hi\b",
    r"^hello\b",
    r"^hey\b",
    r"^good\s+(morning|afternoon|evening)",
    # Thanks (Russian)
    r"^спасибо\b",
    r"^благодар",
    r"^круто\b",
    r"^отлично\b",
    r"^супер\b",
    # Thanks (English)
    r"^thanks?\b",
    r"^thank you\b",
    r"^great\b",
    r"^awesome\b",
    # Bot questions (Russian)
    r"^что ты (умеешь|можешь|делаешь)",
    r"^как (тебя зовут|ты работаешь)",
    r"^кто ты",
    r"^ты бот",
    # Bot questions (English)
    r"^what (can you|do you) do",
    r"^who are you",
    r"^are you (a bot|ai)",
    # Farewells (Russian)
    r"^пока\b",
    r"^до свидания\b",
    r"^всего доброго\b",
    # Farewells (English)
    r"^bye\b",
    r"^goodbye\b",
    r"^see you\b",
]

# Patterns for simple queries (light RAG, no rerank)
SIMPLE_PATTERNS = [
    # Price questions
    r"^сколько стоит\b",
    r"^какая цена\b",
    r"^price\b",
    # Single property queries
    r"^\d+\s*(комнат|спал)",  # "2 комнаты"
    r"^(одно|двух|трёх)комнатн",
]

# Patterns for off-topic detection (non-real-estate queries)
OFF_TOPIC_PATTERNS = [
    # Programming/Tech
    r"\b(python|javascript|java|код|программ|api|docker|kubernetes)\b",
    r"\b(алгоритм|функция|переменная|массив|database)\b",
    # Medical
    r"\b(лечение|болезн|врач|доктор|симптом[а-я]*|таблетк|медицин)\b",
    r"\b(диагноз|аптека|рецепт|health|doctor|medicine|грипп)\b",
    # Legal (non-property)
    r"\b(развод|алимент|уголовн|штраф|суд[^а-я]|адвокат)\b",
    # Cooking/Recipes
    r"\b(рецепт|готовить|приготовить|ингредиент|блюдо|пицц)",
    r"\b(recipe|cook[^i]|food|dish)\b",
    # Travel (non-Bulgaria property)
    r"\b(билет|самолёт|поезд|отел[^ьн]|гостиниц|бронирован)\b",
    r"\b(flight|ticket|hotel|booking)\b",
    # General knowledge
    r"\b(кто (такой|такая)|что такое|когда был|история)\b",
    r"\b(столица|президент|население)\b",
    # Math/Science
    r"\b(формула|уравнение|теорема|физика|химия|математика)\b",
    # Entertainment
    r"\b(фильм|сериал|музыка|песня|игр[аы]|movie|game[s]?|music)\b",
    r"\b(video game)\b",
    # Finance (non-property)
    r"\b(акции|биржа|криптовалюта|биткоин|инвестиц|трейдинг)\b",
    r"\b(торговать на бирже)\b",
    r"\b(crypto|bitcoin|stock|trading)\b",
    # Jobs (non-property)
    r"\b(вакансия|работа[^ть]|резюме|зарплата|job|career|salary)\b",
    # Education
    r"\b(экзамен|школа|универси|курс|диплом|exam|university)\b",
]

# Compile patterns for efficiency
_CHITCHAT_COMPILED = [re.compile(p, re.IGNORECASE) for p in CHITCHAT_PATTERNS]
_SIMPLE_COMPILED = [re.compile(p, re.IGNORECASE) for p in SIMPLE_PATTERNS]
_OFF_TOPIC_COMPILED = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]


# Chit-chat responses (no RAG needed)
CHITCHAT_RESPONSES = {
    "greeting": [
        "Привет! 👋 Я помогу найти недвижимость в Болгарии. Что вас интересует?",
        "Здравствуйте! Чем могу помочь? Ищете квартиру или дом в Болгарии?",
    ],
    "thanks": [
        "Пожалуйста! Если будут ещё вопросы — обращайтесь.",
        "Рад помочь! Нужно что-то ещё?",
    ],
    "bot_info": [
        "Я бот-помощник по недвижимости в Болгарии. Могу найти квартиры, "
        "дома, апартаменты по вашим критериям (город, бюджет, количество комнат).",
    ],
    "farewell": [
        "До свидания! Удачи в поиске! 🏠",
        "Всего доброго! Обращайтесь, если понадобится помощь.",
    ],
}

# Off-topic responses (redirect to real estate)
OFF_TOPIC_RESPONSES = [
    (
        "Я специализируюсь только на недвижимости в Болгарии. 🏠\n\n"
        "Могу помочь найти:\n"
        "• Квартиры и апартаменты\n"
        "• Дома и виллы\n"
        "• Коммерческую недвижимость\n\n"
        "Что из этого вас интересует?"
    ),
    (
        "Извините, но я могу помочь только с вопросами о недвижимости в Болгарии.\n\n"
        "Напишите, например:\n"
        "• «Квартира в Несебре до 50000€»\n"
        "• «Дом у моря с 3 спальнями»\n"
        "• «Что есть в Солнечном берегу?»"
    ),
]


@observe(name="query-router")
def classify_query(query: str) -> QueryType:
    """Classify query type for routing decisions.

    Args:
        query: User query text

    Returns:
        QueryType enum indicating how to handle the query
    """
    query_stripped = query.strip()
    result = QueryType.COMPLEX  # Default

    # Check for chit-chat patterns first (highest priority)
    for pattern in _CHITCHAT_COMPILED:
        if pattern.search(query_stripped):
            logger.debug(f"Query classified as CHITCHAT: {pattern.pattern}")
            result = QueryType.CHITCHAT
            break
    else:
        # Check for off-topic patterns (before simple/complex)
        for pattern in _OFF_TOPIC_COMPILED:
            if pattern.search(query_stripped):
                logger.debug(f"Query classified as OFF_TOPIC: {pattern.pattern}")
                result = QueryType.OFF_TOPIC
                break
        else:
            # Check for simple patterns
            for pattern in _SIMPLE_COMPILED:
                if pattern.search(query_stripped):
                    logger.debug(f"Query classified as SIMPLE: {pattern.pattern}")
                    result = QueryType.SIMPLE
                    break
            else:
                # Default to complex (full RAG pipeline)
                logger.debug("Query classified as COMPLEX (full RAG)")

    # Track classification in Langfuse
    langfuse = get_client()
    langfuse.update_current_span(
        input={"query_preview": query[:50]},
        output={"type": result.value},
    )

    return result


def get_chitchat_response(query: str) -> str | None:
    """Get canned response for chit-chat queries.

    Args:
        query: User query text

    Returns:
        Canned response string, or None if not a chitchat query
    """
    import random

    query_lower = query.lower().strip()

    # Greetings
    if any(
        re.match(p, query_lower)
        for p in [
            r"^привет",
            r"^здравствуй",
            r"^добр",
            r"^хай",
            r"^хелло",
            r"^hi\b",
            r"^hello\b",
            r"^hey\b",
            r"^good\s+(morning|afternoon|evening)",
        ]
    ):
        return random.choice(CHITCHAT_RESPONSES["greeting"])

    # Thanks
    if any(
        re.match(p, query_lower)
        for p in [
            r"^спасибо",
            r"^благодар",
            r"^круто",
            r"^отлично",
            r"^супер",
            r"^thanks?",
            r"^thank you",
            r"^great",
            r"^awesome",
        ]
    ):
        return random.choice(CHITCHAT_RESPONSES["thanks"])

    # Bot info
    if any(
        re.match(p, query_lower)
        for p in [
            r"^что ты (умеешь|можешь)",
            r"^кто ты",
            r"^ты бот",
            r"^what (can you|do you) do",
            r"^who are you",
            r"^are you",
        ]
    ):
        return random.choice(CHITCHAT_RESPONSES["bot_info"])

    # Farewell
    if any(
        re.match(p, query_lower)
        for p in [
            r"^пока",
            r"^до свидания",
            r"^всего доброго",
            r"^bye",
            r"^goodbye",
            r"^see you",
        ]
    ):
        return random.choice(CHITCHAT_RESPONSES["farewell"])

    return None


def get_off_topic_response() -> str:
    """Get response for off-topic queries.

    Returns:
        Response redirecting user to real estate topics
    """
    import random

    return random.choice(OFF_TOPIC_RESPONSES)


def is_off_topic(query: str) -> bool:
    """Quick check if query is off-topic.

    Args:
        query: User query text

    Returns:
        True if query matches off-topic patterns
    """
    return any(pattern.search(query) for pattern in _OFF_TOPIC_COMPILED)


def needs_rerank(query_type: QueryType, result_count: int) -> bool:
    """Check if reranking is needed based on query type and results.

    2026 best practice: Skip rerank for simple queries or few results.

    Args:
        query_type: Classified query type
        result_count: Number of search results

    Returns:
        True if reranking should be performed
    """
    # Skip rerank for simple queries
    if query_type == QueryType.SIMPLE:
        logger.debug("Skipping rerank for SIMPLE query")
        return False

    # Skip rerank if too few results
    if result_count <= 2:
        logger.debug(f"Skipping rerank: only {result_count} results")
        return False

    return True
