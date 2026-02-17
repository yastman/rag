# Design: Prompt Injection Defense Patterns

**Date:** 2026-02-17
**Issue:** #226
**Branch:** epic/supervisor-migration-263

## Issue #226 Requirements

1. Input sanitization в `preprocess_node` — detect injection patterns
2. LLM-based classifier или regex heuristics
3. Reject/flag suspicious inputs до main LLM
4. Log в Langfuse с `security_alert` score

## Current State

- PII masking есть (`src/security/pii_redaction.py`)
- Rate limiting есть (`telegram_bot/middlewares/throttling.py`)
- **Prompt injection defense — нет**

## Архитектура: Defense-in-Depth (4 слоя)

```
User Input → [Layer 1: Regex] → [Layer 2: Classifier] → [Layer 3: LLM Judge] → Main LLM → [Layer 4: Output Filter]
                 ↓ block              ↓ flag                  ↓ block                           ↓ redact
              Langfuse score       Langfuse score          Langfuse score                    Langfuse score
```

## Layer 1: Regex Heuristics (~0ms)

**Где:** Новый `guard_node` перед classify.

```python
INJECTION_PATTERNS = [
    r"\b(ignore|disregard)\b.*\b(previous|above)\b.*\b(instructions|rules)\b",
    r"\byou are now\b.*\b(unrestricted|no rules|developer mode)\b",
    r"\b(reveal|show)\b.*\b(system prompt|hidden instructions)\b",
    r"\b(override|bypass)\b.*\b(system|policy)\b",
    r"\bDAN\b.*\bjailbreak\b",
    r"\bact as\b.*\b(admin|root|developer)\b",
]
```

**Плюсы:** мгновенный, zero cost, no dependencies
**Минусы:** обходится перефразированием, false positives

## Layer 2: ML Classifier

| Tool | Type | Latency | Cost | Notes |
|------|------|---------|------|-------|
| **LLM Guard** (protectai) | Open-source, local | ~50ms | Free | DeBERTa-based, pip install |
| **Lakera Guard** (API) | Cloud API | ~100ms | Freemium | `lakera-chainguard` LangChain |
| **Rebuff** | **ARCHIVED May 2025** | — | — | НЕ использовать |
| **PromptGuard** (Nature 2026) | Research, MiniBERT+regex | ~30ms | Free | 4-layer framework |

**Рекомендация:** LLM Guard — open-source, local, DeBERTa v3 ~50ms на CPU.

```python
from llm_guard.input_scanners import PromptInjection
scanner = PromptInjection(threshold=0.5)
sanitized, is_valid, risk_score = scanner.scan(prompt, user_input)
```

## Layer 3: NeMo Guardrails (intent-based)

```python
from nemoguardrails import RailsConfig
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails

config = RailsConfig.from_path("config/guardrails/")
guardrails = RunnableRails(config=config, passthrough=True)
```

**Плюсы:** intent detection + dialog rails + CoLang DSL
**Минусы:** +200-500ms (LLM call), доп. зависимость

## Layer 4: LangChain Middleware (2026 API)

LangChain `AgentMiddleware` с before/after hooks — для `create_agent()` API, НЕ для нашего `StateGraph`. Для нас лучше отдельный node.

## Рекомендация

### Фаза 1 (minimal, 1-2 дня)

1. Новый `guard_node` в LangGraph (после preprocess, перед classify)
2. Regex heuristics — ~20 паттернов
3. Langfuse score `security_alert` при detection
4. Soft block: `injection_detected=True` в state

### Фаза 2 (advanced, 3-5 дней)

1. LLM Guard scanner (DeBERTa model)
2. Risk scoring (0-1) в Langfuse
3. Hard block при score > 0.8, soft flag при 0.5-0.8
4. Dashboard в Langfuse для security monitoring

### Фаза 3 (optional)

1. NeMo Guardrails для intent-based filtering
2. Output rails (проверка ответов LLM)

## Интеграция в pipeline

```
preprocess → guard_node → classify → cache_check → retrieve → ...
                 ↓
         injection_detected?
           yes → respond (blocked) + Langfuse security_alert
           no  → continue
```

## Связь с #227 (content filtering)

Tasks #226 и #227 **объединяются в один `guard_node`**:
- Regex injection patterns — из #226
- Detoxify toxicity scoring — из #227
- Topic blocklist — из #227
- Langfuse `security_alert` score — общий

## Ссылки

- NVIDIA NeMo + LangGraph: docs.nvidia.com/nemo/guardrails/latest/integration/langchain/langgraph-integration.html
- LLM Guard: github.com/protectai/llm-guard
- Langfuse Security: langfuse.com/docs/security-and-guardrails
- PromptGuard paper (Nature, Jan 2026): nature.com/articles/s41598-025-31086-y
- Rebuff — **ARCHIVED**, не использовать
