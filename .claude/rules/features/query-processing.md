---
paths: "**/query*.py, **/filter*.py, **/classify*.py, **/respond*.py"
---

***REMOVED*** Query Processing

Query classification, analysis, preprocessing, and filter extraction.

***REMOVED******REMOVED*** Purpose

Classify queries to skip unnecessary RAG steps, extract structured filters, and normalize text for optimal search.

***REMOVED******REMOVED*** Architecture

```
LangGraph Pipeline:
  Query → classify_node (6-type regex taxonomy)
       → [CHITCHAT/OFF_TOPIC: canned response → respond_node]
       → [STRUCTURED/FAQ/ENTITY/GENERAL: → cache_check → retrieve → ...]

Legacy (still available):
  Query → QueryRouter (4-type: CHITCHAT/SIMPLE/COMPLEX/OFF_TOPIC)
       → QueryPreprocessor (translit, weights)
       → QueryAnalyzer (LLM filter extraction)
```

***REMOVED******REMOVED*** Key Files

| File | Description |
|------|-------------|
| `telegram_bot/graph/nodes/classify.py` | classify_node (LangGraph, 6-type regex) |
| `telegram_bot/graph/nodes/respond.py` | respond_node (Markdown + plain text fallback) |
| `telegram_bot/services/query_router.py` | Legacy QueryType enum + classify_query() |
| `telegram_bot/services/query_analyzer.py` | QueryAnalyzer (OpenAI SDK, LLM filter extraction) |
| `telegram_bot/services/query_preprocessor.py` | HyDEGenerator + QueryPreprocessor |
| `telegram_bot/services/filter_extractor.py` | FilterExtractor (regex fallback) |

***REMOVED******REMOVED*** Query Types (classify_node — 6 types)

| Type | Action | Example |
|------|--------|---------|
| CHITCHAT | Canned response, skip RAG | "Привет!", "Спасибо" |
| OFF_TOPIC | Canned redirect, skip RAG | "рецепт борща", "код на python" |
| STRUCTURED | Full RAG (numbers, prices, rooms) | "2 комнаты до 80000 евро" |
| FAQ | Full RAG (how-to questions) | "как оформить покупку" |
| ENTITY | Full RAG (named locations) | "квартира в Несебре" |
| GENERAL | Full RAG (everything else) | "уютная квартира с видом на море" |

Priority: CHITCHAT > OFF_TOPIC > STRUCTURED > FAQ > ENTITY > GENERAL.

***REMOVED******REMOVED*** classify_node (LangGraph)

Regex-based classification with pre-compiled patterns. No LLM calls — sub-millisecond.

```python
from telegram_bot.graph.nodes.classify import classify_node
from telegram_bot.graph.state import make_initial_state

state = make_initial_state(user_id=123, session_id="s-abc", query="Привет!")
result = await classify_node(state)
***REMOVED*** {"query_type": "CHITCHAT", "response": "Привет! 👋 ...", "latency_stages": {"classify": 0.001}}
```

CHITCHAT sub-categories: greeting, thanks, bot_info, farewell — each with localized responses.

***REMOVED******REMOVED*** respond_node (LangGraph)

Sends `state["response"]` via `message.answer()` with Markdown `parse_mode`. Falls back to plain text on parse error.

***REMOVED******REMOVED*** Query Preprocessing

```python
from telegram_bot.services.query_preprocessor import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5", use_hyde=True)
***REMOVED*** {
***REMOVED***   "normalized_query": "apartments in Солнечный берег корпус 5",
***REMOVED***   "rrf_weights": {"dense": 0.2, "sparse": 0.8},  ***REMOVED*** Exact → favor sparse
***REMOVED***   "cache_threshold": 0.05,
***REMOVED***   "is_exact": True,
***REMOVED***   "use_hyde": False,
***REMOVED*** }
```

***REMOVED******REMOVED*** HyDE (Hypothetical Document Embeddings)

LLM generates hypothetical answer for short/vague queries, embeds that instead.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_HYDE` | `false` | Enable HyDE globally |
| `HYDE_MIN_WORDS` | `5` | Queries shorter than this use HyDE |

***REMOVED******REMOVED*** LLM Filter Extraction

```python
from telegram_bot.services.query_analyzer import QueryAnalyzer

analyzer = QueryAnalyzer(api_key=key, base_url=url)  ***REMOVED*** Uses langfuse.openai.AsyncOpenAI
result = await analyzer.analyze("квартира до 80000 евро в Несебре")
***REMOVED*** {"filters": {"price": {"lt": 80000}, "city": "Несебр"}, "semantic_query": "квартира"}
```

***REMOVED******REMOVED*** Available Filters

| Filter | Type | Example |
|--------|------|---------|
| `price` | range | `{"lt": 100000}`, `{"gte": 50000, "lte": 80000}` |
| `rooms` | int | `2` |
| `city` | string | `"Несебр"` |
| `area` | range | `{"gte": 50}` |
| `floor` | int | `4` |
| `distance_to_sea` | range | `{"lte": 500}` |

***REMOVED******REMOVED*** Dependencies

- LLM: via LiteLLM for QueryAnalyzer (OpenAI SDK)
- Langfuse: auto-tracing via `langfuse.openai.AsyncOpenAI`

***REMOVED******REMOVED*** Testing

```bash
***REMOVED*** LangGraph nodes
pytest tests/unit/graph/test_classify_node.py -v   ***REMOVED*** 28 tests (6-type taxonomy)
pytest tests/unit/graph/test_respond_node.py -v    ***REMOVED*** 5 tests (Markdown fallback)

***REMOVED*** Services
pytest tests/unit/test_query_router.py -v
pytest tests/unit/services/test_query_analyzer.py -v
pytest tests/unit/test_query_preprocessor.py -v
pytest tests/unit/test_hyde.py -v
pytest tests/unit/test_filter_extractor.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| Chitchat not detected | Add pattern to CHITCHAT_PATTERNS in classify.py |
| Wrong translit | Add to TRANSLIT_MAP in query_preprocessor.py |
| LLM filter extraction failed | Falls back to regex extractor |
| HyDE not applied | Check `USE_HYDE=true` and query is < `HYDE_MIN_WORDS` |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new chitchat pattern

Add to `CHITCHAT_PATTERNS` list in `telegram_bot/graph/nodes/classify.py`.

***REMOVED******REMOVED******REMOVED*** Adding new query type

1. Add constant in `classify.py`
2. Add regex patterns
3. Update `classify_query()` priority chain
4. Update `route_by_query_type` edge in `graph/edges.py` if routing changes
5. Add tests in `tests/unit/graph/test_classify_node.py`
