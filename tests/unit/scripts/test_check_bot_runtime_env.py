"""Tests for scripts/probe/check_bot_runtime_env.py — preflight guard for make bot / docker-bot-up."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/probe/check_bot_runtime_env.py")

CI_ENV_CONTENT = """\
COMPOSE_PROJECT_NAME=dev
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
LITELLM_MASTER_KEY=test-litellm-master-key
REDIS_PASSWORD=test-redis-password
POSTGRES_PASSWORD=postgres
"""

VALID_ENV_CONTENT = """\
COMPOSE_PROJECT_NAME=dev
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl
LITELLM_MASTER_KEY=sk-real-master-key
REDIS_PASSWORD=test-redis-password
POSTGRES_PASSWORD=postgres
"""


# ---------------------------------------------------------------------------
# Helper: run the script with a specific env file
# ---------------------------------------------------------------------------


def _run_script(
    env_file: Path | None = None,
    no_fail: bool = False,
    check_docker: bool = False,
) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT.resolve())]
    if env_file:
        args.extend(["--env-file", str(env_file)])
    if no_fail:
        args.append("--no-fail")
    if not check_docker:
        args.append("--skip-docker")
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=SCRIPT.parents[2],
    )


# ---------------------------------------------------------------------------
# .env presence checks
# ---------------------------------------------------------------------------


def test_script_detects_missing_dotenv(tmp_path: Path) -> None:
    """When the effective env file is the CI fallback, the script must warn
    about the missing .env and explain the fallback behaviour."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert "missing" in combined.lower() or ".env not found" in combined.lower(), (
        f"script must note .env is missing when using CI fallback; got:\n{combined}"
    )
    assert (
        "ci fallback" in combined.lower()
        or "fixture" in combined.lower()
        or "compose.ci.env" in combined.lower()
    ), f"script must explain CI fallback behaviour; got:\n{combined}"


def test_script_detects_dotenv_present(tmp_path: Path) -> None:
    """When the env file is .env, the script should not warn about missing .env."""
    env_file = tmp_path / ".env"
    env_file.write_text(VALID_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    # Should NOT report .env as missing
    assert "missing" not in combined.lower() or ".env not found" not in combined.lower(), (
        f"script should not report .env missing when .env is used; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# TELEGRAM_BOT_TOKEN validation
# ---------------------------------------------------------------------------


def test_script_warns_on_ci_fallback_token(tmp_path: Path) -> None:
    """When TELEGRAM_BOT_TOKEN matches the CI fallback value
    (123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi), the script must warn
    that this token is invalid and explain the bot will fail."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert "TELEGRAM_BOT_TOKEN" in combined, (
        f"script must mention TELEGRAM_BOT_TOKEN; got:\n{combined}"
    )
    assert (
        "invalid" in combined.lower()
        or "placeholder" in combined.lower()
        or "ci" in combined.lower()
    ), f"script must indicate the token is a CI placeholder/invalid; got:\n{combined}"


def test_script_reports_remediation_for_missing_env(tmp_path: Path) -> None:
    """When .env is missing, the script must suggest creating one from
    .env.example and filling credentials."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert ".env.example" in combined or "cp .env.example" in combined, (
        f"script must reference .env.example as remediation; got:\n{combined}"
    )


def test_script_explains_token_validation_failure(tmp_path: Path) -> None:
    """When TELEGRAM_BOT_TOKEN will cause a TokenValidationError, the script
    must explain the crash behaviour (bot will restart/loop)."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert (
        "crash" in combined.lower()
        or "restart" in combined.lower()
        or "fail" in combined.lower()
        or "token" in combined.lower()
    ), f"script must explain bot crash behaviour with placeholder token; got:\n{combined}"


# ---------------------------------------------------------------------------
# LiteLLM port binding warnings
# ---------------------------------------------------------------------------


def test_script_skips_docker_check_when_requested(tmp_path: Path) -> None:
    """When --skip-docker is passed, LiteLLM port check must be skipped."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file, check_docker=False)

    combined = cp.stdout + cp.stderr
    assert "skip" in combined.lower() or "docker" in combined.lower(), (
        f"script must acknowledge Docker check is skipped; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# Exit code behaviour
# ---------------------------------------------------------------------------


def test_script_exits_nonzero_on_ci_fallback_env(tmp_path: Path) -> None:
    """The script must fail fast (exit non-zero) when critical issues are found,
    so Makefile targets can depend on it."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    assert cp.returncode != 0, (
        f"script must exit non-zero when .env is missing and CI fallback is used; "
        f"got exit code {cp.returncode}"
    )


def test_script_exits_zero_with_no_fail_flag(tmp_path: Path) -> None:
    """The --no-fail flag must suppress the non-zero exit so CI can still proceed."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file, no_fail=True)

    assert cp.returncode == 0, (
        f"script must exit 0 with --no-fail, got {cp.returncode}\n"
        f"stdout: {cp.stdout}\nstderr: {cp.stderr}"
    )


# ---------------------------------------------------------------------------
# Script structure / contract checks
# ---------------------------------------------------------------------------


def test_script_exists_and_is_python() -> None:
    """The script file must exist and be a Python script."""
    assert SCRIPT.is_file(), f"{SCRIPT} not found"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "python" in text.lower() or text.startswith("#!"), f"{SCRIPT} must be a Python script"


def test_script_has_shebang_and_main_guard() -> None:
    """The script must have proper shebang and __main__ guard for standalone use."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "#!/usr/bin/env python" in text, f"{SCRIPT} must have a Python shebang"
    assert 'if __name__ == "__main__"' in text, (
        f"{SCRIPT} must have a __main__ guard to allow import testing"
    )


def test_script_does_not_import_telegram_bot_runtime_modules() -> None:
    """Scripts are out-of-process tools and must not import telegram_bot runtime modules."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "from telegram_bot" not in text
    assert "import telegram_bot" not in text


def test_script_provides_help() -> None:
    """The script must support --help for operator documentation."""
    cp = subprocess.run(
        [sys.executable, str(SCRIPT.resolve()), "--help"],
        capture_output=True,
        text=True,
        cwd=SCRIPT.parents[2],
    )
    assert cp.returncode == 0, f"--help must exit 0, got {cp.returncode}"
    assert "usage" in (cp.stdout + cp.stderr).lower(), (
        f"--help must show usage; got:\n{cp.stdout}{cp.stderr}"
    )


def test_script_lists_affected_make_targets_in_help_or_output(tmp_path: Path) -> None:
    """The script must mention affected make targets so operators know what
    this preflight gates."""
    env_file = tmp_path / "compose.ci.env"
    env_file.write_text(CI_ENV_CONTENT)

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert (
        "make bot" in combined.lower()
        or "make docker-bot-up" in combined.lower()
        or "docker-bot-up" in combined.lower()
    ), f"script must reference affected make targets; got:\n{combined}"


def test_script_does_not_print_secret_values(tmp_path: Path) -> None:
    """The script must never print actual secret values from the env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=1234567890:REALsecretKEY1234567890abcdef\n"
        "LITELLM_MASTER_KEY=sk-real-master-key-12345\n"
        "REDIS_PASSWORD=supersecretredis123\n"
    )

    cp = _run_script(env_file=env_file)

    combined = cp.stdout + cp.stderr
    assert "REALsecretKEY" not in combined, "script must not print real TELEGRAM_BOT_TOKEN value"
    assert "sk-real-master-key-12345" not in combined, (
        "script must not print real LITELLM_MASTER_KEY value"
    )
    assert "supersecretredis123" not in combined, "script must not print real REDIS_PASSWORD value"
