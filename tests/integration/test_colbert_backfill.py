"""Integration-style test: partial ColBERT coverage -> backfill -> ColBERT search returns docs."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class _StoredPoint:
    point_id: int
    payload: dict
    vectors: dict


class _FakeQdrantStorage:
    def __init__(self) -> None:
        self.collection_name = "test_col"
        self.points: dict[int, _StoredPoint] = {}

    def collection_info(self):
        return SimpleNamespace(
            points_count=len(self.points),
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={"dense": object(), "colbert": object()},
                    sparse_vectors={"bm42": object()},
                )
            ),
        )


class _FakeSyncQdrantClient:
    def __init__(self, storage: _FakeQdrantStorage):
        self._storage = storage

    def get_collection(self, collection_name: str):
        return self._storage.collection_info()

    def count(self, collection_name: str, count_filter=None, exact=True):
        if count_filter is None:
            return SimpleNamespace(count=len(self._storage.points))

        # Filter contains HasVectorCondition(has_vector="colbert")
        covered = 0
        for point in self._storage.points.values():
            colbert_vec = point.vectors.get("colbert")
            if colbert_vec:
                covered += 1
        return SimpleNamespace(count=covered)

    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        offset=None,
        with_payload=True,
        with_vectors=False,
    ):
        ids = sorted(self._storage.points.keys())
        if offset is None:
            start_index = 0
        else:
            start_index = 0
            for idx, point_id in enumerate(ids):
                if point_id > int(offset):
                    start_index = idx
                    break
            else:
                return [], None

        page_ids = ids[start_index : start_index + limit]
        records = []
        for point_id in page_ids:
            point = self._storage.points[point_id]
            records.append(
                SimpleNamespace(
                    id=point.point_id,
                    payload=point.payload,
                    vector={"colbert": point.vectors.get("colbert")} if with_vectors else {},
                )
            )

        if not page_ids:
            return [], None
        last_id = page_ids[-1]
        has_next = start_index + limit < len(ids)
        next_offset = last_id if has_next else None
        return records, next_offset

    def update_vectors(self, *, collection_name: str, points: list):
        for point in points:
            stored = self._storage.points[int(point.id)]
            for name, value in point.vector.items():
                stored.vectors[name] = value
        return SimpleNamespace(status="ok")


class _FakeAsyncQdrantClient:
    def __init__(self, storage: _FakeQdrantStorage):
        self._storage = storage

    async def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=self._storage.collection_name)])

    async def get_collection(self, collection_name: str):
        return self._storage.collection_info()

    async def query_points(self, *, collection_name: str, limit: int, using=None, **kwargs):
        hits = []
        for point in self._storage.points.values():
            has_colbert = bool(point.vectors.get("colbert"))
            if using == "colbert" and not has_colbert:
                continue
            hits.append(
                SimpleNamespace(
                    id=point.point_id,
                    score=1.0,
                    payload=point.payload,
                )
            )
        return SimpleNamespace(points=hits[:limit])

    async def close(self):
        return None


class _FakeBgeClient:
    def encode_colbert(self, texts: list[str]):
        return SimpleNamespace(colbert_vecs=[[[0.1, 0.2]]] * len(texts))


async def test_backfill_enables_server_side_colbert_search(tmp_path):
    from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner
    from telegram_bot.services.qdrant import QdrantService

    storage = _FakeQdrantStorage()
    storage.points[1] = _StoredPoint(
        point_id=1,
        payload={"page_content": "doc without colbert before backfill", "metadata": {}},
        vectors={"dense": [0.1, 0.2], "bm42": {"indices": [1], "values": [0.4]}},
    )

    sync_client = _FakeSyncQdrantClient(storage)
    backfill = ColbertBackfillRunner(
        collection_name=storage.collection_name,
        qdrant_client=sync_client,
        bge_client=_FakeBgeClient(),
        checkpoint_path=tmp_path / ".checkpoint.json",
        retry_backoff_seconds=0.0,
    )

    service = QdrantService(
        url="http://localhost:6333",
        collection_name=storage.collection_name,
    )
    service._client = _FakeAsyncQdrantClient(storage)

    before = await service.hybrid_search_rrf_colbert(
        dense_vector=[0.1, 0.2],
        sparse_vector={"indices": [1], "values": [0.4]},
        colbert_query=[[0.3, 0.6]],
        top_k=5,
    )
    assert before == []

    stats = backfill.run(batch_size=10)
    assert stats.processed == 1

    service._collection_validated = False
    after = await service.hybrid_search_rrf_colbert(
        dense_vector=[0.1, 0.2],
        sparse_vector={"indices": [1], "values": [0.4]},
        colbert_query=[[0.3, 0.6]],
        top_k=5,
    )
    assert len(after) > 0
    assert after[0]["text"] == "doc without colbert before backfill"
