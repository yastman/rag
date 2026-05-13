from __future__ import annotations

from pathlib import Path

from scripts import validate_trace_runtime as runtime_guard


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_guard_blocks_ci_fallback_with_existing_postgres_volume(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    env_file = tmp_path / "tests/fixtures/compose.ci.env"
    _write(
        env_file,
        "COMPOSE_PROJECT_NAME=dev\nPOSTGRES_PASSWORD=test-postgres-password\n",
    )
    monkeypatch.setattr(runtime_guard, "_volume_exists", lambda _: True)

    exit_code = runtime_guard.main(["--env-file", str(env_file)])

    out = capsys.readouterr()
    assert exit_code == 2
    assert "Postgres auth mismatch risk" in out.err
    assert "dev_postgres_data" in out.err


def test_guard_allows_ci_fallback_when_volume_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    env_file = tmp_path / "tests/fixtures/compose.ci.env"
    _write(
        env_file,
        "COMPOSE_PROJECT_NAME=dev\nPOSTGRES_PASSWORD=test-postgres-password\n",
    )
    monkeypatch.setattr(runtime_guard, "_volume_exists", lambda _: False)

    exit_code = runtime_guard.main(["--env-file", str(env_file)])

    assert exit_code == 0


def test_guard_allows_when_postgres_password_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POSTGRES_PASSWORD", "override-password")
    env_file = tmp_path / "tests/fixtures/compose.ci.env"
    _write(
        env_file,
        "COMPOSE_PROJECT_NAME=dev\nPOSTGRES_PASSWORD=test-postgres-password\n",
    )
    monkeypatch.setattr(runtime_guard, "_volume_exists", lambda _: True)

    exit_code = runtime_guard.main(["--env-file", str(env_file)])

    assert exit_code == 0


def test_guard_allows_when_dotenv_exists_even_if_volume_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    _write(tmp_path / ".env", "POSTGRES_PASSWORD=postgres\n")
    env_file = tmp_path / "tests/fixtures/compose.ci.env"
    _write(
        env_file,
        "COMPOSE_PROJECT_NAME=dev\nPOSTGRES_PASSWORD=test-postgres-password\n",
    )
    monkeypatch.setattr(runtime_guard, "_volume_exists", lambda _: True)

    exit_code = runtime_guard.main(["--env-file", str(env_file)])

    assert exit_code == 0


def test_guard_allows_ci_fallback_with_default_password_and_existing_volume(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    env_file = tmp_path / "tests/fixtures/compose.ci.env"
    _write(
        env_file,
        "COMPOSE_PROJECT_NAME=dev\nPOSTGRES_PASSWORD=postgres\n",
    )
    monkeypatch.setattr(runtime_guard, "_volume_exists", lambda _: True)

    exit_code = runtime_guard.main(["--env-file", str(env_file)])

    assert exit_code == 0
