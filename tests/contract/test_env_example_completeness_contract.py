# tests/contract/test_env_example_completeness_contract.py
"""Bidirectional ``.env.example`` ↔ source code sync contract (#1268).

Issue #1268 (refresh 2026-05-21) called for a deterministic env-var scanner
that fails on drift in either direction:

1. Variables read by production code but missing from ``.env.example``
   (operators can not discover required configuration).
2. Variables documented in ``.env.example`` but no longer referenced by
   any code path (stale documentation, security-leak risk for old SDK
   credentials).

This contract scans the production tree (``src/``, ``telegram_bot/``,
``mini_app/``, ``services/``, ``scripts/``) for:

- ``os.getenv("KEY"[, ...])``
- ``os.environ["KEY"]`` / ``os.environ.get("KEY"[, ...])``
- ``os.environ.setdefault("KEY", ...)``
- ``Field(..., validation_alias=AliasChoices(..., "KEY", ...))`` (Pydantic
  Settings pattern used in ``telegram_bot/config.py`` and friends)
- Bare ``AliasChoices("snake", "UPPER", ...)`` calls

It then compares the discovered set against keys parsed from
``.env.example``. Two YAML allowlists tame the long-tail noise:

- ``ALLOWLIST_NOT_IN_ENV_EXAMPLE`` — vars that are intentionally
  runtime-only (test fixtures, build-arg style, container-internal
  defaults) and must not be re-introduced into ``.env.example``.
- ``ALLOWLIST_NOT_IN_CODE`` — vars that ``.env.example`` documents but
  no longer have a Python reference (typically vars consumed by Compose,
  Dockerfile RUN, shell scripts, or third-party services that read the
  env directly without going through Python).

Drift in either direction without an explicit allowlist entry fails the
contract with a precise list of offending keys, an actionable remediation
hint, and a pointer at this docstring.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "src",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
)
EXCLUDE_PARTS: frozenset[str] = frozenset(
    {".venv", "node_modules", "build", "dist", "__pycache__", "frontend"}
)

ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


# ---------------------------------------------------------------------------
# Allowlists
# ---------------------------------------------------------------------------
#
# Both lists must stay short. Add an entry only with a comment explaining
# why the variable is intentionally not in the other side of the contract.

# Vars READ by Python code but intentionally NOT in .env.example.
# These are runtime-only / test-fixture / container-internal vars that
# operators should never set in their local .env.
ALLOWLIST_NOT_IN_ENV_EXAMPLE: dict[str, str] = {
    # --- Standard library / Python runtime -----------------------------------
    "PATH": "OS PATH; never an operator-set bot variable",
    "HOME": "OS HOME; never an operator-set bot variable",
    "USER": "OS USER; never an operator-set bot variable",
    "PWD": "OS PWD; never an operator-set bot variable",
    "PYTHONPATH": "Python interpreter path; managed by uv/Make, not .env.example",
    "PYTHONHASHSEED": "Python interpreter; not an operator setting",
    "PYTHONUNBUFFERED": "Container runtime flag; set in Dockerfile, not .env.example",
    "PYTHONDONTWRITEBYTECODE": "Container runtime flag; set in Dockerfile",
    "PYTHONIOENCODING": "Container runtime flag",
    "VIRTUAL_ENV": "uv/venv runtime indicator",
    "TZ": "Container TZ; set per-service in compose, not .env.example",
    "TERM": "Terminal capability detection",
    "CI": "GitHub Actions / pytest auto-detect",
    "GITHUB_ACTIONS": "GitHub Actions auto-detect",
    "GITHUB_WORKSPACE": "GitHub Actions auto-detect",
    "GITHUB_OUTPUT": "GitHub Actions output channel",
    "GITHUB_ENV": "GitHub Actions env channel",
    "GITHUB_EVENT_PATH": "GitHub Actions event payload path; CI-only",
    "GITHUB_STEP_SUMMARY": "GitHub Actions step summary channel",
    "RUNNER_OS": "GitHub Actions self-hosted runner detection",
    "RUNNER_TEMP": "GitHub Actions temp dir",
    "FORCE_COLOR": "Color output toggle for CLI tools",
    "NO_COLOR": "Color output toggle for CLI tools",
    # --- Test infrastructure (never set by operators) ------------------------
    "PYTEST_CURRENT_TEST": "Set by pytest at runtime; never an operator var",
    "PYTEST_XDIST_TESTRUNUID": "Set by pytest-xdist at runtime",
    "PYTEST_XDIST_WORKER": "Set by pytest-xdist at runtime",
    "PYTEST_XDIST_WORKER_COUNT": "Set by pytest-xdist at runtime",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "pytest internal",
    "PYTEST_ADDOPTS": "Make/CI knob, not bot config",
    "RUN_BENCHMARK_TESTS": "make test-benchmark gate (#1618); test-only flag",
    "RUN_CHAOS_TESTS": "Chaos suite gate; test-only flag",
    "RUN_E2E_TESTS": "E2E suite gate; test-only flag",
    "RUN_LOAD_TESTS": "Load suite gate; test-only flag",
    "PYTEST_INTEGRATION": "Integration-suite gate; test-only flag",
    # --- E2E test fixtures (read by tests/e2e harnesses, never by bot) -----
    "E2E_COLLECTION_NAME": "E2E harness fixture (tests/e2e); never an operator var",
    "E2E_JUDGE_API_KEY": "E2E LLM-judge harness fixture",
    "E2E_JUDGE_BASE_URL": "E2E LLM-judge harness fixture",
    "E2E_JUDGE_MODEL": "E2E LLM-judge harness fixture",
    "E2E_JUDGE_PROVIDER": "E2E LLM-judge harness fixture",
    "E2E_QDRANT_APARTMENT_COLLECTION": "E2E preflight check, sets which collection to use",
    "E2E_QDRANT_APARTMENT_VECTORS": "E2E preflight check fixture",
    "E2E_QDRANT_DOC_COLLECTION": "E2E preflight check fixture",
    "E2E_QDRANT_DOC_VECTORS": "E2E preflight check fixture",
    "E2E_QDRANT_MIN_APARTMENT_POINTS": "E2E preflight check fixture",
    "E2E_QDRANT_MIN_DOC_POINTS": "E2E preflight check fixture",
    "E2E_VALIDATE_LANGFUSE": "E2E preflight Langfuse-trace check toggle",
    "EVAL_MODEL": "tests/eval LLM model override; eval-suite only",
    "EVAL_SAMPLE_SIZE": "tests/eval sampling knob; eval-suite only",
    "JUDGE_MODEL": "LLM-judge runtime override; eval-suite only",
    "JUDGE_SAMPLE_RATE": "LLM-judge runtime sampling rate; eval-suite only",
    "REPO_BASE_BRANCH": "scripts/lib base-branch resolver; CI/dev tooling",
    "PR_GUARDRAILS_CHANGED_FILES": "PR guardrails test override; CI/dev tooling",
    # --- OpenTelemetry SDK internals (set per-service in Compose, not .env) -
    "UV_LINK_MODE": "uv-only; documented in CONTRIBUTING/Makefile",
    "UV_PROJECT_ENVIRONMENT": "uv-only; managed by uv",
    "UV_CACHE_DIR": "uv-only; managed by uv",
    "FORCE_REINSTALL": "Make-only knob; not a bot env",
    # --- LangChain / Langfuse internal toggles read at import time ----------
    "LANGCHAIN_TRACING_V2": "LangChain SDK auto-detect; not an operator setting",
    "LANGFUSE_DEBUG": "Langfuse SDK debug flag; documented in Langfuse docs",
    "LANGFUSE_OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "Langfuse SDK internal",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "OTel SDK; set per-service in compose, not .env.example",
    "OTEL_EXPORTER_OTLP_HEADERS": "OTel SDK; set per-service in compose",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "OTel SDK; set per-service in compose",
    "OTEL_RESOURCE_ATTRIBUTES": "OTel SDK; set per-service in compose",
    "OTEL_LOGS_EXPORTER": "OTel SDK env; set per-service in Compose",
    "OTEL_METRICS_EXPORTER": "OTel SDK env; set per-service in Compose",
    "OTEL_TRACES_EXPORTER": "OTel SDK env; set per-service in Compose",
    "OTEL_SDK_DISABLED": "OTel SDK kill-switch; tests set explicitly, prod via Compose",
    "OTEL_BSP_SCHEDULE_DELAY": "OTel BSP tuning (#1408); code default 30000, override-able per service",
    "OTEL_BSP_EXPORT_TIMEOUT": "OTel BSP tuning (#1408); code default 10000, override-able per service",
    "OTEL_EXPORTER_OTLP_TIMEOUT": "OTel exporter HTTP timeout (#1408); code default 10000ms, override-able per service",
    # --- Compose / docker-internal hostnames (never operator-set) -----------
    "HOSTNAME": "Container HOSTNAME; never operator-set",
    "DOCKER_HOST": "Docker CLI; not bot config",
    # --- Advanced tuning (#1268 follow-up): production-code env vars with
    # sane defaults that have not yet been documented in .env.example.
    # TODO(#1268): incrementally migrate these into .env.example sections
    # ("Retrieval tuning", "Voice agent", "Apartments", "Funnel/nurturing",
    # "Localization", "Ingestion paths", ...) so operators can discover them.
    # Each entry kept here so the contract test passes today but cannot
    # silently grow new entries without an explicit allowlist commit.
    "ACORN_MODE": "Advanced retrieval tuning (#590); doc TBD",
    "ACORN_ENABLED_SELECTIVITY_THRESHOLD": "Advanced retrieval tuning (#590); doc TBD",
    "ACORN_MAX_SELECTIVITY": "Advanced retrieval tuning (#590); doc TBD",
    "AGENT_CHECKPOINTER_TTL_MINUTES": "Agent state TTL; doc TBD",
    "AGENT_MAX_HISTORY_MESSAGES": "Agent history truncation knob; doc TBD",
    "APARTMENT_EXTRACTION_MODEL": "Apartment LLM extractor model override; doc TBD",
    "APARTMENTS_CSV": "Apartments dataset path; ingestion-only knob",
    "CESC_ENABLED": "Conversational entity-state cache toggle; doc TBD",
    "CESC_EXTRACTION_FREQUENCY": "CESC extraction frequency knob; doc TBD",
    "COLLECTION_NAME": "Generic collection alias used by helper scripts",
    "DATA_DIR": "Filesystem path; ingestion/test fixture",
    "DOCS_DIR": "Filesystem path; ingestion/test fixture",
    "LOGS_DIR": "Filesystem path; logging helper",
    "MANIFEST_DIR": "GDrive ingestion manifest dir; doc TBD",
    "DEFAULT_LOCALE": "i18n default locale; doc TBD",
    "SUPPORTED_LOCALES": "i18n supported locales list; doc TBD",
    "DOCLING_BACKEND": "Docling backend selector; doc TBD",
    "DOCLING_PROFILE": "Docling profile selector; doc TBD",
    "EXPERT_TOPICS_ENABLED": "Expert topics feature flag; doc TBD",
    "FRESHNESS_BOOST": "Score boosting toggle (#590); doc TBD",
    "FRESHNESS_FIELD": "Score boosting payload field; doc TBD",
    "FRESHNESS_SCALE_DAYS": "Score boosting decay scale; doc TBD",
    "FUNNEL_ROLLUP_CRON": "Funnel rollup cron; doc TBD",
    "GOOGLE_SERVICE_ACCOUNT_KEY": "GDrive ingestion credentials; doc TBD",
    "HISTORY_SAVE_DRAIN_TIMEOUT_S": "History flush tuning; doc TBD",
    "HISTORY_SAVE_MAX_CONCURRENCY": "History flush tuning; doc TBD",
    "MMR_ENABLED": "MMR diversity reranking toggle; doc TBD",
    "MMR_LAMBDA": "MMR diversity-vs-relevance balance; doc TBD",
    "NURTURING_DISPATCH_BATCH": "Nurturing batch size; doc TBD",
    "NURTURING_DISPATCH_CRON": "Nurturing dispatch cron; doc TBD",
    "NURTURING_DISPATCH_ENABLED": "Nurturing dispatch toggle; doc TBD",
    "NURTURING_ENABLED": "Master nurturing toggle; doc TBD",
    "NURTURING_INTERVAL_MINUTES": "Nurturing tick interval; doc TBD",
    "RUNTIME_EVENTS_DIR": "Runtime events JSONL dir; doc TBD",
    "RUNTIME_EVENTS_ENABLED": "Runtime events toggle; doc TBD",
    "RUNTIME_EVENTS_MAX_AGE_DAYS": "Runtime events retention; doc TBD",
    "SCORE_IMPROVEMENT_DELTA": "Lead score improvement delta; doc TBD",
    "SESSION_IDLE_TIMEOUT_MIN": "Session idle timeout; doc TBD",
    "SESSION_SUMMARY_MODEL": "Session summary LLM model override; doc TBD",
    "SESSION_SUMMARY_POLL_SEC": "Session summary worker poll cadence; doc TBD",
    "USER_CONTEXT_TTL": "User context cache TTL; doc TBD",
    "VOYAGE_EMBEDDING_DIM": "Voyage matryoshka dimension; legacy",
    "VOYAGE_MODEL_DOCS": "Voyage docs model override; legacy",
    "VOYAGE_MODEL_QUERIES": "Voyage queries model override; legacy",
}

# Vars in .env.example but NOT directly read by Python code. These are
# typically consumed by Compose YAML, Dockerfile RUN, init scripts, or
# third-party services that read the env directly.
ALLOWLIST_NOT_IN_CODE: dict[str, str] = {
    # --- Docker Compose top-level controls ----------------------------------
    "COMPOSE_FILE": "Read by docker compose CLI, not Python",
    "BGE_M3_ONNX_MODEL_HOST_DIR": "Consumed by Compose named-context interpolation (compose.yml) at build time; not read by Python",
    # --- Service credentials consumed by service entrypoints ---------------
    "REDIS_MAXMEMORY": "Read by redis container CMD args, not Python",
    "CLICKHOUSE_PASSWORD": "Read by clickhouse image entrypoint",
    "MINIO_ROOT_PASSWORD": "Read by minio image entrypoint",
    "POSTGRES_PASSWORD": "Read by postgres image entrypoint, not Python",
    "ELEVENLABS_API_KEY": "Read by voice agent SDK at runtime via env_file, not directly by Python",
    # --- Langfuse stack secrets (read by langfuse server image) ------------
    "NEXTAUTH_SECRET": "Read by Langfuse server image",
    "SALT": "Read by Langfuse server image",
    "ENCRYPTION_KEY": "Read by Langfuse server image",
    "LANGFUSE_DOCKER_HOST": "Container-network alias for langfuse; consumed by compose env_file",
    "LANGFUSE_REDIS_PASSWORD": (
        "Read by redis-langfuse / langfuse / langfuse-worker compose services "
        "(REDIS_AUTH + redis-server --requirepass); not consumed by any Python code"
    ),
    # --- OpenTelemetry SDK env consumed by instrumented service runtimes ----
    "OTEL_PROPAGATORS": (
        "Read by OpenTelemetry SDK from Compose service env; documented in "
        ".env.example as an operator override for tracecontext+baggage"
    ),
    # --- Misc ops vars -----------------------------------------------------
    "MLFLOW_TRACKING_URI": "Read by mlflow CLI tooling, not the bot",
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in EXCLUDE_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def _iter_string_args(call: ast.Call) -> list[str]:
    return [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _first_string_arg(call: ast.Call) -> str | None:
    """Return the first positional string arg, or ``None`` if absent.

    Used for ``os.getenv("KEY", "default")`` / ``os.environ.get("KEY", default)``
    where only the first arg names the env var; the second is a default value
    that should not be treated as a separate variable name.
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _is_attr_chain(call: ast.Call, *, root_name: str, leaf_attrs: tuple[str, ...]) -> bool:
    """Match calls like ``os.environ.get(...)`` or ``os.getenv(...)``.

    ``root_name`` is the leftmost ``Name`` token (e.g. ``"os"``).
    ``leaf_attrs`` is the chain of attribute names from the root to the call,
    e.g. ``("environ", "get")`` for ``os.environ.get(...)``.
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    chain: list[str] = []
    node: ast.AST = func
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    chain.reverse()
    return isinstance(node, ast.Name) and node.id == root_name and tuple(chain) == leaf_attrs


def _collect_env_keys_from_tree(tree: ast.Module) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(tree):
        # Subscript access: ``os.environ["KEY"]``
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            attr = node.value
            if (
                attr.attr == "environ"
                and isinstance(attr.value, ast.Name)
                and attr.value.id == "os"
            ):
                slice_node = node.slice
                if (
                    isinstance(slice_node, ast.Constant)
                    and isinstance(slice_node.value, str)
                    and ENV_KEY_PATTERN.match(slice_node.value)
                ):
                    keys.add(slice_node.value)
            continue

        if not isinstance(node, ast.Call):
            continue

        # os.getenv("KEY"[, default])  — only args[0] names the variable
        if _is_attr_chain(node, root_name="os", leaf_attrs=("getenv",)):
            value = _first_string_arg(node)
            if value is not None and ENV_KEY_PATTERN.match(value):
                keys.add(value)
            continue

        # os.environ.get / os.environ.setdefault / os.environ.pop — args[0] only
        if (
            _is_attr_chain(node, root_name="os", leaf_attrs=("environ", "get"))
            or _is_attr_chain(node, root_name="os", leaf_attrs=("environ", "setdefault"))
            or _is_attr_chain(node, root_name="os", leaf_attrs=("environ", "pop"))
        ):
            value = _first_string_arg(node)
            if value is not None and ENV_KEY_PATTERN.match(value):
                keys.add(value)
            continue

        # AliasChoices("snake", "UPPER", ...) (pydantic settings)
        target = node.func
        if isinstance(target, ast.Name) and target.id == "AliasChoices":
            for value in _iter_string_args(node):
                if ENV_KEY_PATTERN.match(value):
                    keys.add(value)

    return keys


def _scan_code() -> set[str]:
    """Return the set of env-var keys read by production code."""
    keys: set[str] = set()
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        keys |= _collect_env_keys_from_tree(tree)
    return keys


_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=")
_COMMENTED_KEY_LINE = re.compile(r"^#\s*([A-Z][A-Z0-9_]*)=")


def _parse_env_example(*, include_commented: bool = True) -> set[str]:
    """Parse ``.env.example`` and return the set of declared variable names.

    With ``include_commented=True`` (default), we also pick up variables
    documented as commented-out templates such as ``# QDRANT_API_KEY=``,
    because operators discover the variable via the comment itself.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    keys: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if (m := _KEY_LINE.match(line)) is not None or (
            include_commented and (m := _COMMENTED_KEY_LINE.match(line)) is not None
        ):
            keys.add(m.group(1))
    return keys


def _parse_env_file(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if (m := _KEY_LINE.match(line)) is not None:
            keys.add(m.group(1))
    return keys


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_env_vars_used_in_code_missing_from_env_example() -> None:
    """Every env var read by Python code must be in ``.env.example`` or allowlist."""
    code_keys = _scan_code()
    env_example_keys = _parse_env_example()
    allowlisted = set(ALLOWLIST_NOT_IN_ENV_EXAMPLE.keys())

    missing = code_keys - env_example_keys - allowlisted
    if missing:
        formatted = "\n".join(f"  - {key}" for key in sorted(missing))
        pytest.fail(
            "The following env vars are read by production code but missing from"
            " .env.example (and not in ALLOWLIST_NOT_IN_ENV_EXAMPLE):\n"
            f"{formatted}\n\n"
            "Remediation: either (a) add the variable to .env.example with a"
            " comment explaining its purpose, or (b) add it to"
            " ALLOWLIST_NOT_IN_ENV_EXAMPLE in"
            " tests/contract/test_env_example_completeness_contract.py with a"
            " short justification (runtime-only / test-only / container-internal)."
        )


def test_no_env_vars_in_env_example_unused_by_code() -> None:
    """Every var in ``.env.example`` must be read by code or live in allowlist."""
    code_keys = _scan_code()
    env_example_keys = _parse_env_example()
    allowlisted = set(ALLOWLIST_NOT_IN_CODE.keys())

    unused = env_example_keys - code_keys - allowlisted
    if unused:
        formatted = "\n".join(f"  - {key}" for key in sorted(unused))
        pytest.fail(
            "The following env vars are documented in .env.example but no"
            " Python code reads them, and they are not in ALLOWLIST_NOT_IN_CODE:\n"
            f"{formatted}\n\n"
            "Remediation: either (a) delete the obsolete entry from .env.example,"
            " or (b) add it to ALLOWLIST_NOT_IN_CODE in"
            " tests/contract/test_env_example_completeness_contract.py with a"
            " short note pointing at the non-Python consumer (Compose, Dockerfile,"
            " shell script, third-party service)."
        )


def test_env_example_is_split_into_sections() -> None:
    """``.env.example`` must be organised into at least 5 sectioned headers.

    Drift here means the file became a flat dump and operator discoverability
    suffered. The marker we look for is the canonical
    ``# ==============================================================================``
    block at the top of each section.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    section_markers = text.count("# " + "=" * 78)
    assert section_markers >= 10, (
        f"Expected at least 10 section header lines (5 sections × 2 lines each)"
        f" in .env.example; got {section_markers}. The file should be grouped"
        " into operator-friendly sections (Required, Database, LLM, Telegram,"
        " Voice, CRM, ...)."
    )


def test_allowlists_have_no_overlap_with_documented_keys() -> None:
    """Sanity check: allowlist entries must not double-count.

    A var in ALLOWLIST_NOT_IN_ENV_EXAMPLE that is also written into
    ``.env.example`` is contradictory configuration; same for the other
    direction. Catching this here protects future contributors from
    introducing silent contradictions.
    """
    env_example_keys = _parse_env_example()
    bogus_not_in_env = set(ALLOWLIST_NOT_IN_ENV_EXAMPLE.keys()) & env_example_keys
    assert not bogus_not_in_env, (
        "ALLOWLIST_NOT_IN_ENV_EXAMPLE entries also exist in .env.example:"
        f" {sorted(bogus_not_in_env)}. These contradict each other — pick one."
    )

    code_keys = _scan_code()
    bogus_not_in_code = set(ALLOWLIST_NOT_IN_CODE.keys()) & code_keys
    assert not bogus_not_in_code, (
        "ALLOWLIST_NOT_IN_CODE entries are actually read by Python code:"
        f" {sorted(bogus_not_in_code)}. Remove them from the allowlist;"
        " they belong in .env.example as documented variables."
    )


def test_langfuse_container_env_surface_is_documented_and_fixture_backed() -> None:
    """Containerized services, including bge-m3, use the Docker Langfuse host."""
    env_example_keys = _parse_env_example()
    ci_env_keys = _parse_env_file(REPO_ROOT / "tests/fixtures/compose.ci.env")

    required = {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_DOCKER_HOST"}
    assert required <= env_example_keys
    assert required <= ci_env_keys
