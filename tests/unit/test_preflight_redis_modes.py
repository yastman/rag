"""Preflight REDIS_MODE gating tests (#3362, decision #3354).

- ``disabled``: redis/redis_cache checks are skipped entirely — no
  connection attempt; the report exposes the selected mode.
- ``single_instance``: Redis is probed but a failure is DEGRADED, not
  fatal ("cache may fail open"; durable capabilities reported honestly).
- ``multi_instance``: Redis is required at startup — a failure is
  CRITICAL and raises PreflightError before polling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.runtime.integrations.redis_mode import RedisMode
from telegram_bot.preflight.checks import PreflightError, check_dependencies
from telegram_bot.startup_status import StartupSeverity


def _config(mode: RedisMode):
    cfg = AsyncMock()
    cfg.redis_mode = mode
    cfg.redis_url = "redis://localhost:6379"
    return cfg


def _recorders(redis_passes: bool):
    """Patch the dep check seams, recording which deps were probed.

    Redis deps return ``redis_passes``; all other deps pass so the tests
    isolate the Redis-mode behavior.
    """
    probed: list[str] = []

    async def _single(name, _config, _client, **_kwargs):
        probed.append(name)
        if name in ("redis", "redis_cache"):
            return redis_passes
        return True

    async def _critical(name, _config, _client, **_kwargs):
        probed.append(name)
        if name in ("redis", "redis_cache"):
            return redis_passes
        return True

    return probed, _single, _critical


def _patched(redis_passes: bool):
    probed, single, critical = _recorders(redis_passes)
    return probed, (
        patch("telegram_bot.preflight._check_single_dep", side_effect=single),
        patch("telegram_bot.preflight._check_critical_with_retry", side_effect=critical),
        patch("telegram_bot.preflight.CRITICAL_RETRY_DELAY", 0),
    )


class TestDisabledModePreflight:
    async def test_redis_checks_skipped_without_connection(self) -> None:
        probed, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=False)
        with single_patch, critical_patch, delay_patch:
            results = await check_dependencies(_config(RedisMode.DISABLED))

        assert "redis" not in probed
        assert "redis_cache" not in probed
        assert "redis" not in results
        assert "redis_cache" not in results
        # Non-Redis deps are still probed.
        assert "qdrant" in probed

    async def test_report_exposes_disabled_mode(self) -> None:
        _, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=False)
        with single_patch, critical_patch, delay_patch:
            result = await check_dependencies(_config(RedisMode.DISABLED))

        mode_signals = [s for s in result.report.signals if s.source == "redis_mode"]
        assert mode_signals, "startup report must expose the selected Redis mode"
        assert "disabled" in mode_signals[0].summary


class TestSingleInstancePreflight:
    async def test_redis_failure_is_degraded_not_fatal(self) -> None:
        probed, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=False)
        with single_patch, critical_patch, delay_patch:
            results = await check_dependencies(_config(RedisMode.SINGLE_INSTANCE))

        assert "redis" in probed
        assert results["redis"] is False
        # Honest degradation: report is DEGRADED and startup is not blocked.
        assert results.report.final_severity is StartupSeverity.DEGRADED

    async def test_redis_failure_marks_capabilities_unavailable(self) -> None:
        _, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=False)
        with single_patch, critical_patch, delay_patch:
            result = await check_dependencies(_config(RedisMode.SINGLE_INSTANCE))

        mode_signals = [s for s in result.report.signals if s.source == "redis_mode"]
        assert mode_signals
        assert "unavailable" in mode_signals[0].summary

    async def test_redis_ok_reports_enabled(self) -> None:
        _, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=True)
        with single_patch, critical_patch, delay_patch:
            result = await check_dependencies(_config(RedisMode.SINGLE_INSTANCE))

        mode_signals = [s for s in result.report.signals if s.source == "redis_mode"]
        assert mode_signals
        assert "enabled" in mode_signals[0].summary
        assert mode_signals[0].severity is StartupSeverity.OK


class TestMultiInstancePreflight:
    async def test_redis_failure_is_fatal(self) -> None:
        probed, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=False)
        with single_patch, critical_patch, delay_patch:
            with pytest.raises(PreflightError) as exc_info:
                await check_dependencies(_config(RedisMode.MULTI_INSTANCE))

        assert "redis" in probed
        assert "redis" in exc_info.value.failed_deps

    async def test_report_exposes_multi_mode_when_healthy(self) -> None:
        _, (single_patch, critical_patch, delay_patch) = _patched(redis_passes=True)
        with single_patch, critical_patch, delay_patch:
            result = await check_dependencies(_config(RedisMode.MULTI_INSTANCE))

        mode_signals = [s for s in result.report.signals if s.source == "redis_mode"]
        assert mode_signals
        assert "multi_instance" in mode_signals[0].summary
        assert "lock" in mode_signals[0].summary.lower()
