# Full Test Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Achieve 80% test coverage for all 12 untested modules using TDD approach.

**Architecture:** Unit tests with mocks for external APIs (Voyage, OpenAI, Qdrant, Redis). Integration tests marked with `@pytest.mark.integration`. Sequential implementation by criticality.

**Tech Stack:** pytest, pytest-asyncio, unittest.mock, httpx (mocking HTTP), coverage

---

## Setup Task: Create Test Infrastructure

### Task 0: Update pytest configuration and create test directories

**Files:**
- Modify: `pyproject.toml:22-35`
- Modify: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/services/__init__.py`
- Create: `tests/unit/config/__init__.py`
- Create: `tests/unit/contextualization/__init__.py`
- Create: `tests/unit/utils/__init__.py`
- Create: `tests/integration/__init__.py`

**Step 1: Update pyproject.toml with markers**

Add to `[tool.pytest.ini_options]`:

```toml
markers = [
    "unit: Unit tests with mocks (fast, no external deps)",
    "integration: Integration tests (requires Docker/API keys)",
    "slow: Tests taking > 5 seconds",
]
```

**Step 2: Update coverage config**

Modify `[tool.coverage.run]`:

```toml
[tool.coverage.run]
source = ["src", "telegram_bot"]
branch = true
omit = [
    "*/tests/*",
    "*/legacy/*",
    "*/__pycache__/*",
    "*/.venv/*",
]

[tool.coverage.report]
fail_under = 80
```

**Step 3: Create directory structure**

Run:
```bash
mkdir -p tests/unit/services tests/unit/config tests/unit/contextualization tests/unit/utils tests/integration
touch tests/unit/__init__.py tests/unit/services/__init__.py tests/unit/config/__init__.py tests/unit/contextualization/__init__.py tests/unit/utils/__init__.py tests/integration/__init__.py
```

**Step 4: Add shared fixtures to conftest.py**

Add to `tests/conftest.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for HTTP tests."""
    with patch("httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx.Response."""
    def _create(status_code=200, json_data=None, text=""):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=response
            )
        return response
    return _create


@pytest.fixture
def sample_context_chunks():
    """Sample context chunks for LLM tests."""
    return [
        {
            "text": "Квартира в Солнечном берегу, 2 комнаты, 65 м².",
            "metadata": {"title": "Апартамент у моря", "city": "Солнечный берег", "price": 75000},
            "score": 0.92,
        },
        {
            "text": "Студия в Несебре, первая линия, 35 м².",
            "metadata": {"title": "Студия на первой линии", "city": "Несебр", "price": 45000},
            "score": 0.87,
        },
    ]
```

**Step 5: Verify setup**

Run: `pytest tests/ --collect-only`
Expected: No errors, test collection works

**Step 6: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/unit tests/integration
git commit -m "test: add test infrastructure for full coverage"
```

---

## Task 1: LLMService Tests (telegram_bot/services/llm.py)

**Files:**
- Create: `tests/unit/services/test_llm.py`
- Test: `telegram_bot/services/llm.py`

### Step 1.1: Write test for __init__

```python
"""Tests for LLMService."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestLLMServiceInit:
    """Tests for LLMService initialization."""

    def test_init_sets_api_key(self):
        """Test __init__ stores api_key."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient"):
            service = LLMService(api_key="test-key")

        assert service.api_key == "test-key"

    def test_init_sets_default_base_url(self):
        """Test __init__ uses default OpenAI base URL."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient"):
            service = LLMService(api_key="test-key")

        assert service.base_url == "https://api.openai.com/v1"

    def test_init_custom_base_url_strips_trailing_slash(self):
        """Test __init__ strips trailing slash from base_url."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient"):
            service = LLMService(api_key="test-key", base_url="https://api.example.com/")

        assert service.base_url == "https://api.example.com"

    def test_init_sets_default_model(self):
        """Test __init__ uses default model gpt-4o-mini."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient"):
            service = LLMService(api_key="test-key")

        assert service.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        """Test __init__ with custom model."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient"):
            service = LLMService(api_key="test-key", model="gpt-4-turbo")

        assert service.model == "gpt-4-turbo"

    def test_init_creates_httpx_client(self):
        """Test __init__ creates AsyncClient with 60s timeout."""
        from telegram_bot.services.llm import LLMService

        with patch("httpx.AsyncClient") as mock_client_class:
            LLMService(api_key="test-key")

        mock_client_class.assert_called_once_with(timeout=60.0)
```

**Step 1.2: Run test to verify it passes (code exists)**

Run: `pytest tests/unit/services/test_llm.py::TestLLMServiceInit -v`
Expected: PASS (implementation exists)

### Step 1.3: Write tests for generate_answer

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceGenerateAnswer:
    """Tests for LLMService.generate_answer."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked client."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            service = LLMService(api_key="test-key")
            service.client = mock_client
            yield service, mock_client

    async def test_generate_answer_returns_response_content(self, llm_service):
        """Test generate_answer returns LLM response content."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test answer"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service.generate_answer(
            question="Test question?",
            context_chunks=[{"text": "context", "metadata": {}, "score": 0.9}],
        )

        assert result == "Test answer"

    async def test_generate_answer_uses_custom_system_prompt(self, llm_service):
        """Test generate_answer uses provided system_prompt."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Answer"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service.generate_answer(
            question="Q?",
            context_chunks=[],
            system_prompt="Custom prompt",
        )

        call_args = mock_client.post.call_args
        request_json = call_args[1]["json"]
        assert request_json["messages"][0]["content"] == "Custom prompt"

    async def test_generate_answer_timeout_returns_fallback(self, llm_service):
        """Test generate_answer returns fallback on timeout."""
        service, mock_client = llm_service

        mock_client.post.side_effect = httpx.TimeoutException("Timeout")

        result = await service.generate_answer(
            question="Q?",
            context_chunks=[
                {"text": "chunk", "metadata": {"title": "Test", "price": 50000}, "score": 0.9}
            ],
        )

        assert "временно недоступен" in result
        assert "Test" in result  # Fallback includes chunk title

    async def test_generate_answer_http_error_returns_fallback(self, llm_service):
        """Test generate_answer returns fallback on HTTP error."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        result = await service.generate_answer(
            question="Q?",
            context_chunks=[{"text": "chunk", "metadata": {}, "score": 0.9}],
        )

        assert "временно недоступен" in result

    async def test_generate_answer_empty_chunks_fallback(self, llm_service):
        """Test generate_answer with empty chunks on error."""
        service, mock_client = llm_service

        mock_client.post.side_effect = Exception("Error")

        result = await service.generate_answer(
            question="Q?",
            context_chunks=[],
        )

        assert "временно недоступен" in result
        assert "Попробуйте повторить запрос" in result
```

**Step 1.4: Run tests**

Run: `pytest tests/unit/services/test_llm.py::TestLLMServiceGenerateAnswer -v`
Expected: PASS

### Step 1.5: Write tests for stream_answer

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceStreamAnswer:
    """Tests for LLMService.stream_answer."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked client."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            service = LLMService(api_key="test-key")
            service.client = mock_client
            yield service, mock_client

    async def test_stream_answer_yields_chunks(self, llm_service):
        """Test stream_answer yields content chunks."""
        service, mock_client = llm_service

        # Mock streaming response
        async def mock_aiter_lines():
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" World"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines

        mock_client.stream.return_value.__aenter__.return_value = mock_response

        chunks = []
        async for chunk in service.stream_answer("Q?", [{"text": "ctx", "metadata": {}, "score": 0.9}]):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    async def test_stream_answer_skips_empty_lines(self, llm_service):
        """Test stream_answer skips empty lines."""
        service, mock_client = llm_service

        async def mock_aiter_lines():
            yield ""
            yield "   "
            yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}'
            yield "data: [DONE]"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_client.stream.return_value.__aenter__.return_value = mock_response

        chunks = []
        async for chunk in service.stream_answer("Q?", [{"text": "ctx", "metadata": {}, "score": 0.9}]):
            chunks.append(chunk)

        assert chunks == ["Hi"]

    async def test_stream_answer_timeout_yields_fallback(self, llm_service):
        """Test stream_answer yields fallback on timeout."""
        service, mock_client = llm_service

        mock_client.stream.return_value.__aenter__.side_effect = httpx.TimeoutException("Timeout")

        chunks = []
        async for chunk in service.stream_answer(
            "Q?",
            [{"text": "chunk", "metadata": {"title": "Test"}, "score": 0.9}],
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "временно недоступен" in chunks[0]
```

**Step 1.6: Run tests**

Run: `pytest tests/unit/services/test_llm.py::TestLLMServiceStreamAnswer -v`
Expected: PASS

### Step 1.7: Write tests for _format_context

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceFormatContext:
    """Tests for LLMService._format_context."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService."""
        with patch("httpx.AsyncClient"):
            return LLMService(api_key="test-key")

    def test_format_context_empty_chunks(self, llm_service):
        """Test _format_context with empty list."""
        result = llm_service._format_context([])

        assert result == "Релевантной информации не найдено."

    def test_format_context_single_chunk(self, llm_service):
        """Test _format_context with single chunk."""
        chunks = [{"text": "Test text", "metadata": {}, "score": 0.95}]

        result = llm_service._format_context(chunks)

        assert "[Объект 1]" in result
        assert "релевантность: 0.95" in result
        assert "Test text" in result

    def test_format_context_with_metadata(self, llm_service):
        """Test _format_context includes metadata."""
        chunks = [
            {
                "text": "Apartment",
                "metadata": {"title": "Nice flat", "city": "Sofia", "price": 50000},
                "score": 0.9,
            }
        ]

        result = llm_service._format_context(chunks)

        assert "Название: Nice flat" in result
        assert "Город: Sofia" in result
        assert "Цена: 50,000€" in result

    def test_format_context_multiple_chunks_separated(self, llm_service):
        """Test _format_context separates chunks with ---."""
        chunks = [
            {"text": "First", "metadata": {}, "score": 0.9},
            {"text": "Second", "metadata": {}, "score": 0.8},
        ]

        result = llm_service._format_context(chunks)

        assert "---" in result
        assert "[Объект 1]" in result
        assert "[Объект 2]" in result
```

**Step 1.8: Run tests**

Run: `pytest tests/unit/services/test_llm.py::TestLLMServiceFormatContext -v`
Expected: PASS

### Step 1.9: Write tests for _get_fallback_answer

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceGetFallbackAnswer:
    """Tests for LLMService._get_fallback_answer."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService."""
        with patch("httpx.AsyncClient"):
            return LLMService(api_key="test-key")

    def test_get_fallback_answer_empty_chunks(self, llm_service):
        """Test _get_fallback_answer with no chunks."""
        result = llm_service._get_fallback_answer("Q?", [])

        assert "временно недоступен" in result
        assert "Попробуйте повторить запрос позже" in result

    def test_get_fallback_answer_formats_chunks(self, llm_service):
        """Test _get_fallback_answer formats first 3 chunks."""
        chunks = [
            {"text": "t1", "metadata": {"title": "A", "price": 10000, "city": "X"}, "score": 0.9},
            {"text": "t2", "metadata": {"title": "B", "price": 20000}, "score": 0.8},
            {"text": "t3", "metadata": {"title": "C"}, "score": 0.7},
            {"text": "t4", "metadata": {"title": "D"}, "score": 0.6},  # Should be excluded
        ]

        result = llm_service._get_fallback_answer("Q?", chunks)

        assert "1. A" in result
        assert "2. B" in result
        assert "3. C" in result
        assert "4. D" not in result  # Only first 3

    def test_get_fallback_answer_handles_non_numeric_price(self, llm_service):
        """Test _get_fallback_answer handles string price."""
        chunks = [
            {"text": "t1", "metadata": {"title": "A", "price": "По запросу"}, "score": 0.9},
        ]

        result = llm_service._get_fallback_answer("Q?", chunks)

        assert "Цена: По запросу€" in result
```

**Step 1.10: Run all LLM tests**

Run: `pytest tests/unit/services/test_llm.py -v`
Expected: All PASS

### Step 1.11: Write tests for generate method

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceGenerate:
    """Tests for LLMService.generate (simple text generation)."""

    @pytest.fixture
    def llm_service(self):
        """Create LLMService with mocked client."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            service = LLMService(api_key="test-key")
            service.client = mock_client
            yield service, mock_client

    async def test_generate_returns_response(self, llm_service):
        """Test generate returns LLM content."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated text"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service.generate("Test prompt")

        assert result == "Generated text"

    async def test_generate_uses_low_temperature(self, llm_service):
        """Test generate uses temperature 0.3."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service.generate("prompt")

        call_args = mock_client.post.call_args
        request_json = call_args[1]["json"]
        assert request_json["temperature"] == 0.3

    async def test_generate_respects_max_tokens(self, llm_service):
        """Test generate respects max_tokens parameter."""
        service, mock_client = llm_service

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service.generate("prompt", max_tokens=100)

        call_args = mock_client.post.call_args
        request_json = call_args[1]["json"]
        assert request_json["max_tokens"] == 100

    async def test_generate_raises_on_error(self, llm_service):
        """Test generate raises exception on API error."""
        service, mock_client = llm_service

        mock_client.post.side_effect = Exception("API Error")

        with pytest.raises(Exception) as exc_info:
            await service.generate("prompt")

        assert "API Error" in str(exc_info.value)
```

**Step 1.12: Write test for close method

Add to `tests/unit/services/test_llm.py`:

```python
class TestLLMServiceClose:
    """Tests for LLMService.close."""

    async def test_close_closes_client(self):
        """Test close calls client.aclose."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            service = LLMService(api_key="test-key")
            service.client = mock_client

            await service.close()

            mock_client.aclose.assert_called_once()
```

**Step 1.13: Run all LLM tests and check coverage**

Run: `pytest tests/unit/services/test_llm.py -v --cov=telegram_bot/services/llm --cov-report=term-missing`
Expected: PASS, coverage >= 80%

**Step 1.14: Commit**

```bash
git add tests/unit/services/test_llm.py
git commit -m "test(llm): add comprehensive unit tests for LLMService"
```

---

## Task 2: EmbeddingService Tests (telegram_bot/services/embeddings.py)

**Files:**
- Create: `tests/unit/services/test_embeddings.py`
- Test: `telegram_bot/services/embeddings.py`

### Step 2.1: Write all tests

```python
"""Tests for EmbeddingService (BGE-M3 API client)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestEmbeddingServiceInit:
    """Tests for EmbeddingService initialization."""

    def test_init_sets_base_url(self):
        """Test __init__ stores base_url."""
        from telegram_bot.services.embeddings import EmbeddingService

        with patch("httpx.AsyncClient"):
            service = EmbeddingService(base_url="http://localhost:8001")

        assert service.base_url == "http://localhost:8001"

    def test_init_strips_trailing_slash(self):
        """Test __init__ strips trailing slash from base_url."""
        from telegram_bot.services.embeddings import EmbeddingService

        with patch("httpx.AsyncClient"):
            service = EmbeddingService(base_url="http://localhost:8001/")

        assert service.base_url == "http://localhost:8001"

    def test_init_creates_httpx_client(self):
        """Test __init__ creates AsyncClient with 30s timeout."""
        from telegram_bot.services.embeddings import EmbeddingService

        with patch("httpx.AsyncClient") as mock_class:
            EmbeddingService(base_url="http://localhost:8001")

        mock_class.assert_called_once_with(timeout=30.0)


class TestEmbeddingServiceEmbedQuery:
    """Tests for EmbeddingService.embed_query."""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService with mocked client."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            service = EmbeddingService(base_url="http://localhost:8001")
            service.client = mock_client
            yield service, mock_client

    async def test_embed_query_returns_vector(self, embedding_service):
        """Test embed_query returns dense vector."""
        service, mock_client = embedding_service

        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1] * 1024]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await service.embed_query("test query")

        assert len(result) == 1024
        assert result[0] == 0.1

    async def test_embed_query_calls_correct_endpoint(self, embedding_service):
        """Test embed_query calls /encode/dense endpoint."""
        service, mock_client = embedding_service

        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1] * 1024]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service.embed_query("test")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8001/encode/dense"

    async def test_embed_query_sends_text_as_array(self, embedding_service):
        """Test embed_query sends text wrapped in array."""
        service, mock_client = embedding_service

        mock_response = MagicMock()
        mock_response.json.return_value = {"dense_vecs": [[0.1] * 1024]}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await service.embed_query("my query")

        call_args = mock_client.post.call_args
        assert call_args[1]["json"] == {"texts": ["my query"]}

    async def test_embed_query_raises_on_http_error(self, embedding_service):
        """Test embed_query raises on HTTP error."""
        service, mock_client = embedding_service

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )
        mock_client.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await service.embed_query("test")


class TestEmbeddingServiceClose:
    """Tests for EmbeddingService.close."""

    async def test_close_closes_client(self):
        """Test close calls client.aclose."""
        from telegram_bot.services.embeddings import EmbeddingService

        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            service = EmbeddingService(base_url="http://localhost:8001")
            service.client = mock_client

            await service.close()

            mock_client.aclose.assert_called_once()
```

**Step 2.2: Run tests**

Run: `pytest tests/unit/services/test_embeddings.py -v --cov=telegram_bot/services/embeddings --cov-report=term-missing`
Expected: PASS, coverage >= 80%

**Step 2.3: Commit**

```bash
git add tests/unit/services/test_embeddings.py
git commit -m "test(embeddings): add unit tests for EmbeddingService"
```

---

## Task 3: FilterExtractor Tests (telegram_bot/services/filter_extractor.py)

**Files:**
- Create: `tests/unit/services/test_filter_extractor.py`
- Test: `telegram_bot/services/filter_extractor.py`

### Step 3.1: Write tests for price extraction

```python
"""Tests for FilterExtractor."""

import pytest


class TestFilterExtractorPrice:
    """Tests for price filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_price_lt_deshevle(self, extractor):
        """Test 'дешевле X' extracts price < X."""
        result = extractor.extract_filters("квартира дешевле 100000")
        assert result["price"] == {"lt": 100000}

    def test_extract_price_lt_do(self, extractor):
        """Test 'до X' extracts price < X."""
        result = extractor.extract_filters("квартира до 80000")
        assert result["price"] == {"lt": 80000}

    def test_extract_price_lt_menshe(self, extractor):
        """Test 'меньше X' extracts price < X."""
        result = extractor.extract_filters("цена меньше 50000")
        assert result["price"] == {"lt": 50000}

    def test_extract_price_gt_dorozhe(self, extractor):
        """Test 'дороже X' extracts price > X."""
        result = extractor.extract_filters("квартира дороже 100000")
        assert result["price"] == {"gt": 100000}

    def test_extract_price_gt_ot(self, extractor):
        """Test 'от X' extracts price > X."""
        result = extractor.extract_filters("квартира от 80000")
        assert result["price"] == {"gt": 80000}

    def test_extract_price_range(self, extractor):
        """Test 'от X до Y' extracts price range."""
        result = extractor.extract_filters("квартира от 50000 до 100000")
        assert result["price"] == {"gte": 50000, "lte": 100000}

    def test_extract_price_with_k_suffix(self, extractor):
        """Test '100к' parses as 100000."""
        result = extractor.extract_filters("квартира до 100к")
        assert result["price"] == {"lt": 100000}

    def test_extract_price_with_spaces(self, extractor):
        """Test '100 000' parses correctly."""
        result = extractor.extract_filters("квартира до 100 000")
        assert result["price"] == {"lt": 100000}


class TestFilterExtractorRooms:
    """Tests for rooms filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_rooms_digit(self, extractor):
        """Test '3 комнаты' extracts rooms=3."""
        result = extractor.extract_filters("квартира 3 комнаты")
        assert result["rooms"] == 3

    def test_extract_rooms_word_dvuh(self, extractor):
        """Test 'двухкомнатная' extracts rooms=2."""
        result = extractor.extract_filters("двухкомнатная квартира")
        assert result["rooms"] == 2

    def test_extract_rooms_word_treh(self, extractor):
        """Test 'трехкомнатная' extracts rooms=3."""
        result = extractor.extract_filters("трехкомнатная квартира")
        assert result["rooms"] == 3

    def test_extract_rooms_studio(self, extractor):
        """Test 'студия' extracts rooms=1."""
        result = extractor.extract_filters("студия у моря")
        assert result["rooms"] == 1


class TestFilterExtractorCity:
    """Tests for city filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_city_solnechny_bereg(self, extractor):
        """Test extracts 'Солнечный берег'."""
        result = extractor.extract_filters("квартира в Солнечный берег")
        assert result["city"] == "Солнечный берег"

    def test_extract_city_nesebr(self, extractor):
        """Test extracts 'Несебр'."""
        result = extractor.extract_filters("квартира в Несебр")
        assert result["city"] == "Несебр"

    def test_extract_city_case_insensitive(self, extractor):
        """Test city extraction is case-insensitive."""
        result = extractor.extract_filters("квартира в БУРГАС")
        assert result["city"] == "Бургас"


class TestFilterExtractorDistanceToSea:
    """Tests for distance_to_sea filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_distance_do_morya(self, extractor):
        """Test 'до 500м до моря' extracts distance <= 500."""
        result = extractor.extract_filters("квартира до 500м до моря")
        assert result["distance_to_sea"] == {"lte": 500}

    def test_extract_distance_pervaya_liniya(self, extractor):
        """Test 'первая линия' extracts distance <= 200."""
        result = extractor.extract_filters("апартаменты первая линия")
        assert result["distance_to_sea"] == {"lte": 200}

    def test_extract_distance_u_morya(self, extractor):
        """Test 'у моря' extracts distance <= 200."""
        result = extractor.extract_filters("квартира у моря")
        assert result["distance_to_sea"] == {"lte": 200}


class TestFilterExtractorFurniture:
    """Tests for furniture filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_furniture_s_mebelyu(self, extractor):
        """Test 'с мебелью' extracts furniture='Есть'."""
        result = extractor.extract_filters("квартира с мебелью")
        assert result["furniture"] == "Есть"

    def test_extract_furniture_meblirovannaya(self, extractor):
        """Test 'меблированная' extracts furniture='Есть'."""
        result = extractor.extract_filters("меблированная квартира")
        assert result["furniture"] == "Есть"


class TestFilterExtractorYearRound:
    """Tests for year_round filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_year_round_kruglogodichny(self, extractor):
        """Test 'круглогодичная' extracts year_round='Да'."""
        result = extractor.extract_filters("круглогодичная резиденция")
        assert result["year_round"] == "Да"

    def test_extract_year_round_krugly_god(self, extractor):
        """Test 'круглый год' extracts year_round='Да'."""
        result = extractor.extract_filters("работает круглый год")
        assert result["year_round"] == "Да"


class TestFilterExtractorCombined:
    """Tests for combined filter extraction."""

    @pytest.fixture
    def extractor(self):
        """Create FilterExtractor instance."""
        from telegram_bot.services.filter_extractor import FilterExtractor
        return FilterExtractor()

    def test_extract_multiple_filters(self, extractor):
        """Test extracting multiple filters from one query."""
        query = "двухкомнатная квартира в Несебр до 80000 с мебелью"
        result = extractor.extract_filters(query)

        assert result["rooms"] == 2
        assert result["city"] == "Несебр"
        assert result["price"] == {"lt": 80000}
        assert result["furniture"] == "Есть"

    def test_extract_no_filters(self, extractor):
        """Test returns empty dict when no filters found."""
        result = extractor.extract_filters("покажи все варианты")
        assert result == {}
```

**Step 3.2: Run tests**

Run: `pytest tests/unit/services/test_filter_extractor.py -v --cov=telegram_bot/services/filter_extractor --cov-report=term-missing`
Expected: PASS, coverage >= 80%

**Step 3.3: Commit**

```bash
git add tests/unit/services/test_filter_extractor.py
git commit -m "test(filter_extractor): add comprehensive unit tests"
```

---

## Task 4: QueryAnalyzer Tests (telegram_bot/services/query_analyzer.py)

**Files:**
- Create: `tests/unit/services/test_query_analyzer.py`
- Test: `telegram_bot/services/query_analyzer.py`

### Step 4.1: Write all tests

```python
"""Tests for QueryAnalyzer (LLM-based filter extraction)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestQueryAnalyzerInit:
    """Tests for QueryAnalyzer initialization."""

    def test_init_sets_api_key(self):
        """Test __init__ stores api_key."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")

        assert analyzer.api_key == "test-key"

    def test_init_sets_base_url(self):
        """Test __init__ stores base_url."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")

        assert analyzer.base_url == "http://api.example.com"

    def test_init_default_model(self):
        """Test __init__ uses default model gpt-4o-mini."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")

        assert analyzer.model == "gpt-4o-mini"

    def test_init_custom_model(self):
        """Test __init__ with custom model."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient"):
            analyzer = QueryAnalyzer(
                api_key="test-key",
                base_url="http://api.example.com",
                model="gpt-4-turbo",
            )

        assert analyzer.model == "gpt-4-turbo"

    def test_init_creates_httpx_client(self):
        """Test __init__ creates AsyncClient with 30s timeout."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient") as mock_class:
            QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")

        mock_class.assert_called_once_with(timeout=30.0)


class TestQueryAnalyzerAnalyze:
    """Tests for QueryAnalyzer.analyze."""

    @pytest.fixture
    def analyzer(self):
        """Create QueryAnalyzer with mocked client."""
        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            from telegram_bot.services.query_analyzer import QueryAnalyzer
            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")
            analyzer.client = mock_client
            yield analyzer, mock_client

    async def test_analyze_returns_filters_and_semantic_query(self, analyzer):
        """Test analyze returns extracted filters and semantic query."""
        analyzer_instance, mock_client = analyzer

        llm_response = {
            "filters": {"price": {"lt": 100000}, "city": "Несебр"},
            "semantic_query": "недорогие квартиры с хорошим ремонтом",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(llm_response)}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_instance.analyze("квартира в Несебр до 100000")

        assert result["filters"] == {"price": {"lt": 100000}, "city": "Несебр"}
        assert result["semantic_query"] == "недорогие квартиры с хорошим ремонтом"

    async def test_analyze_uses_json_response_format(self, analyzer):
        """Test analyze requests JSON response format."""
        analyzer_instance, mock_client = analyzer

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"filters": {}, "semantic_query": "test"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_instance.analyze("test query")

        call_args = mock_client.post.call_args
        request_json = call_args[1]["json"]
        assert request_json["response_format"] == {"type": "json_object"}

    async def test_analyze_uses_zero_temperature(self, analyzer):
        """Test analyze uses temperature 0.0 for deterministic output."""
        analyzer_instance, mock_client = analyzer

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"filters": {}, "semantic_query": "test"}'}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        await analyzer_instance.analyze("test query")

        call_args = mock_client.post.call_args
        request_json = call_args[1]["json"]
        assert request_json["temperature"] == 0.0

    async def test_analyze_fallback_on_json_parse_error(self, analyzer):
        """Test analyze returns fallback on invalid JSON from LLM."""
        analyzer_instance, mock_client = analyzer

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not valid json"}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await analyzer_instance.analyze("original query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "original query"

    async def test_analyze_fallback_on_api_error(self, analyzer):
        """Test analyze returns fallback on API error."""
        analyzer_instance, mock_client = analyzer

        mock_client.post.side_effect = Exception("API Error")

        result = await analyzer_instance.analyze("original query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "original query"

    async def test_analyze_fallback_on_http_error(self, analyzer):
        """Test analyze returns fallback on HTTP error."""
        analyzer_instance, mock_client = analyzer

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        result = await analyzer_instance.analyze("original query")

        assert result["filters"] == {}
        assert result["semantic_query"] == "original query"


class TestQueryAnalyzerClose:
    """Tests for QueryAnalyzer.close."""

    async def test_close_closes_client(self):
        """Test close calls client.aclose."""
        from telegram_bot.services.query_analyzer import QueryAnalyzer

        with patch("httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client

            analyzer = QueryAnalyzer(api_key="test-key", base_url="http://api.example.com")
            analyzer.client = mock_client

            await analyzer.close()

            mock_client.aclose.assert_called_once()
```

**Step 4.2: Run tests**

Run: `pytest tests/unit/services/test_query_analyzer.py -v --cov=telegram_bot/services/query_analyzer --cov-report=term-missing`
Expected: PASS, coverage >= 80%

**Step 4.3: Commit**

```bash
git add tests/unit/services/test_query_analyzer.py
git commit -m "test(query_analyzer): add unit tests for LLM-based filter extraction"
```

---

## Task 5: Settings Tests (src/config/settings.py)

**Files:**
- Create: `tests/unit/config/test_settings.py`
- Test: `src/config/settings.py`

### Step 5.1: Write tests

```python
"""Tests for Settings configuration."""

import os
from unittest.mock import patch

import pytest


class TestSettingsInit:
    """Tests for Settings initialization."""

    def test_init_loads_env_file(self):
        """Test __init__ loads .env file."""
        with patch("dotenv.load_dotenv") as mock_load:
            with patch.dict(os.environ, {"API_PROVIDER": "claude", "ANTHROPIC_API_KEY": "key"}):
                from importlib import reload
                import src.config.settings
                reload(src.config.settings)

            mock_load.assert_called()

    def test_init_sets_api_provider_from_env(self):
        """Test __init__ reads API_PROVIDER from environment."""
        with patch.dict(os.environ, {"API_PROVIDER": "openai", "OPENAI_API_KEY": "key"}, clear=False):
            from src.config.settings import Settings
            settings = Settings()

        assert settings.api_provider.value == "openai"

    def test_init_sets_qdrant_url_from_env(self):
        """Test __init__ reads QDRANT_URL from environment."""
        with patch.dict(os.environ, {
            "QDRANT_URL": "http://qdrant.example.com:6333",
            "API_PROVIDER": "openai",
            "OPENAI_API_KEY": "key",
        }):
            from src.config.settings import Settings
            settings = Settings()

        assert settings.qdrant_url == "http://qdrant.example.com:6333"

    def test_init_default_qdrant_url(self):
        """Test __init__ uses default Qdrant URL."""
        with patch.dict(os.environ, {"API_PROVIDER": "openai", "OPENAI_API_KEY": "key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings()

        assert settings.qdrant_url == "http://localhost:6333"

    def test_init_constructor_overrides_env(self):
        """Test constructor args override environment."""
        with patch.dict(os.environ, {
            "QDRANT_URL": "http://env.example.com",
            "OPENAI_API_KEY": "key",
        }):
            from src.config.settings import Settings
            settings = Settings(
                api_provider="openai",
                qdrant_url="http://constructor.example.com",
            )

        assert settings.qdrant_url == "http://constructor.example.com"


class TestSettingsValidation:
    """Tests for API key validation."""

    def test_validate_raises_for_claude_without_key(self):
        """Test raises ValueError when claude provider has no API key."""
        with patch.dict(os.environ, {"API_PROVIDER": "claude"}, clear=True):
            from src.config.settings import Settings

            with pytest.raises(ValueError) as exc_info:
                Settings(api_provider="claude")

            assert "ANTHROPIC_API_KEY not set" in str(exc_info.value)

    def test_validate_raises_for_openai_without_key(self):
        """Test raises ValueError when openai provider has no API key."""
        with patch.dict(os.environ, {}, clear=True):
            from src.config.settings import Settings

            with pytest.raises(ValueError) as exc_info:
                Settings(api_provider="openai")

            assert "OPENAI_API_KEY not set" in str(exc_info.value)

    def test_validate_raises_for_groq_without_key(self):
        """Test raises ValueError when groq provider has no API key."""
        with patch.dict(os.environ, {}, clear=True):
            from src.config.settings import Settings

            with pytest.raises(ValueError) as exc_info:
                Settings(api_provider="groq")

            assert "GROQ_API_KEY not set" in str(exc_info.value)

    def test_validate_passes_with_correct_key(self):
        """Test validation passes when correct API key is set."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="openai")

        assert settings.openai_api_key == "sk-test"


class TestSettingsToDict:
    """Tests for Settings.to_dict."""

    def test_to_dict_excludes_api_keys(self):
        """Test to_dict does not include sensitive API keys."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="openai")
            result = settings.to_dict()

        assert "openai_api_key" not in result
        assert "anthropic_api_key" not in result
        assert "groq_api_key" not in result

    def test_to_dict_includes_config_values(self):
        """Test to_dict includes configuration values."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="openai", top_k=5)
            result = settings.to_dict()

        assert result["api_provider"] == "openai"
        assert result["top_k"] == 5


class TestSettingsDefaultModel:
    """Tests for default model selection."""

    def test_default_model_for_claude(self):
        """Test default model for Claude provider."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="claude")

        assert "claude" in settings.model_name.lower()

    def test_default_model_for_openai(self):
        """Test default model for OpenAI provider."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="openai")

        assert "gpt" in settings.model_name.lower()

    def test_default_model_for_groq(self):
        """Test default model for Groq provider."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "key"}, clear=True):
            from src.config.settings import Settings
            settings = Settings(api_provider="groq")

        assert "llama" in settings.model_name.lower()
```

**Step 5.2: Run tests**

Run: `pytest tests/unit/config/test_settings.py -v --cov=src/config/settings --cov-report=term-missing`
Expected: PASS, coverage >= 80%

**Step 5.3: Commit**

```bash
git add tests/unit/config/test_settings.py
git commit -m "test(config): add unit tests for Settings"
```

---

## Task 6-8: Contextualization Tests

### Task 6: ContextualizedChunk and ContextualizeProvider Tests

**Files:**
- Create: `tests/unit/contextualization/test_base.py`

(Similar TDD steps - write tests first, verify, commit)

### Task 7: ClaudeContextualizer Tests

**Files:**
- Create: `tests/unit/contextualization/test_claude.py`

### Task 8: GroqContextualizer Tests

**Files:**
- Create: `tests/unit/contextualization/test_groq.py`

---

## Task 9-12: Utility Tests

### Task 9: Embedding Model Singleton Tests

**Files:**
- Create: `tests/unit/utils/test_embedding_model.py`

### Task 10: PII Redaction Tests

**Files:**
- Create: `tests/unit/utils/test_pii_redaction.py`

### Task 11: Structure Parser Tests

**Files:**
- Create: `tests/unit/utils/test_structure_parser.py`

### Task 12: Constants Tests

**Files:**
- Create: `tests/unit/config/test_constants.py`

---

## Final: CI/CD Integration

### Task 13: Update Makefile

Add to `Makefile`:

```makefile
test-unit:
	pytest tests/ -m "not integration" -v

test-integration:
	pytest tests/ -m integration -v

test-all:
	pytest tests/ -v --cov --cov-fail-under=80
```

### Task 14: Final verification

Run: `make test-all`
Expected: All tests PASS, coverage >= 80%

---

## Summary

**Total Tasks:** 14 (Setup + 12 modules + CI)
**Estimated Tests:** 100-120 new tests
**Target Coverage:** 80%

After completing all tasks, the project will have comprehensive test coverage for all critical modules with both unit and integration tests properly organized.
