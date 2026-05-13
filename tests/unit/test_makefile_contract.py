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
