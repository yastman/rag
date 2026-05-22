"""Contract: pin deletions from the 2026-05 dead-code audit (#1978).

Each row in the ``delete_now`` table of
``docs/engineering/dead-code-audit-2026-05.md`` is mirrored here as an
assertion that the deleted file or symbol does not return to ``dev``
without an explicit decision to revert the audit.

Add new assertions as follow-up slices land. Each new assertion should
reference the corresponding row in the audit doc.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_test_search_quality_script_is_gone() -> None:
    """``scripts/test_search_quality.py`` was deleted by the #1997 slice.

    The script had zero references in Makefile, CI, docs, or Python
    imports across the repository. It hard-coded a Qdrant collection
    (``contextual_bulgaria`` without the ``_voyage`` suffix) that no
    longer appears anywhere in ``src/``, ``telegram_bot/``, or
    ``.env.example``, plus ``localhost:6333`` / ``localhost:8000``
    smoke endpoints. It was a one-off "search quality after m=0
    optimisation" probe whose target HNSW tweak is historical.

    Re-introducing the script requires updating
    ``docs/engineering/scripts-inventory-2026-05.md`` and removing
    this assertion explicitly.
    """
    path = REPO_ROOT / "scripts" / "test_search_quality.py"
    assert not path.exists(), (
        f"#1997 regression: {path.relative_to(REPO_ROOT)} reappeared after "
        f"the scripts inventory slice. See "
        f"docs/engineering/scripts-inventory-2026-05.md before re-adding."
    )


def test_index_test_properties_prod_script_is_gone() -> None:
    """``scripts/index_test_properties_prod.py`` was deleted by the #1978 slice.

    The script had zero callers across the repository: no Makefile target,
    no CI workflow, no docs reference, no test reference, and no Python
    import. It was a one-off manual UPSERT helper for production Qdrant
    that has been superseded by the unified ingestion pipeline (#1532).

    Re-introducing the script requires updating
    ``docs/engineering/dead-code-audit-2026-05.md`` and removing this
    assertion explicitly.
    """
    path = REPO_ROOT / "scripts" / "index_test_properties_prod.py"
    assert not path.exists(), (
        f"#1978 regression: {path.relative_to(REPO_ROOT)} reappeared after "
        f"the dead-code audit slice. Either revert the deletion via a "
        f"separate PR that updates docs/engineering/dead-code-audit-2026-05.md, "
        f"or remove the file again."
    )
