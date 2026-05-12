from telegram_bot.integrations.cache import CacheLayerManager
from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


async def test_store_and_get_bge_m3_query_bundle_round_trips() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeRedis()
    cache.redis = fake
    bundle = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[[0.3, 0.4]],
    )

    await cache.store_bge_m3_query_bundle("ВНЖ?", bundle)
    hit = await cache.get_bge_m3_query_bundle(" внж ")

    assert hit == bundle
    assert list(fake.ttls.values()) == [7 * 86400]


async def test_get_bge_m3_query_bundle_returns_none_for_incomplete_payload() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeRedis()
    cache.redis = fake
    await cache.store_exact("bge_m3_query_bundle", "bad-key", {"dense": [0.1]})

    hit = await cache.get_bge_m3_query_bundle("bad-key")

    assert hit is None


async def test_store_bge_m3_query_bundle_noops_for_incomplete_bundle() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    fake = FakeRedis()
    cache.redis = fake
    incomplete = BgeM3QueryVectorBundle(
        dense=[0.1],
        sparse={"indices": [1], "values": [0.2]},
        colbert=[],
    )

    await cache.store_bge_m3_query_bundle("query", incomplete)

    assert fake.values == {}
    assert fake.ttls == {}


async def test_get_bge_m3_query_bundle_returns_none_when_redis_disabled() -> None:
    cache = CacheLayerManager(redis_url="redis://localhost:6379")
    cache.redis = None

    hit = await cache.get_bge_m3_query_bundle("query")

    assert hit is None
