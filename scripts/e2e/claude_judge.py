"""Judge implementations for evaluating bot responses."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from openai import AsyncOpenAI

from .config import E2EConfig
from .scenarios import TestGroup, TestScenario


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
    check_details: dict | None = None

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
            check_details=data.get("check_details"),
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
    """Judge routed through the in-process LiteLLM SDK router."""

    def __init__(self, config: E2EConfig):
        super().__init__(config)
        from src.runtime.llm import create_llm_client

        self._client = create_llm_client(model=config.judge_model, timeout=60.0)


class OpenAICompatibleJudge(_BaseLLMJudge):
    """Judge routed through an explicitly configured OpenAI-compatible endpoint."""

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

        from anthropic.types import TextBlock

        user_prompt = self._build_user_prompt(scenario, bot_response)

        response = await asyncio.to_thread(
            lambda: self._client.messages.create(
                model=self.config.judge_model,
                max_tokens=1024,
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        )
        block = response.content[0]
        if not isinstance(block, TextBlock):
            raise ValueError(f"Unexpected non-text block from Claude judge: {type(block).__name__}")
        response_text = block.text
        return self._parse_judge_response(response_text)


def build_judge(config: E2EConfig) -> LiteLLMJudge | OpenAICompatibleJudge | ClaudeJudge:
    """Build judge instance for configured provider."""
    provider = (config.judge_provider or "").strip().lower()
    if provider in {"", "litellm"}:
        return LiteLLMJudge(config)
    if provider in {"openai-compatible", "openai"}:
        return OpenAICompatibleJudge(config)
    if provider == "anthropic-direct":
        return ClaudeJudge(config)
    raise ValueError(
        f"Unsupported E2E_JUDGE_PROVIDER '{config.judge_provider}'. "
        "Use 'litellm' or 'anthropic-direct'."
    )


class PassthroughJudge:
    """Deterministic judge with product-meaningful checks (no LLM needed)."""

    def __init__(self, config: E2EConfig):
        self.config = config

    @staticmethod
    def _contains_any_keyword(response: str, keywords: list[str]) -> bool:
        lowered = response.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    @staticmethod
    def _generic_fallback_detected(response: str) -> bool:
        lowered = response.lower()
        bad_markers = [
            "не нашел информацию",
            "попробуйте переформулировать",
            "не удалось найти",
            "сервис временно недоступен",
        ]
        return any(marker in lowered for marker in bad_markers)

    @staticmethod
    def _extract_price_values(response: str) -> tuple[list[int], list[str]]:
        """Return normalized prices and explicit malformed price candidates."""
        values: list[int] = []
        unsupported_tokens: list[str] = []
        numeric_candidate = r"\d(?:[\d\s._,]*\d)?"
        for match in re.finditer(
            rf"(?<![\d.,])(?:(?:€|евро\b)\s*(?P<prefix>{numeric_candidate})|"
            rf"(?P<suffix>{numeric_candidate})\s*(?:€|евро\b))",
            response.lower(),
        ):
            raw_value = (match.group("prefix") or match.group("suffix")).strip()
            if re.fullmatch(r"\d+|\d{1,3}(?:[\s_,]\d{3})+", raw_value):
                values.append(int(re.sub(r"[\s_,]", "", raw_value)))
            else:
                unsupported_tokens.append(raw_value)
        for match in re.finditer(
            rf"(?<![\d.,])(?P<value>{numeric_candidate})\s*(?:k|к)\b",
            response.lower(),
        ):
            try:
                normalized = Decimal(match.group("value").replace(",", ".")) * 1000
            except InvalidOperation:
                unsupported_tokens.append(match.group("value"))
            else:
                if normalized != normalized.to_integral_value():
                    unsupported_tokens.append(match.group("value"))
                    continue
                values.append(int(normalized))
        return values, unsupported_tokens

    @staticmethod
    def _extract_room_counts(response: str) -> tuple[list[int], list[str]]:
        """Return room counts and explicit malformed room candidates."""
        lowered = response.lower()
        counts: list[int] = []
        unsupported_tokens: list[str] = []
        numeric_candidate = r"\d(?:[\d\s._,]*\d)?"
        for match in re.finditer(
            rf"(?<![\d.,])(?P<value>{numeric_candidate})\s*[- ]?"
            rf"(?:комнат\w*|комн\w*|спальн\w*)",
            lowered,
        ):
            raw_value = match.group("value").strip()
            if raw_value.isdecimal():
                counts.append(int(raw_value))
            else:
                unsupported_tokens.append(raw_value)
        for count, marker in (
            (0, "студи"),
            (1, "однокомнат"),
            (2, "двухкомнат"),
            (3, "трехкомнат"),
            (4, "четырехкомнат"),
        ):
            if marker in lowered:
                counts.append(count)
        return counts, unsupported_tokens

    @staticmethod
    def _extract_distances_in_meters(response: str) -> tuple[list[Decimal], list[str]]:
        """Return sea-distance values and explicit malformed numeric candidates."""
        numeric_candidate = r"\d(?:[\d\s._,]*\d)?"
        unit = r"км|километр\w*|м|метр\w*"
        destination = r"(?:мор\w*|пляж\w*)"
        patterns = (
            rf"(?<![\d.,])(?P<value>{numeric_candidate})\s*(?P<unit>{unit})\b\s*"
            rf"(?:до|от)\s*{destination}\b",
            rf"(?:до|от)\s*{destination}\b\s*(?P<value>{numeric_candidate})\s*"
            rf"(?P<unit>{unit})\b",
        )
        distances: list[Decimal] = []
        unsupported_tokens: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, response.lower()):
                raw_value = match.group("value").strip()
                if re.fullmatch(r"\d+", raw_value):
                    value = Decimal(raw_value)
                elif re.fullmatch(r"\d{1,3}(?:[\s_]\d{3})+", raw_value):
                    value = Decimal(re.sub(r"[\s_]", "", raw_value))
                elif re.fullmatch(r"\d+(?:[.,]\d+)?", raw_value):
                    value = Decimal(raw_value.replace(",", "."))
                else:
                    unsupported_tokens.append(raw_value)
                    continue
                distances.append(value * 1000 if match.group("unit").startswith("к") else value)
        return distances, unsupported_tokens

    @staticmethod
    def _format_observed_values(values: Sequence[int | Decimal]) -> str:
        if not values:
            return "none"
        formatted_values: list[str] = []
        for value in values:
            formatted = format(Decimal(value).normalize(), "f")
            if "." in formatted:
                formatted = formatted.rstrip("0").rstrip(".")
            formatted_values.append(formatted)
        return ", ".join(formatted_values)

    @staticmethod
    def _city_terms(city: str) -> list[str]:
        """Use each stable city-word stem so case endings do not become a false failure."""
        return [term[:6] for term in re.findall(r"[^\W\d_]+", city.lower())]

    @staticmethod
    def _check_filter_evidence(response: str, filters) -> tuple[dict[str, bool], dict[str, str]]:
        lowered = response.lower()
        checks: dict[str, bool] = {}
        diagnostics: dict[str, str] = {}
        prices: list[int] = []
        unsupported_price_tokens: list[str] = []
        if filters.price_max is not None or filters.price_min is not None:
            prices, unsupported_price_tokens = PassthroughJudge._extract_price_values(response)
        price_diagnostics = f"{PassthroughJudge._format_observed_values(prices)}" + (
            f"; unsupported EUR tokens: {', '.join(unsupported_price_tokens)}"
            if unsupported_price_tokens
            else ""
        )

        if filters.price_max is not None:
            checks["price_max"] = (
                bool(prices)
                and not unsupported_price_tokens
                and all(price <= filters.price_max for price in prices)
            )
            diagnostics["price_max"] = (
                f"expected <= {filters.price_max} EUR; observed EUR values: {price_diagnostics}"
            )

        if filters.price_min is not None:
            checks["price_min"] = (
                bool(prices)
                and not unsupported_price_tokens
                and all(price >= filters.price_min for price in prices)
            )
            diagnostics["price_min"] = (
                f"expected >= {filters.price_min} EUR; observed EUR values: {price_diagnostics}"
            )

        if filters.city is not None:
            expected_terms = PassthroughJudge._city_terms(filters.city)
            observed_terms = [term for term in expected_terms if term in lowered]
            checks["city"] = len(observed_terms) == len(expected_terms)
            diagnostics["city"] = (
                f"expected city terms: {', '.join(expected_terms)}; observed city terms: "
                f"{', '.join(observed_terms) or 'none'}"
            )

        if filters.rooms is not None:
            room_counts, unsupported_room_tokens = PassthroughJudge._extract_room_counts(response)
            room_diagnostics = f"{PassthroughJudge._format_observed_values(room_counts)}" + (
                f"; unsupported room tokens: {', '.join(unsupported_room_tokens)}"
                if unsupported_room_tokens
                else ""
            )
            checks["rooms"] = (
                bool(room_counts)
                and not unsupported_room_tokens
                and all(room_count == filters.rooms for room_count in room_counts)
            )
            diagnostics["rooms"] = (
                f"expected {filters.rooms} rooms; observed room counts: {room_diagnostics}"
            )

        if filters.distance_to_sea_max is not None:
            distances, unsupported_distance_tokens = PassthroughJudge._extract_distances_in_meters(
                response
            )
            checks["distance_to_sea_max"] = (
                bool(distances)
                and not unsupported_distance_tokens
                and all(distance <= filters.distance_to_sea_max for distance in distances)
            )
            distance_diagnostics = PassthroughJudge._format_observed_values(distances) + (
                f"; unsupported distance tokens: {', '.join(unsupported_distance_tokens)}"
                if unsupported_distance_tokens
                else ""
            )
            diagnostics["distance_to_sea_max"] = (
                f"expected <= {filters.distance_to_sea_max} m; observed distances: "
                f"{distance_diagnostics}"
            )

        return checks, diagnostics

    async def evaluate(
        self,
        scenario: TestScenario,
        bot_response: str,
    ) -> JudgeResult:
        """Evaluate bot response with deterministic product checks."""
        if not bot_response or not bot_response.strip():
            return JudgeResult(
                relevance=CriterionScore(0, "Empty response"),
                completeness=CriterionScore(0, "Empty response"),
                filter_accuracy=CriterionScore(0, "Empty response"),
                tone_format=CriterionScore(0, "Empty response"),
                no_hallucination=CriterionScore(0, "Empty response"),
                total_score=0.0,
                passed=False,
                summary="Bot returned empty response",
                check_details={"presence": False},
            )

        check_details: dict = {"presence": True}
        failed_checks: list[str] = []

        # 1. Expected keywords
        if scenario.expected_keywords:
            has_keywords = self._contains_any_keyword(bot_response, scenario.expected_keywords)
            check_details["expected_keywords"] = has_keywords
            if not has_keywords:
                failed_checks.append(f"Missing expected keywords: {scenario.expected_keywords}")
        else:
            check_details["expected_keywords"] = None

        # 2. Generic fallback rejection for RAG/property scenarios
        is_rag_property = scenario.group in {
            TestGroup.PRICE_FILTERS,
            TestGroup.ROOM_FILTERS,
            TestGroup.LOCATION_FILTERS,
            TestGroup.SEARCH,
            TestGroup.IMMIGRATION,
            TestGroup.VOICE_TRANSCRIPTION,
        }
        if is_rag_property and scenario.id not in {"7.1", "8.3"}:
            fallback = self._generic_fallback_detected(bot_response)
            check_details["generic_fallback"] = fallback
            if fallback:
                failed_checks.append("Generic fallback detected")
        else:
            check_details["generic_fallback"] = None

        # 3. Expected filter evidence
        if scenario.expected_filters is not None:
            evidence, diagnostics = self._check_filter_evidence(
                bot_response, scenario.expected_filters
            )
            check_details["filter_evidence"] = evidence
            check_details["filter_diagnostics"] = diagnostics
            missing = [k for k, v in evidence.items() if not v]
            if missing:
                failed_checks.append(
                    "Missing filter evidence: "
                    + "; ".join(f"{key}: {diagnostics[key]}" for key in missing)
                )
        else:
            check_details["filter_evidence"] = None
            check_details["filter_diagnostics"] = None

        passed = not failed_checks

        if passed:
            summary = "Bot responded with meaningful content (no-judge mode)"
            if check_details.get("expected_keywords") is True:
                summary += " | keywords matched"
            if check_details.get("filter_evidence"):
                summary += f" | filters: {check_details['filter_evidence']}"
        else:
            summary = "; ".join(failed_checks)

        score = 8.0 if passed else 2.0
        reason = summary if passed else "Deterministic check failed"

        return JudgeResult(
            relevance=CriterionScore(int(score), reason),
            completeness=CriterionScore(int(score), reason),
            filter_accuracy=CriterionScore(int(score), reason),
            tone_format=CriterionScore(int(score), reason),
            no_hallucination=CriterionScore(int(score), reason),
            total_score=score,
            passed=passed,
            summary=summary,
            check_details=check_details,
        )
