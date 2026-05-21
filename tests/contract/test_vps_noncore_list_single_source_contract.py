# tests/contract/test_vps_noncore_list_single_source_contract.py
"""Contract: VPS non-core service removal list lives in exactly one place.

Closes #1611.

The VPS minimal-runtime transition relies on a list of "non-core" services
that must be stopped/removed on production VPS hosts. Before this contract,
the same list was duplicated across smoke, cleanup, deploy and CI scripts,
risking drift (a service added to one list but not another).

This contract enforces a single source of truth:

1. ``scripts/lib/vps_noncore_services.sh`` exports the canonical
   ``VPS_NONCORE_SERVICES`` bash array.
2. The canonical list matches the set of services in ``compose.vps.yml``
   that declare the ``vps-noncore`` profile (the runtime gate).
3. Each consumer script references the shared lib instead of carrying its
   own copy of the array.
4. No consumer script contains a duplicated literal of the canonical list,
   neither as a shell array nor as a Python set/list inside a heredoc.

The test is fully static: it parses files with regex/yaml and never
shells out to docker.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_LIB = REPO_ROOT / "scripts" / "lib" / "vps_noncore_services.sh"
COMPOSE_VPS = REPO_ROOT / "compose.vps.yml"
CONSUMERS = [
    REPO_ROOT / "scripts" / "test_release_health_vps.sh",
    REPO_ROOT / "scripts" / "vps_cleanup_removed_services.sh",
]

# Profile in compose.vps.yml that gates non-core (removable) services.
NONCORE_PROFILE = "vps-noncore"


def _parse_shared_lib_array() -> list[str]:
    """Extract VPS_NONCORE_SERVICES=( ... ) tokens from the shared lib."""
    text = SHARED_LIB.read_text(encoding="utf-8")
    match = re.search(
        r"VPS_NONCORE_SERVICES=\(\s*(?P<body>[^)]*)\)",
        text,
        re.DOTALL,
    )
    assert match, (
        f"VPS_NONCORE_SERVICES=( ... ) array not found in "
        f"{SHARED_LIB.relative_to(REPO_ROOT)}"
    )
    body = match.group("body")
    items: list[str] = []
    for raw in body.splitlines():
        raw = raw.split("#", 1)[0].strip()
        if not raw:
            continue
        for tok in raw.split():
            tok = tok.strip().strip("'").strip('"')
            if tok:
                items.append(tok)
    return items


def _services_with_noncore_profile() -> list[str]:
    """Services in compose.vps.yml that declare the vps-noncore profile."""
    data = yaml.safe_load(COMPOSE_VPS.read_text(encoding="utf-8"))
    services = (data or {}).get("services", {}) or {}
    matches: list[str] = []
    for name, spec in services.items():
        profiles = (spec or {}).get("profiles") or []
        if NONCORE_PROFILE in profiles:
            matches.append(name)
    return matches


def test_shared_lib_exists_and_is_parseable() -> None:
    assert SHARED_LIB.exists(), (
        f"single source-of-truth file is missing: "
        f"{SHARED_LIB.relative_to(REPO_ROOT)}"
    )
    items = _parse_shared_lib_array()
    assert items, "VPS_NONCORE_SERVICES is empty in shared lib"
    # No duplicates inside the canonical list itself.
    assert len(items) == len(set(items)), (
        f"VPS_NONCORE_SERVICES contains duplicates: {items}"
    )


def test_shared_lib_matches_compose_vps_noncore_profile() -> None:
    canonical = sorted(_parse_shared_lib_array())
    compose = sorted(_services_with_noncore_profile())
    assert canonical == compose, (
        "VPS_NONCORE_SERVICES drifts from compose.vps.yml "
        f"`{NONCORE_PROFILE}` profile.\n"
        f"  shared lib: {canonical}\n"
        f"  compose:    {compose}"
    )


def test_consumers_reference_shared_lib() -> None:
    for path in CONSUMERS:
        text = path.read_text(encoding="utf-8")
        assert "scripts/lib/vps_noncore_services.sh" in text, (
            f"{path.relative_to(REPO_ROOT)} does not source "
            f"scripts/lib/vps_noncore_services.sh"
        )


def test_consumers_have_no_inline_shell_array_duplicate() -> None:
    """No consumer may carry its own ``foo=( a b c ... )`` literal that
    overlaps the canonical list. Catches the original drift hazard."""
    canonical = set(_parse_shared_lib_array())
    threshold = max(2, len(canonical) // 2)
    for path in CONSUMERS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"^\s*(\w+)=\(\s*([^)]*)\)",
            text,
            re.MULTILINE | re.DOTALL,
        ):
            var, body = match.group(1), match.group(2)
            tokens: set[str] = set()
            for line in body.splitlines():
                line = line.split("#", 1)[0]
                for tok in line.split():
                    tok = tok.strip().strip("'").strip('"')
                    if tok:
                        tokens.add(tok)
            overlap = canonical & tokens
            assert len(overlap) < threshold, (
                f"{path.relative_to(REPO_ROOT)}: shell array `{var}=(...)` "
                f"duplicates VPS_NONCORE_SERVICES (overlap={sorted(overlap)})"
            )


def test_consumers_have_no_inline_python_literal_duplicate() -> None:
    """No consumer may embed a Python set/list literal duplicating the
    canonical list (catches the heredoc drift inside
    vps_cleanup_removed_services.sh)."""
    canonical = set(_parse_shared_lib_array())
    threshold = max(2, len(canonical) // 2)
    for path in CONSUMERS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"^\s*\w+\s*=\s*[\{\[]\s*([^{}\[\]]+?)\s*[\}\]]",
            text,
            re.MULTILINE | re.DOTALL,
        ):
            body = match.group(1)
            tokens: set[str] = set()
            for line in body.splitlines():
                line = line.split("#", 1)[0]
                for tok in line.split(","):
                    tok = tok.strip().strip("'").strip('"').strip()
                    if tok:
                        tokens.add(tok)
            overlap = canonical & tokens
            assert len(overlap) < threshold, (
                f"{path.relative_to(REPO_ROOT)}: Python literal "
                f"duplicates VPS_NONCORE_SERVICES (overlap={sorted(overlap)})"
            )
