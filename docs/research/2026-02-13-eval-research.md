# Evaluation & Feedback Research — 2026 Best Practices

Исследование актуальных решений для реализации фидбека пользователей (#229), LLM-as-Judge онлайн (#230), управления датасетами (#233) и атрибуции источников (#225).

---

## 1. User Feedback Collection

### aiogram 3.x Pattern

**CallbackData Factory** — type-safe паттерн для Telegram callback buttons.

**Базовая реализация:**

```python
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram import Router

# Определяем структуру callback data
class FeedbackCallback(CallbackData, prefix="fb"):
    trace_id: str
    rating: int  # 1-5 или thumbs up/down (0/1)
    aspect: str  # "relevance", "accuracy", "completeness"

# Создание кнопок
def create_feedback_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="👍 Полезно",
        callback_data=FeedbackCallback(trace_id=trace_id, rating=1, aspect="helpfulness")
    )
    builder.button(
        text="👎 Не полезно",
        callback_data=FeedbackCallback(trace_id=trace_id, rating=0, aspect="helpfulness")
    )
    builder.adjust(2)  # 2 кнопки в ряд
    return builder.as_markup()

# Обработка callback
router = Router()

@router.callback_query(FeedbackCallback.filter())
async def handle_feedback(
    query: CallbackQuery,
    callback_data: FeedbackCallback
):
    # Автоматический парсинг через filter
    trace_id = callback_data.trace_id
    rating = callback_data.rating
    aspect = callback_data.aspect

    # Отправка в Langfuse (см. след. секцию)
    await send_feedback_to_langfuse(trace_id, rating, aspect)

    await query.answer("Спасибо за фидбек!")
```

**Преимущества CallbackData:**
- Type-safe парсинг (автоматическое извлечение полей)
- Поддержка Magic Filter (`F.rating == 1`)
- Совместимость с InlineKeyboardBuilder
- Поддержка Enum, UUID, int, str, bool

**Источники:**
- [Callback Data Factory & Filter - aiogram 3.22.0](https://docs.aiogram.dev/en/dev-3.x/dispatcher/filters/callback_data.html)
- [Кнопки - aiogram 3.x guide (рус.)](https://mastergroosha.github.io/aiogram-3-guide/buttons/)

### Langfuse Integration

**3 способа отправки scores:**

**1. Low-level API (для внешних источников):**

```python
from langfuse import Langfuse

async def send_feedback_to_langfuse(trace_id: str, rating: int, aspect: str):
    langfuse = Langfuse()
    langfuse.create_score(
        name=f"user_feedback_{aspect}",
        value=rating,  # 0 или 1 для thumbs
        trace_id=trace_id,
        data_type="BOOLEAN",  # или "NUMERIC" для 1-5
        comment=f"User feedback via Telegram callback"
    )
    langfuse.flush()  # Важно для async контекста
```

**2. Context-based (внутри traced функции):**

```python
from langfuse.decorators import observe

@observe(as_type="span")
def process_query(query: str):
    # ... обработка запроса ...

    # Внутренняя оценка
    langfuse.score_current_span(
        name="internal_quality",
        value=0.85,
        data_type="NUMERIC"
    )
```

**3. Update существующего observation:**

```python
with langfuse.start_as_current_observation(as_type="span", name="rag_retrieval") as span:
    results = retrieve_documents(query)

    span.score(
        name="retrieval_quality",
        value=len(results) > 0,
        data_type="BOOLEAN"
    )
```

**Data types:**
- `NUMERIC`: float (0.0-1.0 или любой диапазон)
- `CATEGORICAL`: string ("good", "bad", "neutral")
- `BOOLEAN`: 0 или 1 (для thumbs up/down)

**Источники:**
- [Scores via API/SDK - Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)
- [Score Analytics - Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/score-analytics)

---

## 2. LLM-as-Judge Online

### Langfuse Evaluators

**Setup через UI:**

1. **Create Evaluator**: `Evaluators` → `+ Set up Evaluator`
2. **Configure Model**: GPT-4o / Claude Sonnet / Gemini Pro (требуется structured output)
3. **Evaluator Type**:
   - **Managed**: pre-built (Ragas hallucination, toxicity)
   - **Custom**: свой prompt с `{{variables}}`
4. **Target**:
   - **Observations** (production): fastest, для отдельных LLM calls
   - **Traces** (production): полный workflow
   - **Experiments** (offline): dataset-based
5. **Map Variables**: JSONPath для input/output/ground_truth
6. **Trigger**: автоматически на matching traces или через SDK

**Async Processing:**
- Observation evaluations: **секунды**
- Trace evaluations: **минуты**
- Queue-based: не блокирует production

**Model Requirements:**
- Structured output support (обязательно)
- Рекомендуемые: GPT-4o, Claude Sonnet, Gemini Pro

**Cost Optimization:**
- GPT-4o-mini для simple criteria (5x дешевле)
- Observation-level (faster) vs trace-level (comprehensive)

**Источники:**
- [LLM-as-a-Judge Evaluation - Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Evaluation of LLM Applications - Langfuse](https://langfuse.com/docs/evaluation/overview)

### Custom Judge Pipeline

**Async pattern для production:**

```python
import asyncio
from langfuse import Langfuse
from openai import AsyncOpenAI

class AsyncJudge:
    def __init__(self):
        self.langfuse = Langfuse()
        self.client = AsyncOpenAI()

    async def judge_relevance(self, trace_id: str, query: str, answer: str):
        # LLM-as-Judge prompt
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "Evaluate if answer is relevant to query. Return JSON: {\"score\": 0-1, \"reason\": \"...\"}"
            }, {
                "role": "user",
                "content": f"Query: {query}\n\nAnswer: {answer}"
            }],
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        # Отправка в Langfuse
        self.langfuse.create_score(
            name="llm_judge_relevance",
            value=result["score"],
            trace_id=trace_id,
            data_type="NUMERIC",
            comment=result["reason"]
        )

    async def batch_judge(self, traces: list[dict]):
        # Параллельная оценка
        tasks = [
            self.judge_relevance(t["id"], t["query"], t["answer"])
            for t in traces
        ]
        await asyncio.gather(*tasks)
```

**CI/CD Integration (GitHub Actions):**

```yaml
name: Eval on PR
on: pull_request

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run LLM-as-Judge on Test Dataset
        run: |
          python scripts/eval_on_dataset.py \
            --dataset-name "pr-regression-tests" \
            --judge-model "gpt-4o-mini" \
            --threshold 0.75
      - name: Comment Results on PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              body: '📊 Eval results: [Langfuse link]'
            })
```

**Источники:**
- [LLM as a Judge: A 2026 Guide - Label Your Data](https://labelyourdata.com/articles/llm-as-a-judge)
- [The Complete Guide to LLM Evaluation in 2026 - Adaline](https://www.adaline.ai/blog/complete-guide-llm-ai-agent-evaluation-2026)
- [Automated Evaluations - Langfuse Blog](https://langfuse.com/blog/2025-09-05-automated-evaluations)

### Рекомендация

**Для issue #230 (Online LLM-as-Judge):**

1. **Старт:** Langfuse Evaluators через UI
   - Managed evaluator для hallucination (Ragas)
   - Custom evaluator для relevance (простой prompt)
   - Target: Observations (fast)
   - Model: GPT-4o-mini (cost-effective)

2. **Scaling:** Custom async pipeline для сложных критериев
   - Multi-aspect evaluation (relevance + accuracy + completeness)
   - Hybrid: Langfuse для базовых критериев, custom для domain-specific

3. **Monitoring:** Score Analytics dashboard
   - Track evaluator agreement с user feedback
   - Alert на score drops (Grafana + Langfuse API)

**Cost estimate:**
- GPT-4o-mini: ~$0.0005 per evaluation
- 1000 traces/day × 2 evaluators = ~$1/day

---

## 3. Dataset Management from Traces

### Langfuse Datasets API

**Создание dataset items из production traces:**

**Python SDK:**

```python
from langfuse import Langfuse
from datetime import datetime, timezone

langfuse = Langfuse()

# Паттерн: выбрать failing trace → добавить с исправленным expected_output
def add_failing_trace_to_dataset(trace_id: str, corrected_output: str):
    # Получить trace через Langfuse API
    trace = langfuse.get_trace(trace_id)

    langfuse.create_dataset_item(
        dataset_name="regression_tests",
        input=trace.input,  # Оригинальный запрос
        expected_output={"answer": corrected_output},  # Экспертная правка
        source_trace_id=trace_id,  # Линк на production trace
        metadata={"issue": "hallucination", "fixed_by": "expert"}
    )

# Batch import из filtered traces
def import_low_rated_traces(min_user_feedback: float = 0.3):
    # Langfuse SDK query для traces с низкими scores
    traces = langfuse.fetch_traces(
        filter=[
            {
                "type": "score",
                "name": "user_feedback_helpfulness",
                "operator": "<",
                "value": min_user_feedback
            }
        ],
        limit=100
    )

    for trace in traces:
        # Требует ручной аннотации expected_output
        print(f"Trace {trace.id}: {trace.input} → {trace.output}")
        # Workflow: эксперт проверяет → вызывает add_failing_trace_to_dataset
```

**TypeScript SDK:**

```typescript
await langfuse.api.datasetItems.create({
  datasetName: "customer_support_qa",
  input: { question: "How to reset password?" },
  expectedOutput: { answer: "Click 'Forgot password' link..." },
  sourceTraceId: "trace-abc-123",
  sourceObservationId: "obs-xyz-456",  // опционально
});
```

**Versioning:**

```python
from datetime import datetime, timezone

# Каждое add/update/delete создаёт новую версию (timestamp)

# Fetching dataset at specific version
version_timestamp = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
dataset_v1 = langfuse.get_dataset(
    name="regression_tests",
    version=version_timestamp
)

# Latest version
dataset_latest = langfuse.get_dataset(name="regression_tests")

# Run experiment на старой версии (reproducibility)
langfuse.run_experiment(
    dataset_name="regression_tests",
    dataset_version=version_timestamp,
    experiment_name="model-v2-on-feb10-dataset"
)
```

**Источники:**
- [Datasets - Langfuse](https://langfuse.com/docs/evaluation/experiments/datasets)
- [Dataset Item Versioning - Langfuse Changelog](https://langfuse.com/changelog/2025-12-15-dataset-versioning)

### CI Integration

**Eval on PR pattern:**

```python
# scripts/eval_on_pr.py
import os
from langfuse import Langfuse

def run_eval_on_dataset(dataset_name: str, pr_branch: str):
    langfuse = Langfuse()
    dataset = langfuse.get_dataset(dataset_name)

    results = []
    for item in dataset.items:
        # Run новая версия модели
        output = run_rag_pipeline(item.input)

        # Оценка через LLM-as-Judge
        score = judge_output(item.input, output, item.expected_output)
        results.append(score)

    avg_score = sum(results) / len(results)

    # Fail PR if regression
    threshold = 0.75
    if avg_score < threshold:
        print(f"❌ Eval failed: {avg_score:.2f} < {threshold}")
        exit(1)
    else:
        print(f"✅ Eval passed: {avg_score:.2f}")

if __name__ == "__main__":
    run_eval_on_dataset("regression_tests", os.getenv("GITHUB_HEAD_REF"))
```

**GitHub Actions workflow:**

```yaml
# .github/workflows/eval-on-pr.yml
name: Eval on PR
on:
  pull_request:
    branches: [main]

jobs:
  regression-tests:
    runs-on: ubuntu-latest
    env:
      LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
      LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: uv sync
      - name: Run eval on regression dataset
        run: uv run python scripts/eval_on_pr.py
      - name: Comment results
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = fs.readFileSync('eval_results.json', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              body: `## 📊 Eval Results\n\`\`\`json\n${results}\n\`\`\``
            })
```

**Источники:**
- [Experiments via SDK - Langfuse](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
- [Query Data via SDKs - Langfuse](https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk)

### Рекомендация для issue #233

**Workflow:**

1. **Production → Dataset** (manual curation):
   - Langfuse UI: filter traces by user_feedback < 0.3
   - Эксперт проверяет → исправляет expected_output
   - `create_dataset_item()` с `source_trace_id`

2. **Dataset versioning** (reproducibility):
   - Каждая правка создаёт новую версию
   - CI/CD runs eval на **pinned version** (не latest)

3. **CI integration** (regression prevention):
   - PR → eval на dataset → comment results → block if score drops

4. **Continuous enrichment**:
   - Weekly cron: export low-rated traces → annotation queue
   - Slack notification для экспертов

---

## 4. Source Attribution in RAG

### Prompt Engineering

**System prompt для citations:**

```python
SYSTEM_PROMPT = """
Ты — ассистент с доступом к базе знаний.

ОБЯЗАТЕЛЬНО:
1. Используй ТОЛЬКО информацию из предоставленных документов
2. Для КАЖДОГО факта указывай источник в формате [1], [2] и т.д.
3. Если информации нет в документах — скажи "Не нашёл информацию в документах"

ФОРМАТ ОТВЕТА:
<ответ с inline citations [1][2]>

ИСТОЧНИКИ:
[1] Название документа 1, стр. X
[2] Название документа 2, стр. Y
"""

# Контекст с метаданными
def format_context_with_metadata(documents: list[Document]) -> str:
    context_parts = []
    for i, doc in enumerate(documents, 1):
        context_parts.append(f"""
[Документ {i}]
Название: {doc.metadata.get('title', 'N/A')}
Страница: {doc.metadata.get('page', 'N/A')}
Содержание: {doc.page_content}
""")
    return "\n\n".join(context_parts)

# В промпте
USER_PROMPT = f"""
КОНТЕКСТ:
{format_context_with_metadata(retrieved_docs)}

ВОПРОС:
{user_query}

ОТВЕТ (с inline citations):
"""
```

**Парсинг citations из LLM ответа:**

```python
import re
from dataclasses import dataclass

@dataclass
class AnswerWithCitations:
    text: str
    citations: list[dict]

def parse_citations(llm_response: str, documents: list[Document]) -> AnswerWithCitations:
    # Извлечь citations из текста
    citation_pattern = r'\[(\d+)\]'
    cited_indices = set(int(m.group(1)) for m in re.finditer(citation_pattern, llm_response))

    # Собрать метаданные источников
    citations = []
    for idx in sorted(cited_indices):
        if idx <= len(documents):
            doc = documents[idx - 1]
            citations.append({
                "index": idx,
                "title": doc.metadata.get("title"),
                "url": doc.metadata.get("url"),
                "page": doc.metadata.get("page")
            })

    return AnswerWithCitations(text=llm_response, citations=citations)
```

**Источники:**
- [Source Attribution in RAG - arXiv](https://arxiv.org/abs/2507.04480)
- [RAG in 2025 Enterprise Guide - Data Nucleus](https://datanucleus.dev/rag-and-agentic-ai/what-is-rag-enterprise-guide-2025)

### Formatting for Telegram

**Telegram markdown для citations:**

```python
def format_telegram_response(answer: AnswerWithCitations) -> str:
    # Заменить [1] на [1](url) для кликабельных ссылок
    text = answer.text
    for citation in answer.citations:
        if citation["url"]:
            # Telegram markdown link
            link = f'<a href="{citation["url"]}">[{citation["index"]}]</a>'
            text = text.replace(f'[{citation["index"]}]', link)

    # Добавить список источников внизу
    sources_section = "\n\n📚 <b>Источники:</b>\n"
    for citation in answer.citations:
        title = citation["title"] or "Документ"
        page = f', стр. {citation["page"]}' if citation["page"] else ''
        url = citation["url"]

        if url:
            sources_section += f'[{citation["index"]}] <a href="{url}">{title}</a>{page}\n'
        else:
            sources_section += f'[{citation["index"]}] {title}{page}\n'

    return text + sources_section

# Пример использования
await message.answer(
    format_telegram_response(answer),
    parse_mode="HTML",
    disable_web_page_preview=True  # Не показывать preview для всех ссылок
)
```

**Альтернатива: inline buttons для источников:**

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def create_sources_keyboard(citations: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for citation in citations:
        if citation["url"]:
            builder.button(
                text=f'📄 {citation["title"][:30]}...',
                url=citation["url"]
            )
    builder.adjust(1)  # По 1 кнопке в ряд
    return builder.as_markup()

# Отправка
await message.answer(
    answer.text,
    reply_markup=create_sources_keyboard(answer.citations)
)
```

**Источники:**
- [Telegram Bot API - Formatting Options](https://core.telegram.org/bots/api#formatting-options)
- [aiogram InlineKeyboardButton docs](https://docs.aiogram.dev/en/latest/api/types/inline_keyboard_button.html)

### Advanced: SELF-RAG для accurate citations

**Концепция:**
- LLM генерирует несколько вариантов ответа
- Каждый вариант оценивается на relevance + citation accuracy
- Выбирается best-scoring ответ

```python
async def self_rag_with_citations(query: str, documents: list[Document]) -> str:
    # 1. Generate multiple candidate answers
    candidates = await generate_multiple_answers(query, documents, n=3)

    # 2. Judge each candidate
    scores = []
    for candidate in candidates:
        # Проверить: все ли citations валидны?
        citation_accuracy = verify_citations(candidate, documents)
        # Проверить: relevance к query?
        relevance = await judge_relevance(query, candidate)

        scores.append(citation_accuracy * 0.4 + relevance * 0.6)

    # 3. Select best candidate
    best_idx = scores.index(max(scores))
    return candidates[best_idx]
```

**Источники:**
- [RAG in 2025 - SELF-RAG approach](https://datanucleus.dev/rag-and-agentic-ai/what-is-rag-enterprise-guide-2025)

### Рекомендация для issue #225

**Immediate (2-3 дня):**
1. Обновить system prompt для inline citations `[1][2]`
2. Добавить metadata (title, page, url) в Qdrant payloads
3. Парсинг citations → Telegram HTML formatting

**Next (1 неделя):**
1. Inline buttons для источников (UX улучшение)
2. Langfuse score для citation_accuracy (LLM-as-Judge)

**Advanced (optional):**
1. SELF-RAG для multi-candidate generation
2. Citation verification через embeddings similarity

---

## Summary & Roadmap

| Issue | Solution | Effort | Priority |
|-------|----------|--------|----------|
| #229 | aiogram CallbackData + Langfuse score API | 2-3 дня | High |
| #230 | Langfuse Evaluators (UI) + custom async judge | 3-5 дней | High |
| #233 | Langfuse Datasets API + CI eval on PR | 1 неделя | Medium |
| #225 | Prompt engineering + Telegram HTML citations | 2-3 дня | High |

**Recommended order:**
1. #229 (User feedback) — foundational data source
2. #225 (Citations) — UX improvement
3. #230 (LLM-as-Judge) — automated quality monitoring
4. #233 (Datasets) — long-term regression prevention

---

## References

### aiogram 3.x
- [Callback Data Factory & Filter](https://docs.aiogram.dev/en/dev-3.x/dispatcher/filters/callback_data.html)
- [InlineKeyboardButton API](https://docs.aiogram.dev/en/latest/api/types/inline_keyboard_button.html)
- [Кнопки - aiogram 3.x guide (рус.)](https://mastergroosha.github.io/aiogram-3-guide/buttons/)

### Langfuse Evaluation
- [LLM-as-a-Judge Evaluation](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Scores via API/SDK](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)
- [Datasets](https://langfuse.com/docs/evaluation/experiments/datasets)
- [Dataset Versioning Changelog](https://langfuse.com/changelog/2025-12-15-dataset-versioning)
- [Automated Evaluations Blog](https://langfuse.com/blog/2025-09-05-automated-evaluations)

### LLM-as-Judge Research
- [LLM as a Judge: A 2026 Guide](https://labelyourdata.com/articles/llm-as-a-judge)
- [Complete Guide to LLM Evaluation 2026](https://www.adaline.ai/blog/complete-guide-llm-ai-agent-evaluation-2026)
- [Training LLM-as-Judge Model](https://arxiv.org/abs/2502.02988)
- [LLM-As-Judge Best Practices](https://www.montecarlodata.com/blog-llm-as-judge/)

### RAG Source Attribution
- [Source Attribution in RAG - arXiv](https://arxiv.org/abs/2507.04480)
- [RAG in 2025 Enterprise Guide](https://datanucleus.dev/rag-and-agentic-ai/what-is-rag-enterprise-guide-2025)
- [Retrieval Augmented Generation Guide](https://www.promptingguide.ai/techniques/rag)
