"""Contract test for issue #2043 — keep no-patch Dependabot deps isolated.

Tracks the post-merge security audit on 2026-05-22 which surfaced two open
Dependabot alerts with no upstream patched version:

- ``diskcache`` CVE-2025-69872 (medium) — vulnerable range ``<=5.6.3``,
  patched version: none.
- ``ragas`` CVE-2026-6587 (low) — vulnerable range ``>=0.2.3, <=0.4.3``,
  patched version: none.

The audit decision (see
``docs/security/no-patch-dependency-alerts.md``) is to keep both
packages confined to the optional ``eval`` extra and the
``src/evaluation/`` evaluation pipeline so the production bot/API runtime
is not exposed.

This test prevents accidental drift back into production code or the
default install. The four invariants are:

1. ``ragas`` lives ONLY under ``[project.optional-dependencies].eval`` —
   it must not appear in ``[project].dependencies`` or in any other
   pyproject (telegram_bot, mini_app, services).
2. ``diskcache`` is transitive-only — it must not appear in any
   ``[project]`` or ``[project.optional-dependencies]`` block in any
   pyproject.
3. ``import ragas`` / ``from ragas`` is restricted to
   ``src/evaluation/`` and ``tests/`` (mocks).
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
    REPO / "services" / "user-base" / "pyproject.toml",
    REPO / "services" / "docling" / "pyproject.toml",
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


# ── ragas isolation ────────────────────────────────────────────────────


def test_ragas_not_in_root_pyproject_dependencies() -> None:
    cfg = _load_pyproject(REPO / "pyproject.toml")
    names = {_dep_name(s) for s in _project_dep_strings(cfg)}
    assert "ragas" not in names, (
        "ragas is a no-patch Dependabot alert (CVE-2026-6587) with limited "
        "exposure scope; it must remain in [project.optional-dependencies].eval"
        " and not be promoted to [project].dependencies (issue #2043)."
    )


def test_ragas_only_in_eval_extra() -> None:
    cfg = _load_pyproject(REPO / "pyproject.toml")
    extras = _project_optional_dep_strings(cfg)
    where_ragas_appears = sorted(
        name for name, deps in extras.items() if any(_dep_name(s) == "ragas" for s in deps)
    )
    assert where_ragas_appears == ["eval"], (
        f"ragas must appear in exactly one optional extra ('eval'), but found "
        f"in: {where_ragas_appears}. See issue #2043."
    )


def test_ragas_absent_from_subpackage_pyprojects() -> None:
    """ragas must not leak into bot/mini-app/service pyprojects."""
    for path in PYPROJECTS:
        if not path.exists() or (path.name == "pyproject.toml" and path.parent == REPO):
            # Skip the root pyproject — that one is asserted by the two tests
            # above.
            if path == REPO / "pyproject.toml":
                continue
            if not path.exists():
                continue
        cfg = _load_pyproject(path)
        names = {_dep_name(s) for s in _project_dep_strings(cfg)}
        names |= {
            _dep_name(s) for deps in _project_optional_dep_strings(cfg).values() for s in deps
        }
        assert "ragas" not in names, (
            f"{path.relative_to(REPO)} must not depend on ragas (issue #2043)."
        )


# ── diskcache isolation ────────────────────────────────────────────────


def test_diskcache_is_transitive_only() -> None:
    """diskcache must not appear as a direct dependency in any pyproject.

    It is allowed to land in ``uv.lock`` because ``ragas`` pulls it in
    transitively when the optional ``eval`` extra is installed.
    """
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
                "transitive-only via ragas."
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


def test_ragas_only_imported_under_src_evaluation() -> None:
    """All first-party ragas imports must be under src/evaluation/."""
    allowed_prefix = REPO / "src" / "evaluation"
    offenders: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        if not _imports(text, "ragas"):
            continue
        try:
            path.relative_to(allowed_prefix)
        except ValueError:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], (
        "ragas imports must be confined to src/evaluation/ (issue #2043). "
        f"Found ragas imports outside that directory in: {offenders}."
    )
