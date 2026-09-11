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
    # #3379 (entrypoint convergence): remote-MacBook DSL
    "remote-docker-status",
    "remote-compose-config",
    "remote-docker-ps",
    "remote-env-sync",
    "remote-env-check",
    "remote-core-up",
    "remote-core-ps",
    "remote-core-logs",
    "remote-core-health",
    "remote-core-env-check",
    "remote-bot-up",
    "remote-bot-restart",
    "remote-bot-logs",
    "remote-local-up",
    "remote-local-down",
    "remote-local-logs",
    "remote-service-health",
    # #3379: direct-push / deploy DSL
    "deploy-code",
    "deploy-release",
    "deploy-bot",
    "deploy-vps-local",
    # #3379: git/PR/issue/repo hygiene DSL
    "git-hygiene",
    "git-hygiene-fix",
    "pr-hygiene",
    "issue-hygiene",
    "repo-cleanup",
    "repo-cleanup-force",
    # #3379: duplicate pytest aliases and variants
    "test-fast",
    "test-all-fast",
    "test-all-local",
    "test-ff",
    "test-lf",
    "test-profile",
    "test-unit-loadscope",
    # #3379: retired eval / ingestion / legacy Qdrant/index owners
    # (scripts deleted downstream by #3384/#3423; Make refs removed here)
    "eval-gold-gen",
    "eval-gold-gen-dry",
    "ingest-services",
    "ingest-setup",
    "ingest-test",
    "qdrant-audit-indexes",
    "qdrant-backup",
    "qdrant-cleanup",
    # #3379: Kiro/tmux tooling lane (scripts deleted downstream by #3385)
    "test-tooling",
    # #3379: smoke/shell duplicates (scripts deleted downstream by #3382)
    "smoke-fast",
    "smoke-zoo",
    # #3379: lane duplicates superseded by canonical lanes
    "test-preflight",
    "test-nightly",
    "test-all",
    "test-integration",
    "test-integration-full",
    "test-load-eviction",
    "e2e-setup",
    "e2e-test-group",
    "e2e-install",
    # #3379: uv/setup wrappers (native uv commands are canonical)
    "install",
    "install-all",
    "lock",
    "update",
    "update-pkg",
    "reinstall",
    "local-pr-ready",
    "compile-python",
    # #3379: gate wrappers and tool duplicates (canonical: audit/candidate-check/fix)
    "dead-code",
    "dead-code-check",
    "deps-check",
    "lint-full",
    "all-checks",
    "ci",
    "qa",
    "pre-commit",
    "pylint",
    "cve-gate",
    "audit-deps-refresh",
    # #3379: compose aliases and subsumed/duplicate operations
    "core-up",
    "docker-up",
    "docker-ai-up",
    "docker-ingest-up",
    "docker-ps",
    "docker-down",
    "docker-clean",
    "docker-clean-aggressive",
    "docker-clean-orphan-worktree-volumes-apply",
    "verify-compose-images-json",
    "verify-compose-runtime",
    # #3379: wrappers retired with the Make surface consolidation
    "clean",
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
    # #3382: duplicate quick-health shell deleted (check_services.sh is the owner)
    REPO_ROOT / "scripts" / "smoke-zoo.sh",
)

# Test files that must NOT exist after cleanup (they kept archived scripts alive).
REMOVED_TEST_PATHS = (
    REPO_ROOT / "tests" / "unit" / "test_scripts_lf.py",
    REPO_ROOT / "tests" / "unit" / "scripts" / "test_kommo_seed.py",
    REPO_ROOT / "tests" / "unit" / "scripts" / "test_cost_reconcile.py",
    # #3382: private test of the deleted duplicate quick-health shell
    REPO_ROOT / "tests" / "unit" / "scripts" / "test_smoke_zoo.py",
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
