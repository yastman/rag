import re
from pathlib import Path


MAKEFILE = Path("Makefile")


def test_redis_container_default_matches_local_compose_naming() -> None:
    """Regression test for #1281.

    Local Compose uses COMPOSE_PROJECT_NAME=dev (from .env.example), which produces
    container names like dev_redis_1.  make test-redis must default to that name so
    it works out of the box without manual override.
    """
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^REDIS_CONTAINER\s+\?=\s*(.+)$", text, re.MULTILINE)
    assert match, "REDIS_CONTAINER default not found in Makefile"
    default = match.group(1).strip()
    assert default == "dev_redis_1", (
        f"REDIS_CONTAINER default must be 'dev_redis_1' to match local Compose "
        f"naming (COMPOSE_PROJECT_NAME=dev -> dev_redis_1), got {default!r}"
    )


def test_redis_container_override_behavior_preserved() -> None:
    """The variable must use ?= so it can still be overridden from the environment."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "REDIS_CONTAINER ?= " in text, (
        "REDIS_CONTAINER must use ?= so REDIS_CONTAINER=custom make test-redis still works"
    )
