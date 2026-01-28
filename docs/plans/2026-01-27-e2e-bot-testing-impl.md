# E2E Bot Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build automated E2E testing system for Telegram bot using Telethon userbot and Claude Judge for quality evaluation.

**Architecture:** Telethon sends messages to production bot, collects responses, Claude evaluates quality against rubric, results saved to JSON/HTML report.

**Tech Stack:** Telethon 1.36+, Anthropic SDK, Jinja2, Rich, Voyage AI (for test data embeddings)

---

## Task 1: Project Setup and Dependencies

**Files:**
- Create: `scripts/e2e/__init__.py`
- Create: `requirements-e2e.txt`
- Modify: `Makefile` (add e2e targets)

**Step 1: Create e2e package directory**

```bash
mkdir -p scripts/e2e
```

**Step 2: Create __init__.py**

```python
"""E2E testing package for Telegram bot."""
```

**Step 3: Create requirements-e2e.txt**

```
# E2E Testing Dependencies
telethon>=1.36.0
anthropic>=0.39.0
jinja2>=3.1.0
rich>=13.0.0
```

**Step 4: Add Makefile targets**

Add to Makefile after existing targets:

```makefile
# =============================================================================
# E2E TESTING
# =============================================================================

e2e-install: ## Install E2E testing dependencies
	@echo "$(BLUE)Installing E2E dependencies...$(NC)"
	pip install -r requirements-e2e.txt
	@echo "$(GREEN)✓ E2E dependencies installed$(NC)"

e2e-generate-data: ## Generate test property data
	@echo "$(BLUE)Generating test properties...$(NC)"
	python scripts/generate_test_properties.py
	@echo "$(GREEN)✓ Test data generated$(NC)"

e2e-index-data: ## Index test data into Qdrant
	@echo "$(BLUE)Indexing test properties...$(NC)"
	python scripts/index_test_properties.py
	@echo "$(GREEN)✓ Test data indexed$(NC)"

e2e-test: ## Run E2E tests against Telegram bot
	@echo "$(BLUE)Running E2E tests...$(NC)"
	python scripts/e2e/runner.py
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

e2e-test-group: ## Run specific test group (usage: make e2e-test-group GROUP=filters)
	python scripts/e2e/runner.py --group $(GROUP)

e2e-setup: e2e-install e2e-generate-data e2e-index-data ## Full E2E setup
	@echo "$(GREEN)✓ E2E setup complete$(NC)"
```

**Step 5: Commit**

```bash
git add scripts/e2e/__init__.py requirements-e2e.txt Makefile
git commit -m "chore: add E2E testing package structure and dependencies"
```

---

## Task 2: E2E Configuration

**Files:**
- Create: `scripts/e2e/config.py`

**Step 1: Create config.py with dataclass**

```python
"""E2E testing configuration."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class E2EConfig:
    """Configuration for E2E testing."""

    # Telegram Userbot (from my.telegram.org)
    telegram_api_id: int = field(
        default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0"))
    )
    telegram_api_hash: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_API_HASH", "")
    )
    telegram_session: str = "e2e_tester"

    # Target bot
    bot_username: str = field(
        default_factory=lambda: os.getenv("E2E_BOT_USERNAME", "@test_nika_homes_bot")
    )

    # Timeouts
    response_timeout: int = 60  # Streaming can be slow
    between_tests_delay: float = 2.0  # Rate limiting

    # Claude Judge
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    judge_model: str = "claude-sonnet-4-20250514"

    # Thresholds
    pass_score: float = 6.0

    # Qdrant test collection
    test_collection: str = "contextual_bulgaria_test"

    # Reports
    reports_dir: str = "reports"

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.telegram_api_id:
            errors.append("TELEGRAM_API_ID not set")
        if not self.telegram_api_hash:
            errors.append("TELEGRAM_API_HASH not set")
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY not set")
        return errors
```

**Step 2: Commit**

```bash
git add scripts/e2e/config.py
git commit -m "feat(e2e): add configuration dataclass"
```

---

## Task 3: Test Scenarios Dataclass

**Files:**
- Create: `scripts/e2e/test_scenarios.py`

**Step 1: Create test_scenarios.py**

```python
"""Test scenarios for E2E testing."""

from dataclasses import dataclass, field
from enum import Enum


class TestGroup(Enum):
    """Test scenario groups."""

    COMMANDS = "commands"
    CHITCHAT = "chitchat"
    PRICE_FILTERS = "price_filters"
    ROOM_FILTERS = "room_filters"
    LOCATION_FILTERS = "location_filters"
    SEARCH = "search"
    EDGE_CASES = "edge_cases"


@dataclass
class ExpectedFilters:
    """Expected filters for validation."""

    price_max: int | None = None
    price_min: int | None = None
    rooms: int | None = None
    city: str | None = None
    distance_to_sea_max: int | None = None


@dataclass
class TestScenario:
    """Single test scenario."""

    id: str
    name: str
    query: str
    group: TestGroup
    description: str = ""
    expected_keywords: list[str] = field(default_factory=list)
    expected_filters: ExpectedFilters | None = None
    should_skip_rag: bool = False  # For CHITCHAT tests
    timeout: int = 60


# All 25 test scenarios
SCENARIOS: list[TestScenario] = [
    # Group 1: Commands (4 tests)
    TestScenario(
        id="1.1",
        name="/start command",
        query="/start",
        group=TestGroup.COMMANDS,
        expected_keywords=["недвижимост", "Болгари", "привет", "помощ"],
    ),
    TestScenario(
        id="1.2",
        name="/help command",
        query="/help",
        group=TestGroup.COMMANDS,
        expected_keywords=["пример", "запрос", "команд"],
    ),
    TestScenario(
        id="1.3",
        name="/clear command",
        query="/clear",
        group=TestGroup.COMMANDS,
        expected_keywords=["очищ", "истори"],
    ),
    TestScenario(
        id="1.4",
        name="/stats command",
        query="/stats",
        group=TestGroup.COMMANDS,
        expected_keywords=["статистик", "кеш", "%"],
    ),
    # Group 2: CHITCHAT (4 tests)
    TestScenario(
        id="2.1",
        name="Greeting",
        query="Привет!",
        group=TestGroup.CHITCHAT,
        should_skip_rag=True,
        expected_keywords=["привет", "здравствуй", "добр"],
    ),
    TestScenario(
        id="2.2",
        name="Thanks",
        query="Спасибо большое",
        group=TestGroup.CHITCHAT,
        should_skip_rag=True,
        expected_keywords=["пожалуйста", "рад", "обращ"],
    ),
    TestScenario(
        id="2.3",
        name="Goodbye",
        query="До свидания",
        group=TestGroup.CHITCHAT,
        should_skip_rag=True,
        expected_keywords=["свидан", "удач", "всего"],
    ),
    TestScenario(
        id="2.4",
        name="How are you",
        query="Как дела?",
        group=TestGroup.CHITCHAT,
        should_skip_rag=True,
    ),
    # Group 3: Price Filters (4 tests)
    TestScenario(
        id="3.1",
        name="Price max",
        query="квартиры до 80000 евро",
        group=TestGroup.PRICE_FILTERS,
        expected_filters=ExpectedFilters(price_max=80000),
    ),
    TestScenario(
        id="3.2",
        name="Price range",
        query="от 100к до 150к",
        group=TestGroup.PRICE_FILTERS,
        expected_filters=ExpectedFilters(price_min=100000, price_max=150000),
    ),
    TestScenario(
        id="3.3",
        name="Price cheaper",
        query="дешевле 60 тысяч",
        group=TestGroup.PRICE_FILTERS,
        expected_filters=ExpectedFilters(price_max=60000),
    ),
    TestScenario(
        id="3.4",
        name="No price filter",
        query="покажи квартиры",
        group=TestGroup.PRICE_FILTERS,
        expected_filters=None,
    ),
    # Group 4: Room Filters (4 tests)
    TestScenario(
        id="4.1",
        name="Studio",
        query="студия",
        group=TestGroup.ROOM_FILTERS,
        expected_filters=ExpectedFilters(rooms=0),
        expected_keywords=["студи"],
    ),
    TestScenario(
        id="4.2",
        name="2 rooms",
        query="двухкомнатная квартира",
        group=TestGroup.ROOM_FILTERS,
        expected_filters=ExpectedFilters(rooms=2),
        expected_keywords=["2-комнат", "двухкомнат"],
    ),
    TestScenario(
        id="4.3",
        name="3+ rooms",
        query="трехкомнатные и больше",
        group=TestGroup.ROOM_FILTERS,
        expected_filters=ExpectedFilters(rooms=3),
        expected_keywords=["3-комнат", "трехкомнат"],
    ),
    TestScenario(
        id="4.4",
        name="Rooms + Price combo",
        query="2-комнатная до 100к",
        group=TestGroup.ROOM_FILTERS,
        expected_filters=ExpectedFilters(rooms=2, price_max=100000),
    ),
    # Group 5: Location Filters (3 tests)
    TestScenario(
        id="5.1",
        name="City cyrillic",
        query="квартиры в Несебр",
        group=TestGroup.LOCATION_FILTERS,
        expected_filters=ExpectedFilters(city="Несебр"),
        expected_keywords=["Несебр"],
    ),
    TestScenario(
        id="5.2",
        name="City translit",
        query="Sunny Beach",
        group=TestGroup.LOCATION_FILTERS,
        expected_filters=ExpectedFilters(city="Солнечный берег"),
        expected_keywords=["Солнечн", "берег"],
    ),
    TestScenario(
        id="5.3",
        name="Distance to sea",
        query="до 300м от моря",
        group=TestGroup.LOCATION_FILTERS,
        expected_filters=ExpectedFilters(distance_to_sea_max=300),
        expected_keywords=["мор", "пляж", "300"],
    ),
    # Group 6: Search (3 tests)
    TestScenario(
        id="6.1",
        name="Semantic search",
        query="уютная квартира с видом",
        group=TestGroup.SEARCH,
        expected_keywords=["квартир", "вид"],
    ),
    TestScenario(
        id="6.2",
        name="Exact match",
        query="корпус 5 этаж 3",
        group=TestGroup.SEARCH,
        expected_keywords=["корпус", "этаж"],
    ),
    TestScenario(
        id="6.3",
        name="Complex query",
        query="2-комн в Солнечный берег до 120к с видом на море",
        group=TestGroup.SEARCH,
        expected_filters=ExpectedFilters(
            rooms=2, city="Солнечный берег", price_max=120000
        ),
        expected_keywords=["Солнечн", "мор"],
    ),
    # Group 7: Edge Cases (3 tests)
    TestScenario(
        id="7.1",
        name="No results",
        query="замок за 1 евро",
        group=TestGroup.EDGE_CASES,
        expected_keywords=["не нашел", "не найден", "попробуйте"],
    ),
    TestScenario(
        id="7.2",
        name="Long query",
        query="Я ищу квартиру в Болгарии, желательно на побережье Черного моря, "
        "недалеко от пляжа, в хорошем состоянии, с мебелью, кондиционером, "
        "балконом с видом на море, в комплексе с бассейном и охраной, "
        "цена до 100 тысяч евро, 2 или 3 комнаты, этаж не первый и не последний",
        group=TestGroup.EDGE_CASES,
    ),
    TestScenario(
        id="7.3",
        name="Special chars",
        query="квартира <script>alert(1)</script>",
        group=TestGroup.EDGE_CASES,
        description="Should handle safely without XSS",
    ),
]


def get_scenarios_by_group(group: TestGroup) -> list[TestScenario]:
    """Get scenarios by group."""
    return [s for s in SCENARIOS if s.group == group]


def get_scenario_by_id(scenario_id: str) -> TestScenario | None:
    """Get scenario by ID."""
    for s in SCENARIOS:
        if s.id == scenario_id:
            return s
    return None
```

**Step 2: Commit**

```bash
git add scripts/e2e/test_scenarios.py
git commit -m "feat(e2e): add 25 test scenarios with filters and expectations"
```

---

## Task 4: Telethon Client Wrapper

**Files:**
- Create: `scripts/e2e/telegram_client.py`

**Step 1: Create telegram_client.py**

```python
"""Telethon client wrapper for E2E testing."""

import asyncio
import logging
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import Message

from .config import E2EConfig

logger = logging.getLogger(__name__)


@dataclass
class BotResponse:
    """Response from bot."""

    text: str
    message_id: int
    response_time_ms: int
    raw_message: Message | None = None


class E2ETelegramClient:
    """Telegram client for E2E testing."""

    def __init__(self, config: E2EConfig):
        """Initialize client."""
        self.config = config
        self._client: TelegramClient | None = None

    async def connect(self) -> None:
        """Connect to Telegram."""
        self._client = TelegramClient(
            self.config.telegram_session,
            self.config.telegram_api_id,
            self.config.telegram_api_hash,
        )
        await self._client.start()
        me = await self._client.get_me()
        logger.info(f"Connected as {me.username or me.phone}")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            logger.info("Disconnected from Telegram")

    async def send_and_wait(
        self,
        query: str,
        timeout: int | None = None,
    ) -> BotResponse:
        """Send message to bot and wait for response.

        Args:
            query: Message to send
            timeout: Response timeout in seconds (default from config)

        Returns:
            BotResponse with text and timing

        Raises:
            TimeoutError: If no response within timeout
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        timeout = timeout or self.config.response_timeout

        import time

        start_time = time.time()

        async with self._client.conversation(
            self.config.bot_username,
            timeout=timeout,
        ) as conv:
            await conv.send_message(query)
            logger.debug(f"Sent: {query[:50]}...")

            # Wait for response (handles streaming - waits for final message)
            response = await conv.get_response()

            # For streaming bots, wait a bit more for edits to complete
            await asyncio.sleep(1.0)

            # Try to get the latest version of the message (after edits)
            try:
                final_response = await conv.get_edit(timeout=3)
                response = final_response
            except asyncio.TimeoutError:
                # No edits, use original response
                pass

        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)

        logger.debug(f"Response ({response_time_ms}ms): {response.text[:100]}...")

        return BotResponse(
            text=response.text or "",
            message_id=response.id,
            response_time_ms=response_time_ms,
            raw_message=response,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
```

**Step 2: Commit**

```bash
git add scripts/e2e/telegram_client.py
git commit -m "feat(e2e): add Telethon client wrapper with conversation API"
```

---

## Task 5: Claude Judge

**Files:**
- Create: `scripts/e2e/claude_judge.py`

**Step 1: Create claude_judge.py**

```python
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
```

**Step 2: Commit**

```bash
git add scripts/e2e/claude_judge.py
git commit -m "feat(e2e): add Claude Judge with structured rubric evaluation"
```

---

## Task 6: Test Data Generator

**Files:**
- Create: `scripts/generate_test_properties.py`
- Create: `data/test_properties.json` (generated)

**Step 1: Create generate_test_properties.py**

```python
#!/usr/bin/env python3
"""Generate test property data for E2E testing."""

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Bulgarian property complexes (realistic names)
COMPLEXES = {
    "Солнечный берег": [
        "Сансет Резорт",
        "Голден Сэндс",
        "Сиа Бриз",
        "Роял Бич",
        "Атлантис",
        "Панорама Бич",
        "Оазис",
        "Империал",
    ],
    "Несебр": [
        "Олд Несебр",
        "Месембрия",
        "Форт Нокс",
        "Аполон",
        "Афродита",
    ],
    "Бургас": [
        "Сий Гарден",
        "Марина Сити",
        "Центральный",
        "Лазур",
    ],
    "Поморие": [
        "Сън Сити",
        "Сансет Кози",
        "Бей Вью",
        "Поморие Бич",
    ],
    "Святой Влас": [
        "Галеон",
        "Марина Диневи",
        "Елените",
        "Вилла Рома",
    ],
    "Равда": [
        "Равда Бич",
        "Сий Вью",
        "Аполон Равда",
    ],
}

FEATURES = [
    "бассейн",
    "паркинг",
    "вид на море",
    "кондиционер",
    "мебель",
    "балкон",
    "лифт",
    "охрана 24/7",
    "ресторан",
    "спа",
    "детская площадка",
    "фитнес",
    "Wi-Fi",
    "сауна",
]


@dataclass
class Property:
    """Test property data."""

    id: str
    title: str
    description: str
    city: str
    district: str
    rooms: int
    price: int
    area: int
    floor: int
    total_floors: int
    distance_to_sea: int
    year_built: int
    features: list[str] = field(default_factory=list)


def generate_description(prop: Property) -> str:
    """Generate realistic description."""
    room_text = "Студия" if prop.rooms == 0 else f"{prop.rooms}-комнатная квартира"
    features_text = ", ".join(prop.features[:4]) if prop.features else "базовая комплектация"

    templates = [
        f"{room_text} в комплексе \"{prop.district}\", {prop.city}. "
        f"Площадь {prop.area} м², {prop.floor} этаж из {prop.total_floors}. "
        f"{features_text.capitalize()}. До пляжа {prop.distance_to_sea}м. "
        f"Год постройки: {prop.year_built}. Идеально для отдыха или сдачи в аренду.",
        f"Продается {room_text.lower()} в {prop.city}, комплекс \"{prop.district}\". "
        f"Общая площадь {prop.area} кв.м., этаж {prop.floor}/{prop.total_floors}. "
        f"Расстояние до моря: {prop.distance_to_sea} метров. "
        f"В квартире: {features_text}. Цена: {prop.price:,} EUR.",
        f"Отличное предложение в {prop.city}! {room_text} в популярном комплексе \"{prop.district}\". "
        f"Площадь: {prop.area} м², этажность: {prop.floor} из {prop.total_floors}. "
        f"Особенности: {features_text}. Море в {prop.distance_to_sea}м. "
        f"Построено в {prop.year_built} году.",
    ]

    return random.choice(templates)


def generate_property(city: str, rooms: int) -> Property:
    """Generate single property."""
    complexes = COMPLEXES.get(city, ["Центральный"])
    district = random.choice(complexes)

    # Price correlates with rooms, city, distance to sea
    base_price = 35000 + rooms * 20000
    city_multiplier = {
        "Солнечный берег": 1.2,
        "Несебр": 1.3,
        "Святой Влас": 1.4,
        "Бургас": 0.9,
        "Поморие": 1.0,
        "Равда": 0.95,
    }.get(city, 1.0)
    price = int(base_price * city_multiplier * random.uniform(0.8, 1.5))

    # Area correlates with rooms
    area = 25 + rooms * 20 + random.randint(-5, 15)

    # Distance to sea (lognormal - more close ones)
    distance_to_sea = int(50 + random.lognormvariate(5, 1))
    distance_to_sea = min(distance_to_sea, 2000)

    # Floors
    total_floors = random.randint(4, 12)
    floor = random.randint(1, total_floors)

    # Features (2-6 random)
    features = random.sample(FEATURES, random.randint(2, 6))

    prop = Property(
        id=str(uuid.uuid4()),
        title=f"{'Студия' if rooms == 0 else f'{rooms}-комнатная квартира'} в {city}",
        description="",  # Will be generated
        city=city,
        district=district,
        rooms=rooms,
        price=price,
        area=area,
        floor=floor,
        total_floors=total_floors,
        distance_to_sea=distance_to_sea,
        year_built=random.randint(2005, 2024),
        features=features,
    )
    prop.description = generate_description(prop)

    return prop


def generate_all_properties(count: int = 100) -> list[Property]:
    """Generate all properties with specified distribution."""
    properties = []

    # Distribution: cities
    city_distribution = {
        "Солнечный берег": 30,
        "Несебр": 25,
        "Бургас": 15,
        "Поморие": 15,
        "Святой Влас": 10,
        "Равда": 5,
    }

    # Distribution: rooms (0=studio, 1, 2, 3, 4+)
    room_distribution = {0: 20, 1: 25, 2: 30, 3: 20, 4: 5}

    for city, city_count in city_distribution.items():
        for _ in range(city_count):
            # Pick rooms according to distribution
            rooms = random.choices(
                list(room_distribution.keys()),
                weights=list(room_distribution.values()),
            )[0]
            properties.append(generate_property(city, rooms))

    random.shuffle(properties)
    return properties[:count]


def main():
    """Generate and save test properties."""
    random.seed(42)  # Reproducible

    properties = generate_all_properties(100)

    output_path = Path("data/test_properties.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "count": len(properties),
        "properties": [asdict(p) for p in properties],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(properties)} properties to {output_path}")

    # Stats
    cities = {}
    rooms = {}
    prices = []
    for p in properties:
        cities[p.city] = cities.get(p.city, 0) + 1
        rooms[p.rooms] = rooms.get(p.rooms, 0) + 1
        prices.append(p.price)

    print(f"\nBy city: {cities}")
    print(f"By rooms: {rooms}")
    print(f"Price range: {min(prices):,} - {max(prices):,} EUR")
    print(f"Price median: {sorted(prices)[len(prices)//2]:,} EUR")


if __name__ == "__main__":
    main()
```

**Step 2: Run to generate data**

```bash
python scripts/generate_test_properties.py
```

Expected output:
```
Generated 100 properties to data/test_properties.json
By city: {'Солнечный берег': 30, 'Несебр': 25, ...}
```

**Step 3: Commit**

```bash
git add scripts/generate_test_properties.py data/test_properties.json
git commit -m "feat(e2e): add test property generator with 100 realistic properties"
```

---

## Task 7: Test Data Indexer

**Files:**
- Create: `scripts/index_test_properties.py`

**Step 1: Create index_test_properties.py**

```python
#!/usr/bin/env python3
"""Index test properties into Qdrant for E2E testing."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.services import VoyageService

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
COLLECTION_NAME = "contextual_bulgaria_test"


async def main():
    """Index test properties."""
    # Load properties
    data_path = Path("data/test_properties.json")
    if not data_path.exists():
        print("Error: data/test_properties.json not found. Run generate_test_properties.py first.")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    properties = data["properties"]
    print(f"Loaded {len(properties)} properties")

    # Initialize Voyage for embeddings
    voyage = VoyageService(
        api_key=VOYAGE_API_KEY,
        model_docs="voyage-4-large",
    )

    # Generate embeddings for descriptions
    descriptions = [p["description"] for p in properties]
    print("Generating embeddings...")
    embeddings = await voyage.embed_documents(descriptions)
    print(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    # Initialize Qdrant
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

    # Recreate collection
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection: {COLLECTION_NAME}")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(size=len(embeddings[0]), distance=Distance.COSINE)
        },
    )
    print(f"Created collection: {COLLECTION_NAME}")

    # Index points
    points = []
    for i, (prop, embedding) in enumerate(zip(properties, embeddings)):
        point = PointStruct(
            id=i,
            vector={"dense": embedding},
            payload={
                "page_content": prop["description"],
                "text": prop["description"],  # For reranking
                "metadata": {
                    "id": prop["id"],
                    "title": prop["title"],
                    "city": prop["city"],
                    "district": prop["district"],
                    "rooms": prop["rooms"],
                    "price": prop["price"],
                    "area": prop["area"],
                    "floor": prop["floor"],
                    "total_floors": prop["total_floors"],
                    "distance_to_sea": prop["distance_to_sea"],
                    "year_built": prop["year_built"],
                    "features": prop["features"],
                },
            },
        )
        points.append(point)

    # Batch upsert
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        print(f"Indexed {min(i + batch_size, len(points))}/{len(points)}")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"\nCollection '{COLLECTION_NAME}': {info.points_count} points indexed")

    # Test search
    test_query = "студия в Солнечный берег до 50000"
    test_embedding = await voyage.embed_query(test_query)
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=("dense", test_embedding),
        limit=3,
    )
    print(f"\nTest search for '{test_query}':")
    for r in results:
        meta = r.payload.get("metadata", {})
        print(f"  - {meta.get('title')}: {meta.get('price'):,} EUR (score: {r.score:.3f})")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Run to index data**

```bash
python scripts/index_test_properties.py
```

**Step 3: Commit**

```bash
git add scripts/index_test_properties.py
git commit -m "feat(e2e): add test property indexer with Voyage embeddings"
```

---

## Task 8: Report Generator

**Files:**
- Create: `scripts/e2e/report_generator.py`
- Create: `scripts/e2e/templates/report.html`

**Step 1: Create report_generator.py**

```python
"""Report generator for E2E test results."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from .claude_judge import JudgeResult
from .test_scenarios import TestScenario


@dataclass
class TestResult:
    """Single test result."""

    scenario: TestScenario
    bot_response: str
    response_time_ms: int
    judge_result: JudgeResult
    error: str | None = None

    @property
    def passed(self) -> bool:
        """Check if test passed."""
        return self.judge_result.passed if self.judge_result else False


@dataclass
class TestReport:
    """Full test report."""

    timestamp: datetime
    bot_username: str
    results: list[TestResult]
    total_duration_ms: int

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def passed_tests(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_tests(self) -> int:
        return self.total_tests - self.passed_tests

    @property
    def average_score(self) -> float:
        scores = [r.judge_result.total_score for r in self.results if r.judge_result]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def pass_rate(self) -> float:
        return (self.passed_tests / self.total_tests * 100) if self.total_tests else 0.0


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E2E Test Report - {{ report.timestamp.strftime('%Y-%m-%d %H:%M') }}</title>
    <style>
        :root {
            --pass: #22c55e;
            --fail: #ef4444;
            --bg: #1a1a2e;
            --card: #16213e;
            --text: #e8e8e8;
            --muted: #8b8b8b;
        }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: var(--card);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
        }
        .header h1 { margin: 0 0 8px 0; }
        .header .meta { color: var(--muted); }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat {
            background: var(--card);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        .stat .value { font-size: 32px; font-weight: bold; }
        .stat .label { color: var(--muted); font-size: 14px; }
        .stat.pass .value { color: var(--pass); }
        .stat.fail .value { color: var(--fail); }
        .results { background: var(--card); border-radius: 12px; overflow: hidden; }
        .result {
            padding: 16px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            cursor: pointer;
        }
        .result:hover { background: rgba(255,255,255,0.05); }
        .result-header {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .status { width: 24px; height: 24px; border-radius: 50%; }
        .status.pass { background: var(--pass); }
        .status.fail { background: var(--fail); }
        .result-id { color: var(--muted); font-family: monospace; }
        .result-name { flex: 1; }
        .result-score { font-weight: bold; }
        .result-details {
            display: none;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        .result.expanded .result-details { display: block; }
        .criteria {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }
        .criterion {
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        .criterion .name { font-size: 12px; color: var(--muted); }
        .criterion .score { font-size: 20px; font-weight: bold; }
        .query, .response {
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 12px;
            font-family: monospace;
            white-space: pre-wrap;
            font-size: 13px;
        }
        .label-tag { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>E2E Test Report</h1>
            <div class="meta">
                Bot: {{ report.bot_username }} |
                {{ report.timestamp.strftime('%Y-%m-%d %H:%M:%S') }} |
                Duration: {{ "%.1f"|format(report.total_duration_ms / 1000) }}s
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="value">{{ report.total_tests }}</div>
                <div class="label">Total Tests</div>
            </div>
            <div class="stat pass">
                <div class="value">{{ report.passed_tests }}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat fail">
                <div class="value">{{ report.failed_tests }}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat">
                <div class="value">{{ "%.1f"|format(report.average_score) }}</div>
                <div class="label">Avg Score</div>
            </div>
        </div>

        <div class="results">
            {% for result in report.results %}
            <div class="result" onclick="this.classList.toggle('expanded')">
                <div class="result-header">
                    <div class="status {{ 'pass' if result.passed else 'fail' }}"></div>
                    <span class="result-id">{{ result.scenario.id }}</span>
                    <span class="result-name">{{ result.scenario.name }}</span>
                    <span class="result-score">{{ "%.1f"|format(result.judge_result.total_score) }}</span>
                </div>
                <div class="result-details">
                    <div class="criteria">
                        <div class="criterion">
                            <div class="name">Relevance</div>
                            <div class="score">{{ result.judge_result.relevance.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Completeness</div>
                            <div class="score">{{ result.judge_result.completeness.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Filters</div>
                            <div class="score">{{ result.judge_result.filter_accuracy.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">Tone</div>
                            <div class="score">{{ result.judge_result.tone_format.score }}</div>
                        </div>
                        <div class="criterion">
                            <div class="name">No Halluc.</div>
                            <div class="score">{{ result.judge_result.no_hallucination.score }}</div>
                        </div>
                    </div>
                    <div class="label-tag">Query:</div>
                    <div class="query">{{ result.scenario.query }}</div>
                    <div class="label-tag">Response ({{ result.response_time_ms }}ms):</div>
                    <div class="response">{{ result.bot_response[:500] }}{% if result.bot_response|length > 500 %}...{% endif %}</div>
                    <div class="label-tag">Judge Summary:</div>
                    <div class="response">{{ result.judge_result.summary }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>"""


class ReportGenerator:
    """Generate test reports."""

    def __init__(self, reports_dir: str = "reports"):
        """Initialize generator."""
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, report: TestReport) -> tuple[Path, Path]:
        """Generate JSON and HTML reports.

        Returns:
            Tuple of (json_path, html_path)
        """
        timestamp = report.timestamp.strftime("%Y-%m-%d_%H-%M-%S")

        # JSON report
        json_path = self.reports_dir / f"e2e_{timestamp}.json"
        json_data = {
            "timestamp": report.timestamp.isoformat(),
            "bot_username": report.bot_username,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "average_score": report.average_score,
            "pass_rate": report.pass_rate,
            "total_duration_ms": report.total_duration_ms,
            "results": [
                {
                    "scenario_id": r.scenario.id,
                    "scenario_name": r.scenario.name,
                    "query": r.scenario.query,
                    "bot_response": r.bot_response,
                    "response_time_ms": r.response_time_ms,
                    "passed": r.passed,
                    "judge_result": {
                        "total_score": r.judge_result.total_score,
                        "relevance": asdict(r.judge_result.relevance),
                        "completeness": asdict(r.judge_result.completeness),
                        "filter_accuracy": asdict(r.judge_result.filter_accuracy),
                        "tone_format": asdict(r.judge_result.tone_format),
                        "no_hallucination": asdict(r.judge_result.no_hallucination),
                        "summary": r.judge_result.summary,
                    },
                    "error": r.error,
                }
                for r in report.results
            ],
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # HTML report
        html_path = self.reports_dir / f"e2e_{timestamp}.html"
        template = Template(HTML_TEMPLATE)
        html_content = template.render(report=report)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return json_path, html_path
```

**Step 2: Commit**

```bash
git add scripts/e2e/report_generator.py
git commit -m "feat(e2e): add HTML/JSON report generator with dark theme"
```

---

## Task 9: Main Runner

**Files:**
- Create: `scripts/e2e/runner.py`

**Step 1: Create runner.py**

```python
#!/usr/bin/env python3
"""E2E test runner for Telegram bot."""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.e2e.claude_judge import ClaudeJudge
from scripts.e2e.config import E2EConfig
from scripts.e2e.report_generator import ReportGenerator, TestReport, TestResult
from scripts.e2e.telegram_client import E2ETelegramClient
from scripts.e2e.test_scenarios import SCENARIOS, TestGroup, get_scenarios_by_group

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


async def run_single_test(
    client: E2ETelegramClient,
    judge: ClaudeJudge,
    scenario,
    progress,
    task_id,
) -> TestResult:
    """Run single test scenario."""
    progress.update(task_id, description=f"[cyan]{scenario.id}[/] {scenario.name}")

    try:
        # Send message and get response
        response = await client.send_and_wait(
            query=scenario.query,
            timeout=scenario.timeout,
        )

        # Judge the response
        judge_result = await judge.evaluate(
            scenario=scenario,
            bot_response=response.text,
        )

        return TestResult(
            scenario=scenario,
            bot_response=response.text,
            response_time_ms=response.response_time_ms,
            judge_result=judge_result,
        )

    except asyncio.TimeoutError:
        from scripts.e2e.claude_judge import CriterionScore, JudgeResult

        return TestResult(
            scenario=scenario,
            bot_response="",
            response_time_ms=scenario.timeout * 1000,
            judge_result=JudgeResult(
                relevance=CriterionScore(0, "Timeout"),
                completeness=CriterionScore(0, "Timeout"),
                filter_accuracy=CriterionScore(0, "Timeout"),
                tone_format=CriterionScore(0, "Timeout"),
                no_hallucination=CriterionScore(0, "Timeout"),
                total_score=0.0,
                passed=False,
                summary="Test timed out waiting for bot response",
            ),
            error="Timeout",
        )
    except Exception as e:
        from scripts.e2e.claude_judge import CriterionScore, JudgeResult

        logger.exception(f"Error in test {scenario.id}")
        return TestResult(
            scenario=scenario,
            bot_response="",
            response_time_ms=0,
            judge_result=JudgeResult(
                relevance=CriterionScore(0, "Error"),
                completeness=CriterionScore(0, "Error"),
                filter_accuracy=CriterionScore(0, "Error"),
                tone_format=CriterionScore(0, "Error"),
                no_hallucination=CriterionScore(0, "Error"),
                total_score=0.0,
                passed=False,
                summary=f"Test failed with error: {e}",
            ),
            error=str(e),
        )


async def run_tests(
    config: E2EConfig,
    scenarios: list,
) -> TestReport:
    """Run all test scenarios."""
    results = []
    start_time = time.time()

    async with E2ETelegramClient(config) as client:
        judge = ClaudeJudge(config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task("Running tests...", total=len(scenarios))

            for scenario in scenarios:
                result = await run_single_test(
                    client=client,
                    judge=judge,
                    scenario=scenario,
                    progress=progress,
                    task_id=task_id,
                )
                results.append(result)

                # Print immediate result
                status = "[green]PASS[/]" if result.passed else "[red]FAIL[/]"
                console.print(
                    f"  {status} {scenario.id} {scenario.name}: "
                    f"{result.judge_result.total_score:.1f}"
                )

                progress.advance(task_id)

                # Rate limiting
                await asyncio.sleep(config.between_tests_delay)

    total_duration_ms = int((time.time() - start_time) * 1000)

    return TestReport(
        timestamp=datetime.now(),
        bot_username=config.bot_username,
        results=results,
        total_duration_ms=total_duration_ms,
    )


def print_summary(report: TestReport):
    """Print test summary table."""
    console.print()

    table = Table(title="E2E Test Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total Tests", str(report.total_tests))
    table.add_row("Passed", f"[green]{report.passed_tests}[/]")
    table.add_row("Failed", f"[red]{report.failed_tests}[/]")
    table.add_row("Pass Rate", f"{report.pass_rate:.1f}%")
    table.add_row("Average Score", f"{report.average_score:.2f}")
    table.add_row("Duration", f"{report.total_duration_ms / 1000:.1f}s")

    console.print(table)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="E2E Test Runner")
    parser.add_argument(
        "--group",
        type=str,
        choices=[g.value for g in TestGroup],
        help="Run only specific test group",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run only specific scenario by ID (e.g., 3.1)",
    )
    args = parser.parse_args()

    # Load config
    config = E2EConfig()
    errors = config.validate()
    if errors:
        console.print("[red]Configuration errors:[/]")
        for e in errors:
            console.print(f"  - {e}")
        sys.exit(1)

    # Select scenarios
    if args.scenario:
        from scripts.e2e.test_scenarios import get_scenario_by_id

        scenario = get_scenario_by_id(args.scenario)
        if not scenario:
            console.print(f"[red]Scenario {args.scenario} not found[/]")
            sys.exit(1)
        scenarios = [scenario]
    elif args.group:
        group = TestGroup(args.group)
        scenarios = get_scenarios_by_group(group)
    else:
        scenarios = SCENARIOS

    console.print(f"\n[bold]Running {len(scenarios)} E2E tests against {config.bot_username}[/]\n")

    # Run tests
    report = asyncio.run(run_tests(config, scenarios))

    # Generate reports
    generator = ReportGenerator(config.reports_dir)
    json_path, html_path = generator.generate(report)

    # Print summary
    print_summary(report)

    console.print(f"\n[dim]Reports saved to:[/]")
    console.print(f"  JSON: {json_path}")
    console.print(f"  HTML: {html_path}")

    # Exit code based on pass rate
    sys.exit(0 if report.pass_rate >= 80 else 1)


if __name__ == "__main__":
    main()
```

**Step 2: Make executable**

```bash
chmod +x scripts/e2e/runner.py
```

**Step 3: Commit**

```bash
git add scripts/e2e/runner.py
git commit -m "feat(e2e): add main test runner with Rich CLI output"
```

---

## Task 10: Update .env.example and Documentation

**Files:**
- Modify: `.env.example`
- Modify: `CLAUDE.md`

**Step 1: Add E2E variables to .env.example**

Add to .env.example:

```bash
# E2E Testing (for Telethon userbot)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
E2E_BOT_USERNAME=@test_nika_homes_bot
```

**Step 2: Add E2E section to CLAUDE.md**

Add after Testing section:

```markdown
## E2E Testing

End-to-end testing with real Telegram bot and Claude Judge evaluation.

### Setup

```bash
# 1. Get Telegram API credentials from https://my.telegram.org
# 2. Add to .env:
#    TELEGRAM_API_ID=12345
#    TELEGRAM_API_HASH=abcdef...
#    ANTHROPIC_API_KEY=sk-ant-...

# 3. Install dependencies and generate test data
make e2e-setup
```

### Running Tests

```bash
make e2e-test                           # All 25 tests
make e2e-test-group GROUP=price_filters # Specific group
python scripts/e2e/runner.py --scenario 3.1  # Single test
```

### Test Groups

| Group | Tests | Description |
|-------|-------|-------------|
| `commands` | 4 | /start, /help, /clear, /stats |
| `chitchat` | 4 | Greetings, thanks, goodbyes |
| `price_filters` | 4 | Price range queries |
| `room_filters` | 4 | Room count queries |
| `location_filters` | 3 | City and distance queries |
| `search` | 3 | Semantic and complex search |
| `edge_cases` | 3 | Empty results, long queries, special chars |

### Reports

Reports saved to `reports/` directory:
- `e2e_YYYY-MM-DD_HH-MM-SS.json` — Machine-readable results
- `e2e_YYYY-MM-DD_HH-MM-SS.html` — Visual report with expandable details
```

**Step 3: Commit**

```bash
git add .env.example CLAUDE.md
git commit -m "docs: add E2E testing setup instructions"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | `scripts/e2e/__init__.py`, `requirements-e2e.txt`, `Makefile` | Project setup |
| 2 | `scripts/e2e/config.py` | Configuration dataclass |
| 3 | `scripts/e2e/test_scenarios.py` | 25 test scenarios |
| 4 | `scripts/e2e/telegram_client.py` | Telethon wrapper |
| 5 | `scripts/e2e/claude_judge.py` | Claude evaluation |
| 6 | `scripts/generate_test_properties.py` | Test data generator |
| 7 | `scripts/index_test_properties.py` | Qdrant indexer |
| 8 | `scripts/e2e/report_generator.py` | HTML/JSON reports |
| 9 | `scripts/e2e/runner.py` | Main runner |
| 10 | `.env.example`, `CLAUDE.md` | Documentation |

**Verification command:**
```bash
make e2e-setup && make e2e-test
```

---

*Created: 2026-01-27*
