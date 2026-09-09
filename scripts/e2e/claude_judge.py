"""Judge implementations for evaluating bot responses."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from .config import E2EConfig
from .scenarios import ExpectedFilters, TestGroup, TestScenario


logger = logging.getLogger(__name__)

# ── deterministic value-extraction patterns (issue #3391) ────────────────
# Numeric token: digits with optional space/NBSP/dot thousands groups
# ("70000", "70 000", "70.000").
_NUM_BODY = r"\d+(?:[ \u00a0.]\d{3})*"
# Optional thousand multiplier ("80к", "70 тысяч", "70 тыс.").
_THOUSANDS = r"(?:\s*(?:[kк]|тысяч\w*|тыс\.?))?"

# A price must be currency-anchored: a €-prefixed number ("€70000") or one or
# more numeric items joined by range connectors immediately followed by currency
# ("70 000 евро", "от 100к до 150к евро"). A trailing "/м" marks a per-square-
# meter rate, not a listing price. Bare numbers ("80к") stay unparsed —
# ambiguity cannot count green.
_PRICE_EXPR_RE = re.compile(
    r"(?:€\s*(?P<prefix_item>"
    + _NUM_BODY
    + r")|(?P<expr>"
    + _NUM_BODY
    + _THOUSANDS
    + r"(?:\s*(?:до|—|–|и|,)?\s*"
    + _NUM_BODY
    + _THOUSANDS
    + r")*)\s*(?:евро\b|€))(?!\s*/\s*(?:м|кв))",
    re.IGNORECASE,
)

# Individual numeric item inside a price expression (number + optional multiplier).
_PRICE_ITEM_RE = re.compile(
    r"(?P<raw>" + _NUM_BODY + r")(?P<mult>\s*(?:[kк]|тысяч\w*|тыс\.?))?",
    re.IGNORECASE,
)

# Room counts need explicit "комнат" context ("2-комнатная", "двух комнат",
# "с двумя комнатами") or the studio marker ("студия") for rooms == 0.
_ROOM_RE = re.compile(
    r"(?:(?P<num>\d{1,2})\s*-?\s*комнат\w*)"
    r"|(?:(?P<word>одно|двух|двумя|трех|трёх|тремя|четырех|четырёх|четырьмя|пяти|шести)\s*-?\s*комнат\w*)"
    r"|(?P<studio>\bстуди\w*)",
    re.IGNORECASE,
)
_ROOM_WORD_VALUES = {
    "одно": 1,
    "двух": 2,
    "двумя": 2,
    "трех": 3,
    "трёх": 3,
    "тремя": 3,
    "четырех": 4,
    "четырёх": 4,
    "четырьмя": 4,
    "пяти": 5,
    "шести": 6,
}

# Distance values: number + "м"/"метр" inside a clause that mentions the sea
# or a beach. "м2"/"м²" is apartment area, not a distance.
_SEA_MARK_RE = re.compile(r"(?:мор|пляж|побереж)", re.IGNORECASE)
_METERS_RE = re.compile(
    r"(?P<raw>\d+(?:[ \u00a0]\d{3})*)\s*(?:метр\w*|м(?![a-zа-яё2²\d]))",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n\r]")

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
        for keyword in keywords:
            normalized = keyword.lower()
            if normalized.isdigit():
                # Numeric keywords must be standalone: "120" must not match "1200".
                if re.search(rf"(?<!\d){re.escape(normalized)}(?!\d)", lowered):
                    return True
            elif normalized in lowered:
                return True
        return False

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
    def _number_to_int(raw: str) -> int:
        """Normalize a numeric token ("70000", "70 000", "70.000") to int."""
        return int(re.sub(r"[ \u00a0.]", "", raw))

    @staticmethod
    def _extract_prices(response: str) -> list[int]:
        """Extract explicit currency-marked prices, normalized to integer euros."""
        prices: list[int] = []
        for expr_match in _PRICE_EXPR_RE.finditer(response):
            for item_match in _PRICE_ITEM_RE.finditer(expr_match.group(0)):
                value = PassthroughJudge._number_to_int(item_match.group("raw"))
                if item_match.group("mult"):
                    value *= 1000
                prices.append(value)
        return prices

    @staticmethod
    def _extract_room_counts(response: str) -> list[int]:
        """Extract explicit room-count mentions ("2-комнатная", "двух комнат", "студия")."""
        counts: list[int] = []
        for match in _ROOM_RE.finditer(response):
            if match.group("num") is not None:
                counts.append(int(match.group("num")))
            elif match.group("word") is not None:
                counts.append(_ROOM_WORD_VALUES[match.group("word").lower()])
            else:
                counts.append(0)
        return counts

    @staticmethod
    def _extract_distances_meters(response: str) -> list[int]:
        """Extract explicit sea/beach-adjacent distance values in meters."""
        distances: list[int] = []
        for clause in _CLAUSE_SPLIT_RE.split(response):
            if not _SEA_MARK_RE.search(clause):
                continue
            for match in _METERS_RE.finditer(clause):
                distances.append(PassthroughJudge._number_to_int(match.group("raw")))
        return distances

    @staticmethod
    def _city_present(response: str, city: str) -> bool:
        """Check that every word of the requested city appears at a word start.

        Word-start prefixes keep the check inflection-tolerant ("Несебре",
        "Солнечном береге") without matching the city fragment mid-word.
        """
        words = [w for w in re.split(r"[\W_]+", response.lower()) if w]
        for token in city.lower().split():
            prefix = token[:5] if len(token) > 5 else token
            if not any(word.startswith(prefix) for word in words):
                return False
        return True

    @staticmethod
    def _check_filter_evidence(
        response: str, filters: ExpectedFilters
    ) -> tuple[dict[str, bool], dict[str, dict[str, object]]]:
        """Compare the requested filter values against values parsed from the response.

        Every parsed value must satisfy the requested constraint and at least one
        value must be present; text without explicit parseable values fails so
        ambiguity cannot count green. Returns per-filter verdicts plus diagnostics
        naming the expected constraint and the observed normalized values.
        """
        prices = PassthroughJudge._extract_prices(response)
        room_counts = PassthroughJudge._extract_room_counts(response)
        distances = PassthroughJudge._extract_distances_meters(response)
        checks: dict[str, bool] = {}
        diagnostics: dict[str, dict[str, object]] = {}

        if filters.price_max is not None:
            ok = bool(prices) and all(price <= filters.price_max for price in prices)
            checks["price_max"] = ok
            diagnostics["price_max"] = {
                "expected": f"all prices <= {filters.price_max}",
                "observed": prices,
            }

        if filters.price_min is not None:
            ok = bool(prices) and all(price >= filters.price_min for price in prices)
            checks["price_min"] = ok
            diagnostics["price_min"] = {
                "expected": f"all prices >= {filters.price_min}",
                "observed": prices,
            }

        if filters.rooms is not None:
            ok = bool(room_counts) and all(rooms == filters.rooms for rooms in room_counts)
            checks["rooms"] = ok
            diagnostics["rooms"] = {
                "expected": f"room count == {filters.rooms}",
                "observed": room_counts,
            }

        if filters.city is not None:
            ok = PassthroughJudge._city_present(response, filters.city)
            checks["city"] = ok
            diagnostics["city"] = {
                "expected": filters.city,
                "observed": "matched" if ok else "not found",
            }

        if filters.distance_to_sea_max is not None:
            ok = bool(distances) and all(
                distance <= filters.distance_to_sea_max for distance in distances
            )
            checks["distance_to_sea_max"] = ok
            diagnostics["distance_to_sea_max"] = {
                "expected": f"all distances <= {filters.distance_to_sea_max} м",
                "observed": distances,
            }

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
            if diagnostics:
                check_details["filter_diagnostics"] = diagnostics
            for key, ok in evidence.items():
                if not ok:
                    failed_checks.append(
                        f"{key}: expected {diagnostics[key]['expected']}, "
                        f"observed {diagnostics[key]['observed']}"
                    )
        else:
            check_details["filter_evidence"] = None

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
