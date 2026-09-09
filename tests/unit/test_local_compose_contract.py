import re
from pathlib import Path


MAKEFILE = Path("Makefile")
DOCKER_DOC = Path("DOCKER.md")


def _target_block(target: str) -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    pattern = rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match, f"Target {target!r} not found in Makefile"
    return match.group(0)


def test_local_dev_docker_targets_use_local_compose_override() -> None:
    targets = [
        "docker-core-up",
        "docker-bot-up",
        "docker-ai-up",
        "docker-ingest-up",
        "docker-full-up",
        "docker-down",
        "docker-ps",
        "local-up",
        "local-up-ingest",
        "local-down",
        "local-logs",
        "local-ps",
        "local-build",
    ]
    for target in targets:
        block = _target_block(target)
        assert "$(LOCAL_COMPOSE_CMD)" in block, (
            f"{target} must use $(LOCAL_COMPOSE_CMD) so local/dev workflows always load "
            "compose.yml:compose.dev.yml"
        )


def test_docker_core_help_describes_default_unprofiled_stack() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert (
        "docker-core-up: operator-env-check ## Start default local compose stack "
        "(unprofiled services; env-validated #3367)" in text
    ), "docker-core-up help text must describe the default unprofiled local compose stack"


def test_docker_docs_default_stack_omits_mini_app_services() -> None:
    text = DOCKER_DOC.read_text(encoding="utf-8")
    assert "- `mini-app-api`" not in text
    assert "- `mini-app-frontend`" not in text


def test_local_compose_cmd_uses_explicit_operator_env() -> None:
    """#3367: local compose commands require the explicit operator env file.

    Real build/up commands must never fall back to tests/fixtures/compose.ci.env
    when .env is absent — silent dummy credentials made failing stacks look up.
    """
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "LOCAL_COMPOSE_CMD" in text
    assert "--env-file" in text, (
        "Makefile LOCAL_COMPOSE_CMD must specify --env-file for the operator env"
    )
    assert "compose.ci.env" not in text, (
        "Makefile must not reference tests/fixtures/compose.ci.env: the CI "
        "fixture is confined to named CI/static-validation targets (#3367)"
    )
    local_cmd = next(line for line in text.splitlines() if line.startswith("LOCAL_COMPOSE_CMD :="))
    assert "$(OPERATOR_ENV)" in local_cmd, (
        "LOCAL_COMPOSE_CMD must pass the explicit operator env file"
    )
