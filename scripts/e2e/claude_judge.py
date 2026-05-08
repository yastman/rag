"""Judge implementations for evaluating bot responses."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

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
    """Result from judge model."""

    relevance: CriterionScore
    completeness: CriterionScore
    filter_accuracy: CriterionScore
    tone_format: CriterionScore
    no_hallucination: CriterionScore
    total_score: float
    passed: bool
    summary: str

    @classmethod
    def from_dict(cls, data: dict) -> JudgeResult:
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


class _BaseLLMJudge:
    """Shared logic for judge implementations."""

    def __init__(self, config: E2EConfig):
        self.config = config

    @staticmethod
    def _build_user_prompt(scenario: TestScenario, bot_response: str) -> str:
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

        return f"""## Запрос пользователя
{scenario.query}

## Ожидаемые фильтры
{filters_str}

## Ответ бота
{bot_response}

Оцени ответ по критериям. Ответь ТОЛЬКО валидным JSON."""

    @staticmethod
    def _parse_judge_response(response_text: str) -> JudgeResult:
        logger.debug("Judge response: %s...", response_text[:200])

        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse judge response: %s", exc)
            return JudgeResult(
                relevance=CriterionScore(score=0, reason="Parse error"),
                completeness=CriterionScore(score=0, reason="Parse error"),
                filter_accuracy=CriterionScore(score=0, reason="Parse error"),
                tone_format=CriterionScore(score=0, reason="Parse error"),
                no_hallucination=CriterionScore(score=0, reason="Parse error"),
                total_score=0.0,
                passed=False,
                summary=f"Failed to parse judge response: {exc}",
            )

        return JudgeResult.from_dict(data)


class LiteLLMJudge(_BaseLLMJudge):
    """OpenAI-compatible judge routed through LiteLLM or another proxy."""

    def __init__(self, config: E2EConfig):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.judge_api_key,
            base_url=config.judge_base_url,
            timeout=60.0,
        )

    async def evaluate(self, scenario: TestScenario, bot_response: str) -> JudgeResult:
        user_prompt = self._build_user_prompt(scenario, bot_response)

        response = await self._client.chat.completions.create(
            model=self.config.judge_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1024,
        )
        response_text = response.choices[0].message.content or ""
        return self._parse_judge_response(response_text)


class ClaudeJudge(_BaseLLMJudge):
    """Direct Anthropic judge (explicit opt-in mode only)."""

    def __init__(self, config: E2EConfig):
        super().__init__(config)
        import anthropic

        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    async def evaluate(self, scenario: TestScenario, bot_response: str) -> JudgeResult:
        import asyncio

        user_prompt = self._build_user_prompt(scenario, bot_response)

        response = await asyncio.to_thread(
            self._client.messages.create,
            model=self.config.judge_model,
            max_tokens=1024,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        response_text = response.content[0].text
        return self._parse_judge_response(response_text)


def build_judge(config: E2EConfig) -> LiteLLMJudge | ClaudeJudge:
    """Build judge instance for configured provider."""
    provider = (config.judge_provider or "").strip().lower()
    if provider in {"", "litellm", "openai-compatible", "openai"}:
        return LiteLLMJudge(config)
    if provider == "anthropic-direct":
        return ClaudeJudge(config)
    raise ValueError(
        f"Unsupported E2E_JUDGE_PROVIDER '{config.judge_provider}'. "
        "Use 'litellm' or 'anthropic-direct'."
    )


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
