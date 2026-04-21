"""Regression tests for the image drift CLI defaults."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "check_image_drift.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_image_drift", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_main_exits_nonzero_when_no_running_containers_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: "27.0.0")
    monkeypatch.setattr(module, "check_drift", lambda _compose: module.DriftReport("compose.yml"))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 1


def test_main_exits_zero_when_checked_containers_have_no_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: "27.0.0")
    monkeypatch.setattr(
        module,
        "check_drift",
        lambda _compose: module.DriftReport(
            "compose.yml",
            checked=[
                module.DriftResult(
                    service="redis",
                    container="redis-1",
                    expected_image="redis:8.6.2@sha256:abc",
                    expected_tag="8.6.2",
                    expected_digest="sha256:abc",
                    actual_image="redis:8.6.2",
                    actual_digest="sha256:abc",
                    tag_match=True,
                    digest_match=True,
                )
            ],
        ),
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 0
