from telegram_bot.integrations.cache import BGE_M3_QUERY_BUNDLE_MODEL_NAME, CacheLayerManager
from telegram_bot.services.bge_m3_query_bundle import (
    BgeM3QueryVectorBundle,
    make_bge_m3_query_bundle_key_material,
)


class FakeEmbeddingsCache:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict] = {}
        self.ttls: dict[tuple[str, str], int | None] = {}
        self.get_calls: list[tuple[str, str]] = []

    async def aget(self, content: str, model_name: str):
        self.get_calls.append((content, model_name))
        return self.data.get((content, model_name))

    async def aset(self, content: str, model_name: str, embedding, metadata=None, ttl=None) -> None:
        self.data[(content, model_name)] = {"embedding": embedding, "metadata": metadata}
        self.ttls[(content, model_name)] = ttl


async def test_store_and_get_bge_m3_query_bundle_round_trips() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
    )

    await cache.store_bge_m3_query_bundle("ВНЖ?", bundle)
    hit = await cache.get_bge_m3_query_bundle(" внж ")

    assert hit == bundle


async def test_get_bge_m3_query_bundle_returns_none_for_incomplete_payload() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeEmbeddingsCache()
    cache.embed_cache = fake
    # Store a malformed entry directly (missing colbert in metadata)
    key_material = make_bge_m3_query_bundle_key_material("some-key")
    fake.data[(key_material, BGE_M3_QUERY_BUNDLE_MODEL_NAME)] = {
        "embedding": [0.1],
        "metadata": {"sparse": {"indices": [1], "values": [0.2]}},
    }

    hit = await cache.get_bge_m3_query_bundle("some-key")

    assert hit is None
    assert fake.get_calls == [(key_material, BGE_M3_QUERY_BUNDLE_MODEL_NAME)]


async def test_store_bge_m3_query_bundle_noops_for_incomplete_bundle() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeEmbeddingsCache()
    cache.embed_cache = fake
    incomplete = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[],
    )

    await cache.store_bge_m3_query_bundle("query", incomplete)

    assert fake.data == {}
    assert fake.ttls == {}


async def test_get_bge_m3_query_bundle_returns_none_when_cache_disabled() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = None

    hit = await cache.get_bge_m3_query_bundle("query")

    assert hit is None


async def test_store_uses_bundle_model_by_default_not_returned_by_default_get() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
        model="other-model",
    )

    await cache.store_bge_m3_query_bundle("query", bundle)
    # Default get uses default model, should miss
    hit_default = await cache.get_bge_m3_query_bundle("query")
    # Explicit get with matching model should hit
    hit_matching = await cache.get_bge_m3_query_bundle("query", model="other-model")

    assert hit_default is None
    assert hit_matching == bundle


async def test_store_uses_bundle_max_length_by_default() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
        max_length=1024,
    )

    await cache.store_bge_m3_query_bundle("query", bundle)
    hit_default = await cache.get_bge_m3_query_bundle("query")
    hit_matching = await cache.get_bge_m3_query_bundle("query", max_length=1024)

    assert hit_default is None
    assert hit_matching == bundle


async def test_store_uses_bundle_version_by_default() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
        version="v2",
    )

    await cache.store_bge_m3_query_bundle("query", bundle)
    hit_default = await cache.get_bge_m3_query_bundle("query")
    hit_matching = await cache.get_bge_m3_query_bundle("query", version="v2")

    assert hit_default is None
    assert hit_matching == bundle


async def test_store_uses_explicit_override_when_provided() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
        model="BAAI/bge-m3",
    )

    await cache.store_bge_m3_query_bundle("query", bundle, model="override-model")
    # Get with override model should hit
    hit_override = await cache.get_bge_m3_query_bundle("query", model="override-model")
    # Get with bundle's original model should miss
    hit_original = await cache.get_bge_m3_query_bundle("query", model="BAAI/bge-m3")
    # Default get should also miss
    hit_default = await cache.get_bge_m3_query_bundle("query")

    assert hit_override == bundle
    assert hit_original is None
    assert hit_default is None


async def test_store_override_max_length_separates_from_bundle_default() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.embed_cache = FakeEmbeddingsCache()
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
        max_length=512,
    )

    await cache.store_bge_m3_query_bundle("query", bundle, max_length=2048)
    hit_override = await cache.get_bge_m3_query_bundle("query", max_length=2048)
    hit_original = await cache.get_bge_m3_query_bundle("query", max_length=512)
    hit_default = await cache.get_bge_m3_query_bundle("query")

    assert hit_override == bundle
    assert hit_original is None
    assert hit_default is None
