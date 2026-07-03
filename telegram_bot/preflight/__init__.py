"""Backward-compat re-export — split into checks + remediation."""

import asyncpg
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient

from telegram_bot.preflight.checks import *  # noqa: F403
from telegram_bot.preflight.checks import (
    _DEP_REMEDIATION,
    _build_dependency_report,
    _check_critical_with_retry,
    _check_single_dep,
    _read_colbert_coverage_warn_threshold,
    _validate_bge_m3_url,
)
from telegram_bot.preflight.remediation import *  # noqa: F403
from telegram_bot.preflight.remediation import (
    _check_redis_deep,
    _verify_cache_synthetic,
)
