# Runtime Stabilization (#570) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate noisy runtime warnings/tracebacks (Postgres catalog, ColBERT vector, Qdrant insecure, Kommo CRM) + optimize Qdrant and Redis configuration based on February 2026 best practices audit.

**Architecture:** Phase 1 (Tasks 1-6): runtime fixes with TDD. Phase 2 (Task 7): operational migration. Phase 3 (Tasks 8-12): Qdrant/Redis optimization. Phase 4 (Task 13): final verification.

**Tech Stack:** asyncpg, qdrant-client (gRPC), BGE-M3 (/encode/hybrid), Redis 8.6, pytest + pytest-httpx

**Issue:** https://github.com/yastman/rag/issues/570

**Execution Rule (AGENTS):** run pytest with `-n auto --dist=worksteal` for all steps below.

> **Plan review note (2026-02-22):**
> - Corrected test scope to existing bot lifecycle suite (`tests/unit/test_bot_handlers.py`) instead of `tests/unit/test_bot_config.py`.
> - Fixed Qdrant vector validation logic: `dense`/`colbert` are in `params.vectors`, while `bm42` is in `params.sparse_vectors`.
> - Added mandatory repository validation gate for runtime changes: `make check` and `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`.
> - Kept Task 7 recreate flow, but added safety guardrail (snapshot + explicit destructive step warning).
> - **v2 (2026-02-22):** Added Phase 3 optimization tasks (8-12) from Qdrant+Redis audit. Added scaling recommendations appendix.
> - **v3 (2026-02-22):** Re-audited new tasks; corrected Task 11 to use `config.qdrant_timeout` (no timeout hardcode), expanded Task 8 test scope to include `tests/unit/services/test_redis_monitor.py`, softened Task 9/10 persistence/performance wording to avoid over-claims, and normalized Task 12 reference checks to plain `rg`.

---

## Phase 1: Runtime Fixes (Tasks 1-6)

### Task 1: PostgreSQL — Preflight Validation + Graceful Pool Init

**Problem:** `asyncpg.create_pool()` is lazy — doesn't validate DB exists. Every `get_locale`/`get_role` call logs full traceback. Preflight doesn't check Postgres at all.

**Files:**
- Modify: `telegram_bot/preflight.py:40-47` (add postgres to DEP_CLASSIFICATION)
- Modify: `telegram_bot/preflight.py:193-262` (add _check_single_dep case)
- Modify: `telegram_bot/preflight.py:313` (add to dep_order)
- Test: `tests/unit/test_preflight.py`

**Step 1: Write failing test — preflight postgres check**

In `tests/unit/test_preflight.py`, add:

```python
class TestPostgresPreflight:
    """Postgres preflight check validates database existence."""

    @pytest.mark.asyncio
    async def test_postgres_check_passes_when_db_exists(self):
        """Preflight passes when Postgres connection succeeds."""
        config = _make_config(realestate_database_url="postgresql://u:p@localhost/realestate")
        with patch("telegram_bot.preflight.asyncpg") as mock_asyncpg:
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=1)
            mock_conn.close = AsyncMock()
            mock_asyncpg.connect = AsyncMock(return_value=mock_conn)

            client = AsyncMock()
            result = await _check_single_dep("postgres", config, client)
            assert result is True

    @pytest.mark.asyncio
    async def test_postgres_check_fails_when_db_missing(self):
        """Preflight fails when database does not exist."""
        import asyncpg as real_asyncpg

        config = _make_config(realestate_database_url="postgresql://u:p@localhost/realestate")
        with patch("telegram_bot.preflight.asyncpg") as mock_asyncpg:
            mock_asyncpg.connect = AsyncMock(
                side_effect=real_asyncpg.InvalidCatalogNameError('database "realestate" does not exist')
            )

            client = AsyncMock()
            result = await _check_single_dep("postgres", config, client)
            assert result is False

    @pytest.mark.asyncio
    async def test_postgres_in_dep_classification_as_optional(self):
        """Postgres is OPTIONAL — bot degrades without it."""
        from telegram_bot.preflight import DEP_CLASSIFICATION, DepLevel
        assert DEP_CLASSIFICATION.get("postgres") == DepLevel.OPTIONAL
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_preflight.py::TestPostgresPreflight -n auto --dist=worksteal -v`
Expected: FAIL (postgres not in DEP_CLASSIFICATION, _check_single_dep has no "postgres" case)

**Step 3: Implement preflight postgres check**

In `telegram_bot/preflight.py`:

a) Add import at top (after existing imports):
```python
import asyncpg
```

b) Add to DEP_CLASSIFICATION (line 40-47):
```python
DEP_CLASSIFICATION: dict[str, DepLevel] = {
    "redis": DepLevel.CRITICAL,
    "redis_cache": DepLevel.CRITICAL,
    "qdrant": DepLevel.CRITICAL,
    "bge_m3": DepLevel.CRITICAL,
    "postgres": DepLevel.OPTIONAL,
    "litellm": DepLevel.OPTIONAL,
    "langfuse": DepLevel.OPTIONAL,
}
```

c) Add handler in `_check_single_dep` (before the "litellm" block):
```python
if name == "postgres":
    try:
        conn = await asyncpg.connect(config.realestate_database_url, timeout=5)
        try:
            await conn.fetchval("SELECT 1")
            logger.info("Preflight Postgres: database reachable")
            return True
        finally:
            await conn.close()
    except asyncpg.InvalidCatalogNameError:
        logger.warning(
            "Preflight WARN: Postgres database does not exist "
            "(user features will use defaults)"
        )
        return False
    except Exception as exc:
        logger.warning("Preflight WARN: Postgres unreachable — %s", exc)
        return False
```

d) Add to dep_order (line 313):
```python
dep_order = ["redis", "redis_cache", "qdrant", "bge_m3", "postgres", "litellm", "langfuse"]
```

e) Update `_make_config` in test file to include `realestate_database_url`:
```python
cfg.realestate_database_url = overrides.get(
    "realestate_database_url", "postgresql://postgres:postgres@localhost:5432/realestate"
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_preflight.py::TestPostgresPreflight -n auto --dist=worksteal -v`
Expected: PASS

**Step 5: Write test — bot skips pool when preflight marks postgres failed**

In `tests/unit/test_preflight.py` add:
```python
class TestPostgresOptionalBehavior:
    @pytest.mark.asyncio
    async def test_postgres_optional_does_not_block_startup(self):
        """Postgres failure does not raise PreflightError."""
        config = _make_config(realestate_database_url="postgresql://u:p@localhost/missing")

        async def fake_optional(name, cfg, client):
            # Mark optional checks as failed; only assertion that matters is no PreflightError.
            return False

        with (
            patch(
                "telegram_bot.preflight._check_critical_with_retry",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("telegram_bot.preflight._check_single_dep", side_effect=fake_optional),
        ):
            results = await check_dependencies(config)

        assert results["postgres"] is False
```

Note: this test verifies the integration. The exact mock setup depends on dep_order iteration. Simplify if needed by checking that PreflightError is not raised.

**Step 6: Run tests**

Run: `uv run pytest tests/unit/test_preflight.py -n auto --dist=worksteal -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add telegram_bot/preflight.py tests/unit/test_preflight.py
git diff --cached --stat
git commit -m "feat(preflight): add Postgres database existence check (#570)

Adds 'postgres' as OPTIONAL dependency in preflight checks.
Validates database exists via asyncpg.connect + SELECT 1.
Logs one-line WARNING instead of traceback spam on every query.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: PostgreSQL — Skip Pool Creation When DB Missing

**Problem:** Bot creates asyncpg pool even when DB doesn't exist, then every query logs full traceback.

**Files:**
- Modify: `telegram_bot/bot.py:2030-2044` (validate DB before pool)
- Test: `tests/unit/test_bot_handlers.py`

**Step 1: Write failing test**

In `tests/unit/test_bot_handlers.py`, add a startup lifecycle test (same pattern as existing `start()` tests):

```python
class TestPostgresPoolInit:
    @pytest.mark.asyncio
    async def test_pg_pool_skipped_when_db_missing(self, mock_config):
        """Pool not created when asyncpg.connect raises InvalidCatalogNameError."""
        import asyncpg

        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot._cache.redis = MagicMock()
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        mock_checkpointer = AsyncMock()

        with (
            patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock),
            patch(
                "telegram_bot.integrations.memory.create_redis_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "asyncpg.connect",
                AsyncMock(side_effect=asyncpg.InvalidCatalogNameError("database does not exist")),
            ),
            patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        ):
            await bot.start()

        mock_create_pool.assert_not_awaited()
        assert bot._pg_pool is None
        assert bot._user_service is None
```

Note: keep this in `test_bot_handlers.py` where startup lifecycle helpers already exist.

**Step 2: Implement validation in bot.py**

Replace `bot.py:2030-2040` with:

```python
# Initialize PostgreSQL pool for realestate DB
try:
    import asyncpg

    # Validate DB exists before creating pool (avoid traceback spam #570)
    test_conn = await asyncpg.connect(
        self.config.realestate_database_url, timeout=5
    )
    await test_conn.close()

    self._pg_pool = await asyncpg.create_pool(
        self.config.realestate_database_url,
        min_size=0,
        max_size=5,
        timeout=5,
    )
    logger.info("PostgreSQL pool ready (realestate)")
```

This way, if DB doesn't exist, `asyncpg.connect` raises `InvalidCatalogNameError` which is caught by the existing postgres init `except Exception` block, and `_user_service` stays None.

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_bot_handlers.py -k postgres -n auto --dist=worksteal -v`
Expected: PASS

**Step 4: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git diff --cached --stat
git commit -m "fix(bot): validate Postgres DB exists before creating pool (#570)

Pre-flight asyncpg.connect() catches InvalidCatalogNameError once at
startup instead of logging full traceback on every get_locale/get_role.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Qdrant — Conditional api_key for Insecure Transport

**Problem:** `Api key is used with an insecure connection` warning at qdrant.py:51 and preflight.py:213.

**Files:**
- Modify: `telegram_bot/services/qdrant.py:51-52`
- Modify: `telegram_bot/preflight.py:213`
- Test: `tests/unit/test_qdrant_service.py`

**Step 1: Write failing test**

In `tests/unit/test_qdrant_service.py`:

```python
class TestQdrantApiKeySafety:
    """api_key should be None for http:// URLs to avoid insecure warning."""

    def test_api_key_stripped_for_http(self):
        """HTTP URL + api_key -> api_key=None (no insecure warning)."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as MockClient:
            QdrantService(url="http://localhost:6333", api_key="test-key")
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["api_key"] is None

    def test_api_key_kept_for_https(self):
        """HTTPS URL + api_key -> api_key passed through."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as MockClient:
            QdrantService(url="https://qdrant.example.com:6333", api_key="test-key")
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["api_key"] == "test-key"

    def test_no_api_key_no_change(self):
        """No api_key -> None regardless of scheme."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as MockClient:
            QdrantService(url="http://localhost:6333", api_key=None)
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["api_key"] is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantApiKeySafety -n auto --dist=worksteal -v`
Expected: FAIL (api_key="test-key" passed to HTTP URL)

**Step 3: Implement conditional api_key**

In `telegram_bot/services/qdrant.py`, add import and replace lines 51-53:

```python
from urllib.parse import urlparse

...

# Strip api_key for http:// to avoid "insecure connection" warning (#570)
scheme = urlparse(url).scheme.lower()
effective_api_key = api_key if scheme == "https" else None
self._client = AsyncQdrantClient(
    url=url, api_key=effective_api_key, prefer_grpc=True, timeout=timeout
)
```

In `telegram_bot/preflight.py`, add import and replace line 213:

```python
from urllib.parse import urlparse

...

# In _check_single_dep, "qdrant" block:
scheme = urlparse(config.qdrant_url).scheme.lower()
effective_key = config.qdrant_api_key if scheme == "https" else None
qdrant = AsyncQdrantClient(url=config.qdrant_url, api_key=effective_key)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_qdrant_service.py::TestQdrantApiKeySafety -n auto --dist=worksteal -v`
Expected: PASS

**Step 5: Run full qdrant + preflight tests**

Run: `uv run pytest tests/unit/test_qdrant_service.py tests/unit/test_preflight.py -n auto --dist=worksteal -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add telegram_bot/services/qdrant.py telegram_bot/preflight.py tests/unit/test_qdrant_service.py
git diff --cached --stat
git commit -m "fix(qdrant): strip api_key for http:// URLs (#570)

Prevents 'Api key is used with an insecure connection' warning.
api_key only sent when URL starts with https://.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Kommo CRM — Pre-validate Tokens Before initialize()

**Problem:** Full RuntimeError traceback on every startup when auth_code missing and no tokens in Redis — expected case, not an error.

**Files:**
- Modify: `telegram_bot/bot.py:1998-2028` (pre-validate before initialize)
- Test: `tests/unit/test_bot_handlers.py`

**Step 1: Write failing test**

```python
class TestKommoGracefulInit:
    """Kommo init logs INFO (not WARNING+traceback) when tokens unavailable."""

    @pytest.mark.asyncio
    async def test_kommo_missing_tokens_logs_info_not_warning(self, mock_config, caplog):
        mock_config.kommo_enabled = True
        mock_config.kommo_subdomain = "test"
        mock_config.kommo_auth_code = ""

        bot, _ = _create_bot(mock_config)
        bot._cache = MagicMock()
        bot._cache.initialize = AsyncMock()
        bot._cache.redis = AsyncMock()
        bot._cache.redis.hgetall = AsyncMock(return_value={})
        bot.dp = MagicMock()
        bot.dp.start_polling = AsyncMock()
        bot._redis_monitor = MagicMock()
        bot._redis_monitor.start = AsyncMock()
        bot.bot = MagicMock()
        bot.bot.set_my_commands = AsyncMock()

        mock_checkpointer = AsyncMock()
        with (
            patch("telegram_bot.preflight.check_dependencies", new_callable=AsyncMock),
            patch(
                "telegram_bot.integrations.memory.create_redis_checkpointer",
                return_value=mock_checkpointer,
            ),
            caplog.at_level(logging.INFO),
        ):
            await bot.start()

        assert "Kommo CRM disabled" in caplog.text
        assert "Kommo CRM init failed" not in caplog.text
        assert bot._kommo_client is None
```

**Step 2: Implement pre-validation**

In `telegram_bot/bot.py`, keep one flow (no sentinel exceptions), and reuse the canonical key from `kommo_tokens`:

```python
from .services.kommo_tokens import KommoTokenStore, REDIS_KEY

...
auth_code = self.config.kommo_auth_code or None
should_init_kommo = True
if auth_code is None:
    existing = await self._cache.redis.hgetall(REDIS_KEY)
    if not existing:
        logger.info(
            "Kommo CRM disabled: no stored tokens and no KOMMO_AUTH_CODE "
            "(set env var for first-time setup)"
        )
        self._kommo_client = None
        should_init_kommo = False

if should_init_kommo:
    await token_store.initialize(authorization_code=auth_code)
    self._kommo_client = KommoClient(
        subdomain=self.config.kommo_subdomain,
        token_store=token_store,
    )
```

Implementation constraints:
- Do not raise artificial sentinel exceptions for control flow.
- Keep unexpected/network/auth failures under existing `except Exception` warning path.
- Avoid code duplication for `KommoTokenStore` + `KommoClient` creation.

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_bot_handlers.py -k kommo -n auto --dist=worksteal -v`
Expected: PASS

**Step 4: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git diff --cached --stat
git commit -m "fix(kommo): pre-validate tokens before initialize() (#570)

Checks Redis for existing tokens before calling initialize().
Missing tokens + no auth_code -> INFO one-liner (no traceback).
Actual init errors (network, invalid creds) still log WARNING.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Preflight — Validate Qdrant Collection Vector Names

**Problem:** Preflight checks collection exists (points count) but not that required vectors are configured (`dense` in named vectors + `bm42` in sparse vectors). `colbert` should remain warning-only.

**Files:**
- Modify: `telegram_bot/preflight.py:211-226` (enhance qdrant check)
- Test: `tests/unit/test_preflight.py`

**Step 1: Write failing test**

```python
class TestQdrantVectorValidation:
    """Preflight validates required named vectors in collection."""

    @pytest.mark.asyncio
    async def test_qdrant_warns_when_colbert_vector_missing(self, caplog):
        """Missing colbert vector logged as warning."""
        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        # Simulate collection with dense + bm42 (no colbert)
        mock_collection_info.config.params.vectors = {
            "dense": MagicMock(),
        }
        mock_collection_info.config.params.sparse_vectors = {
            "bm42": MagicMock(),
        }
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is True  # Still passes (colbert is optional warning)
            assert "colbert" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_qdrant_no_warning_when_all_vectors_present(self, caplog):
        """No warning when dense + bm42 required vectors and colbert are present."""
        config = _make_config()
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 278
        mock_collection_info.config.params.vectors = {
            "dense": MagicMock(),
            "colbert": MagicMock(),
        }
        mock_collection_info.config.params.sparse_vectors = {
            "bm42": MagicMock(),
        }
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch("telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant):
            client = AsyncMock()
            result = await _check_single_dep("qdrant", config, client)
            assert result is True
            assert "missing" not in caplog.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_preflight.py::TestQdrantVectorValidation -n auto --dist=worksteal -v`
Expected: FAIL (no vector name validation in current code)

**Step 3: Implement vector name validation**

In `telegram_bot/preflight.py`, replace qdrant check (lines 211-226):

```python
if name == "qdrant":
    collection = config.qdrant_collection
    scheme = urlparse(config.qdrant_url).scheme.lower()
    effective_key = config.qdrant_api_key if scheme == "https" else None
    qdrant = AsyncQdrantClient(url=config.qdrant_url, api_key=effective_key)
    try:
        info = await qdrant.get_collection(collection)
        logger.info(
            "Preflight Qdrant: collection=%s, points=%s",
            collection,
            info.points_count,
        )

        # Validate expected vector configs (#570)
        dense_vectors = info.config.params.vectors
        sparse_vectors = info.config.params.sparse_vectors or {}
        dense_names = set(dense_vectors.keys()) if isinstance(dense_vectors, dict) else set()
        sparse_names = set(sparse_vectors.keys()) if isinstance(sparse_vectors, dict) else set()

        missing_required = set()
        if "dense" not in dense_names:
            missing_required.add("dense")
        if "bm42" not in sparse_names:
            missing_required.add("bm42")
        if missing_required:
            logger.error(
                "Preflight FAIL: Qdrant collection %s missing required vectors: %s",
                collection,
                sorted(missing_required),
            )
            return False

        if "colbert" not in dense_names:
            logger.warning(
                "Preflight WARN: Qdrant collection %s missing 'colbert' vector "
                "(server-side ColBERT reranking unavailable, RRF fallback active)",
                collection,
            )

        return True
    except Exception as exc:
        logger.error("Preflight FAIL: Qdrant — %s", exc)
        return False
    finally:
        await qdrant.close()
```

Note: also apply the `effective_key` fix from Task 3 here (conditional api_key).

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_preflight.py::TestQdrantVectorValidation -n auto --dist=worksteal -v`
Expected: PASS

**Step 5: Run all preflight tests**

Run: `uv run pytest tests/unit/test_preflight.py -n auto --dist=worksteal -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add telegram_bot/preflight.py tests/unit/test_preflight.py
git diff --cached --stat
git commit -m "feat(preflight): validate Qdrant collection vector names (#570)

Checks that 'dense' and 'bm42' vectors exist (required).
Warns if 'colbert' missing (server-side reranking unavailable).
Helps diagnose retrieval degradation at startup, not at query time.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: ColBERT Ingestion — Add ColBERT Vectors to Writer

**Problem:** Collection bootstrap already defines `colbert` vector (cli.py:219-225), but `qdrant_writer.py` never encodes/stores ColBERT vectors. Existing collection (278 points) was created before colbert was added to bootstrap.

**Files:**
- Modify: `src/ingestion/unified/qdrant_writer.py:101-109` (add encode_colbert)
- Modify: `src/ingestion/unified/qdrant_writer.py:298-306` (add colbert to point vector dict)
- Modify: `src/ingestion/unified/qdrant_writer.py:401-408` (same for sync version)
- Modify: `telegram_bot/services/bge_m3_client.py` (add sync `encode_colbert`)
- Test: `tests/unit/ingestion/test_payload_contract.py` (or new ingestion writer test)
- Test: `tests/unit/services/test_bge_m3_client.py` (sync colbert method)

**Step 1: Write failing test**

```python
class TestColbertVectorInUpsert:
    """Writer includes colbert multivectors in upserted points."""

    def test_upsert_point_has_colbert_vector(self):
        """Each point must have 'colbert' key in vector dict when local embeddings."""
        # Mock BGE client to return colbert vectors
        mock_bge = MagicMock()
        mock_bge.encode_dense.return_value = MagicMock(vectors=[[0.1] * 1024])
        mock_bge.encode_sparse.return_value = MagicMock(
            weights=[{"indices": [1, 2], "values": [0.5, 0.3]}]
        )
        # ColBERT returns list of token vectors per document
        mock_bge.encode_colbert.return_value = MagicMock(
            colbert_vecs=[[[0.1] * 1024, [0.2] * 1024]]  # 1 doc, 2 tokens
        )

        writer = QdrantHybridWriter(...)  # setup with mocks
        # Call upsert_chunks_sync with 1 chunk
        # Assert point.vector has "colbert" key
        # Assert colbert value is list[list[float]]
```

Note: exact test setup depends on QdrantHybridWriter constructor. Adapt mocks to match.

**Step 2: Implement ColBERT encoding in writer**

In `src/ingestion/unified/qdrant_writer.py`:

a) Add `encode_colbert` method:
```python
def _embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
    """Generate ColBERT multivectors via BGEM3SyncClient.

    Returns list of token vector lists (one per document).
    Each document's colbert is list[list[float]] (num_tokens x 1024).
    """
    if not texts:
        return []
    result = self._bge_client.encode_colbert(texts)
    return result.colbert_vecs
```

b) In `upsert_chunks` (async, line 278-305) and `upsert_chunks_sync` (line 370-408), add colbert encoding after sparse:
```python
sparse_embeddings = self._embed_sparse(texts)
colbert_embeddings = self._embed_colbert(texts) if self.use_local_embeddings else []
```

c) Update point vector dict:
```python
vector_dict = {
    "dense": dense_vec,
    "bm42": self._to_sparse_vector(sparse_emb),
}
if colbert_embeddings:
    vector_dict["colbert"] = colbert_embeddings[i]

point = PointStruct(
    id=point_id,
    vector=vector_dict,
    payload=payload,
)
```

**Step 3: Run test**

Run: `uv run pytest tests/unit/ingestion/test_payload_contract.py -n auto --dist=worksteal -v`
Expected: PASS

**Step 4: Add sync ColBERT method to BGEM3SyncClient**

In `telegram_bot/services/bge_m3_client.py`, add:

```python
def encode_colbert(self, texts: list[str]) -> ColbertResult:
    """Encode texts to ColBERT multivectors (sync)."""
    if not texts:
        return ColbertResult(colbert_vecs=[])
    resp = self._client.post(
        f"{self.base_url}/encode/colbert",
        json={"texts": texts, "max_length": self.max_length},
    )
    resp.raise_for_status()
    data = resp.json()
    return ColbertResult(
        colbert_vecs=data["colbert_vecs"],
        processing_time=data.get("processing_time"),
    )
```

Add unit test in `tests/unit/services/test_bge_m3_client.py` for `BGEM3SyncClient.encode_colbert`.

**Step 5: Run focused tests**

Run: `uv run pytest tests/unit/services/test_bge_m3_client.py tests/unit/ingestion/test_payload_contract.py -n auto --dist=worksteal -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/ingestion/unified/qdrant_writer.py telegram_bot/services/bge_m3_client.py tests/unit/ingestion/test_payload_contract.py tests/unit/services/test_bge_m3_client.py
git diff --cached --stat
git commit -m "feat(ingestion): add ColBERT multivector encoding to writer (#570)

qdrant_writer now calls encode_colbert() during ingestion and stores
colbert vectors alongside dense + sparse in each Qdrant point.
Only active with use_local_embeddings=True (BGE-M3).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: Operational Migration (Task 7)

### Task 7: Re-create Collection + Re-ingest

**Problem:** Existing collection (278 points) has no `colbert` vector field. As of 2026-02-22, adding a new named vector to an existing collection is still treated as unsupported in Qdrant maintainer guidance, so recreate + re-ingest is the safe path.

**This is a manual/operational task, not code change.**

**Steps:**
1. Stop bot: `Ctrl+C` the running bot.
2. Create backup snapshot before destructive change: `make qdrant-backup`.
3. Verify target collection exists on local Qdrant: `curl -s http://localhost:6333/collections | python -m json.tool`.
4. Delete old collection (destructive, irreversible without snapshot restore): `curl -X DELETE http://localhost:6333/collections/gdrive_documents_bge`.
5. Re-bootstrap: `uv run python -m src.ingestion.unified.cli bootstrap`.
   - This creates collection WITH colbert vector (cli.py:219-225).
6. Re-ingest: `make ingest-unified`.
   - Writer now stores colbert vectors (Task 6).
7. Verify: `curl -s http://localhost:6333/collections/gdrive_documents_bge | python -m json.tool`.
   - Check vectors config includes `"dense"` and `"colbert"`, and sparse vectors include `"bm42"`.
8. Start bot: `make run-bot`.
9. Verify no "Not existing vector name error: colbert" in logs.

**For VPS:** Same steps but via ssh + docker compose.

---

## Phase 3: Qdrant + Redis Optimization (Tasks 8-12)

### Task 8: Redis — Add Connection Pool Size Limit

**Problem:** `redis.from_url()` defaults to unlimited connections. Under load, bot can open hundreds of connections. Both `CacheLayerManager` and `RedisHealthMonitor` create separate pools without limits.

**Files:**
- Modify: `telegram_bot/integrations/cache.py:148-157` (add max_connections)
- Modify: `telegram_bot/services/redis_monitor.py:48-57` (add max_connections)
- Test: `tests/unit/integrations/test_cache_layers.py`
- Test: `tests/unit/services/test_redis_monitor.py`

**Step 1: Write failing test**

In `tests/unit/integrations/test_cache_layers.py`:

```python
class TestRedisPoolConfig:
    """Redis pool has explicit connection limit."""

    @pytest.mark.asyncio
    async def test_redis_pool_has_max_connections(self):
        """CacheLayerManager sets max_connections on Redis pool."""
        with patch("telegram_bot.integrations.cache.redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_redis.from_url.return_value = mock_client

            cache = CacheLayerManager(redis_url="redis://localhost:6379")
            await cache.initialize()

            call_kwargs = mock_redis.from_url.call_args[1]
            assert "max_connections" in call_kwargs
            assert call_kwargs["max_connections"] == 20
```

In `tests/unit/services/test_redis_monitor.py` add a focused startup assertion:

```python
async def test_start_sets_max_connections_for_monitor_pool():
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        await monitor.start()
        await monitor.stop()  # cleanup background task created by start()

    call_kwargs = mock_from_url.call_args[1]
    assert call_kwargs["max_connections"] == 5
```

**Step 2: Run test to verify it fails**

Run:
- `uv run pytest tests/unit/integrations/test_cache_layers.py::TestRedisPoolConfig -n auto --dist=worksteal -v`
- `uv run pytest tests/unit/services/test_redis_monitor.py -k max_connections -n auto --dist=worksteal -v`

Expected: FAIL (`max_connections` not passed yet)

**Step 3: Implement pool limit**

In `telegram_bot/integrations/cache.py`, line 148-157, add `max_connections=20`:

```python
self.redis = redis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=20,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    retry=Retry(ExponentialBackoff(), 3),
    health_check_interval=30,
)
```

In `telegram_bot/services/redis_monitor.py`, line 48-57, add same:

```python
self._redis = aioredis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=5,  # monitor needs fewer connections
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    retry=Retry(ExponentialBackoff(), 3),
    health_check_interval=30,
)
```

**Step 4: Run test to verify it passes**

Run:
- `uv run pytest tests/unit/integrations/test_cache_layers.py::TestRedisPoolConfig -n auto --dist=worksteal -v`
- `uv run pytest tests/unit/services/test_redis_monitor.py -k max_connections -n auto --dist=worksteal -v`

Expected: PASS

**Step 5: Run all cache tests**

Run:
- `uv run pytest tests/unit/integrations/test_cache_layers.py -n auto --dist=worksteal -v`
- `uv run pytest tests/unit/services/test_redis_monitor.py -n auto --dist=worksteal -v`

Expected: ALL PASS

**Step 6: Commit**

```bash
git add telegram_bot/integrations/cache.py telegram_bot/services/redis_monitor.py tests/unit/integrations/test_cache_layers.py tests/unit/services/test_redis_monitor.py
git diff --cached --stat
git commit -m "fix(redis): add explicit max_connections to Redis pools (#570)

CacheLayerManager: max_connections=20 (bot workload).
RedisHealthMonitor: max_connections=5 (low-frequency checks).
Prevents unbounded connection growth under load.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 9: Redis — Align Dev AOF with VPS (Disable for Cache)

**Problem:** Dev Redis explicitly sets `appendonly yes`, while k8s runtime config does not set AOF explicitly. This persistence-mode drift makes local behavior less representative; for dev cache/ephemeral workloads, AOF also adds write amplification.

**Files:**
- Modify: `docker-compose.dev.yml:56-62` (remove `--appendonly yes`)

**Guardrail:** Apply only if dev Redis is not being used as the sole durable store for critical data.

**Step 1: Remove AOF from dev compose**

In `docker-compose.dev.yml`, remove `--appendonly yes` from redis command (line 62):

```yaml
command: >
  redis-server
  --requirepass ${REDIS_PASSWORD:-dev_redis_pass}
  --maxmemory 512mb
  --maxmemory-policy volatile-lfu
  --maxmemory-samples 10
```

**Step 2: Verify Redis restarts without AOF**

```bash
docker compose -f docker-compose.dev.yml restart redis
docker exec dev-redis redis-cli -a "${REDIS_PASSWORD:-dev_redis_pass}" CONFIG GET appendonly
# Expected: appendonly -> no
```

**Step 3: Commit**

```bash
git add docker-compose.dev.yml
git diff --cached --stat
git commit -m "fix(redis): remove AOF from dev (align with VPS/k3s) (#570)

Removes explicit AOF override in dev compose to reduce write amplification
for dev cache/ephemeral data and reduce config drift with k8s runtime settings.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 10: k8s Redis — Bump Image to 8.6.0

**Problem:** k8s deployment uses `redis:8.4.0` while Docker Compose uses `redis:8.6.0`. Redis Open Source 8.6 adds `HOTKEYS` and reports performance/resource improvements vs 8.4 in official release notes/benchmarks; aligning versions reduces environment drift.

**Files:**
- Modify: `k8s/base/redis/deployment.yaml:23` (bump image)

**Step 1: Update image tag**

In `k8s/base/redis/deployment.yaml`, line 23, change:

```yaml
image: redis:8.6.0
```

**Step 2: Commit**

```bash
git add k8s/base/redis/deployment.yaml
git diff --cached --stat
git commit -m "chore(k8s): bump Redis 8.4.0 -> 8.6.0 (align with compose) (#570)

Redis 8.6 adds HOTKEYS and includes published performance/resource
improvements vs 8.4 in official release notes/benchmarks.
Aligns k8s with docker-compose images.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 11: Qdrant Preflight — Add Timeout + prefer_grpc

**Problem:** Preflight creates bare `AsyncQdrantClient` without timeout or gRPC and ignores `BotConfig.qdrant_timeout`, inconsistent with `QdrantService`. Can hang too long or diverge from runtime behavior when Qdrant is slow.

**Files:**
- Modify: `telegram_bot/preflight.py:213` (already modified in Task 3/5, add timeout + grpc)
- Test: `tests/unit/test_preflight.py`

**Step 1: Write failing test**

In `tests/unit/test_preflight.py`:

```python
class TestQdrantPreflightClient:
    """Preflight Qdrant client uses timeout and gRPC."""

    @pytest.mark.asyncio
    async def test_qdrant_preflight_uses_timeout_and_grpc(self):
        """Preflight uses BotConfig timeout and prefer_grpc=True."""
        config = _make_config(qdrant_timeout=42)
        mock_qdrant = AsyncMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 100
        mock_collection_info.config.params.vectors = {"dense": MagicMock()}
        mock_collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        mock_qdrant.get_collection = AsyncMock(return_value=mock_collection_info)
        mock_qdrant.close = AsyncMock()

        with patch(
            "telegram_bot.preflight.AsyncQdrantClient", return_value=mock_qdrant
        ) as MockClient:
            client = AsyncMock()
            await _check_single_dep("qdrant", config, client)

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("timeout") == config.qdrant_timeout
            assert call_kwargs.get("prefer_grpc") is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_preflight.py::TestQdrantPreflightClient -n auto --dist=worksteal -v`
Expected: FAIL (no timeout or prefer_grpc)

**Step 3: Update preflight Qdrant client**

In `telegram_bot/preflight.py`, update the Qdrant client creation (already modified in Tasks 3/5):

```python
qdrant = AsyncQdrantClient(
    url=config.qdrant_url,
    api_key=effective_key,
    timeout=config.qdrant_timeout,
    prefer_grpc=True,
)
```

If `qdrant_timeout` is missing in the test helper, add to `_make_config` in `tests/unit/test_preflight.py`:

```python
cfg.qdrant_timeout = overrides.get("qdrant_timeout", 30)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_preflight.py::TestQdrantPreflightClient -n auto --dist=worksteal -v`
Expected: PASS

**Step 5: Run all preflight tests**

Run: `uv run pytest tests/unit/test_preflight.py -n auto --dist=worksteal -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add telegram_bot/preflight.py tests/unit/test_preflight.py
git diff --cached --stat
git commit -m "fix(preflight): use qdrant_timeout + prefer_grpc in Qdrant client (#570)

Preflight Qdrant check now reuses BotConfig.qdrant_timeout and
prefer_grpc=True, matching runtime transport/timeout behavior and
avoiding divergent startup diagnostics.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 12: Cleanup Legacy Redis Script

**Problem:** `scripts/setup_redis_indexes.py` creates index `idx:rag:semantic_cache` with prefix `rag:semantic:`, but the actual semantic cache uses RedisVL index `sem:v5:bge1024`. The legacy script is dead code.

**Files:**
- Delete: `scripts/setup_redis_indexes.py` (if confirmed unused)

**Step 1: Verify script is unused**

Search for references:
```bash
rg "setup_redis_indexes" --type py
rg "idx:rag:semantic_cache" --type py
rg "rag:semantic:" --type py
```

If no references found (expected), delete the file.

**Step 2: Delete legacy script**

```bash
git rm scripts/setup_redis_indexes.py
```

**Step 3: Commit**

```bash
git diff --cached --stat
git commit -m "chore: remove legacy setup_redis_indexes.py (#570)

Script creates index idx:rag:semantic_cache with prefix rag:semantic:
but actual semantic cache uses RedisVL sem:v5:bge1024. Dead code.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 4: Final Verification (Task 13)

### Task 13: Final Verification

**Step 1: Run all affected tests**

```bash
uv run pytest \
  tests/unit/test_preflight.py \
  tests/unit/test_qdrant_service.py \
  tests/unit/test_bot_handlers.py \
  tests/unit/services/test_bge_m3_client.py \
  tests/unit/services/test_redis_monitor.py \
  tests/unit/ingestion/test_payload_contract.py \
  tests/unit/integrations/test_cache_layers.py \
  -n auto --dist=worksteal -v
```

**Step 2: Mandatory repository gates (runtime changes)**

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

**Step 3: Start bot and check clean startup**

```bash
make run-bot
```

Verify in logs:
- No `InvalidCatalogNameError` traceback
- No `Not existing vector name error: colbert`
- No `Api key is used with an insecure connection`
- Kommo: one-line INFO "disabled: no stored tokens..." (no traceback)
- Preflight: `postgres [OPTIONAL]` line present

**Step 4: Update GitHub issue**

```bash
gh issue edit 570 --repo yastman/rag --add-label "in-progress"
```

Check off completed items in issue body.

---

## Dependencies Between Tasks

```
Phase 1 (Runtime Fixes):
  Task 1 (preflight postgres) ──┐
  Task 2 (bot pool validation)  ├── Independent, can parallel
  Task 3 (qdrant api_key)       │
  Task 4 (kommo pre-validate)   │
  Task 5 (preflight vectors)  ──┘ (depends on Task 3 for effective_key pattern)
  Task 6 (colbert writer)     ──── Independent

Phase 2 (Migration):
  Task 7 (re-create + ingest) ──── Depends on Task 6

Phase 3 (Optimization):
  Task 8 (redis pool limit)   ──┐
  Task 9 (redis AOF)           ├── Independent, can parallel
  Task 10 (k8s redis image)    │
  Task 11 (qdrant preflight)   │ (depends on Tasks 3/5 for preflight qdrant block)
  Task 12 (legacy cleanup)   ──┘

Phase 4:
  Task 13 (final verification) ── Depends on all above
```

**Parallel groups:**
- **Group A (bot runtime):** Tasks 1, 2, 4 — all modify bot.py/preflight, some overlap
- **Group B (qdrant):** Tasks 3, 5, 11 — all modify preflight qdrant section
- **Group C (ingestion):** Task 6 — independent
- **Group D (infra optimization):** Tasks 8, 9, 10, 12 — independent files

**Recommended execution:** Tasks 1-6 sequentially (shared files), Task 7 operational, Tasks 8-12 in parallel, Task 13 after all.

## Test File Mapping

| Source File | Test File |
|-------------|-----------|
| `telegram_bot/preflight.py` | `tests/unit/test_preflight.py` |
| `telegram_bot/services/qdrant.py` | `tests/unit/test_qdrant_service.py` |
| `telegram_bot/bot.py` | `tests/unit/test_bot_handlers.py` |
| `telegram_bot/services/kommo_tokens.py` | `tests/unit/test_bot_handlers.py` |
| `telegram_bot/services/bge_m3_client.py` | `tests/unit/services/test_bge_m3_client.py` |
| `src/ingestion/unified/qdrant_writer.py` | `tests/unit/ingestion/test_payload_contract.py` |
| `telegram_bot/integrations/cache.py` | `tests/unit/integrations/test_cache_layers.py` |
| `telegram_bot/services/redis_monitor.py` | `tests/unit/services/test_redis_monitor.py` |

---

## Appendix: Qdrant Scaling Recommendations by Collection Size

Рекомендации по оптимизации Qdrant при разных масштабах коллекции:

| Точек | Поведение HNSW | Рекомендация |
|-------|----------------|-------------|
| **< 1,000** (сейчас: 278) | Flat scan (HNSW не строится, `indexing_threshold=20000`) | Оптимизации HNSW бесполезны. Binary quantization overhead > benefit. Текущая конфигурация ОК. |
| **1,000 – 20,000** | Flat scan продолжается (threshold=20000) | Можно снизить `indexing_threshold` до 5000 для раннего построения HNSW. Scalar INT8 quantization начинает окупаться. |
| **20,000 – 100,000** | HNSW строится автоматически | `m=16`, `ef_construct=200` — ОК. Добавить `ef=128` при query time для точности. Binary quantization может существенно ускорять поиск (точный прирост зависит от данных/CPU, проверять бенчмарком). `on_disk=True` для vectors экономит RAM. |
| **100,000 – 1,000,000** | HNSW критичен | Увеличить `m=32`, `ef_construct=300`. gRPC `pool_size=10+`. Scalar quantization (`always_ram=True`). `memmap_threshold=50000` ОК. ColBERT `on_disk=True` обязателен. |
| **> 1,000,000** | Шардирование | Несколько шардов (`shard_number`). Distributed mode. `m=48`, `ef_construct=400`. Payload indexes критичны для фильтрации. |

### Текущий профиль (278 точек, gdrive_documents_bge)

| Параметр | Значение | Статус |
|----------|---------|--------|
| HNSW m=16, ef_construct=200 | Не используется (flat scan) | OK — пригодится при росте |
| BinaryQuantization | Не используется (flat scan) | OK — overhead минимален |
| ColBERT m=0, on_disk=True | Корректно для rerank-only | OK |
| indexing_threshold=20000 | HNSW не строится при 278 точках | OK |
| memmap_threshold=50000 | Не активен | OK |
| 8 payload indexes | Больше чем нужно при 278, но не вредят | OK |
| gRPC pool_size | Default (3) | OK при текущей нагрузке |
| Timeout via `BotConfig.qdrant_timeout` (bot + preflight) | Consistent after Task 11 | FIX IN TASK 11 |

### Когда действовать

| Триггер | Действие |
|---------|----------|
| Коллекция > 5,000 точек | Снизить `indexing_threshold` до 5000 |
| Коллекция > 20,000 точек | Добавить `ef=128` при query, проверить quantization benefit |
| Concurrent users > 10 | Увеличить gRPC `pool_size` до 10 |
| Search latency > 200ms p95 | Включить scalar quantization + `always_ram=True` |
| RAM > 80% Qdrant container | `on_disk=True` для dense vectors (уже включено) |

### Redis Scaling Notes

| Точек/ключей | Рекомендация |
|--------------|-------------|
| < 10,000 keys (сейчас) | `maxmemory=256mb` достаточно. `volatile-lfu` корректен. |
| 10,000 – 100,000 keys | Рассмотреть numpy.tobytes() + LZ4 для embedding vectors (часто заметно снижает footprint, подтверждать на своих данных). |
| > 100,000 keys | `BlockingConnectionPool` вместо `ConnectionPool`. `maxmemory=512mb+`. |
| > 50 concurrent users | `ShallowRedisSaver` вместо `AsyncRedisSaver` для checkpoints. |
| Disk space concern | Отключать RDB snapshots (`save ""`) только если Redis хранит строго кэш/эпемерные ключи и потеря данных при рестарте приемлема. |
