# Apartments Ingestion Completion — SDK-Driven Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Завершить ingestion 297 апартаментов в Qdrant, мигрировать на CocoIndex incremental pipeline, применить best practices 2026 для hybrid search.

**Architecture:** Трёхфазный подход — (1) запуск текущего batch ingestion для немедленного результата, (2) миграция на CocoIndex row-level source для incremental updates при изменении CSV, (3) Qdrant 1.17 оптимизации (ACORN, configurable RRF k, multilingual FTS).

**Tech Stack:** Python 3.12 | CocoIndex (Rust engine, Python API) | Qdrant 1.17 (dense 1024 + sparse BM42 + ColBERT MaxSim) | BGE-M3 via HTTP API | existing BGEM3SyncClient

---

## Контекст и исследование

### Текущее состояние

| Компонент | Статус | Файл |
|-----------|--------|------|
| CSV данные | 297 записей, 14 колонок | `data/apartments.csv` |
| Qdrant коллекция | Создана, 11 payload индексов | `scripts/apartments/setup_collection.py` |
| Batch ingestion скрипт | Готов, НЕ запускался | `scripts/apartments/ingest.py` |
| Search pipeline (fast-path) | Реализован | `telegram_bot/services/apartments_service.py` |
| Filter extractor (regex) | Реализован | `telegram_bot/services/apartment_filter_extractor.py` |
| Agent escalation tool | Реализован | `telegram_bot/agents/apartment_tools.py` |
| Data models | Реализованы | `telegram_bot/services/apartment_models.py` |
| Unit tests | Покрыты все модели и сервисы | `tests/unit/services/test_apartment_*.py` |

### SDK-решения 2026 (результаты исследования)

**CocoIndex incremental pipeline:**
- Custom Source API (stable с Oct 2025) — row-level change tracking для CSV
- `refresh_interval` для автоматического пересчёта при изменении CSV
- Одноразовый `flow.update(print_stats=True)` или continuous `FlowLiveUpdater(..., FlowLiveUpdaterOptions(print_stats=True))`
- `behavior_version` использовать только при явном изменении логики трансформаций

**BGE-M3 hybrid text serialization:**
- Гибридный формат: structured prefix `[2BR|70.85m2|141000EUR]` + NL описание на русском
- В текущем repo `BGEM3SyncClient` использует `encode_dense()` + `encode_sparse()` + `encode_colbert()` (sync API)
- `encode_hybrid()` доступен в async `BGEM3Client`, но не в `BGEM3SyncClient`
- `max_length=512` достаточно для коротких описаний апартаментов

**Qdrant 1.17 features:**
- ACORN — улучшенный recall при комбо-фильтрах (rooms + view + price)
- Configurable RRF k — тюнинг баланса dense/sparse через query API
- `MatchTextAny(text_any=...)` — мульти-match по text payload
- Conditional upserts — safe re-indexing без race conditions

### Два пути запросов (уже реализованы)

```
Вход:  "двушка у моря до 150к"
  │
  ├─ ApartmentFilterExtractor (regex, 0 LLM calls)
  │    → rooms=2, view_tags=["sea"], max_price_eur=150000
  │    → confidence=HIGH (score=5)
  │
  ├─ BGE-M3 embeddings (до 3 HTTP calls → 3 вектора):
  │    → dense (1024d) + sparse (BM42 IDF) + ColBERT (multi-vector)
  │
  └─ Qdrant 3-stage nested prefetch:
       Stage 1: Dense→100 + Sparse→100 (candidates)
       Stage 2: RRF fusion → top 30
       Stage 3: ColBERT MaxSim rescore → top 10
       + payload filter: must=[rooms=2, price≤150k, view_tags∋sea]
```

| Путь | Когда | Результат |
|------|-------|-----------|
| **Fast path** | confidence HIGH/MEDIUM | regex filters → hybrid search → карточки + FSM state |
| **Agent escalation** | confidence LOW / 0 results | SDK agent + `apartment_search` @tool |
| **Funnel dialog** | кнопка "🏠 Подбор апартаментов" | 5 шагов UI → hybrid search |

---

## Phase 1: Immediate — Batch Ingestion (P0)

### Task 1: Запустить batch ingestion

**Files:** `scripts/apartments/ingest.py` (без изменений), `data/apartments.csv`

**Step 1: Проверить что сервисы запущены**

```bash
curl -s http://localhost:6333/collections/apartments | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Collection: {d[\"result\"][\"status\"]}, points: {d[\"result\"][\"points_count\"]}')"
curl -s http://localhost:8000/health
```

Expected: Collection exists, points_count=0, BGE-M3 healthy.

**Step 2: Запустить ingestion**

```bash
uv run python scripts/apartments/ingest.py
```

Expected: `Done. 297 apartments in collection 'apartments'.`

**Step 3: Верифицировать результат**

```bash
curl -s http://localhost:6333/collections/apartments | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'points: {d[\"result\"][\"points_count\"]}, indexed: {d[\"result\"][\"indexed_vectors_count\"]}')"
```

Expected: `points: 297, indexed: 297`

**Step 4: Spot-check одной точки**

```bash
curl -s -X POST http://localhost:6333/collections/apartments/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit": 1, "with_payload": true, "with_vectors": false}' | python3 -m json.tool
```

Expected: Payload содержит `complex_name`, `rooms`, `price_eur`, `description` и т.д.

---

### Task 2: Smoke test — поисковый pipeline

**Цель:** Убедиться что hybrid search + payload filters работают на реальных данных.

**Step 1: Написать integration test**

**Create:** `tests/integration/test_apartments_ingestion.py`

```python
"""Smoke test: apartments collection has data and search works."""

import os

import pytest
from qdrant_client import QdrantClient


QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "apartments"


@pytest.fixture
def qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION", ""),
    reason="RUN_INTEGRATION not set",
)
class TestApartmentsIngestion:
    def test_collection_has_points(self, qdrant: QdrantClient) -> None:
        info = qdrant.get_collection(COLLECTION)
        assert info.points_count >= 297

    def test_scroll_with_filter(self, qdrant: QdrantClient) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="rooms", match=MatchValue(value=2))]
            ),
            limit=5,
            with_payload=True,
        )
        assert len(results) > 0
        for point in results:
            assert point.payload["rooms"] == 2

    def test_point_has_all_vectors(self, qdrant: QdrantClient) -> None:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            limit=1,
            with_vectors=True,
        )
        assert len(results) == 1
        vectors = results[0].vector
        assert "dense" in vectors
        assert "bm42" in vectors
        # colbert may be absent for empty-view apartments
```

**Step 2: Запустить тест**

```bash
RUN_INTEGRATION=1 uv run pytest tests/integration/test_apartments_ingestion.py -n auto --dist=worksteal -v
```

Expected: 3 PASSED.

**Step 3: Commit**

```bash
git add tests/integration/test_apartments_ingestion.py
git commit -m "test(apartments): add ingestion smoke tests for collection data"
```

---

### Task 3: Bot E2E verification

**Step 1: Перезапустить бота**

```bash
make bot
```

**Step 2: Проверить в Telegram**

1. Нажать "🏠 Подбор апартаментов" → пройти фаннел → должны показаться карточки
2. Написать "двушка до 150к" → fast-path должен вернуть результаты
3. Проверить кнопки "🔄 Показать ещё", "📌 В закладки"

**Step 3: Проверить логи**

```bash
grep -E "apartment|funnel|ERROR" logs/bot-run.log | tail -20
```

Expected: Нет `Collection 'apartments' doesn't exist!`, есть `apartments-hybrid-search` spans.

---

## Phase 2: Incremental Pipeline (P1, CocoIndex-compatible)

### Task 4: CocoIndex row-level source для apartments CSV

**Goal:** Заменить одноразовый `ingest.py` на CocoIndex flow с incremental updates — при изменении цены/статуса в CSV пересчитываются только изменённые строки.

**Files:**
- Create: `src/ingestion/apartments/source.py`
- Create: `tests/unit/ingestion/test_apartment_source.py`
- Modify: `src/ingestion/apartments/__init__.py` (create)

**Step 1: Написать failing test для source**

**Create:** `tests/unit/ingestion/test_apartment_source.py`

```python
"""Tests for CocoIndex apartment CSV source."""

import csv
from pathlib import Path

from src.ingestion.apartments.source import parse_apartment_row, row_change_key


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "complex_name", "section", "apartment_number", "rooms",
        "floor_label", "area_m2", "view_raw", "price_eur", "price_bgn",
        "is_furnished", "has_floor_plan", "has_photo", "is_promotion", "old_price_eur",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestParseApartmentRow:
    def test_basic_row(self) -> None:
        row = {
            "complex_name": "Premier Fort Beach",
            "section": "D-1",
            "apartment_number": "248",
            "rooms": "2",
            "floor_label": "4",
            "area_m2": "78.66",
            "view_raw": "sea",
            "price_eur": "215000.00",
            "price_bgn": "420503.45",
            "is_furnished": "False",
            "has_floor_plan": "False",
            "has_photo": "False",
            "is_promotion": "False",
            "old_price_eur": "",
        }
        record = parse_apartment_row(row)
        assert record.complex_name == "Premier Fort Beach"
        assert record.rooms == 2
        assert record.price_eur == 215000.0

    def test_ground_floor(self) -> None:
        row = {
            "complex_name": "Test", "section": "A", "apartment_number": "1",
            "rooms": "1", "floor_label": "gr.", "area_m2": "30",
            "view_raw": "", "price_eur": "50000", "price_bgn": "97000",
            "is_furnished": "False", "has_floor_plan": "False",
            "has_photo": "False", "is_promotion": "False", "old_price_eur": "",
        }
        record = parse_apartment_row(row)
        assert record.floor == 0


class TestRowChangeKey:
    def test_same_data_same_key(self) -> None:
        row = {"price_eur": "100000", "area_m2": "50", "is_furnished": "False",
               "is_promotion": "False", "view_raw": "sea"}
        assert row_change_key(row) == row_change_key(row)

    def test_price_change_different_key(self) -> None:
        row1 = {"price_eur": "100000", "area_m2": "50", "is_furnished": "False",
                "is_promotion": "False", "view_raw": "sea"}
        row2 = {**row1, "price_eur": "110000"}
        assert row_change_key(row1) != row_change_key(row2)
```

**Step 2: Запустить тест — убедиться что падает**

```bash
uv run pytest tests/unit/ingestion/test_apartment_source.py -n auto --dist=worksteal -v
```

Expected: FAIL (module not found).

**Step 3: Реализовать source module**

**Create:** `src/ingestion/apartments/__init__.py`

```python
"""Apartments CocoIndex ingestion pipeline."""
```

**Create:** `src/ingestion/apartments/source.py`

```python
"""CocoIndex-compatible CSV source for apartments with row-level change tracking.

Parses apartments.csv and yields one row per apartment. Change detection uses
a hash of mutable fields (price, area, furnished, promotion, view) so only
modified rows trigger re-embedding.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from telegram_bot.services.apartment_models import ApartmentRecord


# Mutable fields — changes in these trigger re-embedding
_CHANGE_FIELDS = ("price_eur", "area_m2", "is_furnished", "is_promotion", "view_raw")


def row_change_key(row: dict) -> str:
    """Deterministic hash of mutable fields for change detection."""
    parts = "|".join(str(row.get(f, "")) for f in _CHANGE_FIELDS)
    return hashlib.sha256(parts.encode()).hexdigest()[:16]


def parse_apartment_row(row: dict) -> ApartmentRecord:
    """Parse a CSV dict row into an ApartmentRecord."""
    return ApartmentRecord.from_raw(row)


def read_apartments_csv(csv_path: str | Path) -> list[tuple[str, str, ApartmentRecord]]:
    """Read CSV and return (unique_key, change_key, record) tuples.

    unique_key: deterministic row identity (complex::section::apt_number)
    change_key: hash of mutable fields (triggers re-embedding when changed)
    """
    results: list[tuple[str, str, ApartmentRecord]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = parse_apartment_row(row)
            unique_key = f"{record.complex_name}::{record.section}::{record.apartment_number}"
            change = row_change_key(row)
            results.append((unique_key, change, record))
    return results
```

**Step 4: Запустить тест**

```bash
uv run pytest tests/unit/ingestion/test_apartment_source.py -n auto --dist=worksteal -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/apartments/__init__.py src/ingestion/apartments/source.py tests/unit/ingestion/test_apartment_source.py
git commit -m "feat(ingestion): add CocoIndex-compatible apartment CSV source with change tracking"
```

---

### Task 5: Flow primitives для apartments

**Goal:** Подготовить базовые primitives для ingestion flow: deterministic point ID, hybrid serialization и `build_ingestion_batch()`. Эти функции переиспользуются в runner/flow wiring на следующем шаге.

**Files:**
- Create: `src/ingestion/apartments/flow.py`
- Create: `tests/unit/ingestion/test_apartment_flow.py`

**Step 1: Написать failing test**

**Create:** `tests/unit/ingestion/test_apartment_flow.py`

```python
"""Tests for apartment ingestion flow — text serialization and embedding prep."""

from telegram_bot.services.apartment_models import ApartmentRecord
from src.ingestion.apartments.flow import format_apartment_text


class TestFormatApartmentText:
    def test_contains_complex_name(self) -> None:
        record = ApartmentRecord(
            complex_name="Premier Fort Beach", section="D-1",
            apartment_number="248", rooms=2, floor=4, floor_label="4",
            area_m2=78.66, view_primary="sea", view_tags=["sea"],
            price_eur=215000.0, price_bgn=420503.45,
            is_furnished=False, has_floor_plan=False, has_photo=False,
        )
        text = format_apartment_text(record)
        assert "Premier Fort Beach" in text
        assert "215" in text  # price
        assert "78.66" in text  # area

    def test_promotion_flag(self) -> None:
        record = ApartmentRecord(
            complex_name="Test", section="A", apartment_number="1",
            rooms=1, floor=2, floor_label="2", area_m2=30.0,
            view_primary="pool", view_tags=["pool"],
            price_eur=50000.0, price_bgn=97000.0,
            is_furnished=True, has_floor_plan=False, has_photo=False,
            is_promotion=True, old_price_eur=60000.0,
        )
        text = format_apartment_text(record)
        assert "Акция" in text or "акция" in text
```

**Step 2: Run test — verify failure**

```bash
uv run pytest tests/unit/ingestion/test_apartment_flow.py -n auto --dist=worksteal -v
```

**Step 3: Implement flow module**

**Create:** `src/ingestion/apartments/flow.py`

```python
"""Flow primitives for apartments ingestion.

Formats hybrid text and builds Qdrant-ready point payloads.
Used by incremental runner / future CocoIndex wiring.
"""

from __future__ import annotations

import uuid

from telegram_bot.services.apartment_models import ApartmentRecord


COLLECTION = "apartments"
NAMESPACE = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_point_id(complex_name: str, section: str, apartment_number: str) -> str:
    """Deterministic UUID5 from complex + section + apartment number."""
    return str(uuid.uuid5(NAMESPACE, f"{complex_name}::{section}::{apartment_number}"))


def format_apartment_text(record: ApartmentRecord) -> str:
    """Hybrid text serialization for BGE-M3: structured prefix + NL description.

    Structured prefix helps sparse/lexical retrieval (exact match on numbers).
    NL body helps dense/semantic retrieval (conceptual queries like "уютная у моря").
    """
    # Structured prefix for sparse retrieval
    price_k = int(record.price_eur / 1000)
    prefix = f"[{record.rooms}BR|{record.area_m2}m2|{price_k}kEUR]"

    # NL body (Russian) for dense retrieval — reuses existing to_description()
    body = record.to_description()

    # Promotion marker
    promo = " Акция!" if record.is_promotion else ""

    return f"{prefix} {body}{promo}"


def build_ingestion_batch(
    records: list[ApartmentRecord],
    dense_vecs: list[list[float]],
    sparse_weights: list[dict],
    colbert_vecs: list[list[list[float]]],
) -> list[dict]:
    """Build Qdrant point dicts from records and their embeddings.

    Returns list of dicts with keys: id, vector, payload.
    """
    from qdrant_client.models import SparseVector

    points = []
    for rec, dense, sparse, colbert in zip(
        records, dense_vecs, sparse_weights, colbert_vecs, strict=True
    ):
        point_id = generate_point_id(rec.complex_name, rec.section, rec.apartment_number)
        vector_dict: dict = {
            "dense": dense,
            "bm42": SparseVector(indices=sparse["indices"], values=sparse["values"]),
        }
        if colbert:
            vector_dict["colbert"] = colbert

        payload = rec.to_payload()
        payload["description_hybrid"] = format_apartment_text(rec)

        points.append({"id": point_id, "vector": vector_dict, "payload": payload})

    return points
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/ingestion/test_apartment_flow.py -n auto --dist=worksteal -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/apartments/flow.py tests/unit/ingestion/test_apartment_flow.py
git commit -m "feat(ingestion): add apartment flow with hybrid text serialization"
```

---

### Task 6: Incremental ingestion runner

**Goal:** CLI-запускаемый incremental runner с change tracking по строкам CSV. Это transitional шаг до полного Custom Source connector; runner должен быть идемпотентным и безопасным для повторного запуска.

**Files:**
- Create: `src/ingestion/apartments/runner.py`
- Modify: `scripts/apartments/ingest.py` (добавить deprecation notice)
- Create: `tests/unit/ingestion/test_apartment_runner.py`

**Step 1: Написать failing test**

**Create:** `tests/unit/ingestion/test_apartment_runner.py`

```python
"""Tests for incremental apartment ingestion runner."""

import csv
from pathlib import Path
from unittest.mock import patch

from src.ingestion.apartments.runner import IncrementalApartmentIngester


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "complex_name", "section", "apartment_number", "rooms",
        "floor_label", "area_m2", "view_raw", "price_eur", "price_bgn",
        "is_furnished", "has_floor_plan", "has_photo", "is_promotion", "old_price_eur",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


SAMPLE_ROW = {
    "complex_name": "Test Complex", "section": "A-1",
    "apartment_number": "101", "rooms": "2", "floor_label": "3",
    "area_m2": "65.0", "view_raw": "sea", "price_eur": "120000",
    "price_bgn": "234000", "is_furnished": "False",
    "has_floor_plan": "False", "has_photo": "False",
    "is_promotion": "False", "old_price_eur": "",
}


class TestIncrementalIngester:
    def test_first_run_ingests_all(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
        )

        with patch.object(ingester, "_embed_and_upsert") as mock_upsert:
            stats = ingester.run_incremental(dry_run=True)

        assert stats["total"] == 1
        assert stats["changed"] == 1
        assert stats["unchanged"] == 0

    def test_second_run_skips_unchanged(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(state_path),
        )

        # First run — saves state
        ingester.run_incremental(dry_run=True)

        # Second run — same data, nothing changed
        stats = ingester.run_incremental(dry_run=True)
        assert stats["changed"] == 0
        assert stats["unchanged"] == 1

    def test_price_change_triggers_reindex(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(state_path),
        )

        # First run
        ingester.run_incremental(dry_run=True)

        # Change price
        changed_row = {**SAMPLE_ROW, "price_eur": "130000"}
        _write_csv([changed_row], csv_path)

        stats = ingester.run_incremental(dry_run=True)
        assert stats["changed"] == 1
```

**Step 2: Run test — verify failure**

```bash
uv run pytest tests/unit/ingestion/test_apartment_runner.py -n auto --dist=worksteal -v
```

**Step 3: Implement runner**

**Create:** `src/ingestion/apartments/runner.py`

```python
"""Incremental apartment ingestion runner.

Tracks row-level changes via SHA-256 hash of mutable fields. Only re-embeds
and upserts rows that changed since last run. State persisted to JSON file.

Usage:
    # Full re-index (first run or force)
    python -m src.ingestion.apartments.runner

    # Incremental (only changed rows)
    python -m src.ingestion.apartments.runner --incremental

    # Dry run (show what would change)
    python -m src.ingestion.apartments.runner --incremental --dry-run
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from src.ingestion.apartments.flow import (
    COLLECTION,
    build_ingestion_batch,
    format_apartment_text,
)
from src.ingestion.apartments.source import read_apartments_csv
from telegram_bot.services.apartment_models import ApartmentRecord

logger = logging.getLogger(__name__)


class IncrementalApartmentIngester:
    """Apartment ingestion with row-level change tracking."""

    def __init__(
        self,
        csv_path: str = "data/apartments.csv",
        qdrant_url: str = "http://localhost:6333",
        bge_url: str = "http://localhost:8000",
        state_path: str = ".apartments_ingestion_state.json",
    ) -> None:
        self.csv_path = csv_path
        self.qdrant_url = qdrant_url
        self.bge_url = bge_url
        self.state_path = state_path
        self._state: dict[str, str] = {}  # unique_key → change_key

    def _load_state(self) -> dict[str, str]:
        """Load previous ingestion state from JSON file."""
        path = Path(self.state_path)
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_state(self, state: dict[str, str]) -> None:
        """Save current ingestion state to JSON file."""
        Path(self.state_path).write_text(json.dumps(state, indent=2))

    def run_incremental(self, dry_run: bool = False) -> dict:
        """Run incremental ingestion. Returns stats dict."""
        rows = read_apartments_csv(self.csv_path)
        prev_state = self._load_state()

        changed: list[ApartmentRecord] = []
        new_state: dict[str, str] = {}

        for unique_key, change_key, record in rows:
            new_state[unique_key] = change_key
            if prev_state.get(unique_key) != change_key:
                changed.append(record)

        stats = {
            "total": len(rows),
            "changed": len(changed),
            "unchanged": len(rows) - len(changed),
        }

        logger.info(
            "Incremental scan: %d total, %d changed, %d unchanged",
            stats["total"], stats["changed"], stats["unchanged"],
        )

        if changed and not dry_run:
            self._embed_and_upsert(changed)

        # Always save state (even dry_run — to track what was seen)
        self._save_state(new_state)

        return stats

    def _embed_and_upsert(self, records: list[ApartmentRecord]) -> None:
        """Embed changed records and upsert to Qdrant."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        from telegram_bot.services.bge_m3_client import BGEM3SyncClient

        bge = BGEM3SyncClient(base_url=self.bge_url)
        client = QdrantClient(url=self.qdrant_url)

        descriptions = [format_apartment_text(r) for r in records]

        # Embed
        dense_result = bge.encode_dense(descriptions)
        sparse_result = bge.encode_sparse(descriptions)
        colbert_result = bge.encode_colbert(descriptions)

        # Build points
        point_dicts = build_ingestion_batch(
            records,
            dense_result.vectors,
            sparse_result.weights,
            colbert_result.colbert_vecs,
        )

        # Upsert
        points = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in point_dicts
        ]
        for i in range(0, len(points), 100):
            batch = points[i : i + 100]
            client.upsert(collection_name=COLLECTION, points=batch)
            logger.info("Upserted %d/%d", min(i + 100, len(points)), len(points))

        bge.close()
        logger.info("Done. %d apartments upserted.", len(points))


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Incremental apartment ingestion")
    parser.add_argument("--incremental", action="store_true", help="Only re-embed changed rows")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without upserting")
    args = parser.parse_args()

    ingester = IncrementalApartmentIngester(
        csv_path=os.getenv("APARTMENTS_CSV", "data/apartments.csv"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        bge_url=os.getenv("BGE_M3_URL", "http://localhost:8000"),
    )

    if args.incremental:
        stats = ingester.run_incremental(dry_run=args.dry_run)
        print(f"Stats: {stats}")
    else:
        # Full re-index: clear state and run
        Path(ingester.state_path).unlink(missing_ok=True)
        stats = ingester.run_incremental(dry_run=args.dry_run)
        print(f"Full re-index stats: {stats}")
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/ingestion/test_apartment_runner.py -n auto --dist=worksteal -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/apartments/runner.py tests/unit/ingestion/test_apartment_runner.py
git commit -m "feat(ingestion): add incremental apartment ingestion runner with change tracking"
```

---

## Phase 3: Qdrant 1.17 Optimizations (P2)

### Task 7: Hybrid text serialization для existing descriptions

**Goal:** Обновить `to_description()` или добавить `description_hybrid` в payload, чтобы улучшить и sparse и dense retrieval quality.

**Files:**
- Modify: `telegram_bot/services/apartment_models.py` — добавить `to_hybrid_description()`
- Modify: `tests/unit/services/test_apartment_models.py` — тесты
- Modify: `scripts/apartments/ingest.py` — использовать hybrid описание

**Step 1: Написать failing test**

Добавить в `tests/unit/services/test_apartment_models.py`:

```python
class TestHybridDescription:
    def test_has_structured_prefix(self) -> None:
        record = ApartmentRecord(
            complex_name="Test", section="A", apartment_number="1",
            rooms=2, floor=3, floor_label="3", area_m2=65.0,
            view_primary="sea", view_tags=["sea"],
            price_eur=120000.0, price_bgn=234000.0,
            is_furnished=False, has_floor_plan=False, has_photo=False,
        )
        text = record.to_hybrid_description()
        assert text.startswith("[2BR|65.0m2|120kEUR]")

    def test_has_natural_language_body(self) -> None:
        record = ApartmentRecord(
            complex_name="Premier Fort Beach", section="D-1",
            apartment_number="248", rooms=2, floor=4, floor_label="4",
            area_m2=78.66, view_primary="sea", view_tags=["sea"],
            price_eur=215000.0, price_bgn=420503.45,
            is_furnished=False, has_floor_plan=False, has_photo=False,
        )
        text = record.to_hybrid_description()
        assert "Premier Fort Beach" in text
        assert "2 комнаты" in text

    def test_promotion_marker(self) -> None:
        record = ApartmentRecord(
            complex_name="Test", section="A", apartment_number="1",
            rooms=1, floor=2, floor_label="2", area_m2=30.0,
            view_primary="pool", view_tags=["pool"],
            price_eur=50000.0, price_bgn=97000.0,
            is_furnished=True, has_floor_plan=False, has_photo=False,
            is_promotion=True, old_price_eur=60000.0,
        )
        text = record.to_hybrid_description()
        assert "Акция" in text
```

**Step 2: Run test — verify failure**

```bash
uv run pytest tests/unit/services/test_apartment_models.py::TestHybridDescription -n auto --dist=worksteal -v
```

**Step 3: Implement `to_hybrid_description()`**

Добавить в `ApartmentRecord` в `apartment_models.py`:

```python
def to_hybrid_description(self) -> str:
    """Hybrid text for BGE-M3: structured prefix + NL body.

    Prefix helps sparse/lexical retrieval (exact numbers).
    Body helps dense/semantic retrieval (conceptual queries).
    """
    price_k = int(self.price_eur / 1000)
    prefix = f"[{self.rooms}BR|{self.area_m2}m2|{price_k}kEUR]"
    body = self.to_description()
    promo = " Акция!" if self.is_promotion else ""
    return f"{prefix} {body}{promo}"
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/services/test_apartment_models.py -n auto --dist=worksteal -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add telegram_bot/services/apartment_models.py tests/unit/services/test_apartment_models.py
git commit -m "feat(apartments): add hybrid text serialization for improved BGE-M3 retrieval"
```

---

### Task 8 (P2): Qdrant ACORN и Configurable RRF k

**Scope:** Отдельные issues после стабилизации основного flow.

| Фича | Что даёт | Как включить | Issue |
|------|---------|-------------|-------|
| **ACORN** (1.16) | +5-10% recall при комбо-фильтрах | `search_params=SearchParams(acorn=AcornSearchParams(enable=True))` | Отдельный |
| **Configurable RRF k** (1.16) | Тюнинг dense/sparse баланса | `query=RrfQuery(rrf=Rrf(k=60, weights=[0.7, 0.3]))` | Отдельный |
| **Multilingual tokenizer** | FTS по русским описаниям | `text_index_params(tokenizer="multilingual")` на `description` | Отдельный |
| **Relevance Feedback** (1.17) | "Похожие на эту квартиру" | positive/negative point IDs | Отдельный |
| **Score Boosting** (1.16) | Буст акций | Custom scoring formula | Отдельный |

---

## Порядок выполнения

```
Phase 1 (P0) — немедленный результат:
  Task 1: Batch ingestion          — 5 мин, запустить скрипт
  Task 2: Smoke test               — 10 мин, integration test
  Task 3: Bot E2E verify           — 5 мин, проверить в Telegram

Phase 2 (P1) — SDK best practices:
  Task 4: CocoIndex source         — 20 мин, row-level CSV parser
  Task 5: Flow primitives          — 20 мин, hybrid text + build batch
  Task 6: Incremental runner       — 30 мин, CLI с change tracking

Phase 3 (P2) — оптимизации:
  Task 7: Hybrid text serialization — 15 мин, to_hybrid_description()
  Task 8: Qdrant 1.17 features     — отдельные issues
```

**Критический путь:** Task 1 → Task 2 → Task 3. После этого бот показывает апартаменты.

---

## Риски

| Риск | Митигация |
|------|-----------|
| BGE-M3 timeout при batch embed 297 записей | Батч по 32, ~12 вызовов, BGE-M3 warm |
| ColBERT rerank >2s на CPU | server-side ColBERT в Qdrant nested prefetch |
| CSV маппинг полей не совпадает | Маппинг проверен, unit tests покрыты |
| CocoIndex API breaking changes | Pin version, использовать stable Custom Source API |
| Incremental state file corruption | JSON + atomic write, state reset при ошибках |
| Hybrid text формат ухудшает retrieval | A/B тест: `description` vs `description_hybrid`, eval через RAGAS |

---

## Review Note (2026-02-25)

- Проверено as-of `2026-02-25`: Qdrant Python client `1.17.0` поддерживает `AcornSearchParams(enable=...)`, `RrfQuery(rrf=Rrf(...))`, `MatchTextAny(text_any=...)`, и conditional upserts (`update_filter` + `update_mode`).
- Проверено as-of `2026-02-25`: `BGEM3SyncClient` в репозитории предоставляет `encode_dense/encode_sparse/encode_colbert`; `encode_hybrid` доступен в async `BGEM3Client`.
- P1 runner помечен transitional (state-based incremental) до отдельного full Custom Source connector.
