"""Contract: Makefile and scripts must expose only supported monolith commands.

Issue #2638: remove optional/archived surface targets from Makefile and archive
obsolete scripts so `make help` shows only the supported product surface.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

# Targets that must NOT appear as definitions in the Makefile after cleanup.
REMOVED_TARGETS = (
    "test-api-adapter",
    "test-legacy-graph-extra",
    "test-voice-extra",
    "test-eval-extra",
    "test-observability-extra",
    "test-optional-surfaces",
    "monitoring-up",
    "monitoring-down",
    "monitoring-logs",
    "monitoring-status",
    "monitoring-test-alert",
    "remote-active-up",
    "remote-full-up",
    # #2720: stale eval targets removed (scripts archived, module removed)
    "eval-rag",
    "eval-rag-quick",
    "eval-rag-full",
    "eval-goldset-sync",
    "eval-experiment",
    # #2720: stale e2e-index-data removed (script never existed)
    "e2e-index-data",
)

# K3S image variables that must NOT appear in the Makefile after cleanup.
REMOVED_K3S_VARS = (
    "K3S_IMAGE_REGISTRY",
    "K3S_IMAGE_TAG",
)

# Scripts that must NOT exist at their original paths after archival.
REMOVED_SCRIPT_PATHS = (
    REPO_ROOT / "scripts" / "kommo_seed.py",
    REPO_ROOT / "scripts" / "lf",
    REPO_ROOT / "scripts" / "eval" / "run_experiment.py",
    REPO_ROOT / "scripts" / "eval" / "goldset_sync.py",
    REPO_ROOT / "scripts" / "eval" / "agent_routing_eval.py",
    REPO_ROOT / "scripts" / "eval" / "calibrate_judge.py",
    REPO_ROOT / "scripts" / "benchmark" / "quantization_int8_vs_binary.py",
    REPO_ROOT / "scripts" / "benchmark" / "quantization_ab.py",
    REPO_ROOT / "scripts" / "benchmark" / "contextualized_ab.py",
    REPO_ROOT / "scripts" / "audit" / "cost_reconcile.py",
)

# Test files that must NOT exist after cleanup (they kept archived scripts alive).
REMOVED_TEST_PATHS = (
    REPO_ROOT / "tests" / "unit" / "test_scripts_lf.py",
    REPO_ROOT / "tests" / "unit" / "scripts" / "test_kommo_seed.py",
    REPO_ROOT / "tests" / "unit" / "scripts" / "test_cost_reconcile.py",
)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_removed_targets_not_defined_in_makefile() -> None:
    """Archived surface targets must not be defined in the Makefile."""
    text = _makefile_text()
    found = [
        target
        for target in REMOVED_TARGETS
        if re.search(rf"^{re.escape(target)}:", text, re.MULTILINE)
    ]
    assert found == [], f"These targets must be removed from Makefile: {found}"


def test_k3s_image_variables_removed_from_makefile() -> None:
    """K3S image variables must not appear in the Makefile after cleanup."""
    text = _makefile_text()
    found = [var for var in REMOVED_K3S_VARS if var in text]
    assert found == [], f"These K3S variables must be removed from Makefile: {found}"


def test_archived_scripts_not_at_original_paths() -> None:
    """Archived scripts must not remain at their pre-cleanup paths."""
    still_present = [str(p.relative_to(REPO_ROOT)) for p in REMOVED_SCRIPT_PATHS if p.exists()]
    assert still_present == [], f"These scripts must be archived/removed: {still_present}"


def test_removed_test_files_not_present() -> None:
    """Test files for archived scripts must be deleted."""
    still_present = [str(p.relative_to(REPO_ROOT)) for p in REMOVED_TEST_PATHS if p.exists()]
    assert still_present == [], (
        f"These test files must be removed (they kept archived scripts alive): {still_present}"
    )


def test_make_help_surface_required_targets_still_exist() -> None:
    """Core supported targets must remain defined after cleanup."""
    text = _makefile_text()
    required = (
        "check",
        "test-core",
        "e2e-core-live",
        "test-contract",
        "ingest-unified-preflight",
        "ingest-unified-bootstrap",
        "ingest-unified",
        "docker-core-up",
        "core-min-up",
    )
    missing = [t for t in required if not re.search(rf"^{re.escape(t)}:", text, re.MULTILINE)]
    assert missing == [], f"These required targets must remain in Makefile: {missing}"
