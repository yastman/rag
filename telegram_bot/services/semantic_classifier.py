"""SemanticClassifier — RedisVL SemanticRouter-based query classifier.

Optional alternative to regex classification. Enabled via CLASSIFIER_MODE=semantic.
Falls back to regex if Redis is unavailable or routing fails.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)

# --- Route references (Russian) ---
# Mirror the regex categories from classify.py

_FAQ_REFERENCES = [
    "как оформить покупку",
    "какие документы нужны для покупки",
    "сколько стоит оформление сделки",
    "как арендовать квартиру",
    "что нужно для покупки недвижимости",
    "налоги при покупке недвижимости в Болгарии",
    "процедура оформления сделки",
    "ВНЖ при покупке недвижимости",
    "способы оплаты квартиры",
    "порядок покупки недвижимости",
    "можно ли купить без агента",
    "нужно ли нотариальное заверение",
    "какие расходы при покупке",
    "как получить ВНЖ",
]

_CHITCHAT_REFERENCES = [
    "привет",
    "здравствуйте",
    "добрый день",
    "как дела",
    "спасибо",
    "благодарю",
    "пока",
    "до свидания",
    "кто ты",
    "что ты умеешь",
    "ты бот",
    "как тебя зовут",
    "всего доброго",
    "привет как дела",
    "hello",
    "hi there",
]

_OFF_TOPIC_REFERENCES = [
    "как написать код на python",
    "рецепт борща",
    "формула воды H2O",
    "посоветуй фильм на вечер",
    "лечение простуды таблетками",
    "биткоин инвестиции криптовалюта",
    "экзамен в университете",
    "вакансия разработчика",
    "история России",
    "столица Франции",
    "как приготовить пиццу",
    "купить авиабилет",
    "акции на бирже",
]

_STRUCTURED_REFERENCES = [
    "двухкомнатная квартира до 80000 евро",
    "трёхкомнатная квартира с балконом",
    "студия до 50000 евро",
    "квартира на третьем этаже",
    "апартаменты 40 квадратных метров",
    "дом с тремя спальнями",
    "2 комнаты до 80000 евро",
    "однокомнатная квартира 35 кв м",
    "вилла 200 квадратных метров",
]

_ENTITY_REFERENCES = [
    "квартира в Несебре",
    "апартаменты в Бургасе",
    "недвижимость в Варне",
    "Солнечный берег апартаменты",
    "жилой комплекс в Созополе",
    "Святой Влас виллы",
    "Sunny Beach apartments",
    "комплекс в Поморие",
    "жк в Равде",
    "золотые пески квартира",
]


class SemanticClassifier:
    """Classifier wrapping RedisVL SemanticRouter for query type detection.

    Supported query types: FAQ, CHITCHAT, OFF_TOPIC, STRUCTURED, ENTITY.
    Unmatched queries return GENERAL.
    """

    def __init__(
        self,
        redis_url: str = "redis://redis:6379",
        distance_threshold: float = 0.5,
        vectorizer: Any = None,
    ) -> None:
        self._available = False
        self._router: Any = None
        try:
            from redisvl.extensions.router import Route, SemanticRouter

            routes = [
                Route(
                    name="CHITCHAT",
                    references=_CHITCHAT_REFERENCES,
                    distance_threshold=distance_threshold,
                ),
                Route(
                    name="OFF_TOPIC",
                    references=_OFF_TOPIC_REFERENCES,
                    distance_threshold=distance_threshold,
                ),
                Route(
                    name="STRUCTURED",
                    references=_STRUCTURED_REFERENCES,
                    distance_threshold=distance_threshold,
                ),
                Route(
                    name="FAQ",
                    references=_FAQ_REFERENCES,
                    distance_threshold=distance_threshold,
                ),
                Route(
                    name="ENTITY",
                    references=_ENTITY_REFERENCES,
                    distance_threshold=distance_threshold,
                ),
            ]
            kwargs: dict[str, Any] = {
                "name": "query_classifier",
                "routes": routes,
                "redis_url": redis_url,
            }
            if vectorizer is not None:
                kwargs["vectorizer"] = vectorizer
            self._router = SemanticRouter(**kwargs)
            self._available = True
            logger.info("SemanticClassifier initialized (redis_url=%s)", redis_url)
        except Exception as exc:
            logger.warning(
                "SemanticClassifier unavailable, will fallback to regex: %s",
                exc,
            )

    @property
    def available(self) -> bool:
        """Return True if SemanticRouter is ready."""
        return self._available

    def classify(self, query: str) -> str:
        """Classify query using SemanticRouter.

        Args:
            query: User query text.

        Returns:
            One of: FAQ, CHITCHAT, OFF_TOPIC, STRUCTURED, ENTITY, GENERAL.

        Raises:
            RuntimeError: If router is not available.
        """
        if not self._available or self._router is None:
            raise RuntimeError("SemanticClassifier not available")
        match = self._router(query)
        if match and match.name:
            return str(match.name)
        return "GENERAL"
