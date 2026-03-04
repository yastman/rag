"""classify_node — regex-based query classification for the RAG pipeline.

Classifies user queries into 6 types: CHITCHAT, OFF_TOPIC, STRUCTURED,
FAQ, ENTITY, GENERAL. Returns canned responses for CHITCHAT/OFF_TOPIC.
"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


# --- Query type constants ---

CHITCHAT = "CHITCHAT"
OFF_TOPIC = "OFF_TOPIC"
STRUCTURED = "STRUCTURED"
FAQ = "FAQ"
ENTITY = "ENTITY"
GENERAL = "GENERAL"

# --- Regex patterns ---

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
    # Travel (non-property)
    r"\b(билет|самолёт|поезд|отел[^ьн]|гостиниц|бронирован)\b",
    r"\b(flight|ticket|hotel|booking)\b",
    # General knowledge
    r"\b(кто (такой|такая)|что такое|когда был|история)\b",
    r"\b(столица|президент|население)\b",
    # Math/Science
    r"\b(формула|уравнение|теорема|физика|химия|математика)\b",
    # Entertainment
    r"\b(фильм|сериал|музыка|песня|игр[аы]|movie|game[s]?|music)\b",
    # Finance (non-property)
    r"\b(акции|биржа|криптовалюта|биткоин|инвестиц|трейдинг)\b",
    r"\b(crypto|bitcoin|stock|trading)\b",
    # Jobs (non-property)
    r"\b(вакансия|работа[^ть]|резюме|зарплата|job|career|salary)\b",
    # Education
    r"\b(экзамен|школа|универси|курс|диплом|exam|university)\b",
]

STRUCTURED_PATTERNS = [
    r"\d+\s*(комнат|спал|bedroom|room)",
    r"(одно|двух|трёх|четырёх)комнатн",
    r"\d+\s*(кв\.?\s*м|м²|sqm|square)",
    r"(до|от|больше|меньше)\s*\d+\s*(евро|€|\$|лв|bgn)",
    r"\d+\s*(евро|€|\$|лв|bgn)",
    r"этаж\s*\d+",
    r"\d+\s*этаж",
    r"корпус\s*\d+",
]

FAQ_PATTERNS = [
    r"как (оформить|купить|продать|арендовать|получить|сделать)",
    r"какие (документы|налоги|расходы|условия)",
    r"сколько (стоит|времени|нужно)",
    r"можно ли\b",
    r"нужно ли\b",
    r"что (нужно|необходимо|требуется)",
    r"(процедура|процесс|порядок)\s+(покупки|оформлен|регистрац)",
    r"(ВНЖ|вид на жительство|гражданств)",
    r"(налог|сбор|пошлин|комисс)",
]

ENTITY_PATTERNS = [
    r"(Несебр|Бургас|Варна|София|Пловдив|Созопол|Поморие|Равда)",
    r"(Солнечный берег|Святой Влас|Золотые пески|Банско)",
    r"(Sunny Beach|Sveti Vlas|Golden Sands|Nessebar)",
    r"комплекс\s+[\"«]?\w+",
    r"жк\s+[\"«]?\w+",
]

# Pre-compile all patterns
_CHITCHAT_COMPILED = [re.compile(p, re.IGNORECASE) for p in CHITCHAT_PATTERNS]
_OFF_TOPIC_COMPILED = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]
_STRUCTURED_COMPILED = [re.compile(p, re.IGNORECASE) for p in STRUCTURED_PATTERNS]
_FAQ_COMPILED = [re.compile(p, re.IGNORECASE) for p in FAQ_PATTERNS]
_ENTITY_COMPILED = [re.compile(p, re.IGNORECASE) for p in ENTITY_PATTERNS]

# --- Canned responses ---

CHITCHAT_RESPONSES: dict[str, list[str]] = {
    "greeting": [
        "Привет! 👋 Я помогу найти недвижимость. Что вас интересует?",
        "Здравствуйте! Чем могу помочь? Ищете квартиру или дом?",
    ],
    "thanks": [
        "Пожалуйста! Если будут ещё вопросы — обращайтесь.",
        "Рад помочь! Нужно что-то ещё?",
    ],
    "bot_info": [
        "Я бот-помощник по недвижимости. Могу найти квартиры, "
        "дома, апартаменты по вашим критериям (город, бюджет, количество комнат).",
    ],
    "farewell": [
        "До свидания! Удачи в поиске! 🏠",
        "Всего доброго! Обращайтесь, если понадобится помощь.",
    ],
}

OFF_TOPIC_RESPONSES = [
    (
        "Я специализируюсь только на недвижимости. 🏠\n\n"
        "Могу помочь найти:\n"
        "• Квартиры и апартаменты\n"
        "• Дома и виллы\n"
        "• Коммерческую недвижимость\n\n"
        "Что из этого вас интересует?"
    ),
    (
        "Извините, но я могу помочь только с вопросами о недвижимости.\n\n"
        "Напишите, например:\n"
        "• «Квартира в Несебре до 50000€»\n"
        "• «Дом у моря с 3 спальнями»\n"
        "• «Что есть в Солнечном берегу?»"
    ),
]


def _match_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _get_chitchat_response(query: str) -> str:
    """Pick a canned response based on chitchat sub-category."""
    q = query.lower().strip()

    greeting_re = [
        r"^привет",
        r"^здравствуй",
        r"^добр",
        r"^хай",
        r"^хелло",
        r"^салют",
        r"^hi\b",
        r"^hello\b",
        r"^hey\b",
        r"^good\s+(morning|afternoon|evening)",
    ]
    thanks_re = [
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
    bot_re = [
        r"^что ты (умеешь|можешь)",
        r"^кто ты",
        r"^ты бот",
        r"^what (can you|do you) do",
        r"^who are you",
        r"^are you",
    ]
    farewell_re = [
        r"^пока",
        r"^до свидания",
        r"^всего доброго",
        r"^bye",
        r"^goodbye",
        r"^see you",
    ]

    for patterns, category in [
        (greeting_re, "greeting"),
        (thanks_re, "thanks"),
        (bot_re, "bot_info"),
        (farewell_re, "farewell"),
    ]:
        if any(re.match(p, q) for p in patterns):
            return random.choice(CHITCHAT_RESPONSES[category])

    return random.choice(CHITCHAT_RESPONSES["greeting"])


@observe(name="classify-query", capture_input=False, capture_output=False)
def classify_query(query: str) -> str:
    """Classify query into one of 6 types using regex patterns.

    Priority order: CHITCHAT > OFF_TOPIC > STRUCTURED > FAQ > ENTITY > GENERAL.
    """
    text = query.strip()
    lf = get_client()
    lf.update_current_span(input={"query_length": len(text)})

    if _match_any(_CHITCHAT_COMPILED, text):
        query_type = CHITCHAT
    elif _match_any(_OFF_TOPIC_COMPILED, text):
        query_type = OFF_TOPIC
    elif _match_any(_STRUCTURED_COMPILED, text):
        query_type = STRUCTURED
    elif _match_any(_FAQ_COMPILED, text):
        query_type = FAQ
    elif _match_any(_ENTITY_COMPILED, text):
        query_type = ENTITY
    else:
        query_type = GENERAL

    lf.update_current_span(output={"query_type": query_type})
    return query_type


@observe(name="node-classify")
async def classify_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """LangGraph node: classify the user query.

    Reads the last user message, classifies it, and optionally sets
    a canned response for CHITCHAT/OFF_TOPIC queries.

    Args:
        state: Current graph state.
        runtime: LangGraph Runtime with GraphContext (classifier).

    Returns partial state update with query_type, response (if canned),
    and latency_stages["classify"].
    """
    t0 = time.perf_counter()
    classifier = runtime.context.get("classifier")

    messages = state["messages"]
    query = messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]

    if classifier is not None and classifier.available:
        try:
            query_type = classifier.classify(query)
            logger.info("Semantic query classified as %s: %.50s", query_type, query)
        except Exception as exc:
            logger.warning("SemanticClassifier failed, falling back to regex: %s", exc)
            query_type = classify_query(query)
            logger.info("Query classified as %s: %.50s", query_type, query)
    else:
        query_type = classify_query(query)
        logger.info("Query classified as %s: %.50s", query_type, query)

    result: dict[str, Any] = {
        "query_type": query_type,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
        "latency_stages": {**state.get("latency_stages", {}), "classify": time.perf_counter() - t0},
    }

    if query_type == CHITCHAT:
        result["response"] = _get_chitchat_response(query)
    elif query_type == OFF_TOPIC:
        result["response"] = random.choice(OFF_TOPIC_RESPONSES)

    return result
