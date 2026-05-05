"""Env-based configuration for structured runtime events.

Uses os.environ directly so the layer remains dependency-free.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeEventsConfig:
    """Configuration for the runtime event writer.

    Fields are populated from environment variables by default, but can be
    overridden with explicit keyword arguments for testing.
    """

    enabled: bool = False
    dir: str = "logs/runtime_events"
    max_age_days: int | None = None

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        dir: str | None = None,
        max_age_days: int | None = None,
    ) -> None:
        # Resolve each field: explicit kwarg > env var > default
        if enabled is not None:
            resolved_enabled = enabled
        else:
            enabled_raw = os.environ.get("RUNTIME_EVENTS_ENABLED", "")
            resolved_enabled = enabled_raw.strip() in (
                "1",
                "true",
                "True",
                "TRUE",
                "yes",
                "Yes",
                "YES",
            )

        if dir is not None:
            resolved_dir = dir
        else:
            resolved_dir = os.environ.get("RUNTIME_EVENTS_DIR", "logs/runtime_events")

        if max_age_days is not None:
            resolved_max_age = max_age_days
        else:
            max_age_raw = os.environ.get("RUNTIME_EVENTS_MAX_AGE_DAYS", "").strip()
            resolved_max_age = None
            if max_age_raw:
                try:
                    resolved_max_age = int(max_age_raw)
                except ValueError:
                    resolved_max_age = None

        object.__setattr__(self, "enabled", resolved_enabled)
        object.__setattr__(self, "dir", resolved_dir)
        object.__setattr__(self, "max_age_days", resolved_max_age)
