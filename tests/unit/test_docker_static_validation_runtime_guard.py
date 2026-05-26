"""Runtime-guard regression tests for ``tests/unit/test_docker_static_validation.py`` (#2009).

#2009 calls out runtime gates that rely on ambient env / runtime
availability. ``test_docker_static_validation`` declares "Docker
availability is checked at runtime; tests skip gracefully when absent",
but the original ``_docker_available`` only probed for the ``docker``
binary. On hosts that have the engine without the Compose v2 plugin
(common in lightweight CI sandboxes and a default RHEL/Amazon Linux
2023 box), ``shutil.which("docker")`` returns truthy yet
``docker compose ...`` exits with status 125 ("looking up compose
provider failed") and the assertion ``result.returncode == 0`` flips a
skip into a hard FAIL.

This test file pins the corrected guard:

* ``_docker_available`` accepts a callable for compose-plugin probing
  so we can inject deterministic outcomes.
* ``_run_docker_command`` calls ``pytest.skip`` (not asserts) when the
  Compose plugin probe returns ``False``.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

import tests.unit.test_docker_static_validation as docker_module


def test_docker_available_returns_false_when_binary_missing() -> None:
    with patch.object(docker_module.shutil, "which", return_value=None):
        assert docker_module._docker_available() is False


def test_docker_available_returns_false_when_compose_plugin_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``docker`` binary present, but ``docker compose version`` exits
    non-zero (the plugin is not installed). ``_docker_available`` must
    report False so the test skips instead of asserting against a
    runtime that cannot honour the call.
    """
    monkeypatch.setattr(docker_module.shutil, "which", lambda _: "/usr/bin/docker")

    def _fake_run(args, **kwargs):
        # Mirrors the real `docker compose version` failure shape on
        # hosts with no Compose v2 plugin.
        return subprocess.CompletedProcess(
            args=args,
            returncode=125,
            stdout="",
            stderr=(
                "Error: looking up compose provider failed\n"
                'exec: "docker-compose": executable file not found in $PATH\n'
            ),
        )

    monkeypatch.setattr(docker_module.subprocess, "run", _fake_run)
    assert docker_module._docker_available() is False


def test_docker_available_returns_true_when_compose_plugin_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker_module.shutil, "which", lambda _: "/usr/bin/docker")

    def _fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="Docker Compose version v2.30.0\n",
            stderr="",
        )

    monkeypatch.setattr(docker_module.subprocess, "run", _fake_run)
    assert docker_module._docker_available() is True


def test_run_docker_command_skips_when_compose_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(docker_module, "_docker_available", lambda: False)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        docker_module._run_docker_command(["docker", "compose", "config", "--quiet"])

    assert "Docker" in str(excinfo.value) or "Compose" in str(excinfo.value)


def test_run_docker_command_skips_when_compose_provider_failure_leaks_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: if the host adds the Compose plugin AFTER ``_docker_available``
    samples it (race) or returns 125 from the actual command, the wrapper
    must downgrade the failure to a skip rather than letting an assertion
    fail. This pins the secondary guard.
    """
    monkeypatch.setattr(docker_module, "_docker_available", lambda: True)

    def _fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=125,
            stdout="",
            stderr="Error: looking up compose provider failed\n",
        )

    monkeypatch.setattr(docker_module.subprocess, "run", _fake_run)

    with pytest.raises(pytest.skip.Exception):
        docker_module._run_docker_command(["docker", "compose", "config", "--quiet"])
