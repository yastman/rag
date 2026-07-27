"""Installed ``rag-ingest`` console-script contract."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.timeout(180)
@pytest.mark.skipif(sys.platform != "linux", reason="requires a Linux installation environment")
def test_locked_install_exposes_rag_ingest_with_module_equivalent_help(tmp_path: Path) -> None:
    """A clean locked install must expose the same CLI dispatcher as ``python -m``."""
    project = tmp_path / "project"
    project.mkdir()
    for filename in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(REPO_ROOT / filename, project / filename)
    shutil.copytree(REPO_ROOT / "src", project / "src")

    subprocess.run(
        ["uv", "sync", "--locked", "--no-dev"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    executable = project / ".venv" / "bin" / "rag-ingest"
    assert executable.is_file(), "uv sync --locked must install rag-ingest"

    console = subprocess.run(
        [str(executable), "--help"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    module = subprocess.run(
        [str(project / ".venv" / "bin" / "python"), "-m", "src.ingestion.unified.main", "--help"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert console.returncode == module.returncode == 0
    for command in ("run", "preflight", "meeting-verify", "schema-check"):
        assert command in console.stdout
        assert command in module.stdout
