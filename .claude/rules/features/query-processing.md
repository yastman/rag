---
paths: "**/query*.py, **/filter*.py, **/classify*.py, **/respond*.py"
---

# Query Processing

Query classification, analysis, preprocessing, and filter extraction.

## Purpose

Classify queries to skip unnecessary RAG steps, extract structured filters, and normalize text for optimal search.

## Architecture

```
LangGraph Pipeline:
  Query → classify_node (6-type regex taxonomy)
       → [CHITCHAT/OFF_TOPIC: canned response → respond_node]
       → [STRUCTURED/FAQ/ENTITY/GENERAL: → guard_node → cache_check → retrieve → ...]

Supporting services (used by graph nodes):
  QueryPreprocessor (translit, weights) + QueryAnalyzer (LLM filter extraction)
```

**Note:** After classify, non-chitchat queries go to `guard_node` (prompt injection defense) before `cache_check`.

## Key Files

| File | Description |
|------|-------------|
| `telegram_bot/graph/nodes/classify.py` | classify_node (LangGraph, 6-type regex) |
| `telegram_bot/graph/nodes/respond.py` | respond_node (Markdown + plain text fallback) |
| `telegram_bot/services/query_analyzer.py` | QueryAnalyzer (OpenAI SDK, LLM filter extraction) |
| `telegram_bot/services/query_preprocessor.py` | HyDEGenerator + QueryPreprocessor |
| `telegram_bot/services/filter_extractor.py` | FilterExtractor (regex fallback) |

## Query Types (classify_node — 6 types)

| Type | Action | Example |
|------|--------|---------|
| CHITCHAT | Canned response, skip RAG | "Привет!", "Спасибо" |
| OFF_TOPIC | Canned redirect, skip RAG | "рецепт борща", "код на python" |
| STRUCTURED | Full RAG (numbers, prices, rooms) | "2 комнаты до 80000 евро" |
| FAQ | Full RAG (how-to questions) | "как оформить покупку" |
| ENTITY | Full RAG (named locations) | "квартира в Несебре" |
| GENERAL | Full RAG (everything else) | "уютная квартира с видом на море" |

Priority: CHITCHAT > OFF_TOPIC > STRUCTURED > FAQ > ENTITY > GENERAL.

## classify_node (LangGraph)

Regex-based classification with pre-compiled patterns. No LLM calls — sub-millisecond.

```python
from telegram_bot.graph.nodes.classify import classify_node
from telegram_bot.graph.state import make_initial_state

state = make_initial_state(user_id=123, session_id="s-abc", query="Привет!")
result = await classify_node(state)
# {"query_type": "CHITCHAT", "response": "Привет! 👋 ...", "latency_stages": {"classify": 0.001}}
```

CHITCHAT sub-categories: greeting, thanks, bot_info, farewell — each with localized responses.

**Routing:**
- `route_by_query_type`: CHITCHAT/OFF_TOPIC → respond_node; others → guard_node
- `route_after_guard`: guard_node → respond (blocked) or cache_check (clean)

## respond_node (LangGraph)

Sends `state["response"]` via `message.answer()` with Markdown `parse_mode`. Falls back to plain text on parse error. Source attribution (`SHOW_SOURCES`, default `false`) appends footnotes when enabled.

## Query Preprocessing

```python
from telegram_bot.services.query_preprocessor import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5", use_hyde=True)
# {
#   "normalized_query": "apartments in Солнечный берег корпус 5",
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},  # Exact → favor sparse
#   "cache_threshold": 0.05,
#   "is_exact": True,
#   "use_hyde": False,
# }
```

## HyDE (Hypothetical Document Embeddings)

LLM generates hypothetical answer for short/vague queries, embeds that instead.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_HYDE` | `false` | Enable HyDE globally |
| `HYDE_MIN_WORDS` | `5` | Queries shorter than this use HyDE |

## LLM Filter Extraction

```python
from telegram_bot.services.query_analyzer import QueryAnalyzer

analyzer = QueryAnalyzer(api_key=key, base_url=url)  # Uses langfuse.openai.AsyncOpenAI
result = await analyzer.analyze("квартира до 80000 евро в Несебре")
# {"filters": {"price": {"lt": 80000}, "city": "Несебр"}, "semantic_query": "квартира"}
```

## Available Filters

| Filter | Type | Example |
|--------|------|---------|
| `price` | range | `{"lt": 100000}`, `{"gte": 50000, "lte": 80000}` |
| `rooms` | int | `2` |
| `city` | string | `"Несебр"` |
| `area` | range | `{"gte": 50}` |
| `floor` | int | `4` |
| `distance_to_sea` | range | `{"lte": 500}` |

## Dependencies

- LLM: via LiteLLM for QueryAnalyzer (OpenAI SDK)
- Langfuse: auto-tracing via `langfuse.openai.AsyncOpenAI`

## Testing

```bash
# LangGraph nodes
pytest tests/unit/graph/test_classify_node.py -v   # 28 tests (6-type taxonomy)
pytest tests/unit/graph/test_respond_node.py -v    # 5 tests (Markdown fallback)

# Services
pytest tests/unit/services/test_query_analyzer.py -v
pytest tests/unit/test_query_preprocessor.py -v
pytest tests/unit/test_hyde.py -v
pytest tests/unit/test_filter_extractor.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Chitchat not detected | Add pattern to CHITCHAT_PATTERNS in classify.py |
| Wrong translit | Add to TRANSLIT_MAP in query_preprocessor.py |
| LLM filter extraction failed | Falls back to regex extractor |
| HyDE not applied | Check `USE_HYDE=true` and query is < `HYDE_MIN_WORDS` |

## Development Guide

### Adding new chitchat pattern

Add to `CHITCHAT_PATTERNS` list in `telegram_bot/graph/nodes/classify.py`.

### Adding new query type

1. Add constant in `classify.py`
2. Add regex patterns
3. Update `classify_query()` priority chain
4. Update `route_by_query_type` edge in `graph/edges.py` if routing changes
5. Add tests in `tests/unit/graph/test_classify_node.py`
