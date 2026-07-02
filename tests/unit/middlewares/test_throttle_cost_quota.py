"""Unit tests for per-window LLM-cost quota in ThrottlingMiddleware.

Test IDs contain 'throttle_cost_quota' so the DoD acceptance command
  pytest -k throttle_cost_quota -q
selects exactly this module.

Strategy:
- QuotaTracker tests are pure-Python (no aiogram); they run regardless of
  whether aiogram is mocked by the conftest.
- ThrottlingMiddleware integration tests use pytest.importorskip so they are
  skipped when aiogram is unavailable.
- TTLCache maxsize tests use QuotaTracker / inspect attributes, not the
  aiogram-backed ThrottlingMiddleware constructor.
"""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# 1. QuotaTracker — pure Python, no aiogram
# ---------------------------------------------------------------------------


class TestQuotaTracker_throttle_cost_quota:
    """Sliding-window quota logic, tested without any aiogram dependency."""

    def _tracker(self, quota: int = 3, window: int = 60):
        from telegram_bot.middlewares.throttling import QuotaTracker

        return QuotaTracker(quota=quota, window_seconds=window)

    def test_zero_quota_never_exceeded(self):
        """quota=0 means no limit — exceeded() always returns False."""
        t = self._tracker(quota=0)
        for _ in range(100):
            assert t.exceeded(1) is False

    def test_first_n_requests_allowed(self):
        """First N requests return False (not exceeded)."""
        t = self._tracker(quota=3)
        for _ in range(3):
            assert t.exceeded(user_id=99) is False

    def test_n_plus_one_request_blocked(self):
        """N+1 th request returns True (exceeded)."""
        t = self._tracker(quota=2)
        t.exceeded(1)
        t.exceeded(1)
        assert t.exceeded(1) is True

    def test_quota_per_user_independent(self):
        """Each user has their own counter; one exhausting does not block another."""
        t = self._tracker(quota=1)
        t.exceeded(user_id=10)  # user 10 exhausts quota
        assert t.exceeded(user_id=10) is True  # 10 is blocked
        assert t.exceeded(user_id=20) is False  # 20 still has quota

    def test_blocked_request_not_counted(self):
        """exceeded()=True does NOT increment the counter (blocked req not recorded)."""
        t = self._tracker(quota=1)
        t.exceeded(1)  # first — allowed, recorded
        assert t.exceeded(1) is True  # second — blocked, NOT recorded
        # Reset and immediately check: only 1 recorded, so after reset user gets full quota
        t.reset(1)
        assert t.exceeded(1) is False  # fresh quota

    def test_reset_single_user(self):
        """reset(user_id) clears only that user's counter."""
        t = self._tracker(quota=1)
        t.exceeded(1)
        t.exceeded(2)
        t.reset(1)
        assert t.exceeded(1) is False  # 1 got reset
        assert t.exceeded(2) is True  # 2 still exhausted

    def test_reset_all_users(self):
        """reset() without argument clears all counters."""
        t = self._tracker(quota=1)
        t.exceeded(1)
        t.exceeded(2)
        t.reset()
        assert t.exceeded(1) is False
        assert t.exceeded(2) is False

    def test_window_expiry_allows_new_requests(self):
        """After the window passes, the same user can make requests again."""
        t = self._tracker(quota=1, window=1)
        t.exceeded(1)  # fill quota
        assert t.exceeded(1) is True  # blocked immediately

        # Manually expire timestamps by replacing them with old ones
        t._counts[1] = [time.time() - 2]  # older than 1s window
        assert t.exceeded(1) is False  # now allowed again (prune happened)


# ---------------------------------------------------------------------------
# 2. Env-var defaults for QuotaTracker / TTLCache maxsize
# ---------------------------------------------------------------------------


class TestEnvVarDefaults_throttle_cost_quota:
    """Module-level env vars (BOT_QUERY_QUOTA, etc.) set middleware defaults."""

    def test_quota_env_var_controls_default(self, monkeypatch: pytest.MonkeyPatch):
        """BOT_QUERY_QUOTA env var sets QuotaTracker default at import time."""
        monkeypatch.setenv("BOT_QUERY_QUOTA", "7")
        monkeypatch.setenv("BOT_QUERY_WINDOW_SECONDS", "120")

        from importlib import reload

        import telegram_bot.middlewares.throttling as mod

        reload(mod)
        try:
            assert mod._DEFAULT_QUERY_QUOTA == 7
            assert mod._DEFAULT_QUERY_WINDOW == 120
        finally:
            reload(mod)  # restore to original env state

    def test_cache_maxsize_env_var(self, monkeypatch: pytest.MonkeyPatch):
        """BOT_THROTTLE_CACHE_MAXSIZE env var sets the default maxsize."""
        monkeypatch.setenv("BOT_THROTTLE_CACHE_MAXSIZE", "500")

        from importlib import reload

        import telegram_bot.middlewares.throttling as mod

        reload(mod)
        try:
            assert mod._DEFAULT_CACHE_MAXSIZE == 500
        finally:
            reload(mod)


# ---------------------------------------------------------------------------
# 3. ThrottlingMiddleware integration (skip if aiogram is not real)
# ---------------------------------------------------------------------------

# Check if aiogram is real (not mocked by conftest)
import sys
from unittest.mock import MagicMock as _MagicMock


_aiogram_real = "aiogram" in sys.modules and not isinstance(sys.modules["aiogram"], _MagicMock)
_skip_integration = pytest.mark.skipif(
    not _aiogram_real,
    reason="aiogram is mocked or not installed; ThrottlingMiddleware integration skipped",
)


class TestThrottlingMiddleware_throttle_cost_quota:
    """Integration tests that exercise ThrottlingMiddleware with quota."""

    from unittest.mock import AsyncMock, MagicMock, patch

    def _make_middleware(self, quota: int = 2, window: int = 60, admin_ids=None):
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        return ThrottlingMiddleware(
            query_quota=quota,
            query_window_seconds=window,
            admin_ids=admin_ids or [],
        )

    def _user(self, uid: int = 1):
        from aiogram.types import User

        u = self.MagicMock(spec=User)
        u.id = uid
        return u

    def _msg(self):
        from aiogram.types import Message

        m = self.MagicMock(spec=Message)
        m.answer = self.AsyncMock()
        return m

    @_skip_integration
    @pytest.mark.asyncio()
    async def test_middleware_respects_quota(self):
        """N+1th request is rejected when quota is active."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from aiogram.types import Message, User

        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        mw = ThrottlingMiddleware(query_quota=2, query_window_seconds=60)
        handler = AsyncMock(return_value="ok")
        user = MagicMock(spec=User)
        user.id = 42
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch("telegram_bot.middlewares.throttling.get_flag", return_value=None):
            r1 = await mw(handler, event, data)
            r2 = await mw(handler, event, data)
            r3 = await mw(handler, event, data)  # 3rd > quota=2

        assert r1 == "ok"
        assert r2 == "ok"
        assert r3 is None
        assert handler.await_count == 2
        event.answer.assert_awaited()

    @_skip_integration
    @pytest.mark.asyncio()
    async def test_admin_bypasses_quota(self):
        """Admins are exempt from the cost quota."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from aiogram.types import Message, User

        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        mw = ThrottlingMiddleware(query_quota=1, query_window_seconds=60, admin_ids=[99])
        handler = AsyncMock(return_value="ok")
        user = MagicMock(spec=User)
        user.id = 99
        event = MagicMock(spec=Message)
        event.answer = AsyncMock()
        data = {"event_from_user": user}

        with patch("telegram_bot.middlewares.throttling.get_flag", return_value=None):
            for _ in range(5):
                assert await mw(handler, event, data) == "ok"

    @_skip_integration
    def test_cache_maxsize_stored(self):
        """Constructor stores cache_maxsize and it matches what TTLCache uses."""
        from telegram_bot.middlewares.throttling import ThrottlingMiddleware

        mw = ThrottlingMiddleware(cache_maxsize=250)
        assert mw._cache_maxsize == 250
        cache = mw._get_cache(1.0)
        assert cache.maxsize == 250
