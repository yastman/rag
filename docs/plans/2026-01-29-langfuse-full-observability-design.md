# Langfuse Full Observability Implementation Plan

> Execute tasks sequentially; keep each task green (tests passing) before moving on.

**Goal:** Complete Langfuse observability with root trace, all spans connected, PII masking, and regression gate (cache calibration is optional follow-up).

**Architecture:** SDK-first approach with `@observe` decorators. Root trace on `handle_query()`, child spans auto-connect. LiteLLM OTEL as separate telemetry layer. Semantic cache calibration is a follow-up task (not required for observability correctness).

**Tech Stack:** Langfuse SDK v3 (`get_client()`, `@observe`), Redis Query Engine, Qdrant `/metrics`, pytest for TDD.

---

## Current State Summary

**Instrumented (11 spans):**
- VoyageService: 5 spans (`voyage-embed-*`, `voyage-rerank`)
- QdrantService: 2 spans (`qdrant-hybrid-search-rrf`, `qdrant-search-score-boosting`)
- CacheService: 4 spans (`cache-semantic-check`, `cache-semantic-store`, `cache-search-check`, `cache-rerank-check`)

**NOT instrumented (critical gaps):**
- Bot handlers: `handle_query()` — no root trace, spans disconnected
- LLMService: `generate_answer()`, `stream_answer()` — no LLM cost visibility
- QueryAnalyzer: `analyze()` — no filter extraction tracing
- QueryRouter: `classify_query()` — no classification tracing

---

## Task 0: Bootstrap Langfuse Client With Masking (CRITICAL)

**Why:** `get_client()` returns the first initialized Langfuse client. If the process creates a client without `mask=...` first, masking will not apply reliably.

**Files:**
- Modify: `telegram_bot/main.py`
- Create/Use: `telegram_bot/observability.py`

### Step 1: Minimal implementation

In `telegram_bot/main.py`, initialize Langfuse before creating the bot:

```python
from .observability import get_langfuse_client

# near the start of main()
_langfuse = get_langfuse_client()  # registers SDK singleton with mask=...
```

### Step 2: Manual check

- Start bot locally, send a message containing an email/phone.
- In Langfuse UI verify the trace input/output is masked.

---

## Task 1: Create PII Masking Module

**Files:**
- Create: `telegram_bot/observability.py`
- Test: `tests/unit/test_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/test_observability.py
"""Unit tests for PII masking and Langfuse client initialization."""

import importlib.util

import pytest


class TestMaskPii:
    """Tests for mask_pii function."""

    def test_mask_user_id_in_string(self):
        """Mask 9-10 digit user IDs in strings."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("User 123456789 sent a message")
        assert "123456789" not in result
        assert "[USER_ID]" in result

    def test_mask_phone_number(self):
        """Mask phone numbers in international format."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("Call me at +79161234567")
        assert "+79161234567" not in result
        assert "[PHONE]" in result

    def test_mask_email(self):
        """Mask email addresses."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("Contact test@example.com for info")
        assert "test@example.com" not in result
        assert "[EMAIL]" in result

    def test_truncate_long_text(self):
        """Truncate texts longer than 500 chars."""
        from telegram_bot.observability import mask_pii

        long_text = "x" * 1000
        result = mask_pii(long_text)
        assert len(result) <= 520  # 500 + "... [TRUNCATED]"
        assert "[TRUNCATED]" in result

    def test_mask_dict_recursively(self):
        """Mask PII in nested dicts."""
        from telegram_bot.observability import mask_pii

        data = {"user_id": "123456789", "nested": {"email": "test@example.com"}}
        result = mask_pii(data)
        assert result["user_id"] == "[USER_ID]"
        assert result["nested"]["email"] == "[EMAIL]"

    def test_mask_list_items(self):
        """Mask PII in list items."""
        from telegram_bot.observability import mask_pii

        data = ["User 123456789", "Call +79161234567"]
        result = mask_pii(data)
        assert "[USER_ID]" in result[0]
        assert "[PHONE]" in result[1]

    def test_preserve_non_pii_data(self):
        """Non-PII data should remain unchanged."""
        from telegram_bot.observability import mask_pii

        result = mask_pii("квартира 3 комнаты 50000 евро")
        assert result == "квартира 3 комнаты 50000 евро"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_observability.py -v`
Expected: ModuleNotFoundError: No module named 'telegram_bot.observability'

### Step 3: Write minimal implementation

```python
# telegram_bot/observability.py
"""Langfuse observability with PII masking.

2026 best practice: "Log everything, but with masking enabled first."
All inputs/outputs go through PII redaction before Langfuse.
"""

import re
from typing import Any

from langfuse import Langfuse


def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse.

    Applied to all inputs/outputs/metadata automatically.

    Masks:
    - Telegram user IDs (9-10 digits)
    - Phone numbers (10-15 digits with optional +)
    - Email addresses
    - Long texts (>500 chars truncated)
    """
    if isinstance(data, str):
        # Mask Telegram user IDs (9-10 digits not part of larger number)
        data = re.sub(r"\b\d{9,10}\b", "[USER_ID]", data)
        # Mask phone numbers
        data = re.sub(r"\+?\d{10,15}", "[PHONE]", data)
        # Mask emails
        data = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]", data)
        # Truncate long texts
        if len(data) > 500:
            data = data[:500] + "... [TRUNCATED]"
        return data
    elif isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [mask_pii(item) for item in data]
    return data


def get_langfuse_client() -> Langfuse:
    """Get Langfuse client with PII masking enabled.

    Returns:
        Langfuse client configured with:
        - mask_pii callback for all data
        - Batch size 50, flush interval 5s
    """
    return Langfuse(
        mask=mask_pii,
        flush_at=50,
        flush_interval=5,
    )
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/test_observability.py -v`
Expected: All 7 tests PASS

### Step 5: Commit

```bash
git add telegram_bot/observability.py tests/unit/test_observability.py
git commit -m "$(cat <<'EOF'
feat(observability): add PII masking module for Langfuse

- mask_pii() masks user IDs, phone numbers, emails
- Truncates long texts to 500 chars
- get_langfuse_client() returns pre-configured client

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Root Trace to Bot Handler

**Files:**
- Modify: `telegram_bot/bot.py:167-175`
- Test: `tests/unit/test_bot_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/test_bot_observability.py
"""Unit tests for bot handler observability."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHandleQueryObservability:
    """Tests for handle_query Langfuse instrumentation."""

    @pytest.fixture
    def mock_message(self):
        """Create mock Telegram message."""
        message = MagicMock()
        message.text = "квартиры до 100000 евро"
        message.from_user.id = 123456789
        message.chat.id = 987654321
        message.message_id = 42
        message.answer = AsyncMock()
        message.bot.send_chat_action = AsyncMock()
        return message

    @pytest.fixture
    def bot_handler(self):
        """Create PropertyBot handler with mocked services."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig
        from telegram_bot.services import QueryType

        # Avoid running PropertyBot.__init__ in unit tests (aiogram + real services)
        handler = PropertyBot.__new__(PropertyBot)

        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,  # keep handle_query on the simplest path
        )
        handler._cache_initialized = True

        # Mock services used by handle_query
        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        # Router decision is external; make it deterministic
        handler._test_query_type = QueryType.COMPLEX

        return handler

    @pytest.mark.asyncio
    async def test_handle_query_updates_trace(self, bot_handler, mock_message):
        """handle_query should call langfuse.update_current_trace."""
        with patch("telegram_bot.bot.get_client") as mock_get_client, patch(
            "telegram_bot.bot.classify_query", autospec=True
        ) as mock_classify_query:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            mock_langfuse.update_current_trace.assert_called_once()
            call_kwargs = mock_langfuse.update_current_trace.call_args.kwargs
            assert call_kwargs["user_id"] == "123456789"
            assert call_kwargs["session_id"] == "chat:987654321"
            assert "telegram" in call_kwargs["tags"]

    @pytest.mark.asyncio
    async def test_handle_query_includes_context_fingerprint(self, bot_handler, mock_message):
        """handle_query should include context_fingerprint in metadata."""
        with patch("telegram_bot.bot.get_client") as mock_get_client, patch(
            "telegram_bot.bot.classify_query", autospec=True
        ) as mock_classify_query:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            call_kwargs = mock_langfuse.update_current_trace.call_args.kwargs
            metadata = call_kwargs["metadata"]
            assert "tenant" in metadata
            assert "cache_schema" in metadata
            assert "retrieval_version" in metadata
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_bot_observability.py -v`
Expected: FAIL — `get_client` not imported or called in bot.py

### Step 3: Write minimal implementation

Add imports and decorator to `telegram_bot/bot.py`:

```python
# At top of file, add:
from langfuse import get_client, observe

from .services.cache import CACHE_SCHEMA_VERSION

# At line ~167, add decorator and trace update:
@observe(name="telegram-message")
async def handle_query(self, message: Message):
    """Handle user query with multi-level caching RAG pipeline."""
    query = message.text or ""
    user_id = message.from_user.id
    logger.info(f"Query from {user_id}: {query}")

    # Context fingerprint for cache isolation + trace filtering
    request_id = f"tg:{message.chat.id}:{message.message_id}"
    context_fingerprint = {
        "tenant": "default",
        "lang": "ru",
        "prompt_version": "v2.1",
        "retrieval_version": f"{self.config.voyage_model_queries}-bm42-rrf",
        "rerank_version": self.config.voyage_model_rerank,
        "model_id": self.config.llm_model,
        "cache_schema": CACHE_SCHEMA_VERSION,
        "request_id": request_id,
    }

    # Update trace with user context
    langfuse = get_client()
    langfuse.update_current_trace(
        name="telegram-rag-query",
        user_id=str(user_id),
        session_id=f"chat:{message.chat.id}",
        input={"query": query[:200]},
        metadata=context_fingerprint,
        tags=["telegram", "rag", context_fingerprint["retrieval_version"]],
    )

    # ... rest of the function unchanged ...
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/test_bot_observability.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/bot.py tests/unit/test_bot_observability.py
git commit -m "$(cat <<'EOF'
feat(bot): add root trace with @observe decorator

- Root trace on handle_query() connects all child spans
- Context fingerprint for cache isolation (tenant, lang, versions)
- Session tracking via chat_id

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Instrument LLMService

**Files:**
- Modify: `telegram_bot/services/llm.py:1-5, 38-60`
- Test: `tests/unit/services/test_llm_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/services/test_llm_observability.py
"""Unit tests for LLMService Langfuse instrumentation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLLMServiceObservability:
    """Tests for LLMService @observe decorators."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked HTTP client."""
        from telegram_bot.services.llm import LLMService

        service = LLMService(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )
        service.client = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_generate_answer_updates_generation(self, llm_service):
        """generate_answer should call update_current_generation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test answer"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        llm_service.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.llm.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            result = await llm_service.generate_answer(
                question="Test question",
                context_chunks=[{"text": "Context"}],
            )

            # Should be called twice: once at start, once with usage
            assert mock_langfuse.update_current_generation.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_answer_tracks_model(self, llm_service):
        """generate_answer should track model name."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Answer"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        llm_service.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.llm.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await llm_service.generate_answer("Test", [{"text": "Context"}])

            first_call = mock_langfuse.update_current_generation.call_args_list[0]
            assert first_call.kwargs["model"] == "gpt-4o-mini"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/services/test_llm_observability.py -v`
Expected: FAIL — `get_client` not imported in llm.py

### Step 3: Write minimal implementation

Modify `telegram_bot/services/llm.py`:

```python
# At top of file, add:
from langfuse import get_client, observe

# Add decorator and instrumentation to generate_answer:
@observe(name="llm-generate-answer", as_type="generation")
async def generate_answer(
    self,
    question: str,
    context_chunks: list[dict[str, Any]],
    system_prompt: str | None = None,
) -> str:
    """Generate answer with Langfuse tracing."""
    langfuse = get_client()

    # Track generation start
    langfuse.update_current_generation(
        input={"question_preview": question[:100], "context_count": len(context_chunks)},
        model=self.model,
    )

    try:
        # ... existing code to build context and messages ...
        context = self._format_context(context_chunks)
        # ... build messages list ...

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages},
        )

        if response.status_code != 200:
            return self._fallback_response(context_chunks)

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        # Track completion with usage
        langfuse.update_current_generation(
            output={"answer_length": len(answer)},
            usage_details={
                "input": data.get("usage", {}).get("prompt_tokens", 0),
                "output": data.get("usage", {}).get("completion_tokens", 0),
            },
        )

        return answer
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return self._fallback_response(context_chunks)
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/services/test_llm_observability.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/llm.py tests/unit/services/test_llm_observability.py
git commit -m "$(cat <<'EOF'
feat(llm): add @observe instrumentation to generate_answer

- Track model, input/output tokens, answer length
- as_type="generation" for LLM visibility in Langfuse

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Instrument QueryRouter

**Files:**
- Modify: `telegram_bot/services/query_router.py:7-8, 70-85`
- Test: `tests/unit/services/test_query_router_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/services/test_query_router_observability.py
"""Unit tests for QueryRouter Langfuse instrumentation."""

from unittest.mock import MagicMock, patch

import pytest


class TestQueryRouterObservability:
    """Tests for classify_query @observe decorator."""

    def test_classify_query_updates_span(self):
        """classify_query should call update_current_span."""
        with patch("telegram_bot.services.query_router.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            from telegram_bot.services.query_router import QueryType, classify_query

            result = classify_query("Привет!")

            assert result == QueryType.CHITCHAT
            mock_langfuse.update_current_span.assert_called_once()
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["type"] == "chitchat"

    def test_classify_complex_query(self):
        """Complex queries should be tracked with type."""
        with patch("telegram_bot.services.query_router.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            from telegram_bot.services.query_router import QueryType, classify_query

            result = classify_query("квартиры до 100000 евро с двумя спальнями")

            assert result == QueryType.COMPLEX
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["type"] == "complex"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/services/test_query_router_observability.py -v`
Expected: FAIL — `get_client` not called in query_router.py

### Step 3: Write minimal implementation

Modify `telegram_bot/services/query_router.py`:

```python
# At top, add imports:
from langfuse import get_client, observe

# Add decorator to classify_query function:
@observe(name="query-router")
def classify_query(query: str) -> QueryType:
    """Classify query type for routing decisions.

    Returns:
        QueryType.CHITCHAT: Skip RAG entirely
        QueryType.SIMPLE: Light RAG, skip rerank
        QueryType.COMPLEX: Full RAG + rerank
    """
    query_lower = query.lower().strip()

    # Check chit-chat patterns
    for pattern in CHITCHAT_PATTERNS:
        if re.match(pattern, query_lower, re.IGNORECASE):
            result = QueryType.CHITCHAT
            break
    else:
        # Check complexity markers
        if _has_complexity_markers(query):
            result = QueryType.COMPLEX
        else:
            result = QueryType.SIMPLE

    # Track classification
    langfuse = get_client()
    langfuse.update_current_span(
        input={"query_preview": query[:50]},
        output={"type": result.value},
    )

    return result
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/services/test_query_router_observability.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/query_router.py tests/unit/services/test_query_router_observability.py
git commit -m "$(cat <<'EOF'
feat(query_router): add @observe instrumentation

- Track query classification decisions (CHITCHAT/SIMPLE/COMPLEX)
- Input preview + output type logged to Langfuse

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Instrument QueryAnalyzer

**Files:**
- Modify: `telegram_bot/services/query_analyzer.py:4-5, 29-45`
- Test: `tests/unit/services/test_query_analyzer_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/services/test_query_analyzer_observability.py
"""Unit tests for QueryAnalyzer Langfuse instrumentation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQueryAnalyzerObservability:
    """Tests for QueryAnalyzer.analyze @observe decorator."""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer with mocked HTTP client."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer(
            api_key="test-key",
            base_url="http://localhost:4000",
            model="gpt-4o-mini",
        )
        analyzer.client = MagicMock()
        return analyzer

    @pytest.mark.asyncio
    async def test_analyze_updates_generation(self, analyzer):
        """analyze should call update_current_generation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"filters": {"price": {"lt": 100000}}, "semantic_query": "квартиры"}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        }
        analyzer.client.post = AsyncMock(return_value=mock_response)

        with patch("telegram_bot.services.query_analyzer.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            result = await analyzer.analyze("квартиры до 100000")

            assert mock_langfuse.update_current_generation.call_count == 2
            second_call = mock_langfuse.update_current_generation.call_args_list[1]
            assert "filters" in second_call.kwargs["output"]
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/services/test_query_analyzer_observability.py -v`
Expected: FAIL — `get_client` not called in query_analyzer.py

### Step 3: Write minimal implementation

Modify `telegram_bot/services/query_analyzer.py`:

```python
# At top, add imports:
from langfuse import get_client, observe

# Add decorator to analyze method:
@observe(name="query-analyzer", as_type="generation")
async def analyze(self, query: str) -> dict[str, Any]:
    """Analyze query with Langfuse tracing."""
    langfuse = get_client()

    # Track at start
    langfuse.update_current_generation(
        input={"query_preview": query[:100]},
        model=self.model,
    )

    # ... existing LLM call logic ...

    try:
        response = await self.client.post(...)
        data = response.json()
        result_str = data["choices"][0]["message"]["content"]
        result = json.loads(result_str)

        # Track completion
        langfuse.update_current_generation(
            output={
                "filters": result.get("filters", {}),
                "has_semantic": bool(result.get("semantic_query")),
            },
            usage_details={
                "input": data.get("usage", {}).get("prompt_tokens", 0),
                "output": data.get("usage", {}).get("completion_tokens", 0),
            },
        )

        return result
    except Exception as e:
        logger.error(f"QueryAnalyzer error: {e}")
        return {"filters": {}, "semantic_query": query}
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/services/test_query_analyzer_observability.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/query_analyzer.py tests/unit/services/test_query_analyzer_observability.py
git commit -m "$(cat <<'EOF'
feat(query_analyzer): add @observe instrumentation

- as_type="generation" for LLM visibility
- Track extracted filters and semantic query presence

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Enhance CacheService Spans with Layer Metadata

**Files:**
- Modify: `telegram_bot/services/cache.py:259-330, 564-600, 636-680`
- Test: `tests/unit/services/test_cache_observability.py`

### Step 1: Write the failing test

```python
# tests/unit/services/test_cache_observability.py
"""Unit tests for CacheService enhanced Langfuse spans."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCacheServiceSpanMetadata:
    """Tests for CacheService span layer attributes."""

    @pytest.fixture
    def cache_service(self):
        """Create CacheService with mocked dependencies."""
        from telegram_bot.services.cache import CacheService

        service = CacheService.__new__(CacheService)
        service.redis_client = MagicMock()
        service.semantic_cache = MagicMock()
        service._initialized = True
        return service

    @pytest.mark.asyncio
    async def test_check_semantic_cache_includes_layer(self, cache_service):
        """check_semantic_cache should include layer=semantic in span."""
        cache_service.semantic_cache.acheck = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.check_semantic_cache("test query")

            mock_langfuse.update_current_span.assert_called_once()
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "semantic"
            assert call_kwargs["output"]["hit"] is False

    @pytest.mark.asyncio
    async def test_check_semantic_cache_hit_includes_distance(self, cache_service):
        """Semantic cache hit should include distance in span."""
        cache_service.semantic_cache.acheck = AsyncMock(
            return_value=[{"response": "cached", "vector_distance": 0.05}]
        )

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            result = await cache_service.check_semantic_cache("test query")

            assert result == "cached"
            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["hit"] is True
            assert call_kwargs["output"]["distance"] == 0.05

    @pytest.mark.asyncio
    async def test_get_cached_search_includes_layer(self, cache_service):
        """get_cached_search should include layer=retrieval in span."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.get_cached_search([0.1] * 1024, None)

            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "retrieval"

    @pytest.mark.asyncio
    async def test_get_cached_rerank_includes_layer(self, cache_service):
        """get_cached_rerank should include layer=rerank in span."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        with patch("telegram_bot.services.cache.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            await cache_service.get_cached_rerank([0.1] * 1024, ["doc1"], "test")

            call_kwargs = mock_langfuse.update_current_span.call_args.kwargs
            assert call_kwargs["output"]["layer"] == "rerank"
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/services/test_cache_observability.py -v`
Expected: FAIL — `update_current_span` not called with layer metadata

### Step 3: Write minimal implementation

Modify `telegram_bot/services/cache.py`:

```python
# At top, update imports:
from langfuse import get_client, observe

# Enhance check_semantic_cache (line ~259):
@observe(name="cache-semantic-check")
async def check_semantic_cache(
    self,
    query: str,
    user_id: Optional[int] = None,
    language: str = "ru",
) -> Optional[str]:
    """Check semantic cache with Langfuse tracing."""
    langfuse = get_client()

    if not self.semantic_cache:
        langfuse.update_current_span(
            output={"hit": False, "layer": "semantic", "reason": "not_initialized"}
        )
        return None

    try:
        results = await self.semantic_cache.acheck(
            prompt=query,
            num_results=1,
            distance_threshold=self.semantic_threshold,
        )

        if results:
            distance = results[0].get("vector_distance", 0)
            langfuse.update_current_span(
                output={
                    "hit": True,
                    "layer": "semantic",
                    "distance": distance,
                    "threshold": self.semantic_threshold,
                }
            )
            return results[0].get("response")

        langfuse.update_current_span(
            output={"hit": False, "layer": "semantic", "reason": "no_match"}
        )
        return None
    except Exception as e:
        logger.error(f"Semantic cache error: {e}")
        langfuse.update_current_span(
            output={"hit": False, "layer": "semantic", "error": str(e)}
        )
        return None

# Similar enhancements for get_cached_search and get_cached_rerank
# with layer="retrieval" and layer="rerank" respectively
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/services/test_cache_observability.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/services/cache.py tests/unit/services/test_cache_observability.py
git commit -m "$(cat <<'EOF'
feat(cache): enhance spans with layer metadata

- All cache spans include layer (semantic/retrieval/rerank)
- Semantic cache tracks distance and threshold
- Better debugging via Langfuse UI filters

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add Scores to Bot Handler

**Files:**
- Modify: `telegram_bot/bot.py:~350` (end of handle_query)
- Test: `tests/unit/test_bot_scores.py`

### Step 1: Write the failing test

```python
# tests/unit/test_bot_scores.py
"""Unit tests for bot handler Langfuse scores."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHandleQueryScores:
    """Tests for handle_query Langfuse scores."""

    @pytest.fixture
    def mock_message(self):
        """Create mock Telegram message."""
        message = MagicMock()
        message.text = "квартиры до 100000 евро"
        message.from_user.id = 123456789
        message.chat.id = 987654321
        message.message_id = 42
        message.answer = AsyncMock()
        message.bot.send_chat_action = AsyncMock()
        return message

    @pytest.fixture
    def bot_handler(self):
        """Create PropertyBot handler with mocked services."""
        from telegram_bot.bot import PropertyBot
        from telegram_bot.config import BotConfig
        from telegram_bot.services import QueryType

        handler = PropertyBot.__new__(PropertyBot)
        handler.config = BotConfig(
            telegram_token="test",
            voyage_api_key="test",
            llm_api_key="test",
            llm_model="test-model",
            cesc_enabled=False,
        )
        handler._cache_initialized = True

        handler.cache_service = MagicMock()
        handler.cache_service.initialize = AsyncMock()
        handler.cache_service.get_cached_embedding = AsyncMock(return_value=[0.1] * 1024)
        handler.cache_service.check_semantic_cache = AsyncMock(return_value="Cached answer")
        handler.cache_service.log_metrics = MagicMock()

        handler._test_query_type = QueryType.COMPLEX
        return handler

    @pytest.mark.asyncio
    async def test_scores_cache_hit(self, bot_handler, mock_message):
        """Should score semantic_cache_hit=1.0 on cache hit."""
        with patch("telegram_bot.bot.get_client") as mock_get_client, patch(
            "telegram_bot.bot.classify_query", autospec=True
        ) as mock_classify_query:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            # Find the semantic_cache_hit score call
            score_calls = [
                c for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs.get("name") == "semantic_cache_hit"
            ]
            assert len(score_calls) == 1
            assert score_calls[0].kwargs["value"] == 1.0

    @pytest.mark.asyncio
    async def test_scores_query_type(self, bot_handler, mock_message):
        """Should score query_type based on classification."""
        with patch("telegram_bot.bot.get_client") as mock_get_client, patch(
            "telegram_bot.bot.classify_query", autospec=True
        ) as mock_classify_query:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse
            mock_classify_query.return_value = bot_handler._test_query_type

            await bot_handler.handle_query(mock_message)

            # Find the query_type score call
            score_calls = [
                c for c in mock_langfuse.score_current_trace.call_args_list
                if c.kwargs.get("name") == "query_type"
            ]
            assert len(score_calls) == 1
            # COMPLEX = 2.0
            assert score_calls[0].kwargs["value"] == 2.0
```

### Step 2: Run test to verify it fails

Run: `pytest tests/unit/test_bot_scores.py -v`
Expected: FAIL — `score_current_trace` not called

### Step 3: Write minimal implementation

Add scores at end of `handle_query` in `telegram_bot/bot.py`:

```python
# At end of handle_query, before final return:

# Log scores to Langfuse
langfuse = get_client()

# Cache effectiveness
langfuse.score_current_trace(
    name="semantic_cache_hit",
    value=1.0 if cached_answer else 0.0,
)

# Query complexity
query_type_map = {"chitchat": 0, "simple": 1, "complex": 2}
langfuse.score_current_trace(
    name="query_type",
    value=float(query_type_map.get(query_type.value, 1)),
)

# Results count (0 if cache hit)
langfuse.score_current_trace(
    name="results_count",
    value=float(len(results)) if not cached_answer and results else 0.0,
)
```

### Step 4: Run test to verify it passes

Run: `pytest tests/unit/test_bot_scores.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "$(cat <<'EOF'
feat(bot): add Langfuse scores for cache and query metrics

- semantic_cache_hit: 1.0/0.0 for cache effectiveness
- query_type: 0/1/2 for chitchat/simple/complex
- results_count: retrieval quality tracking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add Infrastructure Metrics Collector

**Files:**
- Modify: `tests/baseline/collector.py`
- Test: `tests/baseline/test_collector_infra.py`

### Step 1: Write the failing test

```python
# tests/baseline/test_collector_infra.py
"""Unit tests for infrastructure metrics collection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInfrastructureMetrics:
    """Tests for collect_infrastructure_metrics."""

    @pytest.fixture
    def collector(self):
        """Create LangfuseMetricsCollector with mocked deps."""
        from tests.baseline.collector import LangfuseMetricsCollector

        collector = LangfuseMetricsCollector(
            langfuse_client=MagicMock(),
            redis_url="redis://localhost:6379",
            qdrant_url="http://localhost:6333",
        )
        return collector

    @pytest.mark.asyncio
    async def test_collects_redis_stats(self, collector):
        """Should collect Redis INFO stats."""
        mock_info = {
            "keyspace_hits": 1000,
            "keyspace_misses": 200,
            "evicted_keys": 5,
            "used_memory_human": "10M",
        }
        collector.redis = MagicMock()
        collector.redis.info = AsyncMock(return_value=mock_info)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_client.return_value.__aexit__ = AsyncMock()

            metrics = await collector.collect_infrastructure_metrics()

        assert metrics["redis"]["keyspace_hits"] == 1000
        assert metrics["redis"]["hit_rate"] == 83.33  # 1000/(1000+200)*100

    @pytest.mark.asyncio
    async def test_collects_qdrant_metrics(self, collector):
        """Should fetch Qdrant /metrics endpoint."""
        collector.redis = MagicMock()
        collector.redis.info = AsyncMock(return_value={})

        mock_response = MagicMock()
        mock_response.text = "qdrant_points_total 1000\nqdrant_search_seconds_sum 5.0"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock()

            metrics = await collector.collect_infrastructure_metrics()

        assert "qdrant_raw" in metrics or "qdrant" in metrics
```

### Step 2: Run test to verify it fails

Run: `pytest tests/baseline/test_collector_infra.py -v`
Expected: FAIL — `collect_infrastructure_metrics` method not found

### Step 3: Write minimal implementation

Add to `tests/baseline/collector.py`:

```python
async def collect_infrastructure_metrics(self) -> dict:
    """Collect Redis INFO + Qdrant /metrics for baseline.

    Returns:
        Dict with redis and qdrant metrics.
    """
    import httpx

    metrics = {"timestamp": datetime.utcnow().isoformat()}

    # Redis INFO stats
    if self.redis:
        try:
            info = await self.redis.info("stats")
            memory = await self.redis.info("memory")

            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses

            metrics["redis"] = {
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "hit_rate": round(hits / total * 100, 2) if total > 0 else 0,
                "evicted_keys": info.get("evicted_keys", 0),
                "used_memory_human": memory.get("used_memory_human"),
            }
        except Exception as e:
            metrics["redis"] = {"error": str(e)}

    # Qdrant /metrics
    if self.qdrant_url:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.qdrant_url}/metrics", timeout=5)
                metrics["qdrant_raw"] = resp.text[:2000]
            except Exception as e:
                metrics["qdrant_error"] = str(e)

    return metrics
```

### Step 4: Run test to verify it passes

Run: `pytest tests/baseline/test_collector_infra.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add tests/baseline/collector.py tests/baseline/test_collector_infra.py
git commit -m "$(cat <<'EOF'
feat(baseline): add infrastructure metrics collection

- Redis INFO: hit_rate, evicted_keys, memory
- Qdrant /metrics endpoint (Prometheus format)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: E2E Trace Validation (Use Existing Telethon Runner)

**Best practice (per `CLAUDE.md`):** Keep “real Telegram E2E” in `scripts/e2e/` (Telethon userbot). Do not make Telegram a hard dependency for pytest CI runs.

**Files:**
- Create: `scripts/e2e/langfuse_trace_validator.py`
- Modify: `scripts/e2e/runner.py`
- (Optional) Modify: `scripts/e2e/config.py` (flag)
- (Optional) Modify: `Makefile` (target)

### Step 1: Add a small Langfuse validator module

```python
# scripts/e2e/langfuse_trace_validator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from langfuse import Langfuse


EXPECTED_SPANS = {
    "telegram-message",
    "query-router",
    "cache-semantic-check",
    "voyage-embed-query",
    "qdrant-hybrid-search-rrf",
}

EXPECTED_SCORES = {
    "semantic_cache_hit",
    "query_type",
}


@dataclass(frozen=True)
class TraceValidationResult:
    ok: bool
    trace_id: str | None
    missing_spans: set[str]
    missing_scores: set[str]


def validate_latest_trace(*, started_at: datetime) -> TraceValidationResult:
    langfuse = Langfuse()
    traces_page = langfuse.api.trace.list(
        tags=["telegram", "rag"],
        from_timestamp=started_at - timedelta(seconds=5),
        order_by="timestamp.desc",
        limit=5,
    )
    if not traces_page.data:
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(EXPECTED_SPANS),
            missing_scores=set(EXPECTED_SCORES),
        )

    trace_id = traces_page.data[0].id
    trace = langfuse.api.trace.get(trace_id)

    span_names = {obs.name for obs in trace.observations}
    score_names = {s.name for s in trace.scores}

    missing_spans = set(EXPECTED_SPANS - span_names)
    missing_scores = set(EXPECTED_SCORES - score_names)

    return TraceValidationResult(
        ok=(not missing_spans and not missing_scores),
        trace_id=trace_id,
        missing_spans=missing_spans,
        missing_scores=missing_scores,
    )
```

### Step 2: Wire into `scripts/e2e/runner.py`

In `run_single_test(...)`:
- Record `started_at = datetime.utcnow()` right before `send_and_wait(...)`.
- After the bot reply is received, if `E2E_VALIDATE_LANGFUSE=1` (or config flag) then call `validate_latest_trace(started_at=started_at)`.
- If validation fails, mark the scenario as failed (or add a dedicated field like `observability_ok=false`).

### Step 3: Run

- Normal E2E: `make e2e-test`
- With trace validation: `E2E_VALIDATE_LANGFUSE=1 make e2e-test`

---

## Task 10: Add Makefile Targets

**Files:**
- Modify: `Makefile`

### Step 1: Use existing Makefile targets

This repository already provides (see `CLAUDE.md`):
- `make e2e-test` (Telethon runner)
- `make baseline-smoke`, `make baseline-load`
- `make baseline-compare`, `make baseline-set`, `make baseline-report`, `make baseline-check`

Add a small convenience target (optional):

```makefile
e2e-test-traces: ## Run E2E tests + validate Langfuse traces
	E2E_VALIDATE_LANGFUSE=1 python scripts/e2e/runner.py
```

---

## Definition of Done

| Criterion | Verification Command |
|-----------|---------------------|
| Unit tests pass | `pytest tests/unit/ -v` |
| PII masking works | `pytest tests/unit/test_observability.py -v` |
| Root trace created | Send message → trace in Langfuse UI |
| All spans connected | Langfuse UI → Trace → single tree |
| Scores recorded | Langfuse UI → Trace → Scores tab |
| E2E tests pass | `make e2e-test` |
| E2E traces validated | `E2E_VALIDATE_LANGFUSE=1 make e2e-test` |
| Baseline targets work | `make baseline-smoke` and `make baseline-compare ...` |

---

## References

- [Langfuse Python SDK v3](https://langfuse.com/docs/observability/sdk/python/instrumentation)
- [Langfuse @observe Decorator](https://langfuse.com/docs/observability/sdk/python/instrumentation#custom-instrumentation)
- [Langfuse Masking](https://langfuse.com/docs/observability/features/masking)
- [LiteLLM Langfuse OTEL Integration](https://docs.litellm.ai/docs/observability/langfuse_otel_integration)
