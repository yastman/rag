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


def test_polling_lock_key_default_matches_bot_contract() -> None:
    """The manual unlock target must use the canonical bot polling lock key."""
    text = _makefile_text()
    match = re.search(r"^POLLING_LOCK_KEY\s+\?=\s*(.+)$", text, re.MULTILINE)
    assert match, "POLLING_LOCK_KEY default not found in Makefile"
    assert match.group(1).strip() == "telegram-bot:polling"


def test_release_polling_lock_target_exists_and_uses_rediscli_auth() -> None:
    """Operators need a safe local workaround for stale Redis polling locks."""
    text = _makefile_text()
    block_match = re.search(
        r"^release-polling-lock:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "release-polling-lock target not found in Makefile"
    block = block_match.group(0)
    assert "POLLING_LOCK_KEY" in block
    assert "REDISCLI_AUTH" in block, "target must not put Redis passwords on redis-cli -a argv"
    assert 'redis_exec DEL "$$key"' in block
    assert "sh -c" not in block, "target should pass keys/passwords as docker exec args"
    assert "make run-bot" in block


def test_release_polling_lock_requires_bot_not_running_unless_forced() -> None:
    """The manual unlock target must not create a second live poller by default."""
    text = _makefile_text()
    assert "RELEASE_POLLING_LOCK_FORCE ?= 0" in text
    block_match = re.search(
        r"^release-polling-lock:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "release-polling-lock target not found in Makefile"
    block = block_match.group(0)
    assert "docker ps --filter name=bot" in block
    assert "telegram_bot[.]main" in block
    assert "Refusing to release polling lock" in block
    assert "RELEASE_POLLING_LOCK_FORCE=1" in block


def test_release_polling_lock_is_phony() -> None:
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    combined = " ".join(phony_blocks)
    assert "release-polling-lock" in combined


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


def test_obsolete_langfuse_trace_targets_are_removed() -> None:
    """DEPS-14 removes legacy Langfuse/trace Makefile diagnostics."""
    text = _makefile_text()
    obsolete_targets = (
        "validate-traces",
        "validate-traces-fast",
        "validate-voice-traces",
        "langfuse-latency-audit",
        "langfuse-latest-trace-audit",
        "trace-audit-snapshot",
    )

    for target in obsolete_targets:
        assert not re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"{target} should be removed from Makefile"
        )
    assert "the removed trace validation script" not in text
    assert "scripts/validate_trace_runtime.py" not in text
    assert "scripts/validate_voice_traces.py" not in text
    assert "scripts.probe.langfuse_latency_audit" not in text
    assert "the removed latest-trace audit script" not in text
    assert "scripts.audit.trace_audit_snapshot" not in text


# --- Legacy trace validation targets removed ---


def test_removed_e2e_trace_validation_targets_stay_removed() -> None:
    text = _makefile_text()
    assert "e2e-test-traces:" not in text
    assert "e2e-test-traces-core:" not in text
    assert "E2E_VALIDATE_LANGFUSE" not in text


# --- #1490 latest trace audit contract tests ---


# --- #1486 runtime env contract tests ---


def test_e2e_trace_targets_use_runtime_env_file() -> None:
    """E2E trace targets must load runtime env explicitly so worktrees without .env still work."""
    text = _makefile_text()
    for target in ("e2e-telegram-test",):
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


def test_frontend_test_target_removed_from_required_path() -> None:
    """Archived Mini App frontend tests must not be part of the required local gate."""
    text = _makefile_text()
    assert "test-frontend:" not in text
    assert "mini_app/frontend" not in text


def test_all_local_target_runs_pytest_full_only() -> None:
    """The explicit all-local gate follows the Python required path only."""
    text = _makefile_text()
    block_match = re.search(
        r"^test-all-local:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, "test-all-local target not found in Makefile"
    block = block_match.group(0)
    assert "make test-full" in block
    assert "make test-frontend" not in block


def test_local_all_test_target_is_phony() -> None:
    text = _makefile_text()
    phony_blocks = re.findall(r"^\.PHONY:.*(?:\\\n.*)*", text, re.MULTILINE)
    combined = " ".join(phony_blocks)
    assert "test-frontend" not in combined
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
