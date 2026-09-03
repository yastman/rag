"""Contract: single uv manifest/lock authority for the Telegram runtime (#3210).

Decision (issue #3210)
----------------------
The repository root ``pyproject.toml`` + ``uv.lock`` — the ``telegram``
extra plus the base dependencies — are the ONLY dependency authority for
the shipped Telegram runtime. A nested ``telegram_bot/pyproject.toml`` +
``telegram_bot/uv.lock`` authority previously co-existed with production
drift (at removal time: LiteLLM 1.88.1 vs 1.98.0, OpenAI 2.37.0 vs
2.54.0, qdrant-client 1.18.0 vs 1.19.0, redisvl 0.18.2 vs 0.23.0) and was
retired. ``telegram_bot/Dockerfile`` now resolves the bot image with
``uv sync --locked --no-dev --extra telegram`` from the root lock, the
same frozen lock local development and CI (``uv lock --locked``) verify.

This contract encodes three invariants so the decision cannot silently
drift:

1. No nested ``telegram_bot`` manifest/lock may reappear — one authority
   stays authoritative.
2. The root ``telegram`` extra (plus base dependencies) still declares
   every dependency the retired bot manifest carried — removing the
   nested manifest cannot accidentally drop a bot runtime dependency
   (regression intent of the former
   ``tests/unit/test_telegram_bot_pyproject_deps.py``, which guarded
   aiogram-dialog and asyncpg).
3. ``telegram_bot/Dockerfile`` installs from the frozen root lock with
   ``--extra telegram`` (never a nested manifest or unfrozen resolution).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _dep_name(spec: str) -> str:
    """Strip version specifiers/extras/markers to the bare PEP 503 name."""
    return re.split(r"[\s<>=!~\[;]", spec, maxsplit=1)[0].strip().lower().rstrip("/")


# Dependencies declared by the retired telegram_bot/pyproject.toml at
# removal time (#3210). fluent-compiler was declared directly by the bot
# because telegram_bot/middlewares/i18n.py imports it directly.
RETIRED_BOT_DEPENDENCIES: tuple[str, ...] = (
    "aiogram",
    "aiogram-dialog",
    "httpx",
    "qdrant-client",
    "redis",
    "redisvl",
    "tenacity",
    "cachetools",
    "python-dotenv",
    "openai",
    "litellm",
    "pydantic",
    "pydantic-settings",
    "fluentogram",
    "fluent-compiler",
    "asyncpg",
    "phonenumbers",
    "aiohttp",
)


def test_nested_bot_manifest_and_lock_stay_retired() -> None:
    """telegram_bot must not regain its own manifest/lock authority."""
    for rel in ("telegram_bot/pyproject.toml", "telegram_bot/uv.lock"):
        assert not (REPO / rel).exists(), (
            f"{rel} must not exist (#3210): the root pyproject.toml + uv.lock "
            "(--extra telegram) are the single dependency authority for the "
            "Telegram runtime. Update the root manifest instead."
        )


def test_root_telegram_authority_covers_retired_bot_dependencies() -> None:
    """Base deps + telegram extra must cover the retired bot manifest."""
    with (REPO / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)

    project = cfg["project"]
    declared: set[str] = {_dep_name(s) for s in project["dependencies"]}
    for deps in (project.get("optional-dependencies") or {}).values():
        declared |= {_dep_name(s) for s in deps}

    missing = sorted(set(RETIRED_BOT_DEPENDENCIES) - declared)
    assert not missing, (
        "The root pyproject.toml (base + extras) must declare every dependency "
        f"the retired telegram_bot/pyproject.toml carried (#3210). Missing: "
        f"{missing}. Add them to the telegram extra."
    )


def test_bot_dockerfile_resolves_from_frozen_root_lock() -> None:
    """The bot image must sync the root lock with the telegram extra, frozen."""
    dockerfile = REPO / "telegram_bot" / "Dockerfile"
    assert dockerfile.is_file(), "telegram_bot/Dockerfile not found"
    text = dockerfile.read_text(encoding="utf-8")

    # Root manifest/lock are the install inputs (bind-mounted + COPY'd).
    for mount in ("source=pyproject.toml", "source=uv.lock"):
        assert mount in text, (
            f"telegram_bot/Dockerfile must bind-mount the root {mount.split('=')[1]} "
            "(#3210 single authority)."
        )
    assert "COPY pyproject.toml uv.lock ./" in text, (
        "telegram_bot/Dockerfile must COPY the root pyproject.toml and uv.lock "
        "so manifest changes bust the deps cache (#3210)."
    )
    # Frozen resolution against that lock, with the telegram extra.
    for fragment in ("uv sync --locked", "--extra telegram", "--no-dev"):
        assert fragment in text, (
            f"telegram_bot/Dockerfile must contain {fragment!r}: the bot image "
            "resolves from the frozen root lock with the telegram extra (#3210)."
        )
    # The retired nested authority must not be referenced by any
    # functional (non-comment) instruction.
    functional = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert (
        "telegram_bot/pyproject.toml" not in functional
        and "telegram_bot/uv.lock" not in functional
    ), (
        "telegram_bot/Dockerfile must not reference the retired nested "
        "manifest/lock in any instruction (#3210)."
    )
