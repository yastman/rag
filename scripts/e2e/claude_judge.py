"""Claude Judge for evaluating bot responses."""

import json
import logging
from dataclasses import dataclass

import anthropic

from .config import E2EConfig
from .test_scenarios import TestScenario


logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """Ты — судья качества ответов RAG-бота по недвижимости в Болгарии.

## Твоя задача
Оценить ответ бота по 5 критериям. Для каждого критерия дай балл 0-10.

## Критерии оценки

### 1. Relevance (релевантность) — 0-10
- 10: Ответ точно отвечает на вопрос
- 7-9: Ответ релевантен, но есть minor отклонения
- 4-6: Частично релевантен
- 0-3: Не отвечает на вопрос

### 2. Completeness (полнота) — 0-10
- 10: Вся необходимая информация, конкретные цены/адреса
- 7-9: Достаточно информации для принятия решения
- 4-6: Базовая информация, не хватает деталей
- 0-3: Слишком короткий или пустой ответ

### 3. Filter Accuracy (точность фильтров) — 0-10
- 10: Все упомянутые объекты соответствуют фильтрам запроса
- 7-9: Большинство соответствует, 1-2 отклонения
- 4-6: Половина соответствует
- 0-3: Фильтры проигнорированы
- N/A: Если в запросе нет фильтров (верни 10)

### 4. Tone & Format (тон и формат) — 0-10
- 10: Дружелюбный тон, хорошее Markdown форматирование
- 7-9: Адекватный тон, читаемый формат
- 4-6: Нейтральный, но сложно читать
- 0-3: Грубый тон или нечитаемый формат

### 5. No Hallucination (без галлюцинаций) — 0-10
- 10: Все факты можно проверить, признаёт незнание
- 7-9: Нет явных выдумок
- 4-6: Есть сомнительные утверждения
- 0-3: Явно выдуманные данные

## Формат ответа
Ответь ТОЛЬКО валидным JSON без комментариев:
{
  "relevance": {"score": 8, "reason": "краткая причина"},
  "completeness": {"score": 7, "reason": "краткая причина"},
  "filter_accuracy": {"score": 9, "reason": "краткая причина"},
  "tone_format": {"score": 8, "reason": "краткая причина"},
  "no_hallucination": {"score": 10, "reason": "краткая причина"},
  "total_score": 8.2,
  "pass": true,
  "summary": "Краткий вердикт в 1-2 предложения"
}"""


@dataclass
class CriterionScore:
    """Score for a single criterion."""

    score: int
    reason: str


@dataclass
class JudgeResult:
    """Result from Claude Judge."""

    relevance: CriterionScore
    completeness: CriterionScore
    filter_accuracy: CriterionScore
    tone_format: CriterionScore
    no_hallucination: CriterionScore
    total_score: float
    passed: bool
    summary: str

    @classmethod
    def from_dict(cls, data: dict) -> "JudgeResult":
        """Create from dict."""
        return cls(
            relevance=CriterionScore(**data["relevance"]),
            completeness=CriterionScore(**data["completeness"]),
            filter_accuracy=CriterionScore(**data["filter_accuracy"]),
            tone_format=CriterionScore(**data["tone_format"]),
            no_hallucination=CriterionScore(**data["no_hallucination"]),
            total_score=data["total_score"],
            passed=data["pass"],
            summary=data["summary"],
        )


class ClaudeJudge:
    """Claude-based judge for evaluating bot responses."""

    # Weights for criteria
    WEIGHTS = {
        "relevance": 0.30,
        "completeness": 0.25,
        "filter_accuracy": 0.20,
        "tone_format": 0.15,
        "no_hallucination": 0.10,
    }

    def __init__(self, config: E2EConfig):
        """Initialize judge."""
        self.config = config
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    async def evaluate(
        self,
        scenario: TestScenario,
        bot_response: str,
    ) -> JudgeResult:
        """Evaluate bot response against scenario.

        Args:
            scenario: Test scenario with query and expectations
            bot_response: Bot's response text

        Returns:
            JudgeResult with scores and verdict
        """
        # Build evaluation prompt
        filters_str = "Нет"
        if scenario.expected_filters:
            filters_parts = []
            ef = scenario.expected_filters
            if ef.price_max:
                filters_parts.append(f"цена <= {ef.price_max}")
            if ef.price_min:
                filters_parts.append(f"цена >= {ef.price_min}")
            if ef.rooms is not None:
                filters_parts.append(f"комнат: {ef.rooms}")
            if ef.city:
                filters_parts.append(f"город: {ef.city}")
            if ef.distance_to_sea_max:
                filters_parts.append(f"до моря <= {ef.distance_to_sea_max}м")
            filters_str = ", ".join(filters_parts) if filters_parts else "Нет"

        user_prompt = f"""## Запрос пользователя
{scenario.query}

## Ожидаемые фильтры
{filters_str}

## Ответ бота
{bot_response}

Оцени ответ по критериям. Ответь ТОЛЬКО валидным JSON."""

        # Call Claude
        import asyncio

        response = await asyncio.to_thread(
            self._client.messages.create,
            model=self.config.judge_model,
            max_tokens=1024,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Parse response
        response_text = response.content[0].text
        logger.debug(f"Judge response: {response_text[:200]}...")

        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse judge response: {e}")
            # Return default failing result
            return JudgeResult(
                relevance=CriterionScore(score=0, reason="Parse error"),
                completeness=CriterionScore(score=0, reason="Parse error"),
                filter_accuracy=CriterionScore(score=0, reason="Parse error"),
                tone_format=CriterionScore(score=0, reason="Parse error"),
                no_hallucination=CriterionScore(score=0, reason="Parse error"),
                total_score=0.0,
                passed=False,
                summary=f"Failed to parse judge response: {e}",
            )

        return JudgeResult.from_dict(data)


class PassthroughJudge:
    """Simple judge that passes any non-empty bot response (no LLM needed)."""

    def __init__(self, config: E2EConfig):
        self.config = config

    async def evaluate(
        self,
        scenario: TestScenario,
        bot_response: str,
    ) -> JudgeResult:
        """Pass if bot returned a non-empty response."""
        if bot_response and bot_response.strip():
            return JudgeResult(
                relevance=CriterionScore(8, "Response received"),
                completeness=CriterionScore(8, "Response received"),
                filter_accuracy=CriterionScore(8, "Response received"),
                tone_format=CriterionScore(8, "Response received"),
                no_hallucination=CriterionScore(8, "Response received"),
                total_score=8.0,
                passed=True,
                summary="Bot responded (no-judge mode)",
            )
        return JudgeResult(
            relevance=CriterionScore(0, "Empty response"),
            completeness=CriterionScore(0, "Empty response"),
            filter_accuracy=CriterionScore(0, "Empty response"),
            tone_format=CriterionScore(0, "Empty response"),
            no_hallucination=CriterionScore(0, "Empty response"),
            total_score=0.0,
            passed=False,
            summary="Bot returned empty response",
        )
