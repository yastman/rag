"""Contract test for issue #2043 — keep no-patch Dependabot deps isolated.

Tracks the post-merge security audit on 2026-05-22 which surfaced two open
Dependabot alerts with no upstream patched version:

- ``diskcache`` CVE-2025-69872 (medium) — vulnerable range ``<=5.6.3``,
  patched version: none.
- ``ragas`` CVE-2026-6587 (low) — removed entirely from the project (#2043);
  previously lived in the optional ``eval`` extra.

The audit decision (see
``docs/security/no-patch-dependency-alerts.md``) was to confine ragas to the
optional ``eval`` extra; ragas has since been removed entirely (issue #2043).
diskcache must remain transitive-only.

This test prevents accidental re-introduction of ragas and ensures
diskcache stays transitive. The invariants enforced are:

1. ``ragas`` must not appear in any pyproject (root, telegram_bot, services).
2. ``diskcache`` is transitive-only — it must not appear in any
   ``[project]`` or ``[project.optional-dependencies]`` block in any
   pyproject.
3. ``import ragas`` / ``from ragas`` must not appear in any first-party code.
4. ``import diskcache`` / ``from diskcache`` does not appear anywhere in
   first-party code or tests (we only consume it transitively).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]

PYPROJECTS = [
    REPO / "pyproject.toml",
    REPO / "telegram_bot" / "pyproject.toml",
    REPO / "mini_app" / "pyproject.toml",
    REPO / "services" / "bge-m3-api" / "pyproject.toml",
]

# Directories scanned for first-party imports.
FIRST_PARTY_ROOTS = ("src", "telegram_bot", "mini_app", "services", "scripts")


def _load_pyproject(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _project_dep_strings(cfg: dict) -> list[str]:
    """All `[project].dependencies` strings (PEP 621)."""
    return list((cfg.get("project") or {}).get("dependencies", []) or [])


def _project_optional_dep_strings(cfg: dict) -> dict[str, list[str]]:
    """All `[project.optional-dependencies].<extra>` mappings."""
    return dict((cfg.get("project") or {}).get("optional-dependencies", {}) or {})


def _dep_name(spec: str) -> str:
    """Strip version specifiers/extras to the bare PEP 503 distribution name."""
    return re.split(r"[\s<>=!~\[]", spec, maxsplit=1)[0].strip().lower()


# ── ragas removal guard ────────────────────────────────────────────────


def test_ragas_absent_from_all_pyprojects() -> None:
    """ragas (CVE-2026-6587) was removed entirely; guard against re-introduction."""
    for path in PYPROJECTS:
        if not path.exists():
            continue
        cfg = _load_pyproject(path)
        names = {_dep_name(s) for s in _project_dep_strings(cfg)}
        names |= {
            _dep_name(s) for deps in _project_optional_dep_strings(cfg).values() for s in deps
        }
        assert "ragas" not in names, (
            f"{path.relative_to(REPO)} must not depend on ragas (CVE-2026-6587, issue #2043). "
            "ragas was removed from the project; do not re-introduce it."
        )


# ── diskcache isolation ────────────────────────────────────────────────


def test_diskcache_is_transitive_only() -> None:
    """diskcache must not appear as a direct dependency in any pyproject."""
    for path in PYPROJECTS:
        if not path.exists():
            continue
        cfg = _load_pyproject(path)
        direct = {_dep_name(s) for s in _project_dep_strings(cfg)}
        optional = {
            _dep_name(s) for deps in _project_optional_dep_strings(cfg).values() for s in deps
        }
        for bucket_name, bucket in (("dependencies", direct), ("optional", optional)):
            assert "diskcache" not in bucket, (
                f"{path.relative_to(REPO)} declares diskcache as a {bucket_name} "
                f"dependency; CVE-2025-69872 has no upstream patch and the "
                f"agreed mitigation in issue #2043 is to keep diskcache "
                "transitive-only."
            )


# ── First-party import isolation ───────────────────────────────────────


def _python_files() -> list[Path]:
    skip_parts = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
    }
    files: list[Path] = []
    for root_name in FIRST_PARTY_ROOTS:
        root = REPO / root_name
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(part in skip_parts for part in py.parts):
                continue
            files.append(py)
    return files


def _imports(text: str, package: str) -> bool:
    pattern = re.compile(
        rf"^\s*(?:import\s+{re.escape(package)}\b|from\s+{re.escape(package)}(?:\.|\s+import))",
        re.MULTILINE,
    )
    return bool(pattern.search(text))


def test_diskcache_not_imported_in_first_party_code() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if _imports(path.read_text(encoding="utf-8"), "diskcache"):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "diskcache must remain a transitive-only dependency (issue #2043). "
        f"Direct imports found in: {offenders}. If a real need arises, raise "
        "the exposure decision in #2043 first."
    )


def test_ragas_not_imported_in_first_party_code() -> None:
    """ragas (CVE-2026-6587) was removed; guard against re-introduction via import."""
    offenders: list[str] = []
    for path in _python_files():
        if _imports(path.read_text(encoding="utf-8"), "ragas"):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "ragas must not be imported anywhere (CVE-2026-6587, issue #2043). "
        f"Found ragas imports in: {offenders}."
    )
