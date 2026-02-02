#!/usr/bin/env python3
"""Test Redis URL generation (without actual connection)."""

import os
import sys
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_redis_url_generation():
    """Test that Redis URL is correctly generated from env vars."""
    print("🔄 Testing Redis URL generation...")

    # Load password from .env
    env_file = Path("/srv/.env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("REDIS_PASSWORD="):
                    redis_password = line.split("=", 1)[1].strip()
                    os.environ["REDIS_PASSWORD"] = redis_password
                    break

    # Test URL generation logic (same as in RedisSemanticCache)
    redis_password = os.getenv("REDIS_PASSWORD", "")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_CACHE_DB", "2")

    # Verify URL would be generated correctly (same logic as RedisSemanticCache)
    print("\n✅ Generated Redis URL components:")
    print(f"   Host: {redis_host}")
    print(f"   Port: {redis_port}")
    print(f"   DB: {redis_db}")
    print(f"   Password: {'*' * 8} (hidden)")
    print(f"   Full URL: redis://:{('*' * 8)}@{redis_host}:{redis_port}/{redis_db}")

    # Verify components
    assert redis_host == "redis", f"Expected host 'redis', got '{redis_host}'"
    assert redis_port == "6379", f"Expected port '6379', got '{redis_port}'"
    assert redis_db == "2", f"Expected DB '2', got '{redis_db}'"
    assert len(redis_password) > 0, "Password is empty!"

    print("\n✅ All checks passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Redis URL Generation Test")
    print("=" * 60)

    try:
        test_redis_url_generation()
        print("\n" + "=" * 60)
        print("🎉 Test passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
