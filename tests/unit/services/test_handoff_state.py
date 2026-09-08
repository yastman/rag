import pytest

from src.services.handoff_state import HandoffData, HandoffState


def test_handoff_data_creation():
    data = HandoffData(
        client_id=123,
        topic_id=456,
        lead_id=789,
        mode="human_waiting",
        qualification={"goal": "buy", "budget": "50-100"},
    )
    assert data.client_id == 123
    assert data.mode == "human_waiting"
    assert data.manager_joined_at is None


def test_handoff_data_to_redis_dict():
    data = HandoffData(client_id=123, topic_id=456, mode="human_waiting")
    d = data.to_redis_dict()
    assert d["client_id"] == "123"
    assert d["topic_id"] == "456"
    assert d["mode"] == "human_waiting"
    assert "created_at" in d
    assert d["lead_id"] == ""
    assert d["manager_joined_at"] == ""
    assert d["qualification"] == "{}"


def test_handoff_data_to_redis_dict_full():
    data = HandoffData(
        client_id=123,
        topic_id=456,
        mode="human",
        lead_id=789,
        qualification={"goal": "buy", "budget": "50-100"},
    )
    d = data.to_redis_dict()
    assert d["client_id"] == "123"
    assert d["topic_id"] == "456"
    assert d["mode"] == "human"
    assert d["lead_id"] == "789"
    assert d["manager_joined_at"] == ""
    assert d["qualification"] == '{"goal":"buy","budget":"50-100"}'


def test_handoff_data_from_redis_dict():
    raw = {
        "client_id": "123",
        "topic_id": "456",
        "lead_id": "789",
        "mode": "human",
        "created_at": "1709337600.0",
        "manager_joined_at": "1709341200.0",
        "qualification": '{"goal": "buy"}',
    }
    data = HandoffData.from_redis_dict(raw)
    assert data.client_id == 123
    assert data.mode == "human"
    assert data.qualification == {"goal": "buy"}


@pytest.mark.asyncio
async def test_handoff_state_set_and_get(mock_redis):
    state = HandoffState(mock_redis, ttl_hours=24)
    data = HandoffData(client_id=100, topic_id=200, mode="human_waiting")

    await state.set(data)
    result = await state.get_by_client(100)

    assert result is not None
    assert result.topic_id == 200
    assert result.mode == "human_waiting"


@pytest.mark.asyncio
async def test_handoff_state_get_by_topic(mock_redis):
    state = HandoffState(mock_redis, ttl_hours=24)
    data = HandoffData(client_id=100, topic_id=200, mode="human_waiting")
    await state.set(data)

    result = await state.get_by_topic(200)
    assert result is not None
    assert result.client_id == 100


@pytest.mark.asyncio
async def test_handoff_state_update_mode(mock_redis):
    state = HandoffState(mock_redis, ttl_hours=24)
    data = HandoffData(client_id=100, topic_id=200, mode="human_waiting")
    await state.set(data)

    await state.update_mode(100, "human")
    result = await state.get_by_client(100)
    assert result.mode == "human"


@pytest.mark.asyncio
async def test_handoff_state_delete(mock_redis):
    state = HandoffState(mock_redis, ttl_hours=24)
    data = HandoffData(client_id=100, topic_id=200, mode="human_waiting")
    await state.set(data)

    await state.delete(100)
    assert await state.get_by_client(100) is None
    assert await state.get_by_topic(200) is None


# --- Stale reverse topic mappings (#3487) ---


@pytest.mark.asyncio
async def test_set_replaces_topic_and_cleans_old_reverse_key(mock_redis):
    """Topic replace A→B must not leave topic A resolving to handoff B (#3487)."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=111, mode="human_waiting"))
    await state.set(HandoffData(client_id=123, topic_id=222, mode="human_waiting"))

    # Old topic A must not resolve to the new session.
    assert await state.get_by_topic(111) is None
    # New topic B still resolves, and the stale reverse key is gone.
    result = await state.get_by_topic(222)
    assert result is not None
    assert result.client_id == 123
    assert await mock_redis.exists("topic_map:111") == 0
    assert 0 < await mock_redis.ttl("topic_map:222") <= 24 * 3600


@pytest.mark.asyncio
async def test_get_by_topic_validates_current_topic_with_historical_garbage(mock_redis):
    """Reverse keys left behind by older versions must not resolve (#3487)."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=222, mode="human_waiting"))
    # Historical garbage: a reverse key written before replace-cleanup existed.
    await mock_redis.set("topic_map:111", "123")

    assert await state.get_by_topic(111) is None
    # The current mapping still resolves.
    result = await state.get_by_topic(222)
    assert result is not None
    assert result.topic_id == 222


@pytest.mark.asyncio
async def test_delete_with_stale_topic_guard_spares_newer_session(mock_redis):
    """A delete armed with a stale topic must not destroy the replaced session (#3487)."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=111, mode="human"))
    handoff = await state.get_by_topic(111)
    assert handoff is not None

    # Concurrent replacement lands between the snapshot and the close.
    await state.set(HandoffData(client_id=123, topic_id=222, mode="human_waiting"))

    deleted = await state.delete(123, expected_topic_id=handoff.topic_id)

    assert deleted is False
    kept = await state.get_by_client(123)
    assert kept is not None
    assert kept.topic_id == 222
    assert await state.get_by_topic(222) is not None


@pytest.mark.asyncio
async def test_delete_with_matching_topic_removes_both_keys(mock_redis):
    """A guarded delete with the current topic removes forward+reverse keys (#3487)."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=111, mode="human_waiting"))

    deleted = await state.delete(123, expected_topic_id=111)

    assert deleted is True
    assert await state.get_by_client(123) is None
    assert await state.get_by_topic(111) is None
    assert await mock_redis.exists("handoff:123") == 0
    assert await mock_redis.exists("topic_map:111") == 0


@pytest.mark.asyncio
async def test_delete_without_guard_removes_both_keys(mock_redis):
    """Unguarded delete keeps removing forward+reverse keys and reports success."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=111, mode="human_waiting"))

    deleted = await state.delete(123)

    assert deleted is True
    assert await state.get_by_client(123) is None
    assert await mock_redis.exists("topic_map:111") == 0


@pytest.mark.asyncio
async def test_forward_and_reverse_keys_share_ttl_on_update(mock_redis):
    """Forward and reverse keys must refresh TTL together on set (#3487)."""
    state = HandoffState(mock_redis, ttl_hours=24)
    await state.set(HandoffData(client_id=123, topic_id=111, mode="human_waiting"))
    assert 0 < await mock_redis.ttl("handoff:123") <= 24 * 3600
    assert 0 < await mock_redis.ttl("topic_map:111") <= 24 * 3600

    # Re-set through a shorter-TTL state must refresh both keys together.
    refresh = HandoffState(mock_redis, ttl_hours=1)
    await refresh.set(HandoffData(client_id=123, topic_id=111, mode="human"))
    assert 0 < await mock_redis.ttl("handoff:123") <= 3600
    assert 0 < await mock_redis.ttl("topic_map:111") <= 3600


@pytest.fixture
def mock_redis():
    """In-memory Redis mock using fakeredis."""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)
