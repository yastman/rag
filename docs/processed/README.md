# Processed Documents

JSON files created by Claude Code CLI for Contextual Retrieval indexing.

## Workflow

### Step 1: Process VTT with Claude CLI

Open Claude Code CLI in project directory and run:

```
Прочитай файл docs/test_data/[название].vtt

Обработай через Contextual Retrieval:
1. Очисти текст от таймкодов и VTT метаданных
2. Разбей на семантические чанки (LLM решает размер)
3. Для каждого чанка:
   - Добавь context (1-2 предложения о чём этот фрагмент в контексте всего документа)
   - Извлеки topic (3-5 слов)
   - Извлеки keywords (3-7 ключевых слов)

Сохрани результат в docs/processed/[название].json по схеме:

{
  "source": "filename.vtt",
  "processed_at": "ISO timestamp",
  "total_chunks": N,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Тема чанка",
      "keywords": ["слово1", "слово2"],
      "context": "Этот фрагмент из видео о... Обсуждается...",
      "text": "Оригинальный текст чанка",
      "text_for_embedding": "# Тема чанка\n\nКонтекст\n\nТекст"
    }
  ]
}
```

### Step 2: Index into Qdrant

```bash
python scripts/index_contextual.py docs/processed/[название].json --collection contextual_demo
```

### Step 3: Test Search

```python
from src.core.pipeline import RAGPipeline
import asyncio

pipeline = RAGPipeline()
result = asyncio.run(pipeline.search("Ваш запрос"))

for r in result.results:
    print(f"Topic: {r['metadata'].get('topic')}")
    print(f"Score: {r['score']:.3f}")
    print(f"Text: {r['text'][:200]}...")
    print()
```

## JSON Schema

See `src/ingestion/contextual_schema.py` for Python dataclasses.

| Field | Type | Description |
|-------|------|-------------|
| source | string | Original VTT filename |
| processed_at | string | ISO timestamp |
| total_chunks | int | Number of chunks |
| chunks[].chunk_id | int | Sequential ID |
| chunks[].topic | string | Main topic (3-5 words) |
| chunks[].keywords | array | Search keywords |
| chunks[].context | string | LLM-generated context |
| chunks[].text | string | Original chunk text |
| chunks[].text_for_embedding | string | Formatted for BGE-M3 |

## Example

```json
{
  "source": "Как купить квартиру в Болгарии.vtt",
  "processed_at": "2026-01-21T12:00:00",
  "total_chunks": 3,
  "chunks": [
    {
      "chunk_id": 1,
      "topic": "Введение в покупку недвижимости",
      "keywords": ["Болгария", "недвижимость", "покупка", "апартамент"],
      "context": "Это вступительная часть видео о покупке недвижимости в Болгарии. Автор представляется и описывает тематику видео.",
      "text": "Покупка апартамента в Болгарии возле моря. В этом видео я расскажу вам всё: дёшево или дорого, ловушка или безопасность?",
      "text_for_embedding": "# Введение в покупку недвижимости\n\nЭто вступительная часть видео о покупке недвижимости в Болгарии. Автор представляется и описывает тематику видео.\n\nПокупка апартамента в Болгарии возле моря. В этом видео я расскажу вам всё: дёшево или дорого, ловушка или безопасность?"
    }
  ]
}
```
