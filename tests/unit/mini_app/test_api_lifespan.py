"""Tests for mini_app.api lifespan + Redis dependency wiring (#1645).

The previous implementation kept a module-level lazy ``_redis_client``
global and an ``_get_redis()`` factory called from each request handler.
That bypasses FastAPI's native lifecycle and never closes the Redis
connection on app shutdown.

This contract pins the new shape (Context7 /websites/fastapi):

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.redis = aioredis.from_url(...)
        try:
            yield
        finally:
            await app.state.redis.aclose()

    app = FastAPI(lifespan=lifespan)

    async def get_redis(request: Request) -> Any:
        return request.app.state.redis
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("fastapi")
pytestmark = pytest.mark.requires_extras


def test_module_no_longer_exposes_module_level_redis_global() -> None:
    """``_redis_client`` module global must be removed (#1645)."""
    from mini_app import api as mod

    assert not hasattr(mod, "_redis_client"), (
        "mini_app.api._redis_client global must be removed; "
        "Redis lifecycle is now owned by lifespan + app.state.redis"
    )


def test_module_no_longer_exposes_lazy_get_redis_factory() -> None:
    """The lazy ``_get_redis()`` global factory is replaced by ``get_redis(request)``."""
    from mini_app import api as mod

    assert not hasattr(mod, "_get_redis"), (
        "mini_app.api._get_redis lazy-init global must be removed; "
        "use FastAPI Depends(get_redis) instead"
    )


def test_module_exposes_lifespan_and_get_redis_dependency() -> None:
    """``lifespan`` and ``get_redis`` must be importable from mini_app.api."""
    from mini_app import api as mod

    assert hasattr(mod, "lifespan"), "mini_app.api.lifespan async context manager required"
    assert hasattr(mod, "get_redis"), "mini_app.api.get_redis(request) dependency required"


def test_app_uses_lifespan_for_lifecycle() -> None:
    """FastAPI app must be constructed with the lifespan context manager."""
    from mini_app import api as mod

    # FastAPI stores the lifespan on ``app.router.lifespan_context``.
    lifespan_ctx = getattr(mod.app.router, "lifespan_context", None)
    assert lifespan_ctx is not None, "FastAPI(lifespan=...) wiring missing"


async def test_lifespan_opens_and_closes_redis() -> None:
    """Entering lifespan must construct Redis; exit must close it exactly once."""
    from mini_app import api as mod

    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=fake_client) as mock_factory:
        async with mod.lifespan(mod.app):
            assert mod.app.state.redis is fake_client
            mock_factory.assert_called_once()

        # Lifespan exit closes the client exactly once.
        fake_client.aclose.assert_awaited_once()


async def test_get_redis_returns_app_state_redis() -> None:
    """``get_redis(request)`` must return ``request.app.state.redis``."""
    from mini_app import api as mod

    sentinel_redis = MagicMock(name="redis-client")
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=sentinel_redis)))

    result = await mod.get_redis(fake_request)
    assert result is sentinel_redis


def test_start_expert_handler_uses_depends_get_redis() -> None:
    """AST contract: ``start_expert`` consumes Redis via ``Depends(get_redis)``.

    Forbids regressing to the lazy module-level ``await _get_redis()`` lookup
    that owned the connection lifecycle implicitly.
    """
    from mini_app import api as mod

    source = textwrap.dedent(inspect.getsource(mod.start_expert))
    tree = ast.parse(source)

    func_def = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "start_expert"
    )

    # Search default values + annotations for a Depends(get_redis) call.
    uses_depends_get_redis = False
    for default in list(func_def.args.defaults) + list(func_def.args.kw_defaults):
        if default is None:
            continue
        if isinstance(default, ast.Call):
            func = default.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "Depends":
                # Confirm the dependency target is get_redis.
                target = ast.unparse(default.args[0]) if default.args else ""
                if "get_redis" in target:
                    uses_depends_get_redis = True

    # Defensively forbid the legacy lazy lookup inside the body.
    body_source = ast.unparse(func_def)
    assert "_get_redis(" not in body_source, (
        "start_expert must not call legacy _get_redis(); use Depends(get_redis)"
    )
    assert uses_depends_get_redis, (
        "start_expert must declare a Redis parameter via Depends(get_redis) "
        "for FastAPI-native dependency injection (#1645)"
    )


# ---------------------------------------------------------------------------
# #2161 — explicit Langfuse init in mini-app FastAPI lifespan
# ---------------------------------------------------------------------------


async def test_lifespan_initializes_langfuse_when_credentials_present() -> None:
    """Lifespan must explicitly call ``initialize_langfuse`` + ``auth_check``.

    Without an explicit init the SDK lazy-builds a singleton on the first
    ``get_client()`` call. If env wasn't fully loaded by then (or the host is
    unreachable) the singleton stays disabled silently for the rest of the
    process and zero traces materialize for ``@observe``-decorated endpoints
    (``miniapp-start-expert``, ``miniapp-submit-phone``,
    ``miniapp-kommo-create-lead``). Closes #2161.
    """
    from mini_app import api as mod

    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()

    fake_lf_client = MagicMock(name="langfuse-client")
    fake_lf_client.auth_check = MagicMock(return_value=True)
    fake_lf_client.shutdown = MagicMock()

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch("mini_app.api.initialize_langfuse", return_value=fake_lf_client) as init_lf,
    ):
        async with mod.lifespan(mod.app):
            # Client is stashed on app state so it can be reused/shut down.
            assert mod.app.state.langfuse is fake_lf_client
            init_lf.assert_called_once()
            fake_lf_client.auth_check.assert_called_once()

        # Lifespan exit must flush+close the Langfuse client exactly once.
        fake_lf_client.shutdown.assert_called_once()


async def test_lifespan_disables_langfuse_when_credentials_missing() -> None:
    """Missing/invalid credentials must gracefully disable tracing — never crash."""
    from mini_app import api as mod

    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch("mini_app.api.initialize_langfuse", return_value=None) as init_lf,
    ):
        async with mod.lifespan(mod.app):
            assert mod.app.state.langfuse is None
            init_lf.assert_called_once()


async def test_lifespan_handles_auth_check_failure_gracefully() -> None:
    """If ``auth_check`` raises, tracing is disabled but the API still boots."""
    from mini_app import api as mod

    fake_redis = MagicMock()
    fake_redis.aclose = AsyncMock()

    fake_lf_client = MagicMock(name="langfuse-client")
    fake_lf_client.auth_check = MagicMock(side_effect=RuntimeError("bad credentials"))
    fake_lf_client.shutdown = MagicMock()

    with (
        patch("redis.asyncio.from_url", return_value=fake_redis),
        patch("mini_app.api.initialize_langfuse", return_value=fake_lf_client),
    ):
        async with mod.lifespan(mod.app):
            # Auth failed — client must be reset to None so handlers no-op.
            assert mod.app.state.langfuse is None
            fake_lf_client.auth_check.assert_called_once()
            # The failed client must be shut down on auth failure to release threads.
            fake_lf_client.shutdown.assert_called_once()
