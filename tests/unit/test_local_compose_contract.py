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
        "docker-obs-up",
        "docker-ml-up",
        "docker-ai-up",
        "docker-ingest-up",
        "docker-voice-up",
        "docker-full-up",
        "docker-down",
        "docker-ps",
        "local-up",
        "local-down",
        "local-logs",
        "local-ps",
        "local-build",
        "monitoring-up",
        "monitoring-down",
        "monitoring-logs",
        "monitoring-status",
    ]
    for target in targets:
        block = _target_block(target)
        assert "$(LOCAL_COMPOSE_CMD)" in block, (
            f"{target} must use $(LOCAL_COMPOSE_CMD) so local/dev workflows always load "
            "compose.yml:compose.dev.yml"
        )


def test_docker_core_help_describes_default_unprofiled_stack() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "docker-core-up: ## Start default local compose stack (unprofiled services)" in text, (
        "docker-core-up help text must describe the default unprofiled local compose stack"
    )


def test_docker_docs_default_stack_mentions_mini_app_services() -> None:
    text = DOCKER_DOC.read_text(encoding="utf-8")
    assert "- `mini-app-api`" in text, "DOCKER.md must list mini-app-api in the default stack"
    assert "- `mini-app-frontend`" in text, (
        "DOCKER.md must list mini-app-frontend in the default stack"
    )
