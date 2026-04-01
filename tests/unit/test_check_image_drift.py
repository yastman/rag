"""Regression tests for the image drift CLI defaults."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "check_image_drift.py"


def test_help_uses_current_default_compose_file() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "default: compose.yml" in result.stdout
    assert "docker-compose.dev.yml" not in result.stdout


def test_script_examples_use_current_compose_filenames() -> None:
    content = SCRIPT.read_text()
    assert "docker-compose.dev.yml" not in content
    assert "docker-compose.vps.yml" not in content
    assert "compose.vps.yml" in content
