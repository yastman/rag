"""Verify all traced services have LANGFUSE env vars with dev defaults (#langfuse-coverage)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
BASE_COMPOSE = ROOT / "compose.yml"
DEV_COMPOSE = ROOT / "compose.dev.yml"


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _get_service_env(compose: dict, service: str) -> dict[str, str]:
    """Extract environment dict from a compose service."""
    svc = compose["services"][service]
    env = svc.get("environment", {})
    if isinstance(env, list):
        return {
            item.split("=", 1)[0]: (item.split("=", 1)[1] if "=" in item else "") for item in env
        }
    return env


# Сервисы которые ДОЛЖНЫ иметь LANGFUSE vars
TRACED_SERVICES = ["bot", "litellm", "rag-api", "voice-agent", "ingestion"]

# Минимальный набор vars для трейсинга
REQUIRED_LANGFUSE_VARS = [
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
]


@pytest.fixture(scope="module")
def compose_base() -> dict:
    return _load_compose(BASE_COMPOSE)


@pytest.fixture(scope="module")
def compose_dev() -> dict:
    return _load_compose(DEV_COMPOSE)


class TestLangfuseEnvVarsPresent:
    """All traced services must declare LANGFUSE_PUBLIC_KEY, SECRET_KEY, HOST."""

    @pytest.mark.parametrize("service", TRACED_SERVICES)
    @pytest.mark.parametrize("var", REQUIRED_LANGFUSE_VARS)
    def test_service_has_langfuse_var(self, compose_base: dict, service: str, var: str):
        env = _get_service_env(compose_base, service)
        assert var in env, f"compose.yml: {service} missing {var} in environment block"


SERVICES_WITH_DEV_DEFAULTS = ["bot", "litellm", "rag-api", "voice-agent", "ingestion"]


class TestLangfuseSecretPosture:
    """Base compose avoids predictable secrets; dev compose restores convenience defaults."""

    def test_base_redis_langfuse_command_is_safe_without_password(self, compose_base: dict):
        command = compose_base["services"]["redis-langfuse"]["command"]
        assert "redis-server --requirepass ${LANGFUSE_REDIS_PASSWORD:-}" not in str(command), (
            "compose.yml: redis-langfuse command must not render a bare --requirepass when "
            "LANGFUSE_REDIS_PASSWORD is unset"
        )

    def test_base_redis_langfuse_runs_as_redis_uid_999(self, compose_base: dict):
        """redis-langfuse must declare user: "999:999" matching the volume owner.

        With cap_drop:[ALL] (from x-security-defaults), the container loses
        CAP_DAC_OVERRIDE and CAP_FOWNER. If the process runs as root, it cannot
        write to /data which is owned by uid 999 (redis user from the official
        redis:8.x image), and BGSAVE fails with "Permission denied" → MISCONF
        cascades into langfuse-worker queues. See issue #2186.
        """
        svc = compose_base["services"]["redis-langfuse"]
        assert svc.get("user") == "999:999", (
            'compose.yml: redis-langfuse must set user: "999:999" to match the '
            "redis user (uid 999) baked into redis:8.x and the langfuse_redis_data "
            "volume owner; otherwise cap_drop:[ALL] + root → BGSAVE Permission denied. "
            "See issue #2186."
        )

    def test_base_redis_langfuse_healthcheck_handles_optional_password(self, compose_base: dict):
        test_cmd = compose_base["services"]["redis-langfuse"]["healthcheck"]["test"]
        assert "${LANGFUSE_REDIS_PASSWORD:-}" not in str(test_cmd), (
            "compose.yml: redis-langfuse healthcheck must not require an empty password arg"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_has_no_dev_public_key_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_PUBLIC_KEY", ""))
        assert "pk-lf-dev" not in val, (
            f"compose.yml: {service}.LANGFUSE_PUBLIC_KEY must not hardcode dev defaults, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_has_no_dev_secret_key_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_SECRET_KEY", ""))
        assert "sk-lf-dev" not in val, (
            f"compose.yml: {service}.LANGFUSE_SECRET_KEY must not hardcode dev defaults, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_dev_compose_restores_public_key_default(self, compose_dev: dict, service: str):
        env = _get_service_env(compose_dev, service)
        val = str(env.get("LANGFUSE_PUBLIC_KEY", ""))
        assert "pk-lf-dev" in val, (
            f"compose.dev.yml: {service}.LANGFUSE_PUBLIC_KEY must provide dev default, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_dev_compose_restores_secret_key_default(self, compose_dev: dict, service: str):
        env = _get_service_env(compose_dev, service)
        val = str(env.get("LANGFUSE_SECRET_KEY", ""))
        assert "sk-lf-dev" in val, (
            f"compose.dev.yml: {service}.LANGFUSE_SECRET_KEY must provide dev default, got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_host_has_docker_default(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_HOST", ""))
        assert "langfuse:3000" in val, (
            f"compose.yml: {service}.LANGFUSE_HOST must default to http://langfuse:3000, "
            f"got: {val!r}"
        )

    @pytest.mark.parametrize("service", SERVICES_WITH_DEV_DEFAULTS)
    def test_base_compose_uses_docker_specific_host_var(self, compose_base: dict, service: str):
        env = _get_service_env(compose_base, service)
        val = str(env.get("LANGFUSE_HOST", ""))
        assert "LANGFUSE_DOCKER_HOST" in val, (
            f"compose.yml: {service}.LANGFUSE_HOST must use LANGFUSE_DOCKER_HOST to avoid "
            f"host localhost values leaking into containers, got: {val!r}"
        )

    def test_base_langfuse_has_no_headless_dev_key_defaults(self, compose_base: dict):
        env = _get_service_env(compose_base, "langfuse")
        public = str(env.get("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", ""))
        secret = str(env.get("LANGFUSE_INIT_PROJECT_SECRET_KEY", ""))
        assert "pk-lf-dev" not in public
        assert "sk-lf-dev" not in secret

    def test_dev_langfuse_headless_init_matches_traced_service_keys(self, compose_dev: dict):
        langfuse_env = _get_service_env(compose_dev, "langfuse")
        bot_env = _get_service_env(compose_dev, "bot")

        assert langfuse_env["LANGFUSE_INIT_ORG_ID"] == "${LANGFUSE_INIT_ORG_ID:-dev-org}"
        assert langfuse_env["LANGFUSE_INIT_PROJECT_ID"] == (
            "${LANGFUSE_INIT_PROJECT_ID:-dev-project}"
        )
        assert langfuse_env["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"] == (
            "${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-pk-lf-dev}"
        )
        assert langfuse_env["LANGFUSE_INIT_PROJECT_SECRET_KEY"] == (
            "${LANGFUSE_INIT_PROJECT_SECRET_KEY:-sk-lf-dev}"
        )
        assert bot_env["LANGFUSE_PUBLIC_KEY"] == "${LANGFUSE_PUBLIC_KEY:-pk-lf-dev}"
        assert bot_env["LANGFUSE_SECRET_KEY"] == "${LANGFUSE_SECRET_KEY:-sk-lf-dev}"


class TestLitellmCallbacks:
    """LiteLLM config must have langfuse callbacks configured."""

    def test_success_callback_configured(self):
        config_path = ROOT / "docker" / "litellm" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        settings = config.get("litellm_settings", {})
        callbacks = settings.get("success_callback", [])
        assert "langfuse" in callbacks, (
            "docker/litellm/config.yaml: litellm_settings.success_callback must include 'langfuse'"
        )

    def test_failure_callback_configured(self):
        config_path = ROOT / "docker" / "litellm" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        settings = config.get("litellm_settings", {})
        callbacks = settings.get("failure_callback", [])
        assert "langfuse" in callbacks, (
            "docker/litellm/config.yaml: litellm_settings.failure_callback must include 'langfuse'"
        )


class TestLangfuseMemoryLimits:
    """Langfuse dev container must have enough memory to avoid Node heap OOM (#2179).

    Advisory found v3.175.0 crashes with ``JavaScript heap out of memory`` at the
    1GiB container limit.  Fix: at least 2GiB in compose.dev.yml, plus an explicit
    ``NODE_OPTIONS=--max-old-space-size=1536`` for safety.
    """

    def test_dev_langfuse_memory_at_least_2gib(self, compose_dev: dict):
        svc = compose_dev["services"]["langfuse"]
        deploy = svc.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        memory_raw = limits.get("memory", "0")
        mem_str = str(memory_raw).upper()

        # Parse memory value (support "2G", "2g", "2048M", "2147483648")
        if mem_str.endswith("G"):
            mem_gib = float(mem_str[:-1])
        elif mem_str.endswith("M"):
            mem_gib = float(mem_str[:-1]) / 1024
        else:
            # Try raw bytes
            try:
                mem_gib = int(mem_str) / (1024**3)
            except (ValueError, TypeError):
                mem_gib = 0

        assert mem_gib >= 2.0, (
            f"compose.dev.yml langfuse service memory limit is {memory_raw!r} "
            f"({mem_gib:.1f} GiB). The advisory found v3.175.0 crashes with "
            f"Node heap OOM at 1 GiB.  Raise to at least 2G."
        )

    def test_dev_langfuse_node_options_heap_size(self, compose_dev: dict):
        """Verify NODE_OPTIONS with --max-old-space-size is set for langfuse."""
        env = _get_service_env(compose_dev, "langfuse")

        node_opts = str(env.get("NODE_OPTIONS", ""))
        assert "--max-old-space-size=" in node_opts, (
            f"compose.dev.yml langfuse service must set "
            f"NODE_OPTIONS=--max-old-space-size=<value> to prevent Node heap OOM. "
            f"Got: {node_opts!r}"
        )

        # Extract the value and verify it's at least 1536
        import re

        match = re.search(r"--max-old-space-size=(\d+)", node_opts)
        assert match, f"Could not parse --max-old-space-size from {node_opts!r}"
        size_mb = int(match.group(1))
        assert size_mb >= 1536, (
            f"compose.dev.yml langfuse NODE_OPTIONS max-old-space-size is {size_mb} MB. "
            f"Must be at least 1536 to prevent Node heap OOM at 2 GiB container limit."
        )
