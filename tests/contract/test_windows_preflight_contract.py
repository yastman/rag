"""Contract for the native Windows preflight entrypoint."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO_ROOT / "scripts" / "windows_preflight.ps1"


def _source() -> str:
    assert PREFLIGHT.is_file(), f"missing {PREFLIGHT.relative_to(REPO_ROOT)}"
    return PREFLIGHT.read_text(encoding="utf-8")


def test_static_preflight_checks_operator_env_and_model_directory() -> None:
    source = _source()
    assert "Test-OperatorReadiness" in source
    assert "Join-Path $root '.env'" in source
    assert "BGE_M3_ONNX_MODEL_HOST_DIR" in source
    assert "must be a native Windows path" in source
    assert "does not exist:" in source


def test_static_preflight_keeps_fixture_compose_rendering() -> None:
    source = _source()
    assert '"tests", "fixtures", "compose.ci.env"' in source
    assert "docker compose --env-file $envFile" in source


def test_tests_mode_runs_windows_acceptance_files() -> None:
    source = _source()
    for rel_path in (
        "tests/unit/scripts/test_cleanup_orphaned_worktree_volumes.py",
        "tests/unit/scripts/test_smoke_zoo.py",
        "tests/unit/test_logging_config.py",
    ):
        assert rel_path.replace("/", '", "') in source


def test_full_mode_uses_native_venv_for_make_test_full_equivalent() -> None:
    source = _source()
    assert "'Full'" in source
    assert 'Join-Path $root ".venv\\Scripts\\python.exe"' in source
    assert 'RUN_BENCHMARK_TESTS = "1"' in source
    for arg in (
        "tests/chaos/",
        "tests/contract/",
        "tests/unit/",
        "tests/benchmark/",
        "-n",
        "2",
        "--dist=worksteal",
        "--timeout=30",
        "tests/e2e/",
        "tests/integration/",
        "tests/load/",
        "tests/smoke/",
    ):
        assert f'"{arg}"' in source


def test_full_mode_syncs_all_dependencies_before_native_venv_preflight() -> None:
    source = _source()
    sync = "& $uv.Path sync --all-extras --all-groups"
    assert "Get-Command uv -CommandType Application -ErrorAction SilentlyContinue" in source
    assert sync in source
    assert "uv is required for Full mode; install it from https://docs.astral.sh/uv/" in source
    assert "uv sync failed (exit=$syncExit); resolve the error above and retry Full mode" in source
    assert source.index(sync) < source.index("& $python -m pytest --version")


def test_full_mode_restores_caller_environment_and_checks_required_plugins() -> None:
    source = _source()
    assert "$hadPycacheSetting = Test-Path Env:\\PYTHONDONTWRITEBYTECODE" in source
    assert "$savedPycacheSetting = $env:PYTHONDONTWRITEBYTECODE" in source
    assert "$hadBenchmarkSetting = Test-Path Env:\\RUN_BENCHMARK_TESTS" in source
    assert "$savedBenchmarkSetting = $env:RUN_BENCHMARK_TESTS" in source
    assert "-m pytest -p xdist --version" in source
    assert "-m pytest -p pytest_timeout --version" in source
    assert "pytest-xdist is unavailable" in source
    assert "pytest-timeout is unavailable" in source
    assert "Set-Item -Path Env:\\PYTHONDONTWRITEBYTECODE -Value $savedPycacheSetting" in source
    assert "Set-Item -Path Env:\\RUN_BENCHMARK_TESTS -Value $savedBenchmarkSetting" in source


def test_preflight_has_non_executing_help_mode() -> None:
    source = _source()
    assert "[switch]$Help" in source
    assert "uv sync --all-extras --all-groups before native venv checks." in source
