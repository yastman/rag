import re
from pathlib import Path


MAKEFILE = Path("Makefile")


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


# --- #1281 Redis container name contract tests ---


def test_redis_container_default_matches_local_compose_naming() -> None:
    """Regression test for #1281.

    Local Compose uses COMPOSE_PROJECT_NAME=dev (from .env.example), which produces
    container names like dev_redis_1.  make test-redis must default to that name so
    it works out of the box without manual override.
    """
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^REDIS_CONTAINER\s+\?=\s*(.+)$", text, re.MULTILINE)
    assert match, "REDIS_CONTAINER default not found in Makefile"
    default = match.group(1).strip()
    assert default == "dev_redis_1", (
        f"REDIS_CONTAINER default must be 'dev_redis_1' to match local Compose "
        f"naming (COMPOSE_PROJECT_NAME=dev -> dev_redis_1), got {default!r}"
    )


def test_redis_container_override_behavior_preserved() -> None:
    """The variable must use ?= so it can still be overridden from the environment."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "REDIS_CONTAINER ?= " in text, (
        "REDIS_CONTAINER must use ?= so REDIS_CONTAINER=custom make test-redis still works"
    )


# --- #1282 Local services docling contract tests ---


def test_local_services_excludes_docling() -> None:
    text = _makefile_text()
    match = re.search(r"^LOCAL_SERVICES\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match, "LOCAL_SERVICES not found in Makefile"
    services = match.group(1).strip().split()
    assert "docling" not in services, f"docling must not be in LOCAL_SERVICES (found {services!r})"


def test_local_services_includes_postgres_for_native_bot_favorites() -> None:
    text = _makefile_text()
    match = re.search(r"^LOCAL_SERVICES\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match, "LOCAL_SERVICES not found in Makefile"
    services = match.group(1).strip().split()
    assert "postgres" in services, (
        "LOCAL_SERVICES must include postgres so native bot favorites backed by "
        "realestate.public.user_favorites are available in the local loop"
    )


def test_local_ingest_services_includes_docling() -> None:
    text = _makefile_text()
    match = re.search(r"^LOCAL_INGEST_SERVICES\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match, "LOCAL_INGEST_SERVICES not found in Makefile"
    services = match.group(1).strip().split()
    assert "docling" in services, f"docling must be in LOCAL_INGEST_SERVICES (found {services!r})"


def test_local_all_services_combines_both_sets() -> None:
    text = _makefile_text()
    match = re.search(r"^LOCAL_ALL_SERVICES\s*:=\s*(.+)$", text, re.MULTILINE)
    assert match, "LOCAL_ALL_SERVICES not found in Makefile"
    definition = match.group(1).strip()
    assert "$(LOCAL_SERVICES)" in definition, "LOCAL_ALL_SERVICES must reference $(LOCAL_SERVICES)"
    assert "$(LOCAL_INGEST_SERVICES)" in definition, (
        "LOCAL_ALL_SERVICES must reference $(LOCAL_INGEST_SERVICES)"
    )


def test_local_up_ingest_target_exists() -> None:
    text = _makefile_text()
    assert re.search(r"^local-up-ingest:", text, re.MULTILINE), (
        "local-up-ingest target must exist in Makefile"
    )


def test_local_down_uses_all_services() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^local-down:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "local-down target not found"
    block = block_match.group(0)
    assert "$(LOCAL_ALL_SERVICES)" in block, (
        "local-down must reference $(LOCAL_ALL_SERVICES) for coherence"
    )


def test_local_logs_uses_all_services() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^local-logs:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "local-logs target not found"
    block = block_match.group(0)
    assert "$(LOCAL_ALL_SERVICES)" in block, (
        "local-logs must reference $(LOCAL_ALL_SERVICES) for coherence"
    )


def test_local_ps_uses_all_services() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^local-ps:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "local-ps target not found"
    block = block_match.group(0)
    assert "$(LOCAL_ALL_SERVICES)" in block, (
        "local-ps must reference $(LOCAL_ALL_SERVICES) for coherence"
    )


# --- Makefile drift contract tests ---


def test_makefile_targets_refer_only_to_existing_test_files() -> None:
    """Every test file path referenced by a Makefile target must exist."""
    text = _makefile_text()
    # Find pytest invocations with explicit test file paths
    referenced = set(re.findall(r"pytest\s+([\w\-/]+\.py)", text))
    missing = []
    for ref in referenced:
        if not Path(ref).exists():
            missing.append(ref)
    assert not missing, (
        f"Makefile references missing test files: {missing}. "
        "Remove or rewrite the affected targets."
    )


def test_makefile_does_not_use_invalid_core_profile() -> None:
    """`core` is not a defined Compose profile; targets must not reference it."""
    text = _makefile_text()
    matches = list(re.finditer(r"--profile\s+core", text))
    assert not matches, (
        f"Makefile references invalid Compose profile 'core' at position(s) "
        f"{[m.start() for m in matches]}. Use existing profiles (bot, ml, obs, ingest, voice, full) "
        f"or unprofiled services via $(LOCAL_COMPOSE_CMD) up -d."
    )


def test_validate_traces_targets_use_local_compose_cmd() -> None:
    """Trace validation targets must use the local Compose contract (LOCAL_COMPOSE_CMD)."""
    text = _makefile_text()
    for target in ("validate-traces", "validate-traces-fast"):
        block_match = re.search(
            rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert block_match, f"{target} target not found in Makefile"
        block = block_match.group(0)
        assert "$(LOCAL_COMPOSE_CMD)" in block, (
            f"{target} must use $(LOCAL_COMPOSE_CMD) to respect the local Compose contract "
            f"(compose.yml:compose.dev.yml with env-file handling)."
        )


def test_validate_traces_fast_runs_postgres_auth_preflight() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^validate-traces-fast:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "validate-traces-fast target not found in Makefile"
    block = block_match.group(0)
    assert "scripts/validate_trace_runtime.py" in block, (
        "validate-traces-fast must run scripts/validate_trace_runtime.py preflight "
        "before docker compose up to avoid silent Postgres auth mismatch loops."
    )


def test_trace_validation_targets_use_valid_langfuse_key_fallbacks() -> None:
    """Trace validation targets must render valid shell env assignments."""
    text = _makefile_text()
    for target in ("validate-traces-fast", "validate-voice-traces"):
        block_match = re.search(
            rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert block_match, f"{target} target not found in Makefile"
        block = block_match.group(0)

        assert (
            'LANGFUSE_PUBLIC_KEY="$(or $(LANGFUSE_PUBLIC_KEY),pk$(LANGFUSE_DEV_KEY_DASH)lf-dev)"'
            in block
        )
        assert (
            'LANGFUSE_SECRET_KEY="$(or $(LANGFUSE_SECRET_KEY),sk$(LANGFUSE_DEV_KEY_DASH)lf-dev)"'
            in block
        )
        assert "[REDACTED-LANGFUSE-KEY]" not in block, (
            f"{target} must not contain redacted placeholders in shell env "
            "assignments; they break `make validate-traces-fast` with a shell syntax error."
        )


def test_validate_traces_fast_loads_runtime_dotenv_without_redis_default() -> None:
    """Trace validation must not mask .env REDIS_PASSWORD with a stale default."""
    text = _makefile_text()
    block_match = re.search(
        r"^validate-traces-fast:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "validate-traces-fast target not found in Makefile"
    block = block_match.group(0)

    assert (
        "TRACE_ENV_FILE ?= $(shell [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env)"
        in text
    )
    assert 'uv run dotenv -f "$(TRACE_ENV_FILE)" run --no-override --' in block
    assert 'REDIS_PASSWORD="$(or $(REDIS_PASSWORD),dev_redis_pass)"' not in block, (
        "validate-traces-fast must let python-dotenv load REDIS_PASSWORD from the "
        "same env file Compose uses; a hardcoded default causes auth mismatches."
    )


def test_validate_traces_fast_randomizes_minio_host_ports_by_default() -> None:
    """Trace validation must not depend on fixed optional MinIO host ports."""
    text = _makefile_text()
    block_match = re.search(
        r"^validate-traces-fast:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "validate-traces-fast target not found in Makefile"
    block = block_match.group(0)

    assert 'MINIO_API_PORT="$(or $(MINIO_API_PORT),0)"' in block
    assert 'MINIO_CONSOLE_PORT="$(or $(MINIO_CONSOLE_PORT),0)"' in block


# --- #1307 core trace gate contract tests ---


def test_e2e_test_traces_core_is_phony() -> None:
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    assert phony_blocks, ".PHONY declaration not found in Makefile"
    combined = " ".join(phony_blocks)
    assert "e2e-test-traces-core" in combined, "e2e-test-traces-core must be declared in .PHONY"


def test_e2e_test_traces_core_target_exists() -> None:
    text = _makefile_text()
    assert re.search(r"^e2e-test-traces-core:", text, re.MULTILINE), (
        "e2e-test-traces-core target must exist in Makefile"
    )


def test_e2e_test_traces_core_uses_langfuse_validation() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^e2e-test-traces-core:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "e2e-test-traces-core target not found in Makefile"
    block = block_match.group(0)
    assert "E2E_VALIDATE_LANGFUSE=1" in block, (
        "e2e-test-traces-core must set E2E_VALIDATE_LANGFUSE=1"
    )


def test_e2e_test_traces_core_uses_no_judge() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^e2e-test-traces-core:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "e2e-test-traces-core target not found in Makefile"
    block = block_match.group(0)
    assert "--no-judge" in block, (
        "e2e-test-traces-core must use --no-judge to skip LLM judge during core trace gate"
    )


def test_e2e_test_traces_core_includes_required_scenarios() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^e2e-test-traces-core:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "e2e-test-traces-core target not found in Makefile"
    block = block_match.group(0)
    required = ("0.1", "6.3", "7.1", "8.1")
    missing = [s for s in required if f"--scenario {s}" not in block]
    assert not missing, (
        f"e2e-test-traces-core must include all required #1307 scenarios; missing: {missing}"
    )


# --- #1490 latest trace audit contract tests ---


def test_langfuse_latest_trace_audit_is_phony() -> None:
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    assert phony_blocks, ".PHONY declaration not found in Makefile"
    combined = " ".join(phony_blocks)
    assert "langfuse-latest-trace-audit" in combined, (
        "langfuse-latest-trace-audit must be declared in .PHONY"
    )


def test_langfuse_latest_trace_audit_target_exists() -> None:
    text = _makefile_text()
    assert re.search(r"^langfuse-latest-trace-audit:", text, re.MULTILINE), (
        "langfuse-latest-trace-audit target must exist in Makefile"
    )


def test_langfuse_latest_trace_audit_runs_audit_script() -> None:
    text = _makefile_text()
    block_match = re.search(
        r"^langfuse-latest-trace-audit:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "langfuse-latest-trace-audit target not found in Makefile"
    block = block_match.group(0)
    assert "scripts/e2e/langfuse_latest_trace_audit.py" in block, (
        "langfuse-latest-trace-audit must invoke scripts/e2e/langfuse_latest_trace_audit.py"
    )


# --- #1486 runtime env contract tests ---


def test_e2e_trace_targets_use_runtime_env_file() -> None:
    """E2E trace targets must load runtime env explicitly so worktrees without .env still work."""
    text = _makefile_text()
    for target in ("e2e-telegram-test", "e2e-test-traces", "e2e-test-traces-core"):
        block_match = re.search(
            rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert block_match, f"{target} target not found in Makefile"
        block = block_match.group(0)
        assert '--env-file "$$RAG_RUNTIME_ENV_FILE"' in block, (
            f'{target} must use --env-file "$$RAG_RUNTIME_ENV_FILE" '
            f"to load runtime credentials explicitly in worktrees"
        )


def test_runtime_env_file_has_safe_fallback() -> None:
    """RAG_RUNTIME_ENV_FILE must have a safe CI-fallback *and* be exported so recipes
    receive it even when the shell environment does not set it."""
    text = _makefile_text()
    assert "RAG_RUNTIME_ENV_FILE" in text, "RAG_RUNTIME_ENV_FILE not found in Makefile"
    assert "tests/fixtures/compose.ci.env" in text, (
        "Makefile must reference tests/fixtures/compose.ci.env as the safe fallback"
    )
    assert "export RAG_RUNTIME_ENV_FILE" in text, (
        "Makefile must export RAG_RUNTIME_ENV_FILE so recipe shells "
        "receive the Make-defined fallback even when the environment does not set it"
    )


def test_runtime_env_file_resolves_before_export() -> None:
    """RAG_RUNTIME_ENV_FILE must export an env-file path, not a shell expression."""
    text = _makefile_text()
    match = re.search(r"^RAG_RUNTIME_ENV_FILE\s*\?=\s*(.+)$", text, re.MULTILINE)
    assert match, "RAG_RUNTIME_ENV_FILE assignment not found in Makefile"
    value = match.group(1)
    assert "$$(" not in value, (
        "RAG_RUNTIME_ENV_FILE is exported to recipe shells, so it must resolve "
        "to a concrete env-file path before export, not a deferred shell expression"
    )
    assert "$(shell " in value


# --- Local all-test entrypoint contract tests ---


def test_test_bot_health_target_sources_env_file() -> None:
    """The test-bot-health target must source an env file before running the script."""
    text = _makefile_text()
    block_match = re.search(
        r"^test-bot-health:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-bot-health target not found in Makefile"
    block = block_match.group(0)
    assert "tests/fixtures/compose.ci.env" in block, (
        "test-bot-health target must reference tests/fixtures/compose.ci.env "
        "as the safe local env fallback when .env is absent"
    )


def test_test_bot_health_target_env_precedence() -> None:
    """The test-bot-health target must prefer .env over the fixture when .env exists."""
    text = _makefile_text()
    block_match = re.search(
        r"^test-bot-health:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-bot-health target not found in Makefile"
    block = block_match.group(0)
    assert "-f .env" in block, (
        "test-bot-health target must check for .env existence first, "
        "preserving user .env precedence over the compose.ci.env fallback"
    )


def test_run_bot_uses_runtime_env_file_fallback() -> None:
    """`make run-bot` must work in local worktrees without a `.env` file."""
    text = _makefile_text()
    block_match = re.search(
        r"^run-bot:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "run-bot target not found in Makefile"
    block = block_match.group(0)
    assert '--env-file "$$RAG_RUNTIME_ENV_FILE"' in block
    assert "--env-file .env" not in block


def test_bot_uses_runtime_env_file_fallback() -> None:
    """`make bot` must tee logs while using the same `.env`/fixture fallback."""
    text = _makefile_text()
    block_match = re.search(
        r"^bot:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "bot target not found in Makefile"
    block = block_match.group(0)
    assert '--env-file "$$RAG_RUNTIME_ENV_FILE"' in block
    assert "--env-file .env" not in block


def test_bot_depends_on_local_health_preflight() -> None:
    """`make bot` must gate startup on local health checks to fail fast on Redis drift/outage."""
    text = _makefile_text()
    match = re.search(r"^bot:\s*(.+?)\s*##", text, re.MULTILINE)
    assert match, "bot target not found in Makefile"
    prerequisites = match.group(1).split()
    assert "preflight-bot" in prerequisites, "bot target must keep env preflight gate"
    assert "test-bot-health" in prerequisites, (
        "bot target must depend on test-bot-health so Redis/Qdrant/LLM readiness "
        "fails before runtime deep-checks"
    )


def test_bot_preserves_pipeline_failure_exit_code() -> None:
    """`make bot` must not hide Python startup failures behind tee/echo."""
    text = _makefile_text()
    block_match = re.search(
        r"^bot:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "bot target not found in Makefile"
    block = block_match.group(0)
    assert "pipefail" in block
    assert "exit $$status" in block


def test_frontend_test_target_runs_vitest() -> None:
    """The local test inventory includes Vitest tests outside pytest's testpaths."""
    text = _makefile_text()
    block_match = re.search(
        r"^test-frontend:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-frontend target not found in Makefile"
    block = block_match.group(0)
    assert "mini_app/frontend" in block
    assert "npm test" in block


def test_all_local_target_runs_pytest_full_and_frontend() -> None:
    """The explicit all-local gate must include both Python and frontend suites."""
    text = _makefile_text()
    block_match = re.search(
        r"^test-all-local:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-all-local target not found in Makefile"
    block = block_match.group(0)
    assert "make test-full" in block
    assert "make test-frontend" in block


def test_local_all_test_targets_are_phony() -> None:
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    combined = " ".join(phony_blocks)
    assert "test-frontend" in combined
    assert "test-all-local" in combined


# --- #1778 bounded parallelism contract tests ---


def test_test_full_uses_bounded_parallelism_by_default() -> None:
    """Regression test for #1778.

    test-full must use PYTEST_FULL_PARALLEL_ARGS (bounded, e.g. -n 2) instead of
    PYTEST_PARALLEL_ARGS (-n auto) to prevent WSL/Docker OOM under heavy local
    test sessions.
    """
    text = _makefile_text()

    # 1. PYTEST_FULL_PARALLEL_ARGS must be defined
    var_match = re.search(r"^PYTEST_FULL_PARALLEL_ARGS\s*\?=\s*(.+)$", text, re.MULTILINE)
    assert var_match, "PYTEST_FULL_PARALLEL_ARGS not found in Makefile"

    # 2. Its default must NOT be unbounded -n auto
    default_value = var_match.group(1).strip()
    assert "-n auto" not in default_value, (
        f"PYTEST_FULL_PARALLEL_ARGS must use bounded parallelism, "
        f"got {default_value!r} which contains '-n auto'"
    )

    # 3. test-full target must reference PYTEST_FULL_PARALLEL_ARGS, not PYTEST_PARALLEL_ARGS
    block_match = re.search(
        r"^test-full:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-full target not found in Makefile"
    block = block_match.group(0)
    assert "$(PYTEST_FULL_PARALLEL_ARGS)" in block, (
        "test-full must use $(PYTEST_FULL_PARALLEL_ARGS) for bounded parallelism"
    )
    assert "$(PYTEST_PARALLEL_ARGS)" not in block, (
        "test-full must NOT use $(PYTEST_PARALLEL_ARGS) (unbounded -n auto); "
        "use $(PYTEST_FULL_PARALLEL_ARGS) instead"
    )


# --- #2123 / #2126 preflight-bot guardrail contract tests ---


def test_preflight_bot_target_exists() -> None:
    """`preflight-bot` must exist as a standalone Makefile target."""
    text = _makefile_text()
    assert re.search(r"^preflight-bot:", text, re.MULTILINE), (
        "preflight-bot target must exist in Makefile"
    )


def test_preflight_bot_is_phony() -> None:
    """`preflight-bot` must be declared .PHONY."""
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    combined = " ".join(phony_blocks)
    assert "preflight-bot" in combined, "preflight-bot must be declared in .PHONY"


def test_preflight_bot_runs_no_sync_module() -> None:
    """`preflight-bot` must invoke the env checker without uv auto-sync."""
    text = _makefile_text()
    block_match = re.search(
        r"^preflight-bot:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "preflight-bot target not found in Makefile"
    block = block_match.group(0)
    assert "$(UV_RUN_NO_SYNC) python -m scripts.probe.check_bot_runtime_env" in block, (
        "preflight-bot must invoke scripts.probe.check_bot_runtime_env via "
        "$(UV_RUN_NO_SYNC) so bot startup checks do not mutate .venv"
    )


def test_candidate_check_is_read_only_frozen_gate() -> None:
    """`make candidate-check` must fail on stale env before no-sync lint/type checks."""
    text = _makefile_text()
    assert re.search(r"^candidate-check:\s*check-frozen\b", text, re.MULTILINE), (
        "candidate-check must depend on check-frozen"
    )
    block_match = re.search(
        r"^check-frozen:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "check-frozen target not found in Makefile"
    block = block_match.group(0)
    assert "uv sync --frozen --check" in block
    assert "$(UV_RUN_NO_SYNC) ruff check $(LINT_PATHS)" in block
    assert "$(UV_RUN_NO_SYNC) mypy $(LINT_PATHS)" in block
    assert "uv run ruff" not in block
    assert "uv run mypy" not in block


def test_preflight_bot_has_flag_override() -> None:
    """`PREFLIGHT_BOT_FLAGS` must be a ?= variable so CI can pass `--no-fail`."""
    text = _makefile_text()
    match = re.search(r"^PREFLIGHT_BOT_FLAGS\s*\?=", text, re.MULTILINE)
    assert match, "PREFLIGHT_BOT_FLAGS must use ?= so CI can override with --no-fail"


def test_docker_bot_up_depends_on_preflight_bot() -> None:
    """`docker-bot-up` must depend on `preflight-bot` so the env check
    runs before starting the bot containers."""
    text = _makefile_text()
    block_match = re.search(
        r"^docker-bot-up:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "docker-bot-up target not found in Makefile"
    # The dependency line (first line of the target block).
    first_line = block_match.group(0).split("\n")[0]
    assert "preflight-bot" in first_line, (
        "docker-bot-up must list preflight-bot as a dependency so the env "
        f"check runs first. Found: {first_line!r}"
    )


def test_bot_target_depends_on_preflight_bot() -> None:
    """`make bot` (native) must also depend on `preflight-bot` since
    native bot startup requires real credentials."""
    text = _makefile_text()
    block_match = re.search(
        r"^bot:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "bot target not found in Makefile"
    first_line = block_match.group(0).split("\n")[0]
    assert "preflight-bot" in first_line, (
        "bot target must list preflight-bot as a dependency so native bot "
        f"launch fails fast when .env is missing. Found: {first_line!r}"
    )


def test_preflight_bot_script_exists() -> None:
    """The script referenced by preflight-bot must actually exist."""
    script = Path("scripts/probe/check_bot_runtime_env.py")
    assert script.is_file(), (
        f"{script} not found — preflight-bot target references a missing script"
    )
