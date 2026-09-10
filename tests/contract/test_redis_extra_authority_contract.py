"""Contract: Redis clients live in one explicit optional extra (#3365).

Decision (issue #3365)
----------------------
Base/core installs no Redis package. redis-py and RedisVL move out of the
base dependencies into one bounded ``[project.optional-dependencies].redis``
extra — the single manifest for the Redis client cohort. The Redis-enabled
Telegram production image installs ``--extra telegram --extra redis``
(see ``telegram_bot/Dockerfile``; pinned by
``tests/contract/test_telegram_uv_authority_contract.py``).

Invariants encoded here:

1. Base dependencies declare neither ``redis`` nor ``redisvl``.
2. The ``redis`` extra exists, declares the redis-py/RedisVL cohort exactly
   once, and keeps the #3226 compatibility caps (redis ``<8``, redisvl
   ``<0.27``).
3. No other manifest lane (dev group, e2e group, other extras) declares the
   cohort — one extra stays the single authority. ``fakeredis`` is a test
   double with its own name and is not part of the cohort.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"

REDIS_COHORT = {"redis", "redisvl"}


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _package_name(requirement: str) -> str:
    return (
        requirement.split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .strip()
        .lower()
    )


def test_base_dependencies_exclude_redis_packages() -> None:
    """Base/core installs no Redis package (#3365 outcome)."""
    deps = {_package_name(dep) for dep in _load(ROOT_PYPROJECT)["project"]["dependencies"]}
    clash = REDIS_COHORT & deps
    assert not clash, (
        f"Redis client packages must not be base dependencies (#3365): {sorted(clash)}. "
        "Declare them in the [project.optional-dependencies].redis extra instead."
    )


def test_redis_extra_declares_cohort_once_with_compatibility_caps() -> None:
    """One bounded ``redis`` extra carries redis-py + RedisVL exactly once."""
    optional = _load(ROOT_PYPROJECT)["project"].get("optional-dependencies", {})
    assert "redis" in optional, (
        "pyproject.toml must define [project.optional-dependencies].redis (#3365): "
        "the single manifest for the Redis client cohort."
    )
    specs = [str(dep) for dep in optional["redis"]]
    names = [_package_name(spec) for spec in specs]
    for member in sorted(REDIS_COHORT):
        assert names.count(member) == 1, (
            f"{member} must be declared exactly once in the redis extra (#3365); "
            f"got {names.count(member)}."
        )
    # #3226 compatibility caps must survive the move: redis-py 8 stays a
    # non-goal while RedisVL is frozen on the 0.26 line.
    redis_spec = next(spec for spec in specs if _package_name(spec) == "redis")
    redisvl_spec = next(spec for spec in specs if _package_name(spec) == "redisvl")
    assert "<8" in redis_spec, f"redis must keep the #3226 <8 cap; got {redis_spec!r}"
    assert "<0.27" in redisvl_spec, f"redisvl must keep the #3226 <0.27 cap; got {redisvl_spec!r}"


def test_redis_cohort_declared_in_no_other_lane() -> None:
    """The redis extra is the single authority — no other lane redeclares it."""
    cfg = _load(ROOT_PYPROJECT)
    lanes: dict[str, list[str]] = {}
    lanes["dependency-groups.dev"] = [
        str(d) for d in cfg.get("dependency-groups", {}).get("dev", []) if isinstance(d, str)
    ]
    lanes["dependency-groups.e2e"] = [
        str(d) for d in cfg.get("dependency-groups", {}).get("e2e", []) if isinstance(d, str)
    ]
    for extra, deps in cfg["project"].get("optional-dependencies", {}).items():
        if extra != "redis":
            lanes[f"extra.{extra}"] = [str(d) for d in deps]

    for lane, deps in lanes.items():
        clash = REDIS_COHORT & {_package_name(dep) for dep in deps}
        assert not clash, (
            f"Redis client packages must live only in the redis extra (#3365); "
            f"found {sorted(clash)} in {lane}."
        )
