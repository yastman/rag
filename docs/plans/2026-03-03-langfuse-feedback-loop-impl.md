# Langfuse Feedback Loop & Quality Improvement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Построить полный feedback loop: 6-category dislike, implicit signals, annotation queues, observation-level evals, dataset pipeline, alerting.

**Architecture:** Расширяем существующий feedback (0/1 score) до 2-step flow с причинами. Добавляем implicit retry detection через embedding similarity. Auto-triage скрипт кладёт dislike-и в Langfuse Annotation Queue. Observation-level evaluators оценивают retrieve и generate отдельно.

**Tech Stack:** Python 3.12, aiogram 3, Langfuse SDK v3 (>=3.14.0), `lf` CLI v0.1.4, `npx langfuse-cli`

**Design doc:** `docs/plans/2026-03-03-langfuse-feedback-loop-design.md`

**Worktree:** `/home/user/projects/rag-fresh/.claude/worktrees/langfuse-feedback-audit/`

---

## Phase 1: Foundation (6-8h)

### Task 1.1: Add Environment Support

**Files:**
- Modify: `telegram_bot/observability.py:333-341`
- Modify: `.env.example:111-113`
- Test: `tests/unit/test_observability.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_observability.py — добавить тест
def test_langfuse_init_passes_environment(monkeypatch, mock_langfuse_class):
    """Environment env var должен передаваться в Langfuse()."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "staging")

    from telegram_bot.observability import initialize_langfuse
    # Reset singleton
    import telegram_bot.observability as obs
    obs._langfuse_client = None

    initialize_langfuse()
    mock_langfuse_class.assert_called_once()
    call_kwargs = mock_langfuse_class.call_args[1]
    assert call_kwargs.get("environment") == "staging"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/user/projects/rag-fresh/.claude/worktrees/langfuse-feedback-audit && uv run pytest tests/unit/test_observability.py::test_langfuse_init_passes_environment -v`
Expected: FAIL — environment не передаётся

**Step 3: Write minimal implementation**

В `telegram_bot/observability.py:333-341`, добавить `environment` в kwargs:

```python
# После строки 341 (перед Langfuse(**kwargs)):
env = os.getenv("LANGFUSE_TRACING_ENVIRONMENT")
if env:
    kwargs["environment"] = env
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_observability.py::test_langfuse_init_passes_environment -v`
Expected: PASS

**Step 5: Add env var to .env.example**

```bash
# Добавить после LANGFUSE_HOST:
# LANGFUSE_TRACING_ENVIRONMENT=development  # production | staging | development | ci
```

**Step 6: Commit**

```bash
git add telegram_bot/observability.py .env.example tests/unit/test_observability.py
git commit -m "feat(langfuse): add LANGFUSE_TRACING_ENVIRONMENT support"
```

---

### Task 1.2: Externalize Flush Config + Graceful Shutdown

**Files:**
- Modify: `telegram_bot/observability.py:333-355`
- Modify: `.env.example`
- Test: `tests/unit/test_observability.py`

**Step 1: Write failing tests**

```python
def test_langfuse_flush_config_from_env(monkeypatch, mock_langfuse_class):
    """flush_at и flush_interval читаются из env vars."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_FLUSH_AT", "25")
    monkeypatch.setenv("LANGFUSE_FLUSH_INTERVAL", "10")

    import telegram_bot.observability as obs
    obs._langfuse_client = None
    obs.initialize_langfuse()

    call_kwargs = mock_langfuse_class.call_args[1]
    assert call_kwargs["flush_at"] == 25
    assert call_kwargs["flush_interval"] == 10


def test_langfuse_shutdown_registers_atexit(monkeypatch, mock_langfuse_class):
    """Shutdown hook регистрируется при инициализации."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    import telegram_bot.observability as obs
    obs._langfuse_client = None

    with unittest.mock.patch("atexit.register") as mock_atexit:
        obs.initialize_langfuse()
        mock_atexit.assert_called_once()
```

**Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/unit/test_observability.py -k "flush_config or shutdown_registers" -v`

**Step 3: Implement**

В `observability.py:333-355`:

```python
import atexit

# Замена hardcoded flush_at=50, flush_interval=5:
kwargs = {
    "public_key": public_key,
    "secret_key": secret_key,
    "mask": mask_pii,
    "flush_at": int(os.getenv("LANGFUSE_FLUSH_AT", "50")),
    "flush_interval": int(os.getenv("LANGFUSE_FLUSH_INTERVAL", "5")),
}
# ... existing env/host logic ...

# После успешной инициализации клиента:
atexit.register(_shutdown_langfuse)

# Новая функция:
def _shutdown_langfuse() -> None:
    """Graceful shutdown — flush pending events."""
    if _langfuse_client is not None:
        try:
            _langfuse_client.shutdown()
        except Exception:
            pass
```

**Step 4: Run tests — expect PASS**

**Step 5: Update .env.example**

```bash
# LANGFUSE_FLUSH_AT=50              # Batch size before flush
# LANGFUSE_FLUSH_INTERVAL=5         # Flush interval in seconds
# LANGFUSE_TRACING_ENVIRONMENT=development
```

**Step 6: Commit**

```bash
git add telegram_bot/observability.py .env.example tests/unit/test_observability.py
git commit -m "feat(langfuse): externalize flush config, add graceful shutdown"
```

---

### Task 1.3: Create Score Configs Script

**Files:**
- Create: `scripts/setup_score_configs.py`
- Test: manual run

**Step 1: Write the script**

```python
"""Create Langfuse Score Configs for standardized scoring.

Usage: uv run python -m scripts.setup_score_configs
"""
from __future__ import annotations

import os

from langfuse import Langfuse


def create_score_configs() -> None:
    lf = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )
    lf.auth_check()

    configs = [
        # Feedback
        {"name": "user_feedback", "data_type": "NUMERIC",
         "description": "User like (1) / dislike (0)", "min_value": 0, "max_value": 1},
        {"name": "user_feedback_reason", "data_type": "CATEGORICAL",
         "description": "Reason for dislike",
         "categories": [
             {"label": "wrong_topic", "value": 0},
             {"label": "missing_info", "value": 1},
             {"label": "bad_sources", "value": 2},
             {"label": "hallucination", "value": 3},
             {"label": "incomplete", "value": 4},
             {"label": "formatting", "value": 5},
         ]},
        {"name": "implicit_retry", "data_type": "BOOLEAN",
         "description": "User reformulated query (cosine sim > 0.7 within 60s)"},
        # Quality
        {"name": "judge_faithfulness", "data_type": "NUMERIC",
         "description": "LLM-as-Judge: answer grounded in context", "min_value": 0, "max_value": 1},
        {"name": "judge_answer_relevance", "data_type": "NUMERIC",
         "description": "LLM-as-Judge: answer relevance to question", "min_value": 0, "max_value": 1},
        {"name": "judge_context_relevance", "data_type": "NUMERIC",
         "description": "LLM-as-Judge: retrieved docs relevance", "min_value": 0, "max_value": 1},
        # Performance
        {"name": "latency_total_ms", "data_type": "NUMERIC",
         "description": "End-to-end pipeline wall-time (ms)", "min_value": 0},
        {"name": "confidence_score", "data_type": "NUMERIC",
         "description": "Grade confidence", "min_value": 0, "max_value": 1},
    ]

    for cfg in configs:
        try:
            lf.api.score_configs.create(**cfg)
            print(f"  ✓ {cfg['name']}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ⊘ {cfg['name']} (already exists)")
            else:
                print(f"  ✗ {cfg['name']}: {e}")

    lf.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    create_score_configs()
```

**Step 2: Commit**

```bash
git add scripts/setup_score_configs.py
git commit -m "feat(langfuse): add score configs setup script"
```

---

### Task 1.4: Cleanup — Delete Legacy, Fix Stubs, Update Contract

**Files:**
- Delete: `telegram_bot/integrations/langfuse.py`
- Modify: `telegram_bot/scoring.py:80` (remove hyde stub)
- Modify: `tests/observability/trace_contract.yaml:252-278`
- Modify: `.env.example`

**Step 1: Verify legacy file is unused**

Run: `cd /home/user/projects/rag-fresh/.claude/worktrees/langfuse-feedback-audit && grep -r "from telegram_bot.integrations.langfuse import" --include="*.py" | grep -v __pycache__ | grep -v .pyc`
Expected: 0 matches (or only test files)

**Step 2: Delete legacy file**

```bash
git rm telegram_bot/integrations/langfuse.py
```

**Step 3: Remove hyde_used stub**

В `scoring.py:80`, удалить строку:
```python
# DELETE: "hyde_used": 0.0,  # HyDE not implemented
```

**Step 4: Update trace contract — add missing scores**

В `tests/observability/trace_contract.yaml`, в секцию `scores:`, добавить:

```yaml
  feedback:
    - user_feedback
    - user_feedback_reason
    - implicit_retry
  agent:
    - supervisor_model
    - user_role
    - hitl_action
```

**Step 5: Add undocumented env vars to .env.example**

```bash
# LANGFUSE_MODEL_DEFINITIONS_JSON=   # Custom model definitions JSON path
# LANGFUSE_MODEL_SYNC_ENABLED=true   # Sync model definitions on startup
# LANGFUSE_PROMPT_LABEL=production   # Prompt label to fetch
# JUDGE_SAMPLE_RATE=0.2              # LLM-as-Judge sampling rate (0-1)
# ENABLE_LANGFUSE=true               # Master toggle for Langfuse
```

**Step 6: Run existing tests**

Run: `uv run pytest tests/unit/test_observability.py tests/unit/test_feedback_handler.py tests/unit/test_bot_scores.py -v`
Expected: All PASS (no regressions)

**Step 7: Commit**

```bash
git add -u  # stages deletions and modifications
git add .env.example tests/observability/trace_contract.yaml
git commit -m "chore(langfuse): remove legacy callback handler, fix hyde stub, update contract"
```

---

### Task 1.5: Add Prompt Version to Span Output

**Files:**
- Modify: `telegram_bot/integrations/prompt_manager.py:45-65`
- Test: `tests/unit/test_observability.py` (or dedicated test)

**Step 1: Write failing test**

```python
def test_prompt_manager_logs_version(monkeypatch):
    """prompt_version должен быть в span output."""
    from unittest.mock import MagicMock, patch

    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "compiled prompt"
    mock_prompt.version = 3

    mock_lf = MagicMock()

    with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_lf):
        with patch("telegram_bot.integrations.prompt_manager._get_langfuse_prompt", return_value=mock_prompt):
            from telegram_bot.integrations.prompt_manager import get_prompt
            result = get_prompt("test-prompt", fallback="fallback")

    # Verify span output includes version
    output_call = mock_lf.update_current_span.call_args_list[-1]
    output_kwargs = output_call[1].get("output", {})
    assert "prompt_version" in output_kwargs
```

**Step 2: Implement**

В `prompt_manager.py`, в секции где update_current_span(output=...), добавить:

```python
lf.update_current_span(output={
    "source": source,
    "reason": reason,
    "result_length": len(result) if result else 0,
    "prompt_version": getattr(prompt_obj, "version", None),  # NEW
})
```

**Step 3: Run test — PASS**

**Step 4: Commit**

```bash
git add telegram_bot/integrations/prompt_manager.py tests/unit/test_observability.py
git commit -m "feat(langfuse): log prompt_version in span output"
```

---

## Phase 2: Rich Feedback (8-12h)

### Task 2.1: 6-Category Dislike Keyboard

**Files:**
- Modify: `telegram_bot/feedback.py`
- Test: `tests/unit/test_feedback_handler.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_feedback_handler.py — добавить

class TestDislikeReasonKeyboard:
    def test_build_dislike_reason_keyboard_returns_6_buttons(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard
        kb = build_dislike_reason_keyboard("trace123")
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        assert len(buttons) == 6

    def test_dislike_reason_callback_data_format(self):
        from telegram_bot.feedback import build_dislike_reason_keyboard
        kb = build_dislike_reason_keyboard("trace123")
        first_btn = kb.inline_keyboard[0][0]
        assert first_btn.callback_data.startswith("fb:0:")
        assert "trace123" in first_btn.callback_data

    def test_parse_dislike_reason_callback(self):
        from telegram_bot.feedback import parse_feedback_callback
        result = parse_feedback_callback("fb:0:ha:trace123")
        assert result is not None
        value, trace_id, reason = result
        assert value == 0.0
        assert trace_id == "trace123"
        assert reason == "hallucination"

    def test_parse_like_callback_no_reason(self):
        from telegram_bot.feedback import parse_feedback_callback
        result = parse_feedback_callback("fb:1:trace123")
        assert result is not None
        value, trace_id = result[0], result[1]
        assert value == 1.0
        assert result[2] is None  # no reason for like
```

**Step 2: Run — expect FAIL (functions don't exist)**

Run: `uv run pytest tests/unit/test_feedback_handler.py::TestDislikeReasonKeyboard -v`

**Step 3: Implement in feedback.py**

```python
# Добавить после существующих констант:

_REASON_CODES: dict[str, str] = {
    "wt": "wrong_topic",
    "mi": "missing_info",
    "bs": "bad_sources",
    "ha": "hallucination",
    "ic": "incomplete",
    "fm": "formatting",
}

_REASON_LABELS: dict[str, str] = {
    "wt": "Не по теме",
    "mi": "Нет информации",
    "bs": "Плохие источники",
    "ha": "Выдумал факты",
    "ic": "Неполный ответ",
    "fm": "Плохой формат",
}


def build_dislike_reason_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard with 6 dislike reason buttons (3 rows × 2 columns)."""
    codes = list(_REASON_CODES.keys())
    rows = []
    for i in range(0, len(codes), 2):
        row = []
        for code in codes[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=_REASON_LABELS[code],
                    callback_data=f"{_FB_PREFIX}0:{code}:{trace_id}",
                )
            )
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

Обновить `parse_feedback_callback()`:

```python
def parse_feedback_callback(data: str) -> tuple[float, str, str | None] | None:
    """Parse feedback callback data.

    Returns (value, trace_id, reason) or None.
    reason is None for likes, string for dislikes with reason.
    """
    if not data or not data.startswith(_FB_PREFIX):
        return None
    parts = data[len(_FB_PREFIX) :].split(":", maxsplit=2)
    if len(parts) < 2:
        return None
    try:
        value = float(parts[0])
    except ValueError:
        return None
    if parts[0] == "done":
        return None

    if len(parts) == 3 and parts[1] in _REASON_CODES:
        # fb:0:ha:trace_id — dislike with reason
        reason_code = parts[1]
        trace_id = parts[2]
        return (value, trace_id, _REASON_CODES[reason_code])
    elif len(parts) == 2:
        # fb:1:trace_id — like (no reason)
        trace_id = parts[1]
        return (value, trace_id, None)
    else:
        # fb:0:trace_id — legacy dislike without reason
        trace_id = parts[-1]
        return (value, trace_id, None)
```

**Step 4: Run tests — PASS**

Run: `uv run pytest tests/unit/test_feedback_handler.py -v`

**Step 5: Commit**

```bash
git add telegram_bot/feedback.py tests/unit/test_feedback_handler.py
git commit -m "feat(feedback): add 6-category dislike reason keyboard"
```

---

### Task 2.2: Handle Dislike Reason in Bot

**Files:**
- Modify: `telegram_bot/bot.py:3150-3197` (handle_feedback)
- Test: `tests/unit/test_feedback_handler.py`

**Step 1: Write failing test**

```python
class TestHandleFeedbackWithReason:
    @pytest.mark.asyncio
    async def test_dislike_shows_reason_keyboard(self):
        """Первый 👎 показывает keyboard с причинами."""
        # Mock callback with fb:0:trace123 (legacy dislike, no reason)
        # Should respond with build_dislike_reason_keyboard()
        ...

    @pytest.mark.asyncio
    async def test_dislike_with_reason_writes_two_scores(self):
        """fb:0:ha:trace123 пишет user_feedback=0 И user_feedback_reason=hallucination."""
        mock_lf = MagicMock()
        # ... setup callback with fb:0:ha:trace123 ...
        # Verify two create_score calls:
        calls = mock_lf.create_score.call_args_list
        assert len(calls) == 2
        # First: user_feedback = 0
        assert calls[0][1]["name"] == "user_feedback"
        assert calls[0][1]["value"] == 0.0
        # Second: user_feedback_reason = "hallucination"
        assert calls[1][1]["name"] == "user_feedback_reason"
        assert calls[1][1]["value"] == "hallucination"
        assert calls[1][1]["data_type"] == "CATEGORICAL"
```

**Step 2: Implement in bot.py handle_feedback**

Логика:
1. `fb:1:{tid}` → like → write score(user_feedback=1) → confirmation
2. `fb:0:{tid}` (без reason) → показать `build_dislike_reason_keyboard(tid)`
3. `fb:0:{code}:{tid}` (с reason) → write score(user_feedback=0) + score(user_feedback_reason=reason) → confirmation

```python
async def handle_feedback(self, callback: CallbackQuery) -> None:
    parsed = parse_feedback_callback(callback.data)
    if parsed is None:
        await callback.answer()
        return

    value, trace_id, reason = parsed
    lf_client = get_langfuse_client()

    if value == 0.0 and reason is None:
        # Step 1: dislike without reason → show reason keyboard
        await callback.message.edit_reply_markup(
            reply_markup=build_dislike_reason_keyboard(trace_id),
        )
        await callback.answer("Укажите причину")
        return

    # Write user_feedback score
    if lf_client is not None:
        user_id = callback.from_user.id if callback.from_user else 0
        lf_client.create_score(
            trace_id=trace_id,
            name="user_feedback",
            value=value,
            data_type="NUMERIC",
            comment=f"user_id:{user_id}",
            score_id=f"{trace_id}-user_feedback",
        )

        # Write reason score for dislikes
        if reason is not None:
            lf_client.create_score(
                trace_id=trace_id,
                name="user_feedback_reason",
                value=reason,
                data_type="CATEGORICAL",
                comment=f"user_id:{user_id}",
                score_id=f"{trace_id}-user_feedback_reason",
            )

    # Show confirmation
    await callback.message.edit_reply_markup(
        reply_markup=build_feedback_confirmation(liked=value > 0),
    )
    await callback.answer()
    asyncio.create_task(
        self._clear_feedback_confirmation_later(callback.message),
    )
```

**Step 3: Run tests — PASS**

**Step 4: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_feedback_handler.py
git commit -m "feat(feedback): 2-step dislike flow with reason selection"
```

---

### Task 2.3: Implicit Retry Detection

**Files:**
- Create: `telegram_bot/implicit_feedback.py`
- Modify: `telegram_bot/bot.py:2138-2170` (handle_query)
- Test: `tests/unit/test_implicit_feedback.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_implicit_feedback.py
import pytest
from telegram_bot.implicit_feedback import is_reformulation


class TestReformulationDetection:
    def test_similar_queries_detected(self):
        # Cosine similarity > 0.7 → reformulation
        assert is_reformulation(
            current_embedding=[1.0, 0.0, 0.0],
            previous_embedding=[0.9, 0.1, 0.0],
            time_delta_seconds=30,
        ) is True

    def test_different_queries_not_detected(self):
        assert is_reformulation(
            current_embedding=[1.0, 0.0, 0.0],
            previous_embedding=[0.0, 1.0, 0.0],
            time_delta_seconds=30,
        ) is False

    def test_old_query_not_detected(self):
        # > 60s → not a retry even if similar
        assert is_reformulation(
            current_embedding=[1.0, 0.0, 0.0],
            previous_embedding=[0.95, 0.05, 0.0],
            time_delta_seconds=120,
        ) is False

    def test_none_previous_not_detected(self):
        assert is_reformulation(
            current_embedding=[1.0, 0.0, 0.0],
            previous_embedding=None,
            time_delta_seconds=10,
        ) is False
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# telegram_bot/implicit_feedback.py
"""Implicit feedback detection: retry/reformulation via embedding similarity."""
from __future__ import annotations

import math


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def is_reformulation(
    current_embedding: list[float],
    previous_embedding: list[float] | None,
    time_delta_seconds: float,
    similarity_threshold: float = 0.7,
    max_time_seconds: float = 60.0,
) -> bool:
    """Detect if current query is a reformulation of previous."""
    if previous_embedding is None:
        return False
    if time_delta_seconds > max_time_seconds:
        return False
    sim = _cosine_similarity(current_embedding, previous_embedding)
    return sim > similarity_threshold
```

**Step 4: Run tests — PASS**

**Step 5: Integrate into bot.py handle_query**

В `bot.py`, после получения embedding текущего query (внутри `propagate_attributes` блока):

```python
# Implicit feedback: detect reformulation
from telegram_bot.implicit_feedback import is_reformulation

if prev_embedding and is_reformulation(
    current_embedding=query_embedding,
    previous_embedding=prev_embedding,
    time_delta_seconds=time_since_last_query,
):
    lf = get_client()
    if lf:
        lf.score_current_trace(
            name="implicit_retry",
            value=1,
            data_type="BOOLEAN",
        )
```

**Step 6: Commit**

```bash
git add telegram_bot/implicit_feedback.py telegram_bot/bot.py tests/unit/test_implicit_feedback.py
git commit -m "feat(feedback): add implicit retry detection via embedding similarity"
```

---

## Phase 3: Review Pipeline (10-14h)

### Task 3.1: Auto-Triage Script (Dislike → Annotation Queue)

**Files:**
- Create: `scripts/langfuse_triage.py`
- Test: `tests/unit/test_langfuse_triage.py`

**Step 1: Write failing test**

```python
# tests/unit/test_langfuse_triage.py
from unittest.mock import MagicMock, patch
from scripts.langfuse_triage import fetch_dislike_traces, add_to_annotation_queue


class TestFetchDislikeTraces:
    def test_fetches_scores_with_correct_filters(self):
        mock_lf = MagicMock()
        mock_lf.api.scores.list.return_value.data = []
        fetch_dislike_traces(mock_lf, hours=24)
        mock_lf.api.scores.list.assert_called_once()
        call_kwargs = mock_lf.api.scores.list.call_args[1]
        assert call_kwargs["name"] == "user_feedback"


class TestAddToAnnotationQueue:
    def test_adds_trace_to_queue(self):
        mock_lf = MagicMock()
        add_to_annotation_queue(mock_lf, trace_id="t1", queue_name="dislike-review")
        mock_lf.api.annotation_queues.add_item.assert_called_once()
```

**Step 2: Implement**

```python
"""Auto-triage: fetch dislike traces, add to Langfuse Annotation Queue.

Usage: uv run python -m scripts.langfuse_triage [--hours 24] [--queue dislike-review]
"""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta

from langfuse import Langfuse


def fetch_dislike_traces(lf: Langfuse, hours: int = 24) -> list[dict]:
    """Fetch traces with user_feedback=0 in the last N hours."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    scores = lf.api.scores.list(
        name="user_feedback",
        from_timestamp=since,
    )
    return [
        {"trace_id": s.trace_id, "value": s.value, "comment": s.comment}
        for s in scores.data
        if s.value == 0.0
    ]


def add_to_annotation_queue(
    lf: Langfuse, trace_id: str, queue_name: str = "dislike-review",
) -> None:
    """Add trace to annotation queue via API."""
    # Get queue ID by name
    queues = lf.api.annotation_queues.list()
    queue = next((q for q in queues.data if q.name == queue_name), None)
    if queue is None:
        print(f"Queue '{queue_name}' not found. Create it in Langfuse UI first.")
        return
    lf.api.annotation_queues.add_item(
        queue_id=queue.id,
        body={"trace_id": trace_id, "type": "TRACE"},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--queue", default="dislike-review")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lf = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )

    dislikes = fetch_dislike_traces(lf, hours=args.hours)
    print(f"Found {len(dislikes)} dislikes in last {args.hours}h")

    for d in dislikes:
        if args.dry_run:
            print(f"  [DRY-RUN] Would add {d['trace_id']}")
        else:
            add_to_annotation_queue(lf, d["trace_id"], args.queue)
            print(f"  ✓ Added {d['trace_id']}")

    lf.shutdown()


if __name__ == "__main__":
    main()
```

**Step 3: Run tests — PASS**

**Step 4: Commit**

```bash
git add scripts/langfuse_triage.py tests/unit/test_langfuse_triage.py
git commit -m "feat(langfuse): add auto-triage script for dislike → annotation queue"
```

---

### Task 3.2: Alert Script (Cron Hourly)

**Files:**
- Create: `scripts/langfuse_alert.py`
- Test: `tests/unit/test_langfuse_alert.py`

**Step 1: Write tests**

```python
class TestDislikeRateCalculation:
    def test_high_dislike_rate_triggers_alert(self):
        from scripts.langfuse_alert import calculate_dislike_rate
        scores = [
            {"name": "user_feedback", "value": 0.0},
            {"name": "user_feedback", "value": 0.0},
            {"name": "user_feedback", "value": 1.0},
            {"name": "user_feedback", "value": 1.0},
        ]
        rate = calculate_dislike_rate(scores)
        assert rate == 0.5  # 50% dislike

    def test_should_alert_above_threshold(self):
        from scripts.langfuse_alert import should_alert
        assert should_alert(dislike_rate=0.20, min_samples=5, total=20) is True
        assert should_alert(dislike_rate=0.05, min_samples=5, total=20) is False
        assert should_alert(dislike_rate=0.20, min_samples=5, total=3) is False  # too few
```

**Step 2: Implement**

Script fetches scores hourly, calculates dislike rate, sends Telegram alert if threshold exceeded.

**Step 3: Commit**

```bash
git add scripts/langfuse_alert.py tests/unit/test_langfuse_alert.py
git commit -m "feat(langfuse): add hourly alert script for dislike rate monitoring"
```

---

## Phase 4: Experiment Loop (10-14h)

### Task 4.1: Fix Dataset Export Bugs

**Files:**
- Modify: `scripts/export_traces_to_dataset.py:99-100, 206-223`
- Test: `tests/unit/test_dataset_export.py`

**Step 1: Fix field mapping**

```python
# Line 99-100: Change "retrieved_context" to "eval_docs"
context_parts = output.get("eval_docs", [])  # was: "retrieved_context"
```

**Step 2: Add deduplication**

```python
# Line 209-223: Add source_trace_id check
existing_trace_ids = {item.source_trace_id for item in existing_items}
for item in items:
    if item["trace_id"] in existing_trace_ids:
        continue  # skip duplicate
    langfuse.create_dataset_item(...)
```

**Step 3: Add idempotent dataset creation**

```python
# Line 206: Wrap in try/except
try:
    langfuse.create_dataset(name=dataset_name)
except Exception as e:
    if "already exists" not in str(e).lower():
        raise
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add scripts/export_traces_to_dataset.py tests/unit/test_dataset_export.py
git commit -m "fix(langfuse): fix dataset export field mapping, add dedup and idempotency"
```

---

### Task 4.2: Agent Trajectory Evaluation Dataset

**Files:**
- Create: `scripts/eval/agent_routing_eval.py`
- Create: `tests/eval/agent_routing_golden.yaml`

**Step 1: Create golden set**

```yaml
# tests/eval/agent_routing_golden.yaml
- query: "Квартиры на Подоле 2 комнаты"
  expected_tool: apartment_search
- query: "Что такое ипотека?"
  expected_tool: rag_search
- query: "Создай задачу в CRM"
  expected_tool: crm_create_task
- query: "Покажи лид #123"
  expected_tool: crm_get_deal
- query: "Привет, как дела?"
  expected_tool: direct  # no tool, direct answer
- query: "Какие ЖК есть в Киеве до 50000$?"
  expected_tool: apartment_search
- query: "Расскажи о программе рассрочки"
  expected_tool: rag_search
```

**Step 2: Create evaluation script**

Script that runs queries through agent, captures tool calls from trace, compares with expected.

**Step 3: Commit**

```bash
git add scripts/eval/agent_routing_eval.py tests/eval/agent_routing_golden.yaml
git commit -m "feat(eval): add agent trajectory evaluation for tool routing"
```

---

## Phase 5: Monitoring (6-8h)

### Task 5.1: Judge Calibration Script

**Files:**
- Create: `scripts/eval/calibrate_judge.py`

Скрипт сравнивает `user_feedback` scores с `judge_faithfulness` scores на тех же traces. Считает Cohen's Kappa для оценки agreement.

### Task 5.2: Morning Digest

Расширение `scripts/langfuse_alert.py` с `--digest` флагом: daily summary в Telegram admin chat.

---

## Phase 6: Automation (future)

### Task 6.1: Webhook Integration (когда Langfuse выпустит)

Watch: https://langfuse.com/docs/roadmap

### Task 6.2: Synthetic Dataset Generation

LLM-generated edge cases для расширения golden set.

---

## Run Order & Dependencies

```
Phase 1 (Foundation):
  1.1 Environment     → нет зависимостей
  1.2 Flush + Shutdown → нет зависимостей
  1.3 Score Configs    → нет зависимостей
  1.4 Cleanup          → нет зависимостей
  1.5 Prompt Version   → нет зависимостей
  ↓ (все параллельно, коммит каждый)

Phase 2 (Rich Feedback):
  2.1 Dislike Keyboard → зависит от Phase 1.4 (contract update)
  2.2 Bot Handler      → зависит от 2.1
  2.3 Implicit Retry   → независим от 2.1/2.2
  ↓

Phase 3 (Review Pipeline):
  3.1 Auto-Triage      → зависит от Phase 2 (новые scores)
  3.2 Alert Script     → независим
  ↓

Phase 4 (Experiment Loop):
  4.1 Fix Dataset      → независим
  4.2 Agent Eval       → независим
  ↓

Phase 5 (Monitoring):
  5.1 Judge Calibrate  → зависит от данных в Langfuse
  5.2 Morning Digest   → зависит от 3.2
```

## Verification Checklist

После каждой фазы:

```bash
# Lint + types
make check

# Unit tests
uv run pytest tests/unit/ -n auto

# Specific tests
uv run pytest tests/unit/test_feedback_handler.py -v
uv run pytest tests/unit/test_observability.py -v
uv run pytest tests/unit/test_implicit_feedback.py -v
```

## Total Effort

| Phase | Tasks | Effort |
|-------|-------|--------|
| 1: Foundation | 5 tasks | 6-8h |
| 2: Rich Feedback | 3 tasks | 8-12h |
| 3: Review Pipeline | 2 tasks | 10-14h |
| 4: Experiment Loop | 2 tasks | 10-14h |
| 5: Monitoring | 2 tasks | 6-8h |
| **Total** | **14 tasks** | **40-56h** |
