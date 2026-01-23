# Redis Cache Bugfix & Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 bugs in Telegram bot cache layer and add SemanticMessageHistory for conversation context.

**Architecture:** Fix EmbeddingsCache API mismatch (text→content), add missing LLMService.generate() for CESC, fix Telegram streaming duplicate edit error. Then migrate from manual LIST-based history to RedisVL SemanticMessageHistory for semantic conversation search.

**Tech Stack:** RedisVL 0.4+, aiogram 3.x, httpx, voyage-3-lite vectorizer

---

## Task 1: Fix EmbeddingsCache API

**Files:**

- Modify: `telegram_bot/services/cache.py:293-296, 330-335`
- Test: `tests/test_embeddings_cache.py` (create)

**Step 1: Write the failing test**

Create `tests/test_embeddings_cache.py`:

```python
"""Test EmbeddingsCache with correct RedisVL API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_embeddings_cache():
    """Mock EmbeddingsCache."""
    cache = MagicMock()
    cache.aget = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})
    cache.aset = AsyncMock(return_value="key:123")
    return cache


@pytest.mark.asyncio
async def test_get_cached_embedding_uses_content_param(mock_embeddings_cache):
    """EmbeddingsCache.aget should use 'content' not 'text' parameter."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    service.embeddings_cache = mock_embeddings_cache

    result = await service.get_cached_embedding("test query", "voyage-3-large")

    # Verify aget was called with 'content' parameter
    mock_embeddings_cache.aget.assert_called_once_with(
        content="test query",
        model_name="voyage-3-large",
    )
    assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_store_embedding_uses_content_param(mock_embeddings_cache):
    """EmbeddingsCache.aset should use 'content' not 'text' parameter."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    service.embeddings_cache = mock_embeddings_cache

    await service.store_embedding(
        text="test query",
        embedding=[0.1, 0.2, 0.3],
        model_name="voyage-3-large",
        metadata={"source": "test"},
    )

    # Verify aset was called with 'content' parameter
    mock_embeddings_cache.aset.assert_called_once_with(
        content="test query",
        model_name="voyage-3-large",
        embedding=[0.1, 0.2, 0.3],
        metadata={"source": "test"},
    )
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_embeddings_cache.py -v
```

Expected: FAIL with `AssertionError` because code still uses `text=` parameter.

**Step 3: Fix get_cached_embedding (line 293-296)**

In `telegram_bot/services/cache.py`, change:

```python
# Line 293-296: Change text= to content=
result = await self.embeddings_cache.aget(
    content=text,  # Was: text=text
    model_name=model_name,
)
```

**Step 4: Fix store_embedding (line 330-335)**

In `telegram_bot/services/cache.py`, change:

```python
# Line 330-335: Change text= to content=
await self.embeddings_cache.aset(
    content=text,  # Was: text=text
    model_name=model_name,
    embedding=embedding,
    metadata=metadata or {},
)
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/test_embeddings_cache.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_embeddings_cache.py telegram_bot/services/cache.py
git commit -m "fix(cache): use 'content' param for EmbeddingsCache API"
```

---

## Task 2: Add LLMService.generate() Method

**Files:**

- Modify: `telegram_bot/services/llm.py` (add method after line 277)
- Test: `tests/test_llm_generate.py` (create)

**Step 1: Write the failing test**

Create `tests/test_llm_generate.py`:

```python
"""Test LLMService.generate() method for CESC."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


@pytest.mark.asyncio
async def test_llm_service_has_generate_method():
    """LLMService should have generate() method."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")
    assert hasattr(service, "generate"), "LLMService missing generate() method"
    await service.close()


@pytest.mark.asyncio
async def test_generate_returns_text():
    """generate() should return text from LLM."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"cities": ["София"]}'}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await service.generate("Extract cities from: квартира в Софии")

        assert result == '{"cities": ["София"]}'
        mock_post.assert_called_once()

    await service.close()


@pytest.mark.asyncio
async def test_generate_uses_low_temperature():
    """generate() should use low temperature for structured output."""
    from telegram_bot.services.llm import LLMService

    service = LLMService(api_key="test-key", base_url="https://api.test.com")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "test"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await service.generate("test prompt", max_tokens=100)

        # Check temperature is low (0.3) for structured output
        call_args = mock_post.call_args
        assert call_args[1]["json"]["temperature"] == 0.3

    await service.close()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_llm_generate.py -v
```

Expected: FAIL with `AttributeError: 'LLMService' object has no attribute 'generate'`

**Step 3: Add generate() method to LLMService**

In `telegram_bot/services/llm.py`, add after line 277 (before `close` method):

```python
    async def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """Simple text generation for internal use (CESC, preference extraction).

        Uses low temperature for more deterministic/structured output.

        Args:
            prompt: Text prompt to send to LLM
            max_tokens: Maximum tokens in response (default: 200)

        Returns:
            Generated text from LLM

        Raises:
            Exception: If LLM API call fails
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,  # Low for structured output
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM generate failed: {e}")
            raise

```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_llm_generate.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_llm_generate.py telegram_bot/services/llm.py
git commit -m "feat(llm): add generate() method for CESC preference extraction"
```

---

## Task 3: Fix Streaming Duplicate Edit Error

**Files:**

- Modify: `telegram_bot/bot.py:253-262`
- Test: Manual verification (Telegram API specific)

**Step 1: Understand the problem**

Current code at line 257-262:

```python
if chunk_count % 10 == 0 or chunk in ".!?\n":
    with contextlib.suppress(Exception):
        await temp_message.edit_text(accumulated_text)

# Final update with complete answer
await temp_message.edit_text(accumulated_text)
```

Problem: If `accumulated_text` hasn't changed, Telegram returns error.

**Step 2: Add tracking variable**

In `telegram_bot/bot.py`, modify the streaming section (lines 245-262):

```python
        # 6. Generate answer with LLM STREAMING
        temp_message = await message.answer("🔍 Генерирую ответ...")
        accumulated_text = ""
        last_sent_text = ""  # Track what we last sent
        chunk_count = 0

        try:
            async for chunk in self.llm_service.stream_answer(
                question=query,
                context_chunks=results,
            ):
                accumulated_text += chunk
                chunk_count += 1

                # Update message every 10 chunks or when punctuation appears
                # Only if text actually changed
                if (chunk_count % 10 == 0 or chunk in ".!?\n") and accumulated_text != last_sent_text:
                    with contextlib.suppress(Exception):
                        await temp_message.edit_text(accumulated_text)
                        last_sent_text = accumulated_text

            # Final update with complete answer (only if different)
            if accumulated_text != last_sent_text:
                await temp_message.edit_text(accumulated_text)
            answer = accumulated_text
```

**Step 3: Verify manually**

```bash
# Rebuild and restart bot
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot

# Check logs for streaming errors
docker logs dev-bot --tail 50 | grep -i "message is not modified"
```

Expected: No more "message is not modified" errors.

**Step 4: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "fix(bot): prevent duplicate edit errors in streaming"
```

---

## Task 4: Add SemanticMessageHistory for Conversation

**Files:**

- Modify: `telegram_bot/services/cache.py` (add import, init, methods)
- Test: `tests/test_semantic_history.py` (create)

**Step 1: Write the failing test**

Create `tests/test_semantic_history.py`:

```python
"""Test SemanticMessageHistory integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_cache_service_has_message_history():
    """CacheService should have message_history attribute."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")
    assert hasattr(service, "message_history"), "Missing message_history attribute"


@pytest.mark.asyncio
async def test_get_relevant_history():
    """get_relevant_history should return semantically relevant messages."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")

    mock_history = MagicMock()
    mock_history.aget_relevant = AsyncMock(return_value=[
        {"role": "user", "content": "квартира в Софии"},
        {"role": "assistant", "content": "Найдено 5 квартир в Софии"},
    ])
    service.message_history = mock_history

    result = await service.get_relevant_history(user_id=123, query="апартаменты София", top_k=3)

    mock_history.aget_relevant.assert_called_once()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_add_semantic_message():
    """add_semantic_message should store message with embedding."""
    from telegram_bot.services.cache import CacheService

    service = CacheService(redis_url="redis://localhost:6379")

    mock_history = MagicMock()
    mock_history.aadd_message = AsyncMock()
    service.message_history = mock_history

    await service.add_semantic_message(user_id=123, role="user", content="тест")

    mock_history.aadd_message.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_semantic_history.py -v
```

Expected: FAIL with `AttributeError`

**Step 3: Update imports in cache.py**

At the top of `telegram_bot/services/cache.py`, change:

```python
# Add new import (line ~14)
from redisvl.extensions.message_history import SemanticMessageHistory
```

**Step 4: Add message_history attribute to **init****

In `telegram_bot/services/cache.py`, add to `__init__` (around line 77):

```python
        # Native RedisVL SemanticMessageHistory (for conversation context)
        self.message_history: Optional[SemanticMessageHistory] = None
```

**Step 5: Initialize message_history in initialize()**

In `telegram_bot/services/cache.py`, add to `initialize()` method (after embeddings_cache init, around line 145):

```python
            # Initialize SemanticMessageHistory for conversation context
            try:
                self.message_history = SemanticMessageHistory(
                    name="rag_conversations",
                    redis_url=self.redis_url,
                    vectorizer=vectorizer,  # Reuse voyage-3-lite
                    distance_threshold=0.3,
                )
                logger.info("✓ SemanticMessageHistory initialized (voyage-3-lite)")
            except Exception as e:
                logger.warning(f"SemanticMessageHistory initialization failed: {e}")
                self.message_history = None
```

**Step 6: Add get_relevant_history method**

Add new method to CacheService (after `get_conversation_history`):

```python
    async def get_relevant_history(
        self, user_id: int, query: str, top_k: int = 3
    ) -> list[dict[str, Any]]:
        """Get semantically relevant messages from conversation history.

        Uses vector similarity to find messages related to current query.

        Args:
            user_id: Telegram user ID
            query: Current user query for similarity search
            top_k: Number of relevant messages to return

        Returns:
            List of relevant messages [{"role": "user", "content": "..."}]
        """
        if not self.message_history:
            return []

        try:
            messages = await self.message_history.aget_relevant(
                session_tag=str(user_id),
                prompt=query,
                top_k=top_k,
            )
            logger.debug(f"Retrieved {len(messages)} relevant messages for user {user_id}")
            return messages
        except Exception as e:
            logger.error(f"SemanticMessageHistory error: {e}")
            return []
```

**Step 7: Add add_semantic_message method**

Add new method to CacheService:

```python
    async def add_semantic_message(
        self, user_id: int, role: str, content: str
    ):
        """Add message to semantic conversation history.

        Stores message with embedding for later semantic retrieval.

        Args:
            user_id: Telegram user ID
            role: Message role ('user' or 'assistant')
            content: Message content
        """
        if not self.message_history:
            return

        try:
            await self.message_history.aadd_message(
                session_tag=str(user_id),
                role=role,
                content=content,
            )
            logger.debug(f"Added semantic message for user {user_id}: {role}")
        except Exception as e:
            logger.error(f"SemanticMessageHistory add error: {e}")
```

**Step 8: Run test to verify it passes**

```bash
pytest tests/test_semantic_history.py -v
```

Expected: PASS

**Step 9: Commit**

```bash
git add tests/test_semantic_history.py telegram_bot/services/cache.py
git commit -m "feat(cache): add SemanticMessageHistory for conversation context"
```

---

## Task 5: Test Full Bot Locally

**Step 1: Rebuild and restart bot**

```bash
docker compose -f docker-compose.dev.yml build bot
docker compose -f docker-compose.dev.yml up -d bot
```

**Step 2: Check logs for errors**

```bash
docker logs dev-bot --tail 100 2>&1 | grep -iE "(error|exception|failed)"
```

Expected: No EmbeddingsCache or LLMService errors.

**Step 3: Send test message to bot**

Send "привет" to @test_nika_homes_bot in Telegram.

**Step 4: Verify in logs**

```bash
docker logs dev-bot --tail 30
```

Expected:

- ✓ No `EmbeddingsCache.aget() got an unexpected keyword argument` errors
- ✓ No `'LLMService' object has no attribute 'generate'` errors
- ✓ No `message is not modified` errors

**Step 5: Run all tests**

```bash
pytest tests/ -v --ignore=tests/compare_rrf_vs_dbsf.py
```

Expected: All tests pass.

**Step 6: Commit**

```bash
git add .
git commit -m "test: verify all bug fixes work"
```

---

## Task 6: Update TODO.md

**Step 1: Update TODO.md with completed tasks**

```bash
# Mark tasks as complete in TODO.md
```

**Step 2: Commit**

```bash
git add TODO.md
git commit -m "docs: update TODO with completed bug fixes"
```

---

## Summary

| Task | Description                  | Files                                  |
| ---- | ---------------------------- | -------------------------------------- |
| 1    | Fix EmbeddingsCache API      | `cache.py`, `test_embeddings_cache.py` |
| 2    | Add LLMService.generate()    | `llm.py`, `test_llm_generate.py`       |
| 3    | Fix streaming duplicate edit | `bot.py`                               |
| 4    | Add SemanticMessageHistory   | `cache.py`, `test_semantic_history.py` |
| 5    | Test full bot                | Manual verification                    |
| 6    | Update docs                  | `TODO.md`                              |

**Estimated commits:** 6

---

## Post-Implementation

After completing this plan:

1. **Merge to main:** `git checkout main && git merge feat/redis-stack-vector-search`
2. **Deploy:** `make deploy-release VERSION=2.9.1`

---

**Last Updated:** 2026-01-22
