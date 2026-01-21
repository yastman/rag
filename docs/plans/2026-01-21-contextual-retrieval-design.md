# Contextual Retrieval Design Plan

**Date:** 2026-01-21
**Status:** Draft
**Author:** Claude + User

## Overview

Добавление Contextual Retrieval (Anthropic approach) в RAG pipeline для улучшения качества поиска на +35-49%.

### Цель

Каждый чанк перед embedding получает контекст от LLM, что решает проблему потери контекста при chunking.

### Scope

- Demo данные: VTT субтитры (Болгария, недвижимость)
- Ручной workflow через Claude Code CLI
- Интеграция с существующим BGE-M3 + Qdrant pipeline

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      INDEXING PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐  │
│  │   VTT   │───▶│  Clean  │───▶│  Chunk  │───▶│ Contextualize│  │
│  │  File   │    │  Text   │    │  (LLM)  │    │    (LLM)     │  │
│  └─────────┘    └─────────┘    └─────────┘    └──────┬──────┘  │
│                                                       │         │
│                                                       ▼         │
│                                              ┌─────────────┐    │
│                                              │    JSON     │    │
│                                              │   Output    │    │
│                                              └──────┬──────┘    │
│                                                     │           │
└─────────────────────────────────────────────────────┼───────────┘
                                                      │
┌─────────────────────────────────────────────────────┼───────────┐
│                 EXISTING PIPELINE                   │           │
├─────────────────────────────────────────────────────┼───────────┤
│                                                     ▼           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   BGE-M3    │───▶│   Qdrant    │───▶│  Hybrid Search      │  │
│  │  Embedding  │    │   Store     │    │  + ColBERT Rerank   │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Step 1: VTT Cleaning

**Input:** Raw VTT file with timestamps
```
00:00:01.000 --> 00:00:05.000
Привет, сегодня поговорим о недвижимости

00:00:05.000 --> 00:00:10.000
в Болгарии, конкретно в Бургасе
```

**Output:** Clean text
```
Привет, сегодня поговорим о недвижимости в Болгарии, конкретно в Бургасе
```

**Method:** Claude CLI или regex parser

---

### Step 2: LLM-based Chunking

**Input:** Clean text (full document)

**Prompt:**
```
Разбей этот текст на семантические чанки.

Правила:
- Каждый чанк = одна законченная мысль или тема
- Оптимальный размер: 500-1500 символов
- Не разрывай предложения
- Сохраняй логическую связность

Текст:
{{DOCUMENT}}

Верни JSON массив чанков:
[
  {"chunk_id": 1, "text": "..."},
  {"chunk_id": 2, "text": "..."}
]
```

**Output:** Array of chunks

---

### Step 3: Contextual Retrieval

**Input:** Each chunk + full document

**Prompt (Anthropic official):**
```
<document>
{{WHOLE_DOCUMENT}}
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{{CHUNK_CONTENT}}
</chunk>

Please give a short succinct context to situate this chunk
within the overall document for the purposes of improving
search retrieval of the chunk. Answer only with the succinct
context and nothing else.
```

**Output:** Context string (1-2 sentences)

---

### Step 4: Metadata Extraction

**Input:** Each chunk

**Prompt:**
```
Для этого чанка извлеки:
- topic: основная тема (3-5 слов)
- keywords: ключевые слова для поиска (3-7 слов)

Чанк:
{{CHUNK}}

Верни JSON: {"topic": "...", "keywords": ["...", "..."]}
```

---

## JSON Schema

### Output Format

```json
{
  "source": "filename.vtt",
  "processed_at": "2026-01-21T12:00:00Z",
  "total_chunks": 5,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Цены на недвижимость в Бургасе",
      "keywords": ["Бургас", "цены", "студия", "евро", "недвижимость"],
      "context": "Этот фрагмент из видео о покупке недвижимости в Болгарии. Обсуждаются начальные цены на квартиры в городе Бургас.",
      "text": "В Бургасе цены начинаются от 50 тысяч евро за студию. Это один из самых доступных городов на побережье.",
      "text_for_embedding": "# Недвижимость в Болгарии - Бургас\n\nЭтот фрагмент из видео о покупке недвижимости в Болгарии. Обсуждаются начальные цены на квартиры в городе Бургас.\n\nВ Бургасе цены начинаются от 50 тысяч евро за студию. Это один из самых доступных городов на побережье."
    }
  ]
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Original filename |
| `chunk_id` | int | Sequential chunk number |
| `topic` | string | Main topic (3-5 words) |
| `keywords` | array | Search keywords |
| `context` | string | LLM-generated context (Contextual Retrieval) |
| `text` | string | Original chunk text |
| `text_for_embedding` | string | context + text formatted for embedding |

---

## Integration with Existing Pipeline

### Current Pipeline (src/ingestion/)

```python
# chunker.py - Chunk dataclass
@dataclass
class Chunk:
    text: str
    chunk_id: int
    document_name: str
    article_number: str
    extra_metadata: Optional[dict]  # ← Use this for topic, keywords
```

### Integration Point

```python
# New: Load JSON and convert to Chunk objects
def load_contextual_chunks(json_path: str) -> list[Chunk]:
    with open(json_path) as f:
        data = json.load(f)

    chunks = []
    for item in data["chunks"]:
        chunk = Chunk(
            text=item["text_for_embedding"],  # ← Contextualized text
            chunk_id=item["chunk_id"],
            document_name=data["source"],
            article_number=f"chunk_{item['chunk_id']}",
            extra_metadata={
                "topic": item["topic"],
                "keywords": item["keywords"],
                "original_text": item["text"],
                "context": item["context"],
            }
        )
        chunks.append(chunk)

    return chunks
```

### Indexing

```python
# Use existing DocumentIndexer
indexer = DocumentIndexer(settings)
chunks = load_contextual_chunks("processed/video1.json")
await indexer.index_chunks(chunks, collection_name="contextual_demo")
```

---

## Workflow: Manual (Claude CLI)

### Step-by-step

1. **Read VTT file**
   ```
   Claude: "Прочитай файл docs/test_data/example.vtt"
   ```

2. **Clean text**
   ```
   Claude: "Очисти этот VTT от таймкодов, объедини в связный текст"
   ```

3. **Chunk**
   ```
   Claude: "Разбей на семантические чанки по 500-1500 символов"
   ```

4. **Add context + metadata**
   ```
   Claude: "Для каждого чанка добавь context и извлеки topic, keywords.
            Сформируй text_for_embedding. Верни JSON."
   ```

5. **Save JSON**
   ```
   Claude: "Сохрани в docs/processed/example.json"
   ```

6. **Index**
   ```bash
   python -m scripts.index_contextual docs/processed/example.json
   ```

---

## Future: Automation

После тестирования ручного workflow - автоматизация:

```python
# src/ingestion/contextual_processor.py

class ContextualProcessor:
    """
    Automates Contextual Retrieval pipeline.

    Uses Anthropic API with prompt caching for efficiency.
    """

    def __init__(self, settings: Settings):
        self.client = anthropic.Anthropic()
        self.model = "claude-sonnet-4-20250514"

    async def process_document(self, text: str, source: str) -> dict:
        # 1. Clean (if VTT)
        # 2. Chunk with LLM
        # 3. Contextualize each chunk
        # 4. Extract metadata
        # 5. Return JSON structure
        pass
```

---

## Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| Retrieval accuracy | Baseline | +35% |
| Context relevance | Low | High |
| Query understanding | Basic | Semantic |

---

## Open Questions

1. **Chunk size:** 500-1500 символов оптимально для BGE-M3?
2. **Batch processing:** Обрабатывать все чанки одним вызовом или по одному?
3. **Caching:** Использовать Anthropic prompt caching для экономии?

---

## Next Steps

1. [ ] Протестировать на одном VTT файле через Claude CLI
2. [ ] Валидировать JSON schema
3. [ ] Написать скрипт интеграции с indexer
4. [ ] Сравнить качество поиска before/after
