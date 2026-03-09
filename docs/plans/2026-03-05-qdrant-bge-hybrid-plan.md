# BGE-M3 Hybrid Encoding + Qdrant Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Switch ingestion from 3 separate BGE-M3 calls to single `/encode/hybrid`, add payload indexes, fix bugs, cover with regression tests.

**Architecture:** `BGEM3SyncClient` gets `encode_hybrid()` method. Apartment runner + unified qdrant_writer switch to it. Payload indexes added via setup script. Warmup includes ColBERT.

**Tech Stack:** Python 3.12, httpx, qdrant-client, pytest, pytest-httpx

---

### Task 1: Add `encode_hybrid()` to `BGEM3SyncClient`

**Files:**
- Modify: `telegram_bot/services/bge_m3_client.py:399` (before `close()`)
- Test: `tests/unit/services/test_bge_m3_client.py`

**Step 1: Write failing tests**

Add to `tests/unit/services/test_bge_m3_client.py` — new class after existing `TestBGEM3Client`:

```python
class TestBGEM3SyncClient:
    """Tests for BGEM3SyncClient.encode_hybrid()."""

    def test_encode_hybrid_returns_hybrid_result(self, sync_client):
        """Single /encode/hybrid call returns dense + sparse + colbert."""
        with mock.patch.object(sync_client._client, "post") as mock_post:
            mock_post.return_value = mock.MagicMock(
                status_code=200,
                json=lambda: {
                    "dense_vecs": [[0.1] * 1024],
                    "lexical_weights": [{"indices": [1, 2], "values": [0.5, 0.3]}],
                    "colbert_vecs": [[[0.1] * 1024] * 5],
                    "processing_time": 0.42,
                },
                raise_for_status=lambda: None,
            )
            result = sync_client.encode_hybrid(["hello"])

            assert len(result.dense_vecs) == 1
            assert len(result.lexical_weights) == 1
            assert result.colbert_vecs is not None
            assert len(result.colbert_vecs) == 1
            assert result.processing_time == 0.42
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "/encode/hybrid" in call_url

    def test_encode_hybrid_empty_input(self, sync_client):
        """Empty input returns empty HybridResult without HTTP call."""
        result = sync_client.encode_hybrid([])
        assert result.dense_vecs == []
        assert result.lexical_weights == []

    def test_encode_hybrid_http_error_raises(self, sync_client):
        """HTTP 500 raises HTTPStatusError."""
        with mock.patch.object(sync_client._client, "post") as mock_post:
            mock_post.return_value = mock.MagicMock()
            mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error", request=mock.MagicMock(), response=mock.MagicMock(status_code=500)
            )
            with pytest.raises(httpx.HTTPStatusError):
                sync_client.encode_hybrid(["hello"])

    def test_encode_hybrid_batches_large_input(self, sync_client):
        """Input larger than batch_size is split into multiple requests."""
        sync_client.batch_size = 2
        texts = ["a", "b", "c"]

        call_count = 0
        def mock_post(url, json=None):
            nonlocal call_count
            call_count += 1
            n = len(json["texts"])
            resp = mock.MagicMock()
            resp.json.return_value = {
                "dense_vecs": [[0.1] * 1024] * n,
                "lexical_weights": [{"indices": [1], "values": [0.5]}] * n,
                "colbert_vecs": [[[0.1] * 1024] * 5] * n,
                "processing_time": 0.1,
            }
            resp.raise_for_status = lambda: None
            return resp

        with mock.patch.object(sync_client._client, "post", side_effect=mock_post):
            result = sync_client.encode_hybrid(texts)

        assert call_count == 2  # batch of 2 + batch of 1
        assert len(result.dense_vecs) == 3
        assert len(result.lexical_weights) == 3
        assert len(result.colbert_vecs) == 3
```

Add fixture at top of file (after existing `sync_client` fixture or create one):

```python
@pytest.fixture
def sync_client():
    from telegram_bot.services.bge_m3_client import BGEM3SyncClient
    return BGEM3SyncClient(base_url="http://localhost:8000")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_bge_m3_client.py::TestBGEM3SyncClient -v`
Expected: FAIL — `BGEM3SyncClient has no attribute 'encode_hybrid'`

**Step 3: Implement `encode_hybrid()` in BGEM3SyncClient**

Add before `close()` method at line 399 in `telegram_bot/services/bge_m3_client.py`:

```python
    def encode_hybrid(self, texts: list[str]) -> HybridResult:
        """Encode texts to dense + sparse + colbert in a single /encode/hybrid call.

        This is 3x more efficient than calling encode_dense + encode_sparse +
        encode_colbert separately, as the BGE-M3 model runs one forward pass.
        """
        if not texts:
            return HybridResult(dense_vecs=[], lexical_weights=[])
        all_dense: list[list[float]] = []
        all_weights: list[dict[str, Any]] = []
        all_colbert: list[list[list[float]]] = []
        processing_time: float | None = None
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self._client.post(
                f"{self.base_url}/encode/hybrid",
                json={"texts": batch, "batch_size": len(batch), "max_length": self.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            all_dense.extend(data["dense_vecs"])
            all_weights.extend(data["lexical_weights"])
            if data.get("colbert_vecs"):
                all_colbert.extend(data["colbert_vecs"])
            processing_time = data.get("processing_time")
        return HybridResult(
            dense_vecs=all_dense,
            lexical_weights=all_weights,
            colbert_vecs=all_colbert or None,
            processing_time=processing_time,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_bge_m3_client.py::TestBGEM3SyncClient -v`
Expected: 4 PASSED

**Step 5: Run full test suite for this file**

Run: `uv run pytest tests/unit/services/test_bge_m3_client.py -v`
Expected: all existing + new tests PASS

**Step 6: Commit**

```bash
git add telegram_bot/services/bge_m3_client.py tests/unit/services/test_bge_m3_client.py
git commit -m "feat(bge-m3): add encode_hybrid() to BGEM3SyncClient"
```

---

### Task 2: Switch apartment runner to `encode_hybrid()`

**Files:**
- Modify: `src/ingestion/apartments/runner.py:163-166, 184`
- Test: `tests/unit/ingestion/test_apartment_runner.py`

**Step 1: Write regression guard test**

Add to `tests/unit/ingestion/test_apartment_runner.py`:

```python
class TestHybridEncoding:
    """Regression guard: ingestion MUST use encode_hybrid, not 3 separate calls."""

    def test_embed_uses_single_hybrid_call(self, tmp_path: Path) -> None:
        """Runner calls encode_hybrid() once, never encode_dense/sparse/colbert."""
        csv = tmp_path / "apt.csv"
        csv.write_text(
            "complex_name,city,section,apartment_number,rooms,floor_label,"
            "area_m2,view_raw,price_eur,price_bgn,is_furnished,"
            "has_floor_plan,has_photo,is_promotion,old_price_eur\n"
            "TestComplex,TestCity,A-1,101,2,3,75.0,sea,100000.00,195000.00,"
            "False,False,False,False,\n"
        )
        ingester = IncrementalApartmentIngester(
            csv_path=str(csv),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
        )

        with (
            mock.patch(
                "src.ingestion.apartments.runner.BGEM3SyncClient"
            ) as MockBGE,
            mock.patch(
                "src.ingestion.apartments.runner.QdrantClient"
            ) as MockQdrant,
        ):
            mock_bge = MockBGE.return_value
            mock_bge.encode_hybrid.return_value = HybridResult(
                dense_vecs=[[0.1] * 1024],
                lexical_weights=[{"indices": [1], "values": [0.5]}],
                colbert_vecs=[[[0.1] * 1024] * 5],
            )
            mock_bge.encode_dense = mock.MagicMock()
            mock_bge.encode_sparse = mock.MagicMock()
            mock_bge.encode_colbert = mock.MagicMock()

            ingester._embed_and_upsert(ingester._load_records())

            mock_bge.encode_hybrid.assert_called_once()
            mock_bge.encode_dense.assert_not_called()
            mock_bge.encode_sparse.assert_not_called()
            mock_bge.encode_colbert.assert_not_called()
```

Add required import at top:
```python
from telegram_bot.services.bge_m3_client import HybridResult
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_apartment_runner.py::TestHybridEncoding -v`
Expected: FAIL — runner still calls encode_dense/sparse/colbert

**Step 3: Refactor runner to use encode_hybrid**

In `src/ingestion/apartments/runner.py`, replace lines 163-166:

```python
            # OLD: 3 separate calls
            # dense_result = bge.encode_dense(descriptions)
            # sparse_result = bge.encode_sparse(descriptions)
            # colbert_result = bge.encode_colbert(descriptions)

            # NEW: single hybrid call (3x fewer HTTP requests, 1 model forward pass)
            hybrid_result = bge.encode_hybrid(descriptions)
```

Replace lines 169-173 (build_ingestion_batch args):

```python
            point_dicts = build_ingestion_batch(
                records,
                hybrid_result.dense_vecs,
                hybrid_result.lexical_weights,
                hybrid_result.colbert_vecs or [],
            )
```

**Step 4: Fix progress log bug (line 184)**

Replace `min(i + 100, len(points))` with `min(i + 20, len(points))`:

```python
                logger.info("Upserted %d/%d", min(i + 20, len(points)), len(points))
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_apartment_runner.py -v`
Expected: all PASS (existing + new regression guard)

**Step 6: Commit**

```bash
git add src/ingestion/apartments/runner.py tests/unit/ingestion/test_apartment_runner.py
git commit -m "feat(apartments): switch ingestion to single encode_hybrid call

Also fixes progress log bug (i+100 → i+20 matching actual batch size)."
```

---

### Task 3: Switch unified qdrant_writer to `encode_hybrid()`

**Files:**
- Modify: `src/ingestion/unified/qdrant_writer.py:448-464`
- Test: `tests/unit/ingestion/test_qdrant_writer_behavior.py`

**Step 1: Write regression guard test**

Add to `tests/unit/ingestion/test_qdrant_writer_behavior.py`:

```python
class TestHybridEncodingRegression:
    """Regression: local BGE-M3 ingestion MUST use encode_hybrid, not 3 calls."""

    def test_upsert_chunks_sync_uses_hybrid_when_local(
        self, writer_local, mock_bge_client, mock_qdrant_client
    ):
        """Writer with use_local_embeddings=True calls bge.encode_hybrid once."""
        mock_bge_client.encode_hybrid.return_value = HybridResult(
            dense_vecs=[[0.2] * 1024],
            lexical_weights=[{"indices": [1, 2], "values": [0.5, 0.3]}],
            colbert_vecs=[[[0.1] * 128] * 5],
        )
        mock_qdrant_client.count.return_value = MagicMock(count=0)

        chunk = _make_chunk("test text", 0)
        writer_local.upsert_chunks_sync(
            chunks=[chunk],
            file_id="test-file",
            source_path="test.md",
            collection_name="test_collection",
        )

        mock_bge_client.encode_hybrid.assert_called_once_with(["test text"])
        mock_bge_client.encode_dense.assert_not_called()
        mock_bge_client.encode_sparse.assert_not_called()
        mock_bge_client.encode_colbert.assert_not_called()
```

Add required import:
```python
from telegram_bot.services.bge_m3_client import HybridResult
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_qdrant_writer_behavior.py::TestHybridEncodingRegression -v`
Expected: FAIL

**Step 3: Refactor qdrant_writer**

In `src/ingestion/unified/qdrant_writer.py`, replace lines 448-464 in `upsert_chunks_sync()`:

Replace the 3 separate embed calls (lines 448-464):
```python
            # Step 3: Generate embeddings — single hybrid call when local BGE-M3
            if self.use_local_embeddings:
                hybrid_result = self.bge_client.encode_hybrid(texts)
                all_dense_embeddings = hybrid_result.dense_vecs
                sparse_embeddings = hybrid_result.lexical_weights
                colbert_embeddings = hybrid_result.colbert_vecs or []
            else:
                if self.voyage is None:
                    raise RuntimeError("VoyageService not initialized")
                all_dense_embeddings = []
                for i in range(0, len(texts), self.VOYAGE_BATCH_SIZE):
                    batch = texts[i : i + self.VOYAGE_BATCH_SIZE]
                    response = self.voyage._client.embed(
                        texts=batch,
                        model=self.voyage._model_docs,
                        input_type="document",
                    )
                    all_dense_embeddings.extend(response.embeddings)
                sparse_embeddings = self._embed_sparse(texts)
                colbert_embeddings = []
```

Note: Keep `_embed_documents_local`, `_embed_sparse`, `_embed_colbert` methods — they're used by the async `upsert_chunks` path and Voyage fallback.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_qdrant_writer_behavior.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/ingestion/unified/qdrant_writer.py tests/unit/ingestion/test_qdrant_writer_behavior.py
git commit -m "feat(ingestion): switch unified writer to single encode_hybrid call"
```

---

### Task 4: Update legacy script

**Files:**
- Modify: `scripts/apartments/ingest.py:43-46`

**Step 1: Refactor to use encode_hybrid**

Replace lines 40-49:

```python
    # Embed in batches
    all_dense, all_sparse, all_colbert = [], [], []
    for i in range(0, len(descriptions), BATCH_SIZE):
        batch = descriptions[i : i + BATCH_SIZE]
        result = bge.encode_hybrid(batch)
        all_dense.extend(result.dense_vecs)
        all_sparse.extend(result.lexical_weights)
        all_colbert.extend(result.colbert_vecs or [])
        print(f"  Embedded {min(i + BATCH_SIZE, len(descriptions))}/{len(descriptions)}")
```

**Step 2: Commit**

```bash
git add scripts/apartments/ingest.py
git commit -m "refactor(scripts): use encode_hybrid in legacy ingest script"
```

---

### Task 5: Enable ColBERT in warmup

**Files:**
- Modify: `services/bge-m3-api/app.py:50`

**Step 1: Change `return_colbert_vecs=False` to `True`**

In `services/bge-m3-api/app.py` line 50:

```python
        return_colbert_vecs=True,  # warm up all codepaths including ColBERT
```

**Step 2: Commit**

```bash
git add services/bge-m3-api/app.py
git commit -m "fix(bge-m3): include ColBERT in model warmup"
```

---

### Task 6: Create payload indexes on apartments

**Files:**
- Script: `scripts/apartments/setup_collection.py` (already has `create_payload_indexes`)

**Step 1: Run setup script to create indexes**

```bash
uv run python scripts/apartments/setup_collection.py
```

Expected: "Collection 'apartments' already exists, skipping creation" + 12 index lines.

**Step 2: Write integration test for payload indexes**

Add to `tests/integration/test_apartments_ingestion.py`:

```python
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="requires Qdrant")
def test_apartments_payload_indexes_exist():
    """Apartments collection must have payload indexes for filtered search."""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
    info = client.get_collection("apartments")

    indexed_fields = set(info.payload_schema.keys())
    required = {"city", "complex_name", "rooms", "price_eur", "area_m2", "floor"}

    missing = required - indexed_fields
    assert not missing, f"Missing payload indexes: {missing}"
```

**Step 3: Commit**

```bash
git add tests/integration/test_apartments_ingestion.py
git commit -m "test(apartments): add integration test for payload indexes"
```

---

### Task 7: Load documents into `gdrive_documents_bge`

**Step 1: Run unified ingestion**

```bash
tmux new-window -n "W-INGEST" -c /home/user/projects/rag-fresh
tmux send-keys -t "W-INGEST" "make ingest-unified 2>&1 | tee logs/ingest-unified.log; echo '[COMPLETE]'" Enter
```

**Step 2: Verify points were created**

```bash
curl -s http://localhost:6333/collections/gdrive_documents_bge | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'points: {d[\"result\"][\"points_count\"]}')"
```

Expected: `points: > 0`

**Step 3: No commit needed — data operation only**

---

### Task 8: Run full checks and final commit

**Step 1: Lint + types**

```bash
make check
```

Expected: clean (0 errors)

**Step 2: Unit tests**

```bash
uv run pytest tests/unit/ -n auto -q --timeout=30
```

Expected: all PASS

**Step 3: Integration tests (if Qdrant running)**

```bash
RUN_INTEGRATION=1 uv run pytest tests/integration/test_apartments_ingestion.py -v
```

**Step 4: Verify bot still works**

Check tmux window W-BOT — no new errors in logs after ingestion.

---

## Summary of changes

| File | Change |
|------|--------|
| `telegram_bot/services/bge_m3_client.py` | Add `BGEM3SyncClient.encode_hybrid()` |
| `src/ingestion/apartments/runner.py` | Use `encode_hybrid`, fix batch log bug |
| `src/ingestion/unified/qdrant_writer.py` | Use `encode_hybrid` for local BGE-M3 |
| `scripts/apartments/ingest.py` | Use `encode_hybrid` |
| `services/bge-m3-api/app.py` | Warmup with ColBERT |
| `tests/unit/services/test_bge_m3_client.py` | 4 new sync hybrid tests |
| `tests/unit/ingestion/test_apartment_runner.py` | Regression guard test |
| `tests/unit/ingestion/test_qdrant_writer_behavior.py` | Regression guard test |
| `tests/integration/test_apartments_ingestion.py` | Payload index test |

## Commit sequence

1. `feat(bge-m3): add encode_hybrid() to BGEM3SyncClient`
2. `feat(apartments): switch ingestion to single encode_hybrid call`
3. `feat(ingestion): switch unified writer to single encode_hybrid call`
4. `refactor(scripts): use encode_hybrid in legacy ingest script`
5. `fix(bge-m3): include ColBERT in model warmup`
6. `test(apartments): add integration test for payload indexes`
