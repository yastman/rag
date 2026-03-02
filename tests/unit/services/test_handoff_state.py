import pytest

from telegram_bot.services.handoff_state import HandoffData, HandoffState


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


@pytest.fixture
def mock_redis():
    """In-memory Redis mock using fakeredis."""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)
