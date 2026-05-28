"""Mini App FastAPI backend."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import uuid as _uuid_lib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from mini_app.auth import validate_init_data
from mini_app.expert_start import StartExpertRequest, StartExpertResponse
from mini_app.phone import PhoneRequest, submit_phone
from src.observability import get_client, initialize_langfuse, observe, propagate_attributes
from src.observability_sentry import initialize_sentry, set_runtime_tags
from src.services.content_loader import load_mini_app_config


logger = logging.getLogger(__name__)


_DEEPLINK_TTL = 300  # seconds

# Test-mode sentinel: when ``TELEGRAM_BOT_TOKEN`` (or legacy ``BOT_TOKEN``) is
# set to this exact value we bypass HMAC validation and inject a synthetic
# user so CI / smoke tests can exercise the mutation paths without a live
# Telegram bot. The sentinel is intentionally non-secret and obvious.
_TEST_TOKEN_SENTINEL = "TEST"  # nosec B105 - explicit non-secret CI sentinel


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the Redis client on startup and close it on shutdown.

    The Mini App backend uses Redis for short-lived deeplink payloads
    (``miniapp:q:<uuid>``) and pub/sub notifications to the bot. Owning
    the connection lifecycle here (instead of a module-level lazy
    global) ensures graceful close on process shutdown and matches the
    FastAPI-native pattern (#1645).

    Langfuse tracing is initialized explicitly here as well (#2161). The
    Mini App process owns its own ``Langfuse()`` client built via
    :func:`src.observability.initialize_langfuse` so ``@observe``-
    decorated endpoints (``miniapp-start-expert``, ``miniapp-submit-phone``,
    ``miniapp-kommo-create-lead``) actually emit traces. Without an
    explicit init the Langfuse SDK lazy-builds a singleton on first
    ``get_client()`` call; if env wasn't fully loaded by then (or if
    ``auth_check`` would have failed) the singleton stays disabled
    silently for the remainder of the process. Initializing in lifespan
    surfaces credential / connectivity errors loudly at startup and
    flushes pending spans on graceful shutdown.
    """
    # Initialize Sentry FIRST so any subsequent startup error (Redis,
    # config) is captured. No-op when SENTRY_DSN is unset (#1417).
    if initialize_sentry():
        set_runtime_tags(service="mini-app")
        logger.info("Sentry error tracking enabled with PII redaction")

    # Initialize Langfuse explicitly (#2161). ``initialize_langfuse``
    # logs the reason for any disable (missing keys, unreachable host,
    # SDK import failure) at INFO/WARNING and never raises, so the API
    # boots cleanly even when Langfuse is not configured. Stash the
    # client on ``app.state.langfuse`` so it can be shut down on exit
    # alongside Redis.
    langfuse_client = initialize_langfuse()
    if langfuse_client is not None:
        try:
            langfuse_client.auth_check()
            logger.info("Langfuse initialized for mini-app-api")
        except Exception:
            logger.exception("Langfuse auth_check failed; tracing disabled for mini-app-api")
            with contextlib.suppress(Exception):
                langfuse_client.shutdown()
            langfuse_client = None
    app.state.langfuse = langfuse_client

    # Activate FastAPI OTEL auto-instrumentation (#2225). Adds standard
    # ASGI server spans with http.method / http.route / http.status_code
    # semantic attributes; auto-extracts traceparent / baggage from incoming
    # requests so any @observe span downstream nests under the originating
    # cross-service trace. Idempotent and best-effort — never blocks boot.
    from src.observability_otel import instrument_fastapi_app

    instrument_fastapi_app(app)

    import redis.asyncio as aioredis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = aioredis.from_url(redis_url, decode_responses=True)
    app.state.redis = client
    try:
        yield
    finally:
        # ``aioredis`` clients expose ``aclose`` in modern versions; fall back to
        # ``close`` for older releases. Either way, the connection pool drains.
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        # Flush + close Langfuse so pending spans land in the backend
        # before the process exits (#2161). ``shutdown`` is idempotent
        # and safe to call even when ``initialize_langfuse`` returned
        # ``None`` (suppressed below).
        if app.state.langfuse is not None:
            with contextlib.suppress(Exception):
                app.state.langfuse.shutdown()


async def get_redis(request: Request) -> Any:
    """FastAPI dependency that returns the app-scoped Redis client.

    Handlers receive the connection via ``Depends(get_redis)`` so the
    lifecycle stays owned by ``lifespan`` instead of leaking into module
    globals.
    """
    return request.app.state.redis


def _get_bot_token() -> str:
    """Return the Telegram bot token from environment.

    Reads ``TELEGRAM_BOT_TOKEN`` (canonical, shared with ``telegram_bot``)
    and falls back to ``BOT_TOKEN`` for legacy compatibility. Returns an
    empty string if neither is set, so the caller can map that into a
    user-facing 401 ("server misconfigured") rather than a 500 stack
    trace.
    """
    return os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")


async def get_validated_init_data(
    x_init_data: str | None = Header(
        default=None,
        alias="X-Init-Data",
        description="Telegram WebApp signed initData string",
    ),
) -> dict[str, Any]:
    """FastAPI dependency: validate Telegram initData and return parsed dict.

    Mounted on every Mini App mutation endpoint (#1595) so callers cannot
    reach the Redis / CRM layer without proving they hold a fresh, signed
    initData payload from Telegram. Validation itself is delegated to the
    SDK helper :func:`mini_app.auth.validate_init_data`, which in turn
    delegates the HMAC check to ``aiogram.utils.web_app``.

    Returns
    -------
    dict
        Parsed initData with at least a ``user`` sub-dict carrying the
        Telegram numeric user id. Handlers downstream MUST derive
        ``user_id`` from this dict, never from the JSON request body.

    Raises
    ------
    HTTPException(status_code=401)
        For any of: missing header, server bot token not configured,
        invalid HMAC signature, expired ``auth_date``.
    """
    if x_init_data is None:
        raise HTTPException(status_code=401, detail="X-Init-Data header is required")

    bot_token = _get_bot_token()
    if not bot_token:
        # Fail closed — no token, no validation, no auth.
        raise HTTPException(status_code=401, detail="Server bot token not configured")

    if bot_token == _TEST_TOKEN_SENTINEL:
        # CI/local-test bypass — never trips in production because the
        # sentinel is the literal string "TEST" and not a real BotFather
        # token. The synthetic user keeps downstream code paths exercised
        # without requiring a live Telegram client.
        return {"user": {"id": 0, "first_name": "TestUser"}, "auth_date": "0"}

    try:
        return validate_init_data(x_init_data, bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# CORS — restrict to configured origin (#1595).
#
# Operators set ``MINI_APP_ALLOWED_ORIGIN`` in production (e.g.
# ``https://mini-app.fortnoks.com``). The default ``https://t.me`` lets the
# stack boot in dev without configuration while still rejecting arbitrary
# cross-origin callers. An empty/whitespace-only env value is treated as
# unset and falls back to the default.
# ---------------------------------------------------------------------------

_CORS_ORIGIN = os.environ.get("MINI_APP_ALLOWED_ORIGIN", "").strip() or "https://t.me"


app = FastAPI(title="FortNoks Mini App API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_CORS_ORIGIN],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Init-Data"],
)


@app.get("/api/config")
async def get_config() -> dict:
    """Return Mini App UI config: questions + experts."""
    return load_mini_app_config()


def _update_current_span(**kwargs: Any) -> None:
    """Curated update_current_span; no-op when Langfuse client absent."""
    lf = get_client()
    if lf is not None:
        lf.update_current_span(**kwargs)


@app.post("/api/start-expert")
@observe(name="miniapp-start-expert", capture_input=False, capture_output=False)
async def start_expert(
    request: StartExpertRequest,
    redis: Any = Depends(get_redis),
    init_data: dict = Depends(get_validated_init_data),
) -> StartExpertResponse:
    """Store deep-link payload in Redis and return a Telegram start link.

    The Telegram numeric user id is taken from the SDK-validated initData
    dict (``init_data["user"]["id"]``) — request body ``user_id`` is no
    longer trusted (#1595). The body's optional ``message`` and
    ``query_id`` fields stay caller-supplied.

    Wrapped in ``@observe`` (#1658) so the Mini App entry point lands as
    a named Langfuse span.
    """
    # Trust only the server-validated identity (#1595).
    user_id: int = int(init_data["user"]["id"])

    with propagate_attributes(
        session_id=f"miniapp-{user_id}",
        user_id=str(user_id),
        tags=["miniapp", "start-expert", request.expert_id],
        metadata={"surface": "miniapp"},
        as_baggage=True,
    ):
        _update_current_span(
            input={
                "expert_id": request.expert_id,
                "has_message": request.message is not None,
                "has_query_id": request.query_id is not None,
            }
        )

        config = load_mini_app_config()
        experts = config.get("experts", [])
        expert = next((e for e in experts if e["id"] == request.expert_id), None)
        if expert is None:
            _update_current_span(level="ERROR", status_message="expert_not_found")
            raise HTTPException(status_code=404, detail="Expert not found")

        uid = str(_uuid_lib.uuid4())
        payload = json.dumps(
            {
                "expert_id": request.expert_id,
                "message": request.message,
                "user_id": user_id,
                "query_id": request.query_id,
            }
        )
        await redis.set(f"miniapp:q:{uid}", payload, ex=_DEEPLINK_TTL)

        bot_username = os.environ.get("BOT_USERNAME", "")
        if not bot_username:
            _update_current_span(level="ERROR", status_message="bot_username_not_configured")
            raise HTTPException(status_code=500, detail="BOT_USERNAME not configured")
        start_link = f"https://t.me/{bot_username}?start=q_{uid}"

        # Notify bot via Redis pub/sub — bot calls answerWebAppQuery + creates
        # topic + RAG.
        await redis.publish(
            "miniapp:start",
            json.dumps(
                {
                    "uuid": uid,
                    "user_id": user_id,
                    "query_id": request.query_id,
                }
            ),
        )

        # Curated success metadata — no raw UUID, no full URL.
        _update_current_span(
            output={
                "expert_id": request.expert_id,
                "expert_name": expert["name"],
                "deeplink_published": True,
            }
        )

        return StartExpertResponse(
            start_link=start_link,
            expert_name=expert["name"],
        )


_MAX_DATA_VALUE_LEN = 10_000  # max length for any single string value in data


class LogRequest(BaseModel):
    """Validated schema for frontend remote-log payloads.

    Constraints prevent log-injection, large-payload DoS, and unknown log
    levels that could confuse structured log aggregators.

    Allowed levels mirror the TypeScript ``remoteLog`` helper in
    ``mini_app/frontend/src/api.ts``:  debug | info | warn | error.
    ``CRITICAL`` and other Python-native levels are intentionally excluded
    so that frontend logs never get confused with backend-severity events.
    """

    level: Literal["debug", "info", "warn", "error"]
    message: Annotated[str, Field(max_length=1000)]
    # ``data`` is optional free-form context; values are already serialised to
    # a string by the frontend (``JSON.stringify(data)``), so we cap each
    # string value at _MAX_DATA_VALUE_LEN chars to prevent memory exhaustion.
    data: Annotated[dict | None, Field(default=None)]

    @field_validator("data")
    @classmethod
    def validate_data_value_sizes(cls, v: dict | None) -> dict | None:
        """Reject data dicts whose string values exceed _MAX_DATA_VALUE_LEN."""
        if v is None:
            return v
        for val in v.values():
            if isinstance(val, str) and len(val) > _MAX_DATA_VALUE_LEN:
                msg = f"data values must be at most {_MAX_DATA_VALUE_LEN} characters"
                raise ValueError(msg)
        return v


def _remote_log_data_shape(data: dict | None) -> str:
    """Summarize untrusted frontend log context without copying raw values."""
    if not data:
        return "data_keys=0"
    return f"data_keys={len(data)}"


# Mapping from frontend level strings to Python logging levels.
_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}

# TODO(#1613): Add rate-limiting via slowapi (``@limiter.limit("30/minute")``)
# once ``slowapi`` is added to the ``mini-app`` optional-dependency group.
# Tracked as a follow-up because introducing a new dependency needs a separate
# pyproject / uv-lock change that is out of scope for this security patch.


@app.post("/api/log")
async def remote_log(
    request: LogRequest,
    _init_data: dict = Depends(get_validated_init_data),
) -> dict:
    """Receive bounded, validated frontend remote logs.

    Accepts only the four levels declared in ``LogRequest.level`` and caps
    ``message`` at 1 000 characters.  Unknown levels or oversized payloads
    are rejected by Pydantic with HTTP 422 before this handler is entered.

    Uses the standard Python ``logging`` module instead of ``print()`` so
    that log aggregators (e.g. Loki, Cloud Logging) can parse level/message
    as structured fields.
    """
    lvl = _LEVEL_MAP.get(request.level, logging.INFO)
    # Reconstruct a validated level name from the mapped integer so that
    # CodeQL cannot trace the string back to user-controlled ``request.level``.
    level_name: str = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warn",
        logging.ERROR: "error",
    }.get(lvl, "info")
    logger.log(
        lvl,
        "[REMOTE:%s] frontend log received message_len=%d %s",
        level_name,
        len(request.message),
        _remote_log_data_shape(request.data),
    )
    return {"status": "ok"}


@app.post("/api/phone")
@observe(name="miniapp-submit-phone", capture_input=False, capture_output=False)
async def phone(
    request: PhoneRequest,
    init_data: dict = Depends(get_validated_init_data),
) -> Any:
    """Collect phone and create CRM lead.

    ``user_id`` is overridden with the SDK-validated value from initData
    so a forged JSON body cannot attribute leads to a different Telegram
    user (#1595).
    """
    from fastapi.responses import JSONResponse

    user_id: int = int(init_data["user"]["id"])
    # Recreate the request with the verified user_id; submit_phone's
    # signature stays unchanged.
    verified_request = request.model_copy(update={"user_id": user_id})

    with propagate_attributes(
        session_id=f"miniapp-{user_id}",
        user_id=str(user_id),
        tags=["miniapp", "submit-phone", request.source],
        metadata={"surface": "miniapp"},
        as_baggage=True,
    ):
        _update_current_span(input={"source": request.source, "has_name": request.name is not None})
        result = await submit_phone(verified_request)
        if not result.get("success"):
            _update_current_span(level="ERROR", status_message="crm_submission_failed")
            return JSONResponse(status_code=502, content=result)
        return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
