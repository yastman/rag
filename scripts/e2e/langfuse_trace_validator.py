"""Langfuse trace validation for Telethon E2E runs.

Used by `scripts/e2e/runner.py` when `E2E_VALIDATE_LANGFUSE=1`.
Validation is done via Langfuse SDK v3 API client (Langfuse().api.trace.list/get).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

from langfuse import Langfuse


DEFAULT_TRACE_NAME = "telegram-rag-query"
DEFAULT_TAGS = ["telegram", "rag"]

SCORE_NAMES = {
    "query_type",
    "latency_total_ms",
    "semantic_cache_hit",
    "embeddings_cache_hit",
    "search_cache_hit",
    "rerank_applied",
    "rerank_cache_hit",
    "results_count",
    "no_results",
    "llm_used",
}

# Observation alias groups: canonical name -> set of acceptable aliases.
# Any alias present in the trace satisfies the requirement for the canonical name.
OBSERVATION_ALIAS_GROUPS = {
    "node-cache-check": {"node-cache-check", "cache-check"},
}

SCENARIO_CONTRACTS = {
    "text_rag": {
        "trace_names": ["telegram-message"],
        "tags": ["telegram"],
        "required_observations": {"telegram-rag-query", "telegram-rag-supervisor"},
        "required_scores": set(SCORE_NAMES),
    },
    "apartment": {
        "trace_names": ["telegram-message"],
        "tags": ["telegram"],
        "required_observations": {"client-direct-pipeline"},
        "required_scores": set(SCORE_NAMES),
    },
    "fallback": {
        "trace_names": ["telegram-message"],
        "tags": ["telegram"],
        "required_observations": set(),
        "required_scores": set(SCORE_NAMES),
    },
    "voice_note": {
        "trace_names": ["telegram-rag-voice", "telegram-message"],
        "tags": ["telegram", "voice"],
        "required_observations": {"telegram-rag-voice", "transcribe"},
        "required_scores": set(SCORE_NAMES) | {"input_type", "voice_duration_s"},
    },
}


@dataclass(frozen=True)
class TraceValidationResult:
    ok: bool
    trace_id: str | None
    missing_spans: set[str]
    missing_scores: set[str]
    error: str | None = None


@dataclass(frozen=True)
class LiteLLMRouteProof:
    """Alias-to-provider model mapping proof from LiteLLM /model/info."""

    alias: str
    route_model: str | None
    info_url: str
    source: str


def _langfuse_is_configured() -> bool:
    # Langfuse SDK can be configured via env. If keys are missing, validation is meaningless.
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def is_validation_enabled() -> bool:
    """True when E2E should validate Langfuse traces."""
    return os.getenv("E2E_VALIDATE_LANGFUSE", "0").lower() in {"1", "true", "yes"}


def probe_litellm_route(
    *, base_url: str, model_alias: str, timeout_s: float = 2.0
) -> LiteLLMRouteProof | None:
    """Best-effort local probe for LiteLLM route mapping.

    Returns None when probing is not possible/safe (for example non-local URL).
    """
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1"}:
        return None

    base = base_url.rstrip("/").removesuffix("/v1")
    info_url = f"{base}/model/info"

    request = urllib.request.Request(info_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # nosec B310
            raw_payload = response.read().decode("utf-8")
    except Exception:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return LiteLLMRouteProof(
            alias=model_alias,
            route_model=None,
            info_url=info_url,
            source="local-probe-invalid-json",
        )

    model_list = payload.get("data") if isinstance(payload, dict) else None
    route_model: str | None = None
    if isinstance(model_list, list):
        for item in model_list:
            if not isinstance(item, dict):
                continue
            if item.get("model_name") == model_alias:
                params = item.get("litellm_params") or {}
                if isinstance(params, dict):
                    route_model = params.get("model")
                break

    return LiteLLMRouteProof(
        alias=model_alias,
        route_model=route_model,
        info_url=info_url,
        source="local-probe",
    )


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) >= 0.5
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "y"}:
            return True
        if lower in {"0", "false", "no", "n"}:
            return False
    return None


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _resolve_missing_observations(
    required_observations: set[str], span_names: set[str]
) -> set[str]:
    """Return required observations not satisfied by any present span name.

    Supports alias groups: if a required observation has aliases defined in
    :data:`OBSERVATION_ALIAS_GROUPS`, any alias present in ``span_names``
    satisfies the requirement for the canonical name.
    """
    missing: set[str] = set()
    for req in required_observations:
        aliases = OBSERVATION_ALIAS_GROUPS.get(req, {req})
        if not (aliases & span_names):
            missing.add(req)
    return missing


def wait_for_trace(
    *,
    started_at: datetime,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.5,
    trace_name: str | list[str] = DEFAULT_TRACE_NAME,
    tags: list[str] | None = DEFAULT_TAGS,
) -> str | None:
    """Poll Langfuse until a recent trace exists, returning trace_id.

    Supports multiple trace names to accommodate different scenario root names
    while preserving backward compatibility with a single string.
    """
    if not _langfuse_is_configured():
        return None

    langfuse = Langfuse()
    deadline = time.time() + timeout_s
    trace_names = [trace_name] if isinstance(trace_name, str) else trace_name

    while time.time() < deadline:
        for name in trace_names:
            traces_page = langfuse.api.trace.list(
                name=name,
                tags=tags,
                from_timestamp=started_at - timedelta(seconds=5),
                order_by="timestamp.desc",
                limit=5,
            )
            if traces_page.data:
                return traces_page.data[0].id

        time.sleep(poll_interval_s)

    return None


def validate_latest_trace(
    *,
    started_at: datetime,
    should_skip_rag: bool,
    is_command: bool,
    timeout_s: float = 15.0,
    poll_interval_s: float = 0.5,
    trace_name: str | list[str] = DEFAULT_TRACE_NAME,
    tags: list[str] | None = DEFAULT_TAGS,
    scenario_kind: str = "text_rag",
) -> TraceValidationResult:
    """Validate that the latest trace contains required spans/scores."""
    if is_command:
        # Commands are handled by separate handlers, not the RAG pipeline entrypoint.
        return TraceValidationResult(
            ok=True,
            trace_id=None,
            missing_spans=set(),
            missing_scores=set(),
        )

    contract = SCENARIO_CONTRACTS.get(scenario_kind, SCENARIO_CONTRACTS["text_rag"])

    # Base contract from scenario; branch-aware RAG expectations are additive.
    required_scores: set[str] = set(contract["required_scores"])
    required_observations: set[str] = set(contract["required_observations"])

    if not _langfuse_is_configured():
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_observations),
            missing_scores=set(required_scores),
            error="Langfuse keys are not configured (LANGFUSE_PUBLIC_KEY/SECRET_KEY).",
        )

    # Use scenario trace names and tags when the caller has not overridden them.
    effective_trace_name = trace_name
    if trace_name == DEFAULT_TRACE_NAME and contract.get("trace_names"):
        effective_trace_name = contract["trace_names"]

    effective_tags = tags
    if tags == DEFAULT_TAGS and contract.get("tags"):
        effective_tags = contract["tags"]

    trace_id = wait_for_trace(
        started_at=started_at,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        trace_name=effective_trace_name,
        tags=effective_tags,
    )
    if not trace_id:
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_observations),
            missing_scores=set(required_scores),
            error="No matching trace found in Langfuse within timeout.",
        )

    langfuse = Langfuse()
    trace = langfuse.api.trace.get(trace_id)

    span_names = {obs.name for obs in trace.observations}
    scores = {s.name: getattr(s, "value", None) for s in trace.scores}
    score_names = set(scores.keys())

    # Base observation misses from the scenario contract.
    missing_spans = _resolve_missing_observations(required_observations, span_names)

    # Root trace input/output checks (trace-level, not observation-level).
    trace_input = getattr(trace, "input", None) or {}
    trace_output = getattr(trace, "output", None) or {}

    if not isinstance(trace_input, dict) or trace_input.get("query_hash") is None:
        missing_spans.add("root_input")

    if not isinstance(trace_output, dict) or trace_output.get("answer_hash") is None:
        missing_spans.add("root_output")

    # Determine branch from scores, falling back to scenario hints when scores are missing.
    query_type = _as_float(scores.get("query_type"))
    semantic_hit = _as_bool(scores.get("semantic_cache_hit"))
    llm_used = _as_bool(scores.get("llm_used"))
    results_count = _as_float(scores.get("results_count"))
    no_results = _as_bool(scores.get("no_results"))
    rerank_applied = _as_bool(scores.get("rerank_applied"))

    # If query_type missing, infer CHITCHAT from scenario hint.
    is_chitchat = (query_type == 0.0) if query_type is not None else bool(should_skip_rag)

    if not is_chitchat:
        required_observations |= {"node-cache-check"}

    if not is_chitchat and semantic_hit is False:
        # Retrieval path: cache miss → retrieve → grade
        required_observations |= {"node-retrieve", "node-grade"}

        if rerank_applied is True:
            required_observations |= {"node-rerank"}

        if (llm_used is True) and (no_results is False) and ((results_count or 0) > 0):
            # Generation path: generate → cache-store → respond
            required_observations |= {"node-generate", "node-cache-store", "node-respond"}

    # Recompute observation misses after branch-aware additions.
    missing_spans |= _resolve_missing_observations(required_observations, span_names)
    missing_scores = set(required_scores - score_names)

    return TraceValidationResult(
        ok=(not missing_spans and not missing_scores),
        trace_id=trace_id,
        missing_spans=missing_spans,
        missing_scores=missing_scores,
    )
