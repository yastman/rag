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
