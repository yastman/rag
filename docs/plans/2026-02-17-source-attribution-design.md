# Design: Source Attribution / Citations in RAG Responses

**Date:** 2026-02-17
**Issue:** #225
**Branch:** epic/supervisor-migration-263

## Issue #225 Requirements

1. `generate_node`: include source metadata в LLM prompt, instruct to cite
2. `respond_node`: format citations как clickable links (Telegram Markdown)
3. Optional: inline quotes showing which chunk backs each claim
4. Config flag `SHOW_SOURCES=true|false`

## Current State

- `_format_context()` уже передаёт metadata (title, city, price, score) как `[Объект 1]`, `[Объект 2]`
- `state["documents"]` содержит `text`, `metadata` (source, title, city, price, rooms...), `score`
- `metadata["source"]` — relative path файла в Qdrant payload
- **Citations НЕ генерируются** — LLM не инструктирован, respond_node не форматирует

## Подход 1: Prompt-Based Citations (рекомендуется для Фазы 1)

**Суть:** Инструктировать LLM ссылаться на `[Объект N]`, respond_node форматирует footnotes.

**Изменения в generate_node:**

```python
# В system prompt:
"""
Когда используешь информацию из контекста, указывай номер источника [1], [2].
В конце ответа НЕ добавляй список источников — он будет добавлен автоматически.
"""
```

**Изменения в respond_node:**

```python
def _format_sources(documents: list[dict], max_sources: int = 5) -> str:
    if not documents:
        return ""
    lines = ["\n\n📎 *Источники:*"]
    for i, doc in enumerate(documents[:max_sources], 1):
        meta = doc.get("metadata", {})
        title = meta.get("title", meta.get("source", f"Документ {i}"))
        city = meta.get("city", "")
        score = doc.get("score", 0)
        line = f"`[{i}]` {title}"
        if city:
            line += f" — {city}"
        line += f" _(rel: {score:.2f})_"
        lines.append(line)
    return "\n".join(lines)
```

**Плюсы:** Минимальные изменения, работает с любой LLM, zero latency overhead
**Минусы:** LLM может "забыть" цитировать, нет точной привязки к chunks

## Подход 2: Structured Output Citations (Pydantic)

```python
class Citation(BaseModel):
    source_index: int
    quoted_text: str

class CitedResponse(BaseModel):
    answer: str
    citations: list[Citation]
```

**Плюсы:** Точные цитаты, machine-parseable
**Минусы:** +latency, не все модели поддерживают, сложнее со streaming

## Подход 3: Anthropic Native Citations

Claude API `citations: { enabled: true }` с `type: "document"` — автоматические `char_location`.

**НЕ подходит** — наш стек Cerebras/Groq через LiteLLM не поддерживает.

## Подход 4: Post-Processing Verification

Отдельный LLM call проверяет каждую цитату.

**Минусы:** +200-500ms latency, extra LLM cost.

## Рекомендация

### Фаза 1 (2-3 дня, prompt-based)

| Файл | Изменение |
|------|-----------|
| `telegram_bot/graph/state.py` | Добавить `show_sources: bool` в RAGState |
| `telegram_bot/graph/config.py` | `SHOW_SOURCES` env var (default: true) |
| `telegram_bot/graph/nodes/generate.py` | Инструкция цитировать `[1]`, `[2]` в system prompt |
| `telegram_bot/graph/nodes/respond.py` | `_format_sources()` — footnotes после ответа |

Pipeline (без новых nodes):
```
generate_node: LLM получает [Объект 1]...[Объект 5] → ответ с [1], [2] inline
respond_node: ответ + _format_sources(documents) → Telegram Markdown
```

### Фаза 2 (optional)

1. Pydantic CitedResponse для non-streaming path
2. Fuzzy match цитат к chunks (без LLM call)
3. Langfuse score `citation_accuracy`

### Фаза 3 (future, если мигрируем на Claude)

1. Native Anthropic citations API

## Best Practices (Tensorlake, 2025)

1. Citation anchors в preprocessing — `[page.order]` маркеры при chunking
2. Metadata-aware storage — bounding boxes, page numbers в Qdrant payload
3. Prompt instruction — "cite using [N]" → post-process в UI
4. **У нас уже есть** `source` field + numbered `[Объект N]` — осталось инструктировать и форматировать

## Ссылки

- Tensorlake Citation-Aware RAG: tensorlake.ai/blog/rag-citations
- LangChain citations how-to: python.langchain.com/docs/how_to/qa_citations/
- Anthropic native citations: docs (ChatAnthropic `citations: {enabled: true}`)
- LLM Citation Frameworks survey: rankstudio.net/articles/en/ai-citation-frameworks
