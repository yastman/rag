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
    VOICE_TRANSCRIPTION = "voice_transcription"


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


# All 28 test scenarios
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
        expected_filters=ExpectedFilters(rooms=2, city="Солнечный берег", price_max=120000),
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
    # Group 8: Voice transcription (3 tests)
    TestScenario(
        id="8.1",
        name="Voice transcription + property search",
        query="(voice) найди квартиру у моря до 120 тысяч",
        group=TestGroup.VOICE_TRANSCRIPTION,
        description="Voice message should transcribe and run property search flow.",
        expected_keywords=["квартир", "мор", "120"],
    ),
    TestScenario(
        id="8.2",
        name="Voice transcription + CRM lookup",
        query="(voice) покажи мои сделки в crm",
        group=TestGroup.VOICE_TRANSCRIPTION,
        description="Voice message should transcribe and route to CRM tool path.",
        expected_keywords=["сделк", "crm", "ID"],
    ),
    TestScenario(
        id="8.3",
        name="Voice transcription timeout handling",
        query="(voice) [simulate timeout]",
        group=TestGroup.VOICE_TRANSCRIPTION,
        description="Voice transcription timeout should return graceful fallback.",
        expected_keywords=["не удалось", "попробуйте", "голос"],
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
