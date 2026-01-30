#!/usr/bin/env python3
"""Setup Redis vector search indexes for RAG semantic cache.

This script creates the necessary Redis indexes for the RAG pipeline:
- idx:rag:semantic_cache: Vector search index for semantic cache (LLM answers)

Usage:
    python scripts/setup_redis_indexes.py
    python scripts/setup_redis_indexes.py --force  # Drop and recreate

Environment variables:
    REDIS_URL: Full Redis URL (default: redis://localhost:6379)
    REDIS_HOST: Redis host (used if REDIS_URL not set)
    REDIS_PORT: Redis port (default: 6379)
    REDIS_PASSWORD: Redis password (optional)
"""

import argparse
import os
import sys

import redis


def get_redis_url() -> str:
    """Get Redis URL from environment variables."""
    # Check for full URL first
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url

    # Build URL from individual components
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    password = os.environ.get("REDIS_PASSWORD")

    if password:
        return f"redis://:{password}@{host}:{port}"
    return f"redis://{host}:{port}"


def check_query_engine(client: redis.Redis) -> bool:
    """Check if Redis Query Engine (FT.* commands) is available.

    Works with both Redis 8.4+ (native) and Redis Stack (module).
    """
    try:
        client.execute_command("FT._LIST")
        return True
    except redis.ResponseError as e:
        # "unknown command" means Query Engine not available
        # Other errors mean command exists but something else failed
        return "unknown command" not in str(e).lower()
    except Exception:
        return False


def index_exists(client: redis.Redis, index_name: str) -> bool:
    """Check if index already exists."""
    try:
        client.execute_command("FT.INFO", index_name)
        return True
    except redis.ResponseError:
        return False


def drop_index(client: redis.Redis, index_name: str) -> bool:
    """Drop existing index."""
    try:
        # DD flag drops documents, without DD only index is dropped
        client.execute_command("FT.DROPINDEX", index_name)
        return True
    except redis.ResponseError as e:
        print(f"  Warning: Could not drop index: {e}")
        return False


def create_semantic_cache_index(client: redis.Redis) -> dict:
    """Create the semantic cache vector search index.

    Index schema:
        - query_vector: VECTOR FLAT (1024 dim, FLOAT32, COSINE distance)
        - answer: TEXT (searchable)
        - timestamp: NUMERIC (for sorting/filtering)

    Returns:
        dict with index info after creation
    """
    index_name = "idx:rag:semantic_cache"

    # FT.CREATE command for semantic cache index
    # Using FLAT index for exact KNN search (good for smaller cache sizes)
    # BGE-M3 model outputs 1024-dimensional vectors
    client.execute_command(
        "FT.CREATE",
        index_name,
        "ON",
        "HASH",
        "PREFIX",
        "1",
        "rag:semantic:",
        "SCHEMA",
        "query_vector",
        "VECTOR",
        "FLAT",
        "6",  # Number of following args for FLAT
        "TYPE",
        "FLOAT32",
        "DIM",
        "1024",
        "DISTANCE_METRIC",
        "COSINE",
        "answer",
        "TEXT",
        "timestamp",
        "NUMERIC",
    )

    # Get index info after creation
    info = client.execute_command("FT.INFO", index_name)
    return parse_ft_info(info)


def parse_ft_info(info: list) -> dict:
    """Parse FT.INFO response into a readable dict."""
    result = {}
    i = 0
    while i < len(info):
        key = info[i]
        if isinstance(key, bytes):
            key = key.decode()

        i += 1
        if i < len(info):
            value = info[i]
            if isinstance(value, bytes):
                value = value.decode()
            elif isinstance(value, list):
                # Handle nested lists (like attributes)
                value = str(value)
            result[key] = value
            i += 1

    return result


def print_index_info(info: dict, index_name: str):
    """Print formatted index information."""
    print(f"\n  Index: {index_name}")
    print("  -------------------------")

    # Key metrics to display
    display_keys = [
        ("num_docs", "Documents"),
        ("max_doc_id", "Max Doc ID"),
        ("num_terms", "Terms"),
        ("num_records", "Records"),
        ("inverted_sz_mb", "Inverted Index Size (MB)"),
        ("vector_index_sz_mb", "Vector Index Size (MB)"),
        ("total_indexing_time", "Indexing Time (ms)"),
    ]

    for key, label in display_keys:
        if key in info:
            print(f"  {label}: {info[key]}")


def main():
    parser = argparse.ArgumentParser(
        description="Setup Redis vector search indexes for RAG semantic cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  REDIS_URL         Full Redis URL (default: redis://localhost:6379)
  REDIS_HOST        Redis host (used if REDIS_URL not set)
  REDIS_PORT        Redis port (default: 6379)
  REDIS_PASSWORD    Redis password (optional)

Examples:
  python scripts/setup_redis_indexes.py
  python scripts/setup_redis_indexes.py --force
  REDIS_URL=redis://localhost:6379 python scripts/setup_redis_indexes.py
        """,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop and recreate index if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check configuration without creating indexes",
    )

    args = parser.parse_args()

    # Get Redis URL
    redis_url = get_redis_url()
    # Mask password in URL for display
    display_url = redis_url
    if "@" in redis_url:
        parts = redis_url.split("@")
        display_url = f"redis://***@{parts[1]}"

    print("=" * 60)
    print("Redis Index Setup for RAG Semantic Cache")
    print("=" * 60)
    print(f"\nConnecting to: {display_url}")

    # Connect to Redis
    try:
        client = redis.from_url(
            redis_url,
            decode_responses=False,  # Keep bytes for proper handling
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        client.ping()
        print("  Connection: OK")
    except redis.ConnectionError as e:
        print(f"\n  ERROR: Cannot connect to Redis: {e}")
        print("\n  Please check:")
        print("    - Redis server is running")
        print("    - REDIS_URL or REDIS_HOST/REDIS_PORT are correct")
        print("    - Network connectivity")
        sys.exit(1)

    # Check for Query Engine
    print("\nChecking Redis Query Engine...")
    if not check_query_engine(client):
        print("\n  ERROR: Redis Query Engine is not available!")
        print("\n  FT.* commands are required for vector search functionality.")
        print("  Solutions:")
        print("\n  Option 1: Use Redis 8.4+ (Query Engine built-in)")
        print("    docker run -p 6379:6379 redis:8.4.0")
        print("\n  Option 2: Use Redis Stack (legacy)")
        print("    docker run -p 6379:6379 redis/redis-stack-server:latest")
        print("\n  More info: https://redis.io/docs/latest/develop/whats-new/8-0/")
        sys.exit(1)
    print("  Query Engine: OK")

    if args.dry_run:
        print("\n[DRY RUN] Configuration verified, no indexes created.")
        sys.exit(0)

    # Create semantic cache index
    index_name = "idx:rag:semantic_cache"
    print(f"\nSetting up index: {index_name}")
    print("  Prefix: rag:semantic:")
    print("  Schema:")
    print("    - query_vector: VECTOR FLAT (DIM=1024, FLOAT32, COSINE)")
    print("    - answer: TEXT")
    print("    - timestamp: NUMERIC")

    exists = index_exists(client, index_name)

    if exists:
        if args.force:
            print("\n  Index exists, dropping (--force)...")
            if drop_index(client, index_name):
                print("  Dropped existing index")
            else:
                print("  WARNING: Failed to drop index, will try to recreate anyway")
            exists = False
        else:
            print("\n  Index already exists. Use --force to recreate.")
            # Show current index info
            info = client.execute_command("FT.INFO", index_name)
            parsed_info = parse_ft_info(info)
            print_index_info(parsed_info, index_name)
            print("\n" + "=" * 60)
            print("Setup complete (no changes made)")
            print("=" * 60)
            sys.exit(0)

    if not exists:
        print("\n  Creating index...")
        try:
            info = create_semantic_cache_index(client)
            print("  Index created successfully!")
            print_index_info(info, index_name)
        except redis.ResponseError as e:
            print(f"\n  ERROR: Failed to create index: {e}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print("\nThe semantic cache index is ready for use.")
    print("Cache entries will be stored with prefix: rag:semantic:")
    print("\nTo verify, run:")
    print(f"  redis-cli FT.INFO {index_name}")


if __name__ == "__main__":
    main()
