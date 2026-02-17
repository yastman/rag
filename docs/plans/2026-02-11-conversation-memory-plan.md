# Conversation Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **2026-02-17 Alignment Note (#243):**
> PostgresSaver tasks (1-2) were NOT implemented — Redis checkpointer remains the thread state backend.
> Qdrant `conversation_history` (tasks 3+) was implemented in #239. History agent integrated in #240.
> This plan is partially superseded. See actual implementation in `telegram_bot/services/history_service.py`.

**Goal:** Add persistent conversation memory with semantic search — store Q&A history in Qdrant ~~, replace MemorySaver with PostgresSaver,~~ enable bot auto-recall and manager search.

**Architecture:** ~~PostgresSaver for thread persistence (replaces MemorySaver),~~ Redis checkpointer for thread state (existing), new Qdrant collection `conversation_history` for Q&A pairs with dense search (BGE-M3), `/history` command + supervisor `history_search` tool. LangMem for background fact extraction deferred to Phase 2.

**Tech Stack:** ~~langgraph-checkpoint-postgres, psycopg[binary,pool],~~ qdrant-client (existing), BGE-M3 (existing)

**Design Doc:** `docs/plans/2026-02-11-conversation-memory-design.md`

---

## Task 1: Add psycopg dependency + conversation database

**Files:**
- Modify: `pyproject.toml` (dependencies section, ~line 45)
- Modify: `docker/postgres/init/00-init-databases.sql`

**Step 1: Add psycopg to dependencies**

In `pyproject.toml`, add after `langgraph-checkpoint-postgres` line (line 47):

```toml
    "psycopg[binary,pool]>=3.2",       # Async PostgreSQL driver for checkpointer
```

**Step 2: Add conversation database to init script**

Append to `docker/postgres/init/00-init-databases.sql`:

```sql
-- Database for conversation memory (PostgresSaver + PostgresStore)
CREATE DATABASE conversation;
GRANT ALL PRIVILEGES ON DATABASE conversation TO postgres;
```

**Step 3: Sync dependencies**

Run: `uv sync`
Expected: psycopg installed successfully

**Step 4: Verify psycopg imports**

Run: `uv run python -c "import psycopg; print(psycopg.__version__)"`
Expected: Version number printed

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock docker/postgres/init/00-init-databases.sql
git commit -m "feat(memory): add psycopg dependency and conversation database init"
```

---

## Task 2: Replace MemorySaver with AsyncPostgresSaver

**Files:**
- Modify: `telegram_bot/integrations/memory.py` (lines 1-13)
- Modify: `telegram_bot/bot.py` (lines 291-299 — build_graph call)
- Modify: `telegram_bot/config.py` — add `conversation_db_uri` field
- Test: `tests/unit/integrations/test_memory.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/integrations/test_memory.py`:

```python
"""Tests for conversation memory — PostgresSaver factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCreateCheckpointer:
    """Test checkpointer creation factory."""

    def test_creates_memory_saver_when_no_db_uri(self):
        """Fallback to MemorySaver when DB URI is not configured."""
        from telegram_bot.integrations.memory import create_checkpointer

        cp = create_checkpointer(db_uri=None)
        assert cp is not None
        assert type(cp).__name__ == "MemorySaver"

    @patch("telegram_bot.integrations.memory.AsyncPostgresSaver")
    def test_creates_postgres_saver_with_db_uri(self, mock_cls):
        """Use AsyncPostgresSaver when DB URI is provided."""
        from telegram_bot.integrations.memory import create_checkpointer

        mock_instance = MagicMock()
        mock_cls.from_conn_string.return_value = mock_instance

        cp = create_checkpointer(db_uri="postgresql://localhost/conversation")
        mock_cls.from_conn_string.assert_called_once_with(
            "postgresql://localhost/conversation"
        )
        assert cp is mock_instance
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/integrations/test_memory.py -v`
Expected: FAIL — `create_checkpointer` not found

**Step 3: Implement memory.py factory**

Replace `telegram_bot/integrations/memory.py` entirely:

```python
"""Checkpointer factory for LangGraph conversation persistence.

Uses AsyncPostgresSaver when DB URI is configured (production),
falls back to MemorySaver for development/testing.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


def create_checkpointer(db_uri: str | None = None) -> Any:
    """Create a checkpointer instance.

    Args:
        db_uri: PostgreSQL connection string. If None, uses in-memory.

    Returns:
        AsyncPostgresSaver if db_uri provided, else MemorySaver.
    """
    if db_uri:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        logger.info("Using AsyncPostgresSaver (persistent)")
        return AsyncPostgresSaver.from_conn_string(db_uri)

    logger.info("Using MemorySaver (in-memory, non-persistent)")
    return MemorySaver()


# Backward compat: default singleton for dev
checkpointer = MemorySaver()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/integrations/test_memory.py -v`
Expected: 2 PASSED

**Step 5: Add `conversation_db_uri` to BotConfig**

In `telegram_bot/config.py`, add field to BotConfig class:

```python
    conversation_db_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CONVERSATION_DB_URI", "conversation_db_uri"),
    )
```

**Step 6: Wire checkpointer in bot.py**

In `telegram_bot/bot.py`, in `PropertyBot.__init__`, after service initialization (~line 178), add:

```python
        from telegram_bot.integrations.memory import create_checkpointer
        self._checkpointer = create_checkpointer(db_uri=config.conversation_db_uri)
```

In `handle_query` (~line 291), pass checkpointer to build_graph:

```python
            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
                checkpointer=self._checkpointer,  # NEW
            )
```

**Step 7: Run full unit tests**

Run: `uv run pytest tests/unit/ -x -q`
Expected: All pass (no breaking changes — checkpointer=None still works)

**Step 8: Commit**

```bash
git add telegram_bot/integrations/memory.py telegram_bot/bot.py telegram_bot/config.py tests/unit/integrations/test_memory.py
git commit -m "feat(memory): replace MemorySaver with AsyncPostgresSaver factory"
```

---

## Task 3: Conversation history service (Qdrant storage + search)

**Files:**
- Create: `telegram_bot/services/conversation_history.py`
- Test: `tests/unit/services/test_conversation_history.py` (create)

**Step 1: Write the failing tests**

Create `tests/unit/services/test_conversation_history.py`:

```python
"""Tests for ConversationHistoryService — Qdrant storage + search."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from telegram_bot.services.conversation_history import ConversationHistoryService


@pytest.fixture
def mock_qdrant():
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.upsert = AsyncMock()
    return client


@pytest.fixture
def mock_embeddings():
    emb = AsyncMock()
    emb.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"word1": 0.5, "word2": 0.3})
    )
    return emb


@pytest.fixture
def service(mock_qdrant, mock_embeddings):
    return ConversationHistoryService(
        qdrant_client=mock_qdrant,
        embeddings=mock_embeddings,
        collection_name="conversation_history",
    )


class TestStoreQAPair:
    @pytest.mark.asyncio
    async def test_stores_qa_pair_with_correct_payload(self, service, mock_qdrant):
        await service.store_qa_pair(
            user_id=123,
            query="Какие налоги?",
            response="Плоская ставка 10%",
            session_id="chat-abc-20260211",
            query_type="STRUCTURED",
        )
        mock_qdrant.upsert.assert_awaited_once()
        call_args = mock_qdrant.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[1]
        point = points[0]
        assert point.payload["user_id"] == "tg_123"
        assert point.payload["query"] == "Какие налоги?"
        assert point.payload["response"] == "Плоская ставка 10%"
        assert point.payload["session_id"] == "chat-abc-20260211"
        assert point.payload["query_type"] == "STRUCTURED"

    @pytest.mark.asyncio
    async def test_embeds_concatenated_query_response(self, service, mock_embeddings):
        await service.store_qa_pair(
            user_id=123,
            query="Вопрос",
            response="Ответ",
            session_id="s",
            query_type="GENERAL",
        )
        mock_embeddings.aembed_hybrid.assert_awaited_once_with("Вопрос\nОтвет")


class TestSearchHistory:
    @pytest.mark.asyncio
    async def test_searches_with_user_filter(self, service, mock_qdrant, mock_embeddings):
        mock_qdrant.query_points = AsyncMock(
            return_value=MagicMock(points=[])
        )
        await service.search_history(user_id=123, query="налоги", limit=3)
        mock_embeddings.aembed_hybrid.assert_awaited_once_with("налоги")

    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, service, mock_qdrant, mock_embeddings):
        mock_point = MagicMock()
        mock_point.payload = {
            "query": "Какие налоги?",
            "response": "Плоская ставка 10%",
            "timestamp": 1739280000,
            "session_id": "chat-abc",
        }
        mock_point.score = 0.85
        mock_qdrant.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_point])
        )
        results = await service.search_history(user_id=123, query="налоги", limit=3)
        assert len(results) == 1
        assert results[0]["query"] == "Какие налоги?"
        assert results[0]["response"] == "Плоская ставка 10%"
        assert results[0]["score"] == 0.85
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_conversation_history.py -v`
Expected: FAIL — module not found

**Step 3: Implement ConversationHistoryService**

Create `telegram_bot/services/conversation_history.py`:

```python
"""Conversation history storage and semantic search via Qdrant.

Stores Q&A pairs as vectors (BGE-M3 dense+sparse) with user-level
multi-tenancy (payload filter on user_id with is_tenant).
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    NamedSparseVector,
    NamedVector,
    PointStruct,
    SparseVector,
)

logger = logging.getLogger(__name__)


class ConversationHistoryService:
    """Store and search conversation Q&A pairs in Qdrant."""

    def __init__(
        self,
        qdrant_client: Any,
        embeddings: Any,
        collection_name: str = "conversation_history",
    ) -> None:
        self._client = qdrant_client
        self._embeddings = embeddings
        self._collection_name = collection_name

    async def store_qa_pair(
        self,
        user_id: int,
        query: str,
        response: str,
        session_id: str,
        query_type: str = "GENERAL",
    ) -> None:
        """Store a Q&A pair with BGE-M3 embeddings.

        Embeds the concatenation of query+response for search by both.
        """
        text_to_embed = f"{query}\n{response}"
        dense, sparse = await self._embeddings.aembed_hybrid(text_to_embed)

        point = PointStruct(
            id=str(uuid4()),
            vectors={
                "dense": dense,
            },
            payload={
                "user_id": f"tg_{user_id}",
                "query": query,
                "response": response,
                "session_id": session_id,
                "query_type": query_type,
                "timestamp": int(time.time()),
            },
        )

        await self._client.upsert(
            collection_name=self._collection_name,
            points=[point],
        )
        logger.info(
            "conversation_history: stored Q&A for user=%s session=%s",
            user_id,
            session_id,
        )

    async def search_history(
        self,
        user_id: int,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Semantic search over user's conversation history.

        Args:
            user_id: Telegram user ID
            query: Search query text
            limit: Max results to return

        Returns:
            List of {query, response, timestamp, session_id, score}
        """
        dense, _sparse = await self._embeddings.aembed_hybrid(query)

        result = await self._client.query_points(
            collection_name=self._collection_name,
            query=dense,
            using="dense",
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=f"tg_{user_id}"),
                    ),
                ]
            ),
            limit=limit,
        )

        return [
            {
                "query": p.payload.get("query", ""),
                "response": p.payload.get("response", ""),
                "timestamp": p.payload.get("timestamp", 0),
                "session_id": p.payload.get("session_id", ""),
                "score": p.score,
            }
            for p in result.points
        ]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_conversation_history.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add telegram_bot/services/conversation_history.py tests/unit/services/test_conversation_history.py
git commit -m "feat(memory): add ConversationHistoryService for Qdrant Q&A storage"
```

---

## Task 4: Collection initialization script

**Files:**
- Create: `telegram_bot/services/conversation_history_init.py`
- Test: `tests/unit/services/test_conversation_history_init.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/services/test_conversation_history_init.py`:

```python
"""Tests for conversation_history Qdrant collection initialization."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_skips_if_exists(self):
        from telegram_bot.services.conversation_history_init import ensure_collection

        client = AsyncMock()
        client.collection_exists = AsyncMock(return_value=True)
        await ensure_collection(client, "conversation_history")
        client.create_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_if_missing(self):
        from telegram_bot.services.conversation_history_init import ensure_collection

        client = AsyncMock()
        client.collection_exists = AsyncMock(return_value=False)
        client.create_collection = AsyncMock()
        client.create_payload_index = AsyncMock()
        await ensure_collection(client, "conversation_history")
        client.create_collection.assert_awaited_once()
        # Should create both user_id and timestamp indexes
        assert client.create_payload_index.await_count == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_conversation_history_init.py -v`
Expected: FAIL — module not found

**Step 3: Implement collection init**

Create `telegram_bot/services/conversation_history_init.py`:

```python
"""Initialize conversation_history Qdrant collection.

Creates collection with dense vectors (BGE-M3 1024d) and tenant index.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    KeywordIndexParams,
    KeywordIndexType,
    PayloadSchemaType,
    VectorParams,
)

logger = logging.getLogger(__name__)

_DENSE_DIM = 1024  # BGE-M3


async def ensure_collection(
    client: Any,
    collection_name: str = "conversation_history",
) -> None:
    """Create conversation_history collection if it doesn't exist."""
    if await client.collection_exists(collection_name):
        logger.info("Collection %s already exists", collection_name)
        return

    await client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": VectorParams(
                size=_DENSE_DIM,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=128),
                on_disk=True,
            ),
        },
    )

    # Tenant index for per-user isolation
    await client.create_payload_index(
        collection_name=collection_name,
        field_name="user_id",
        field_schema=KeywordIndexParams(
            type=KeywordIndexType.KEYWORD,
            is_tenant=True,
        ),
    )

    # Timestamp index for chronological queries
    await client.create_payload_index(
        collection_name=collection_name,
        field_name="timestamp",
        field_schema=PayloadSchemaType.INTEGER,
    )

    logger.info("Created collection %s with tenant+timestamp indexes", collection_name)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_conversation_history_init.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add telegram_bot/services/conversation_history_init.py tests/unit/services/test_conversation_history_init.py
git commit -m "feat(memory): add conversation_history Qdrant collection init"
```

---

## Task 5: history_store_node — save Q&A to Qdrant

**Files:**
- Create: `telegram_bot/graph/nodes/history.py`
- Test: `tests/unit/graph/test_history_nodes.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/graph/test_history_nodes.py`:

```python
"""Tests for history_store_node and history_recall_node."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.state import make_initial_state


class TestHistoryStoreNode:
    @pytest.mark.asyncio
    async def test_stores_qa_pair(self):
        from telegram_bot.graph.nodes.history import history_store_node

        history_service = AsyncMock()
        history_service.store_qa_pair = AsyncMock()

        state = make_initial_state(user_id=42, session_id="chat-abc", query="Вопрос")
        state["response"] = "Ответ бота"
        state["query_type"] = "STRUCTURED"

        result = await history_store_node(state, history_service=history_service)

        history_service.store_qa_pair.assert_awaited_once_with(
            user_id=42,
            query="Вопрос",
            response="Ответ бота",
            session_id="chat-abc",
            query_type="STRUCTURED",
        )
        assert result["history_stored"] is True

    @pytest.mark.asyncio
    async def test_skips_empty_response(self):
        from telegram_bot.graph.nodes.history import history_store_node

        history_service = AsyncMock()
        state = make_initial_state(user_id=42, session_id="s", query="Q")
        state["response"] = ""

        result = await history_store_node(state, history_service=history_service)
        history_service.store_qa_pair.assert_not_awaited()
        assert result["history_stored"] is False

    @pytest.mark.asyncio
    async def test_handles_store_error_gracefully(self):
        from telegram_bot.graph.nodes.history import history_store_node

        history_service = AsyncMock()
        history_service.store_qa_pair = AsyncMock(side_effect=Exception("Qdrant down"))

        state = make_initial_state(user_id=42, session_id="s", query="Q")
        state["response"] = "Answer"

        result = await history_store_node(state, history_service=history_service)
        assert result["history_stored"] is False  # Graceful degradation
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_history_nodes.py::TestHistoryStoreNode -v`
Expected: FAIL — module not found

**Step 3: Implement history_store_node**

Create `telegram_bot/graph/nodes/history.py`:

```python
"""History nodes — store and recall conversation Q&A pairs.

history_store_node: saves Q&A pair to Qdrant after generation
history_recall_node: searches past Q&A for context injection
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langfuse import observe

logger = logging.getLogger(__name__)


@observe(name="node-history-store", capture_input=False, capture_output=False)
async def history_store_node(
    state: dict[str, Any],
    *,
    history_service: Any,
) -> dict[str, Any]:
    """Store current Q&A pair in conversation history (Qdrant).

    Runs after cache_store. Gracefully degrades on errors.
    """
    response = state.get("response", "")
    if not response:
        return {"history_stored": False}

    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )

    if not query:
        return {"history_stored": False}

    start = time.perf_counter()
    try:
        await history_service.store_qa_pair(
            user_id=state.get("user_id", 0),
            query=query,
            response=response,
            session_id=state.get("session_id", ""),
            query_type=state.get("query_type", "GENERAL"),
        )
        latency = time.perf_counter() - start
        logger.info("history_store: saved Q&A (%.0fms)", latency * 1000)
        return {"history_stored": True}
    except Exception:
        logger.warning("history_store: failed to save Q&A", exc_info=True)
        return {"history_stored": False}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/graph/test_history_nodes.py::TestHistoryStoreNode -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/history.py tests/unit/graph/test_history_nodes.py
git commit -m "feat(memory): add history_store_node for Qdrant Q&A persistence"
```

---

## Task 6: history_recall_node — search history for context

**Files:**
- Modify: `telegram_bot/graph/nodes/history.py` (append)
- Modify: `tests/unit/graph/test_history_nodes.py` (append)

**Step 1: Write the failing tests**

Append to `tests/unit/graph/test_history_nodes.py`:

```python
class TestHistoryRecallNode:
    @pytest.mark.asyncio
    async def test_searches_user_history(self):
        from telegram_bot.graph.nodes.history import history_recall_node

        history_service = AsyncMock()
        history_service.search_history = AsyncMock(return_value=[
            {"query": "Старый вопрос", "response": "Старый ответ", "score": 0.9},
        ])

        state = make_initial_state(user_id=42, session_id="s", query="Новый вопрос")
        result = await history_recall_node(state, history_service=history_service)

        history_service.search_history.assert_awaited_once_with(
            user_id=42, query="Новый вопрос", limit=3,
        )
        assert len(result["history_context"]) == 1
        assert result["history_context"][0]["query"] == "Старый вопрос"

    @pytest.mark.asyncio
    async def test_skips_chitchat(self):
        from telegram_bot.graph.nodes.history import history_recall_node

        history_service = AsyncMock()
        state = make_initial_state(user_id=42, session_id="s", query="Привет")
        state["query_type"] = "CHITCHAT"

        result = await history_recall_node(state, history_service=history_service)
        history_service.search_history.assert_not_awaited()
        assert result["history_context"] == []

    @pytest.mark.asyncio
    async def test_handles_search_error_gracefully(self):
        from telegram_bot.graph.nodes.history import history_recall_node

        history_service = AsyncMock()
        history_service.search_history = AsyncMock(side_effect=Exception("timeout"))

        state = make_initial_state(user_id=42, session_id="s", query="Вопрос")
        state["query_type"] = "GENERAL"

        result = await history_recall_node(state, history_service=history_service)
        assert result["history_context"] == []  # Graceful degradation
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_history_nodes.py::TestHistoryRecallNode -v`
Expected: FAIL — `history_recall_node` not found

**Step 3: Implement history_recall_node**

Append to `telegram_bot/graph/nodes/history.py`:

```python
_SKIP_RECALL_TYPES = frozenset({"CHITCHAT", "OFF_TOPIC"})
_DEFAULT_RECALL_LIMIT = 3


@observe(name="node-history-recall", capture_input=False, capture_output=False)
async def history_recall_node(
    state: dict[str, Any],
    *,
    history_service: Any,
) -> dict[str, Any]:
    """Search conversation history for relevant past Q&A.

    Runs after classify, before cache_check. Skips for CHITCHAT/OFF_TOPIC.
    """
    query_type = state.get("query_type", "GENERAL")
    if query_type in _SKIP_RECALL_TYPES:
        return {"history_context": []}

    messages = state.get("messages") or []
    last_msg = messages[-1] if messages else {}
    query = (
        last_msg.content
        if hasattr(last_msg, "content")
        else (last_msg.get("content", "") if isinstance(last_msg, dict) else "")
    )

    if not query:
        return {"history_context": []}

    start = time.perf_counter()
    try:
        results = await history_service.search_history(
            user_id=state.get("user_id", 0),
            query=query,
            limit=_DEFAULT_RECALL_LIMIT,
        )
        latency = time.perf_counter() - start
        logger.info(
            "history_recall: found %d results (%.0fms)", len(results), latency * 1000,
        )
        return {"history_context": results}
    except Exception:
        logger.warning("history_recall: search failed", exc_info=True)
        return {"history_context": []}
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/graph/test_history_nodes.py -v`
Expected: 6 PASSED (3 store + 3 recall)

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/history.py tests/unit/graph/test_history_nodes.py
git commit -m "feat(memory): add history_recall_node for past Q&A context injection"
```

---

## Task 7: Add state fields + wire nodes into graph

**Files:**
- Modify: `telegram_bot/graph/state.py` (lines 13-51 — add 2 fields)
- Modify: `telegram_bot/graph/graph.py` (lines 17-137 — add nodes + edges)
- Modify: `telegram_bot/graph/edges.py` (add route_after_classify)
- Modify: `telegram_bot/bot.py` (~line 159 — init ConversationHistoryService)
- Test: `tests/unit/graph/test_state.py` (existing — add fields check)

**Step 1: Add state fields**

In `telegram_bot/graph/state.py`, add to RAGState TypedDict (after `streaming_enabled`):

```python
    # Conversation memory
    history_context: list[dict[str, Any]]
    history_stored: bool
```

In `make_initial_state`, add to the return dict:

```python
        "history_context": [],
        "history_stored": False,
```

**Step 2: Update build_graph to accept history_service**

In `telegram_bot/graph/graph.py`, add parameter to `build_graph`:

```python
def build_graph(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
    message: Any | None = None,
    checkpointer: Any | None = None,
    event_stream: Any | None = None,
    history_service: Any | None = None,  # NEW
) -> Any:
```

Add import at top of function body (after existing imports ~line 48):

```python
    from telegram_bot.graph.nodes.history import history_recall_node, history_store_node
```

Add nodes after `classify` (~line 53) and before `respond` (~line 93):

```python
    # History recall — search past Q&A for context (after classify, before cache_check)
    if history_service is not None:
        workflow.add_node(
            "history_recall",
            functools.partial(history_recall_node, history_service=history_service),
        )

    # ... existing nodes ...

    # History store — save Q&A to Qdrant (after cache_store, before respond)
    if history_service is not None:
        workflow.add_node(
            "history_store",
            functools.partial(history_store_node, history_service=history_service),
        )
```

Update edges — replace the classify→cache_check edge:

```python
    # Edge: classify → history_recall → cache_check (or classify → cache_check if no history)
    if history_service is not None:
        workflow.add_conditional_edges(
            "classify",
            route_by_query_type,
            {
                "respond": "respond",
                "cache_check": "history_recall",  # Route through history_recall first
            },
        )
        workflow.add_edge("history_recall", "cache_check")
    else:
        workflow.add_conditional_edges(
            "classify",
            route_by_query_type,
            {
                "respond": "respond",
                "cache_check": "cache_check",
            },
        )

    # ... existing edges (cache_check → retrieve → grade etc.) ...

    # Edge: cache_store → history_store → respond (or cache_store → respond if no history)
    if history_service is not None:
        workflow.add_edge("cache_store", "history_store")
        workflow.add_edge("history_store", "respond")
    else:
        workflow.add_edge("cache_store", "respond")
```

Remove the old edges that are now conditional:
- Remove: `workflow.add_edge("cache_store", "respond")` (line 134) — now conditional above

**Step 3: Wire in bot.py**

In `telegram_bot/bot.py`, in `__init__` (after qdrant init, ~line 165):

```python
        from telegram_bot.services.conversation_history import ConversationHistoryService
        from telegram_bot.services.conversation_history_init import ensure_collection

        self._history_service: ConversationHistoryService | None = None
        if config.conversation_db_uri:  # Only enable if DB configured
            self._history_service = ConversationHistoryService(
                qdrant_client=self._qdrant._client,  # reuse existing async client
                embeddings=self._hybrid,
                collection_name=config.qdrant_conversation_collection,
            )
```

Add to BotConfig in `config.py`:

```python
    qdrant_conversation_collection: str = Field(
        default="conversation_history",
        validation_alias=AliasChoices(
            "CONVERSATION_COLLECTION", "qdrant_conversation_collection"
        ),
    )
```

In `handle_query`, pass to build_graph:

```python
            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
                checkpointer=self._checkpointer,
                history_service=self._history_service,  # NEW
            )
```

**Step 4: Run existing tests**

Run: `uv run pytest tests/unit/graph/ -x -q`
Expected: All pass (history_service=None → old behavior preserved)

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: All pass (no history_service → old edges)

**Step 5: Commit**

```bash
git add telegram_bot/graph/state.py telegram_bot/graph/graph.py telegram_bot/graph/edges.py telegram_bot/bot.py telegram_bot/config.py
git commit -m "feat(memory): wire history nodes into LangGraph pipeline"
```

---

## Task 8: Inject history_context into generate_node prompt

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py` (~line 228 — system prompt)
- Test: `tests/unit/graph/test_generate_node.py` (add test)

**Step 1: Write the failing test**

Add to `tests/unit/graph/test_generate_node.py`:

```python
class TestHistoryContextInjection:
    @pytest.mark.asyncio
    async def test_includes_history_in_system_prompt(self):
        """When history_context is present, it appears in LLM messages."""
        from telegram_bot.graph.nodes.generate import _build_llm_messages

        history_context = [
            {"query": "Старый вопрос", "response": "Старый ответ"},
        ]
        messages = _build_llm_messages(
            system_prompt="You are helpful.",
            context="Doc context here",
            query="Новый вопрос",
            conversation_history=[],
            history_context=history_context,
        )
        system_content = messages[0]["content"]
        assert "Старый вопрос" in system_content
        assert "Старый ответ" in system_content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestHistoryContextInjection -v`
Expected: FAIL — `_build_llm_messages` signature mismatch

**Step 3: Implement history injection in generate_node**

In `telegram_bot/graph/nodes/generate.py`, modify message building (~line 228) to include history_context from state:

```python
    # After building system_prompt and context:
    history_context = state.get("history_context") or []
    if history_context:
        history_text = "\n".join(
            f"Q: {h['query']}\nA: {h['response']}"
            for h in history_context[:3]
        )
        system_prompt += f"\n\n## Relevant past conversations:\n{history_text}"
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/graph/test_generate_node.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "feat(memory): inject history_context into generate_node prompt"
```

---

## Task 9: Integration test — full pipeline with history

**Files:**
- Modify: `tests/integration/test_graph_paths.py` (add test)

**Step 1: Write the integration test**

Add to `tests/integration/test_graph_paths.py`:

```python
class TestHistoryPipeline:
    @pytest.mark.asyncio
    async def test_full_path_with_history_service(self):
        """End-to-end: classify → history_recall → cache_check → retrieve → ... → history_store → respond."""
        from telegram_bot.graph.graph import build_graph
        from telegram_bot.graph.state import make_initial_state

        history_service = AsyncMock()
        history_service.search_history = AsyncMock(return_value=[
            {"query": "Прошлый вопрос", "response": "Прошлый ответ", "score": 0.85},
        ])
        history_service.store_qa_pair = AsyncMock()

        mocks = _make_graph_mocks()
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
            history_service=history_service,
        )

        state = make_initial_state(user_id=1, session_id="s", query="Новый вопрос")
        result = await graph.ainvoke(state)

        # history_recall was called
        history_service.search_history.assert_awaited_once()
        # history_store was called
        history_service.store_qa_pair.assert_awaited_once()
        # Pipeline completed
        assert result["response"]
        assert result["history_stored"] is True
        assert len(result["history_context"]) == 1

    @pytest.mark.asyncio
    async def test_chitchat_skips_history_recall(self):
        """CHITCHAT should skip history_recall but still go through history_store."""
        from telegram_bot.graph.graph import build_graph
        from telegram_bot.graph.state import make_initial_state

        history_service = AsyncMock()
        history_service.search_history = AsyncMock()
        history_service.store_qa_pair = AsyncMock()

        mocks = _make_graph_mocks()
        graph = build_graph(
            cache=mocks["cache"],
            embeddings=mocks["embeddings"],
            sparse_embeddings=mocks["sparse_embeddings"],
            qdrant=mocks["qdrant"],
            reranker=mocks["reranker"],
            llm=mocks["llm"],
            message=mocks["message"],
            history_service=history_service,
        )

        state = make_initial_state(user_id=1, session_id="s", query="Привет!")
        result = await graph.ainvoke(state)

        # CHITCHAT goes to respond directly, skips history_recall
        assert result["query_type"] == "CHITCHAT"
```

**Step 2: Run test**

Run: `uv run pytest tests/integration/test_graph_paths.py::TestHistoryPipeline -v`
Expected: 2 PASSED

**Step 3: Commit**

```bash
git add tests/integration/test_graph_paths.py
git commit -m "test(memory): add integration tests for history pipeline"
```

---

## Task 10: Collection init on bot startup

**Files:**
- Modify: `telegram_bot/bot.py` (startup hook)

**Step 1: Add collection init to bot startup**

In `telegram_bot/bot.py`, find the startup initialization (likely in `start()` or `__init__`). After cache initialization, add:

```python
        # Ensure conversation_history collection exists
        if self._history_service is not None:
            from telegram_bot.services.conversation_history_init import ensure_collection

            await ensure_collection(
                self._qdrant._client,
                self._config.qdrant_conversation_collection,
            )
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ -x -q`
Expected: All pass

**Step 3: Run lint + types**

Run: `make check`
Expected: Clean (or fix any issues)

**Step 4: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(memory): init conversation_history collection on bot startup"
```

---

## Task 11: Docker env vars + documentation

**Files:**
- Modify: `docker-compose.dev.yml` (bot service env)
- Modify: `.env.example`

**Step 1: Add env vars to docker-compose.dev.yml**

In the bot service section, add:

```yaml
      CONVERSATION_DB_URI: postgresql://postgres:postgres@postgres:5432/conversation
      CONVERSATION_COLLECTION: conversation_history
```

**Step 2: Add to .env.example**

```bash
# Conversation Memory
CONVERSATION_DB_URI=postgresql://postgres:postgres@postgres:5432/conversation
CONVERSATION_COLLECTION=conversation_history
```

**Step 3: Commit**

```bash
git add docker-compose.dev.yml .env.example
git commit -m "feat(memory): add conversation memory env vars to Docker config"
```

---

## Task 12: Verification — end-to-end with Docker

**Step 1: Recreate postgres to pick up new init script**

Run: `docker compose -f docker-compose.dev.yml down postgres && docker compose -f docker-compose.dev.yml up -d postgres`

Verify DB exists:
Run: `docker exec dev-postgres psql -U postgres -c "\l" | grep conversation`
Expected: `conversation` database listed

**Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ -x -q`
Expected: All pass

**Step 3: Run lint + types**

Run: `make check`
Expected: Clean

---

## Summary

| Task | What | Files | Est. |
|------|------|-------|------|
| 1 | psycopg dep + conversation DB | pyproject.toml, init SQL | 5 min |
| 2 | AsyncPostgresSaver factory | memory.py, bot.py, config.py | 15 min |
| 3 | ConversationHistoryService | services/conversation_history.py | 20 min |
| 4 | Collection init script | services/conversation_history_init.py | 10 min |
| 5 | history_store_node | graph/nodes/history.py | 15 min |
| 6 | history_recall_node | graph/nodes/history.py | 15 min |
| 7 | Wire into graph + state | graph.py, state.py, bot.py | 20 min |
| 8 | Inject history into generate | generate.py | 10 min |
| 9 | Integration tests | test_graph_paths.py | 15 min |
| 10 | Collection init on startup | bot.py | 5 min |
| 11 | Docker env vars | docker-compose, .env.example | 5 min |
| 12 | E2E verification | Docker + tests | 10 min |
| **Total** | | | **~2.5 hours** |

## Phase 2 (deferred)

- LangMem background fact extraction
- PostgresStore for user profiles
- Manager search UI/command
- Retention jobs (pg_cron)
- Summarization pipeline
