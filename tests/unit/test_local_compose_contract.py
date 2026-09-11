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


# =============================================================================
# Full-stack startup: ordered, waited, failure-honest (#3361)
# =============================================================================


def test_docker_full_up_waits_with_bounded_timeout() -> None:
    """docker-full-up must wait for health with a bounded timeout (#3361).

    Plain `up -d` returns as soon as containers are created — a false green
    while services are still starting or crash-looping. `up --wait` returns
    success only when every started service is running|healthy, and
    `--wait-timeout` bounds the wait instead of hanging forever.
    """
    block = _target_block("docker-full-up")
    assert "up -d --wait --wait-timeout $(FULL_UP_WAIT_TIMEOUT)" in block, (
        "docker-full-up must use `up -d --wait --wait-timeout "
        "$(FULL_UP_WAIT_TIMEOUT)` so success means the full stack is healthy "
        "and the wait is bounded (#3361)"
    )
    assert re.search(
        r"^FULL_UP_WAIT_TIMEOUT \?= \d+$", MAKEFILE.read_text(encoding="utf-8"), re.MULTILINE
    ), (
        "FULL_UP_WAIT_TIMEOUT must be defined with a numeric ?= default so "
        "operators can override the bound (#3361)"
    )


def test_docker_full_up_failure_is_honest_names_services_and_leaks_no_secrets() -> None:
    """A failed full-stack wait must exit nonzero, name failing services, print no secrets.

    #3361 test-first: "Force each dependency unhealthy; command is nonzero,
    names the service and prints no secret." The failure handler lists the
    project's containers with statuses (`docker compose ps -a` — container
    names and states only) and propagates the compose exit code.
    """
    block = _target_block("docker-full-up")

    assert "exit $$status" in block, (
        "docker-full-up must propagate the compose exit status on failure (nonzero exit, #3361)"
    )
    assert "ps -a" in block, (
        "docker-full-up must print the failed stack's container statuses "
        "(compose ps -a names the unhealthy services) so the operator learns "
        "which dependency broke the wait (#3361)"
    )
    for secret_sink in ("ENV_LOAD", 'cat "$(OPERATOR_ENV)"', "cat .env", "set -a"):
        assert secret_sink not in block, (
            f"docker-full-up must not source or dump the operator env ({secret_sink!r}): "
            "failure output prints service names and statuses, never secret values (#3367/#3361)"
        )


def test_docker_core_up_wait_is_bounded() -> None:
    """docker-core-up already waits; the wait must be bounded (#3361)."""
    text = MAKEFILE.read_text(encoding="utf-8")
    block = _target_block("docker-core-up")
    assert "up -d --wait --wait-timeout $(CORE_UP_WAIT_TIMEOUT)" in block, (
        "docker-core-up must bound its `up --wait` with --wait-timeout "
        "$(CORE_UP_WAIT_TIMEOUT) so a never-healthy service fails the command "
        "instead of hanging it forever (#3361)"
    )
    assert re.search(r"^CORE_UP_WAIT_TIMEOUT \?= \d+$", text, re.MULTILINE), (
        "CORE_UP_WAIT_TIMEOUT must be defined with a numeric ?= default (#3361)"
    )
