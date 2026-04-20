"""Runtime defaults for pytest in WSL environments."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_pytest_defaults_force_sys_capture() -> None:
    """Global pytest config should avoid fd-capture tempfile issues on WSL."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    addopts = str(data["tool"]["pytest"]["ini_options"]["addopts"])

    assert "--capture=sys" in addopts
