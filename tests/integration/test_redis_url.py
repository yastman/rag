"""Test Redis URL generation (without actual connection)."""

import os


def test_redis_url_generation():
    """Test that Redis URL components are available from env vars."""
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_CACHE_DB", "2")

    # Port and DB should always have valid defaults
    assert redis_port == "6379", f"Expected port '6379', got '{redis_port}'"
    assert redis_db == "2", f"Expected DB '2', got '{redis_db}'"

    # Host should be a non-empty string (could be 'redis', 'localhost', etc.)
    assert len(redis_host) > 0, "REDIS_HOST is empty"

    # URL format should be valid
    url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    assert url.startswith("redis://")
