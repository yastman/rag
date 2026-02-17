# Design: Content Filtering / Toxicity Detection

**Date:** 2026-02-17
**Issue:** #227
**Branch:** epic/supervisor-migration-263

## Issue #227 Requirements

1. Input filter: detect toxic/off-topic queries before processing
2. Output filter: check LLM response before sending to user
3. Configurable topic allowlist/blocklist per collection
4. Integration point: `classify_node` or new `guard_node`

## Current State

- `classify_node` — 6-type regex taxonomy, **НЕ фильтрует toxic content**
- PII masking есть (`src/security/pii_redaction.py`)
- **Content filtering — нет** ни на input, ни на output

## Сравнение инструментов

| Tool | Type | Latency | Cost | Categories |
|------|------|---------|------|-----------|
| **LLM Guard** | Open-source, local | ~50ms | Free | toxicity, bias, injection, PII, banned topics |
| **Detoxify** | Open-source, local | ~20ms | Free | toxicity, obscene, threat, insult, identity_hate |
| **OpenAI Moderation** | API | ~100ms | Free | hate, violence, sexual, self-harm, harassment |
| **Guardrails AI** | Framework | ~50ms+ | Free | toxic language, PII, profanity |
| **NeMo Guardrails** | Framework + LLM | ~300ms | LLM cost | custom topics via CoLang |
| **OpenGuardrails** | Open-source | ~40ms | Free | 119 languages, 3.3B quantized |
| **Perspective API** | Google API | ~150ms | Free (quota) | toxicity score 0-1 |

## Подход 1: LLM Guard

Единая библиотека для input + output:

```python
# Input
from llm_guard.input_scanners import Toxicity, BanTopics, PromptInjection
input_scanners = [
    Toxicity(threshold=0.7),
    BanTopics(topics=["weapons", "drugs", "gambling"], threshold=0.6),
    PromptInjection(threshold=0.5),
]

# Output
from llm_guard.output_scanners import Toxicity as OutputToxicity, NoRefusal
output_scanners = [
    OutputToxicity(threshold=0.7),
    NoRefusal(),
]
```

**Плюсы:** Всё-в-одном, local models
**Минусы:** ~100MB models, медленный первый запуск

## Подход 2: Detoxify (lightweight, рекомендуется для Фазы 1)

```python
from detoxify import Detoxify
model = Detoxify('multilingual')  # поддерживает русский!
results = model.predict("toxic text")
# {'toxicity': 0.98, 'obscene': 0.92, 'insult': 0.95, ...}
```

**Плюсы:** ~20ms, **multilingual (русский!)**, lightweight (~300MB)
**Минусы:** Только toxicity, нет topic filtering, нет prompt injection

## Подход 3: OpenAI Moderation API

```python
response = await client.moderations.create(input=user_query)
# response.results[0].flagged → bool
```

**Плюсы:** Бесплатный, 11 категорий
**Минусы:** External call, НЕ поддерживает custom topics

## Подход 4: Guardrails AI (ToxicLanguage)

```python
import guardrails as gd
from guardrails.hub import ToxicLanguage
guard = gd.Guard().use(ToxicLanguage(threshold=0.25, on_fail="fix"))
# on_fail="fix" → removes toxic sentences
```

**Плюсы:** Sentence-level filtering
**Минусы:** Тяжёлый framework

## Подход 5: Custom Topic Allowlist/Blocklist

```python
BLOCKED_PATTERNS = [
    re.compile(r"\b(оружие|наркотик|казино|ставк)\w*\b", re.I),
]
```

## Рекомендация

### Фаза 1 (2-3 дня)

| Компонент | Инструмент | Где |
|-----------|-----------|-----|
| **Input toxicity** | Detoxify `multilingual` | `guard_node` (перед classify) |
| **Topic blocklist** | Regex patterns | `guard_node` |
| **Langfuse** | `security_alert` score | `guard_node` |
| **Config** | `CONTENT_FILTER_ENABLED=true` | `GraphConfig` |

```
preprocess → guard_node → classify → ...
                ↓
        toxic/blocked?
          yes → respond (rejection) + Langfuse security_alert
          no  → continue
```

### Фаза 2 (3-5 дней)

| Компонент | Инструмент | Где |
|-----------|-----------|-----|
| **Input full scan** | LLM Guard (Toxicity + BanTopics + PromptInjection) | `guard_node` |
| **Output filter** | LLM Guard OutputToxicity | `output_guard_node` (после generate) |
| **Risk scoring** | 0-1 score в Langfuse | Оба nodes |
| **Config** | Per-collection topic allowlist | `GraphConfig` |

### Фаза 3 (optional)

1. NeMo Guardrails (dialog rails, CoLang)
2. OpenAI Moderation API как fallback
3. OpenGuardrails (3.3B unified, 119 languages)

## Связь с #226 (prompt injection)

Tasks #226 и #227 **объединяются в один `guard_node`**:
- Regex injection patterns — из #226
- Detoxify toxicity scoring — из #227
- Topic blocklist — из #227
- Langfuse `security_alert` score — общий

## Ссылки

- LLM Guard: llm-guard.com
- Detoxify (multilingual): github.com/unitaryai/detoxify
- Guardrails AI ToxicLanguage: guardrailsai.com/docs/examples/toxic_language
- OpenAI Moderation: platform.openai.com/docs/guides/moderation
- OpenGuardrails (arxiv Oct 2025): arxiv.org/abs/2510.19169
