---
paths: "**/query*.py, **/filter*.py"
---

***REMOVED*** Query Processing

Query routing, analysis, preprocessing, and filter extraction.

***REMOVED******REMOVED*** Purpose

Classify queries to skip unnecessary RAG steps, extract structured filters, and normalize text for optimal search.

***REMOVED******REMOVED*** Architecture

```
Query → QueryRouter (CHITCHAT/SIMPLE/COMPLEX)
     → [CHITCHAT: canned response, skip RAG]
     → [SIMPLE: light RAG, skip rerank]
     → [COMPLEX: full RAG + rerank]
     → QueryPreprocessor (translit, weights)
     → QueryAnalyzer (LLM filter extraction)
     → Search with filters
```

***REMOVED******REMOVED*** Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/query_router.py` | 17 | QueryType enum |
| `telegram_bot/services/query_router.py` | 107 | classify_query() |
| `telegram_bot/services/query_analyzer.py` | 14 | QueryAnalyzer (LLM) |
| `telegram_bot/services/query_preprocessor.py` | 11 | QueryPreprocessor |
| `telegram_bot/services/filter_extractor.py` | 7 | FilterExtractor (regex) |

***REMOVED******REMOVED*** Query Types

| Type | Action | Example |
|------|--------|---------|
| CHITCHAT | Skip RAG, return canned response | "Привет!", "Спасибо" |
| SIMPLE | Light RAG, skip rerank | "сколько стоит", "2 комнаты" |
| COMPLEX | Full RAG + rerank | "уютная квартира с видом на море" |

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Chitchat patterns | 30+ regex | Greetings, thanks, farewells |
| Simple patterns | 5+ regex | Price, room queries |
| Translit map | 20+ cities | Latin → Cyrillic |

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** Query routing

```python
from telegram_bot.services.query_router import classify_query, QueryType, get_chitchat_response

query_type = classify_query(query)

if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)
    return response  ***REMOVED*** Skip RAG entirely

if query_type == QueryType.SIMPLE:
    ***REMOVED*** Light RAG, skip rerank
    pass
```

***REMOVED******REMOVED******REMOVED*** Query preprocessing

```python
from telegram_bot.services.query_preprocessor import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5")
***REMOVED*** {
***REMOVED***   "original_query": "apartments in Sunny Beach корпус 5",
***REMOVED***   "normalized_query": "apartments in Солнечный берег корпус 5",
***REMOVED***   "rrf_weights": {"dense": 0.2, "sparse": 0.8},
***REMOVED***   "cache_threshold": 0.05,
***REMOVED***   "is_exact": True
***REMOVED*** }
```

***REMOVED******REMOVED******REMOVED*** LLM filter extraction

```python
from telegram_bot.services.query_analyzer import QueryAnalyzer

analyzer = QueryAnalyzer(api_key=key, base_url=url)
result = await analyzer.analyze("квартира до 80000 евро в Несебре")
***REMOVED*** {
***REMOVED***   "filters": {"price": {"lt": 80000}, "city": "Несебр"},
***REMOVED***   "semantic_query": "квартира"
***REMOVED*** }
```

***REMOVED******REMOVED******REMOVED*** Regex filter extraction (fallback)

```python
from telegram_bot.services.filter_extractor import FilterExtractor

extractor = FilterExtractor()
filters = extractor.extract_filters("2-комнатная до 100к")
***REMOVED*** {"rooms": 2, "price": {"lt": 100000}}
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
| `maintenance` | range | `{"lte": 12.0}` |
| `bathrooms` | int | `2` |
| `furniture` | string | `"Есть"` |
| `year_round` | string | `"Да"` |

***REMOVED******REMOVED*** Transliteration Map

| Latin | Cyrillic |
|-------|----------|
| Sunny Beach | Солнечный берег |
| Nesebar | Несебър |
| Burgas | Бургас |
| Sveti Vlas | Святой Влас |

***REMOVED******REMOVED*** Rerank Decision

```python
from telegram_bot.services.query_router import needs_rerank

if needs_rerank(query_type, result_count):
    results = await voyage.rerank(query, results)
```

Skip rerank when:
- `query_type == SIMPLE`
- `result_count <= 2`

***REMOVED******REMOVED*** Dependencies

- LLM: via LiteLLM for QueryAnalyzer
- Langfuse: @observe decorators

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_query_router.py -v
pytest tests/unit/test_query_analyzer.py -v
pytest tests/unit/test_query_preprocessor.py -v
pytest tests/unit/test_filter_extractor.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| Chitchat not detected | Add pattern to CHITCHAT_PATTERNS |
| Wrong translit | Add to TRANSLIT_MAP |
| LLM filter extraction failed | Falls back to regex extractor |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new chitchat pattern

```python
***REMOVED*** telegram_bot/services/query_router.py
CHITCHAT_PATTERNS = [
    ...
    r"^new pattern\b",  ***REMOVED*** Add here
]
```

***REMOVED******REMOVED******REMOVED*** Adding new filter

1. Add to QueryAnalyzer system prompt
2. Add extraction method to FilterExtractor
3. Add to Qdrant filter building
