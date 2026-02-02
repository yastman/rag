---
paths: "**/query*.py, **/filter*.py"
---

# Query Processing

Query routing, analysis, preprocessing, and filter extraction.

## Purpose

Classify queries to skip unnecessary RAG steps, extract structured filters, and normalize text for optimal search.

## Architecture

```
Query → QueryRouter (CHITCHAT/SIMPLE/COMPLEX)
     → [CHITCHAT: canned response, skip RAG]
     → [SIMPLE: light RAG, skip rerank]
     → [COMPLEX: full RAG + rerank]
     → QueryPreprocessor (translit, weights)
     → QueryAnalyzer (LLM filter extraction)
     → Search with filters
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/services/query_router.py` | 17 | QueryType enum |
| `telegram_bot/services/query_router.py` | 107 | classify_query() |
| `telegram_bot/services/query_analyzer.py` | 14 | QueryAnalyzer (LLM) |
| `telegram_bot/services/query_preprocessor.py` | 14 | HyDEGenerator |
| `telegram_bot/services/query_preprocessor.py` | 126 | QueryPreprocessor |
| `telegram_bot/services/filter_extractor.py` | 7 | FilterExtractor (regex) |

## Query Types

| Type | Action | Example |
|------|--------|---------|
| CHITCHAT | Skip RAG, return canned response | "Привет!", "Спасибо" |
| SIMPLE | Light RAG, skip rerank | "сколько стоит", "2 комнаты" |
| COMPLEX | Full RAG + rerank | "уютная квартира с видом на море" |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Chitchat patterns | 30+ regex | Greetings, thanks, farewells |
| Simple patterns | 5+ regex | Price, room queries |
| Translit map | 20+ cities | Latin → Cyrillic |

## Common Patterns

### Query routing

```python
from telegram_bot.services.query_router import classify_query, QueryType, get_chitchat_response

query_type = classify_query(query)

if query_type == QueryType.CHITCHAT:
    response = get_chitchat_response(query)
    return response  # Skip RAG entirely

if query_type == QueryType.SIMPLE:
    # Light RAG, skip rerank
    pass
```

### Query preprocessing

```python
from telegram_bot.services.query_preprocessor import QueryPreprocessor

pp = QueryPreprocessor()
result = pp.analyze("apartments in Sunny Beach корпус 5", use_hyde=True)
# {
#   "original_query": "apartments in Sunny Beach корпус 5",
#   "normalized_query": "apartments in Солнечный берег корпус 5",
#   "rrf_weights": {"dense": 0.2, "sparse": 0.8},
#   "cache_threshold": 0.05,
#   "is_exact": True,
#   "use_hyde": False,  # Disabled for exact queries
#   "word_count": 5
# }
```

### HyDE (Hypothetical Document Embeddings)

HyDE improves recall for short/vague queries by generating a hypothetical answer and embedding that instead of the original query.

**How it works:**
1. User query: "квартира у моря" (3 words)
2. LLM generates hypothetical doc: "Уютная двухкомнатная квартира в Несебре, 50м², в 200 метрах от пляжа..."
3. Embed the hypothetical doc (better semantic match with actual documents)
4. Search with hypothetical embedding

**When HyDE is useful:**
- Short queries (< 5 words)
- Queries without domain-specific keywords
- Semantic/conceptual queries

**When NOT to use HyDE:**
- Exact queries (IDs, corpus numbers, floor numbers)
- Long detailed queries (already have context)
- Queries matching document vocabulary

```python
from telegram_bot.services.query_preprocessor import HyDEGenerator, QueryPreprocessor

# Check if HyDE should be applied
pp = QueryPreprocessor()
result = pp.analyze("студия", use_hyde=True, hyde_min_words=5)

if result["use_hyde"]:
    # Generate hypothetical document
    hyde = HyDEGenerator(base_url="http://localhost:4000")
    hypothetical_doc = await hyde.generate_hypothetical_document("студия")
    # Use hypothetical_doc for embedding instead of original query
    embedding = await voyage.embed_query(hypothetical_doc)
```

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_HYDE` | `false` | Enable HyDE globally |
| `HYDE_MIN_WORDS` | `5` | Queries shorter than this use HyDE |

### LLM filter extraction

```python
from telegram_bot.services.query_analyzer import QueryAnalyzer

analyzer = QueryAnalyzer(api_key=key, base_url=url)
result = await analyzer.analyze("квартира до 80000 евро в Несебре")
# {
#   "filters": {"price": {"lt": 80000}, "city": "Несебр"},
#   "semantic_query": "квартира"
# }
```

### Regex filter extraction (fallback)

```python
from telegram_bot.services.filter_extractor import FilterExtractor

extractor = FilterExtractor()
filters = extractor.extract_filters("2-комнатная до 100к")
# {"rooms": 2, "price": {"lt": 100000}}
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
| `maintenance` | range | `{"lte": 12.0}` |
| `bathrooms` | int | `2` |
| `furniture` | string | `"Есть"` |
| `year_round` | string | `"Да"` |

## Transliteration Map

| Latin | Cyrillic |
|-------|----------|
| Sunny Beach | Солнечный берег |
| Nesebar | Несебър |
| Burgas | Бургас |
| Sveti Vlas | Святой Влас |

## Rerank Decision

```python
from telegram_bot.services.query_router import needs_rerank

if needs_rerank(query_type, result_count):
    results = await voyage.rerank(query, results)
```

Skip rerank when:
- `query_type == SIMPLE`
- `result_count <= 2`

## Dependencies

- LLM: via LiteLLM for QueryAnalyzer
- Langfuse: @observe decorators

## Testing

```bash
pytest tests/unit/test_query_router.py -v
pytest tests/unit/test_query_analyzer.py -v
pytest tests/unit/test_query_preprocessor.py -v
pytest tests/unit/test_hyde.py -v              # HyDE tests (29 tests)
pytest tests/unit/test_filter_extractor.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Chitchat not detected | Add pattern to CHITCHAT_PATTERNS |
| Wrong translit | Add to TRANSLIT_MAP |
| LLM filter extraction failed | Falls back to regex extractor |
| HyDE not applied | Check `USE_HYDE=true` and query is < `HYDE_MIN_WORDS` |
| HyDE generation fails | Falls back to original query (graceful degradation) |

## Development Guide

### Adding new chitchat pattern

```python
# telegram_bot/services/query_router.py
CHITCHAT_PATTERNS = [
    ...
    r"^new pattern\b",  # Add here
]
```

### Adding new filter

1. Add to QueryAnalyzer system prompt
2. Add extraction method to FilterExtractor
3. Add to Qdrant filter building
