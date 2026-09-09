"""Redis operating modes — the single public ``REDIS_MODE`` contract (#3362).

Implements the mode table from architecture decision #3354 verbatim:

=============== =========================================== ================================ ==========================
Mode            Connection/cache                            Durable Redis capabilities       Polling ownership
=============== =========================================== ================================ ==========================
``disabled``    no Redis import/client/DNS/socket;          unavailable, never replaced      operator runs one process;
                cache miss/no-store                         with memory                      no distributed-lock claim
``single``      connect when configured; cache may          enabled only while connected     exactly one process; no
``_instance``   fail open                                   and reported honestly            distributed-lock claim
``multi``       Redis required at startup                   required shared/durable state    distributed polling lock
``_instance``                                                                                required; loss stops polling
=============== =========================================== ================================ ==========================

Defaults: reusable core ``disabled``; Compose bot explicitly
``single_instance``; scaled deployment explicitly ``multi_instance``.

Invariants enforced here (via :func:`validate_redis_mode`):

- Disabled mode plus an explicitly enabled Redis-only durable feature is
  a configuration error.
- Multi-instance mode requires a nonempty Redis URL (a live handshake is
  additionally required before polling — enforced by preflight and the
  polling-lock gate).
- A present Redis URL/password in disabled mode triggers no import or
  connection (this module is stdlib-only and imports nothing from the
  ``redis`` / ``redisvl`` packages).

Consumers receive the typed :class:`RedisMode` / :class:`RedisModePolicy`
values; nothing else reparses mode strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RedisMode(StrEnum):
    """Honest Redis operating mode (decision #3354)."""

    DISABLED = "disabled"
    SINGLE_INSTANCE = "single_instance"
    MULTI_INSTANCE = "multi_instance"


class RedisCapability(StrEnum):
    """Capability reporting state: enabled, degraded, or disabled (#3354)."""

    ENABLED = "enabled"
    DEGRADED = "degraded"
    DISABLED = "disabled"


#: Reusable-core default (decision #3354). Compose overrides it to
#: ``single_instance`` explicitly; scaled deployments set ``multi_instance``.
DEFAULT_REDIS_MODE = RedisMode.DISABLED


@dataclass(frozen=True, slots=True)
class RedisModePolicy:
    """One row of the mode policy table — what a mode allows and requires."""

    mode: RedisMode
    #: May this mode create a Redis client/connection at all?
    allows_client: bool
    #: Must a live connection exist before polling starts?
    requires_connection_before_polling: bool
    #: Is the distributed polling lock required before polling?
    polling_lock_required: bool
    #: May Redis-backed durable capabilities (handoff state, Kommo token
    #: store, lead sink) run at all?
    durable_capabilities_allowed: bool
    #: May the cache fail open (miss/no-store) on connection loss?
    cache_fail_open: bool


REDIS_MODE_POLICIES: dict[RedisMode, RedisModePolicy] = {
    RedisMode.DISABLED: RedisModePolicy(
        mode=RedisMode.DISABLED,
        allows_client=False,
        requires_connection_before_polling=False,
        polling_lock_required=False,
        durable_capabilities_allowed=False,
        cache_fail_open=False,
    ),
    RedisMode.SINGLE_INSTANCE: RedisModePolicy(
        mode=RedisMode.SINGLE_INSTANCE,
        allows_client=True,
        requires_connection_before_polling=False,
        polling_lock_required=False,
        durable_capabilities_allowed=True,
        cache_fail_open=True,
    ),
    RedisMode.MULTI_INSTANCE: RedisModePolicy(
        mode=RedisMode.MULTI_INSTANCE,
        allows_client=True,
        requires_connection_before_polling=True,
        polling_lock_required=True,
        durable_capabilities_allowed=True,
        cache_fail_open=True,
    ),
}


class RedisModeConfigError(ValueError):
    """Raised for invalid REDIS_MODE values or invalid mode combinations."""


def parse_redis_mode(raw: RedisMode | str | None) -> RedisMode:
    """Parse a raw mode value into the typed enum.

    ``None`` and empty strings resolve to :data:`DEFAULT_REDIS_MODE`
    (``disabled``). Anything else that is not a valid mode name raises
    :class:`RedisModeConfigError` listing the valid values — the single
    string-parsing point of the whole contract.
    """
    if raw is None:
        return DEFAULT_REDIS_MODE
    if isinstance(raw, RedisMode):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if not normalized:
            return DEFAULT_REDIS_MODE
        try:
            return RedisMode(normalized)
        except ValueError:
            valid = ", ".join(mode.value for mode in RedisMode)
            msg = f"Invalid REDIS_MODE {raw!r}; valid values: {valid}"
            raise RedisModeConfigError(msg) from None
    valid = ", ".join(mode.value for mode in RedisMode)
    msg = f"Invalid REDIS_MODE {raw!r} ({type(raw).__name__}); valid values: {valid}"
    raise RedisModeConfigError(msg)


def redis_mode_policy(mode: RedisMode) -> RedisModePolicy:
    """Return the policy row for a typed mode."""
    return REDIS_MODE_POLICIES[mode]


def validate_redis_mode(
    mode: RedisMode,
    *,
    redis_url: str | None,
    redis_only_feature_enabled: bool,
) -> None:
    """Validate mode combinations at configuration time (#3354 invariants).

    Raises:
        RedisModeConfigError: on an invalid combination — multi-instance
            without a nonempty Redis URL, or disabled mode with an
            explicitly enabled Redis-only durable feature (e.g.
            ``HANDOFF_ENABLED=true``).
    """
    policy = redis_mode_policy(mode)

    if mode is RedisMode.MULTI_INSTANCE and not (redis_url or "").strip():
        msg = (
            "REDIS_MODE=multi_instance requires a nonempty REDIS_URL "
            "(distributed polling lock needs shared Redis state)"
        )
        raise RedisModeConfigError(msg)

    if policy.durable_capabilities_allowed is False and redis_only_feature_enabled:
        msg = (
            "REDIS_MODE=disabled cannot run with an explicitly enabled Redis-only "
            "durable feature (HANDOFF_ENABLED=true); "
            "use REDIS_MODE=single_instance or REDIS_MODE=multi_instance"
        )
        raise RedisModeConfigError(msg)


__all__ = [
    "DEFAULT_REDIS_MODE",
    "REDIS_MODE_POLICIES",
    "RedisCapability",
    "RedisMode",
    "RedisModeConfigError",
    "RedisModePolicy",
    "parse_redis_mode",
    "redis_mode_policy",
    "validate_redis_mode",
]
