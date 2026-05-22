"""Contract tests for `scripts/cleanup_orphaned_worktree_volumes.sh`.

Tracks issue #1546 — orphaned Docker volumes from removed git worktrees.

These are fast text-only contract tests: they assert the script exists, has
the documented safety surface (dry-run default, explicit `--apply` flag,
exclusions for active worktrees and long-lived projects), is wired into
the Makefile, and is referenced from `DOCKER.md`. We do not exercise
real Docker calls in unit tests.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


SCRIPT_PATH = Path("scripts/cleanup_orphaned_worktree_volumes.sh")


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), f"{SCRIPT_PATH} must exist"
    mode = SCRIPT_PATH.stat().st_mode
    assert mode & stat.S_IXUSR, f"{SCRIPT_PATH} must be executable for the owner"


def test_script_uses_safe_bash_options() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert text.startswith(("#!/usr/bin/env bash", "#!/bin/bash")), (
        "script must declare a bash shebang"
    )
    assert "set -euo pipefail" in text, "script must enable strict bash mode (set -euo pipefail)"


def test_script_defaults_to_dry_run() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    # Help text must explicitly mention dry-run as default and require --apply
    assert "--apply" in text, "script must document an explicit --apply flag"
    assert "dry-run" in text.lower(), "script must default to dry-run mode"
    # Refuse `docker volume rm` unless --apply is given (a literal token check)
    assert "docker volume rm" in text, "script should call `docker volume rm` when applying"


def test_script_protects_active_worktrees() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "git worktree list" in text, "script must enumerate active worktrees to skip them"


def test_script_protects_long_lived_projects() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    # Reserve protection for the canonical local-dev / VPS project names so
    # that running this on a developer machine does not blow away `dev_*`
    # data volumes (qdrant_data, postgres_data, etc.).
    for protected in ("dev", "rag-fresh"):
        assert protected in text, (
            f"protected project prefix {protected!r} must be referenced in the script"
        )


def test_script_help_flag_runs_without_docker(tmp_path) -> None:
    """`--help` must succeed with exit 0 and not require Docker to be installed."""

    env = os.environ.copy()
    # Force a PATH that excludes docker so help cannot accidentally call it.
    env["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH.resolve()), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"--help must succeed without docker. stderr={result.stderr}"
    combined = result.stdout + result.stderr
    assert "--apply" in combined, "help output must document --apply"
    assert "dry-run" in combined.lower(), "help output must mention dry-run"


def test_apply_ignores_unrelated_compose_project_prefix(tmp_path) -> None:
    """`--apply` must not delete volumes from unrelated Compose projects."""

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    removed_log = tmp_path / "removed.log"

    git = fake_bin / "git"
    git.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "$*" == "worktree list --porcelain" ]]; then',
                "  printf 'worktree /tmp/rag-fresh-wt-active\\n'",
                "  exit 0",
                "fi",
                "exit 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    git.chmod(0o755)

    docker = fake_bin / "docker"
    docker.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "$1 $2" == "volume ls" ]]; then',
                "  printf 'otherproject_db\\nrag-fresh-wt-old_qdrant\\nrag-fresh-wt-active_db\\ndev_db\\n'",
                "  exit 0",
                "fi",
                'if [[ "$1 $2" == "volume rm" ]]; then',
                '  printf \'%s\\n\' "$3" >> "$REMOVED_LOG"',
                "  exit 0",
                "fi",
                "exit 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["REMOVED_LOG"] = str(removed_log)

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH.resolve()), "--apply"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    removed = removed_log.read_text(encoding="utf-8").splitlines()
    assert removed == ["rag-fresh-wt-old_qdrant"]


def test_makefile_exposes_orphan_volume_cleanup_target() -> None:
    text = Path("Makefile").read_text(encoding="utf-8")
    assert "docker-clean-orphan-worktree-volumes" in text, (
        "Makefile must expose docker-clean-orphan-worktree-volumes target"
    )
    assert "scripts/cleanup_orphaned_worktree_volumes.sh" in text, (
        "Makefile target must invoke the cleanup script"
    )


def test_docker_md_documents_worktree_cleanup() -> None:
    text = Path("DOCKER.md").read_text(encoding="utf-8")
    assert "cleanup_orphaned_worktree_volumes.sh" in text or (
        "docker-clean-orphan-worktree-volumes" in text
    ), "DOCKER.md must reference the cleanup script or Make target"
    assert "worktree" in text.lower(), "DOCKER.md must include a worktree-cleanup section"


def test_repo_hygiene_runbook_references_orphan_volume_cleanup() -> None:
    text = Path("docs/engineering/repo-hygiene-runbook.md").read_text(encoding="utf-8")
    assert "docker-clean-orphan-worktree-volumes" in text, (
        "repo-hygiene runbook must mention the orphan-volume cleanup target"
    )
