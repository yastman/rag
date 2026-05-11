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

SCENARIO_CONTRACTS = {
    "text_rag": {
        "root_names": ["telegram-rag-query", "telegram-message"],
        "required_spans": {"node-classify"},
        "required_scores": set(SCORE_NAMES),
    },
    "apartment": {
        "root_names": ["telegram-message"],
        "required_spans": {"node-apartment-search", "node-respond"},
        "required_scores": set(SCORE_NAMES),
    },
    "fallback": {
        "root_names": ["telegram-message"],
        "required_spans": {"node-fallback", "node-respond"},
        "required_scores": set(SCORE_NAMES),
    },
    "voice_note": {
        "root_names": ["telegram-message"],
        "required_spans": {"node-voice-transcribe", "node-classify", "node-respond"},
        "required_scores": set(SCORE_NAMES),
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
    required_spans: set[str] = set(contract["required_spans"])

    if not _langfuse_is_configured():
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_spans),
            missing_scores=set(required_scores),
            error="Langfuse keys are not configured (LANGFUSE_PUBLIC_KEY/SECRET_KEY).",
        )

    # Use scenario root names when the caller has not overridden trace_name.
    effective_trace_name = trace_name
    if trace_name == DEFAULT_TRACE_NAME and contract["root_names"]:
        effective_trace_name = contract["root_names"]

    trace_id = wait_for_trace(
        started_at=started_at,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        trace_name=effective_trace_name,
        tags=tags,
    )
    if not trace_id:
        return TraceValidationResult(
            ok=False,
            trace_id=None,
            missing_spans=set(required_spans),
            missing_scores=set(required_scores),
            error="No matching trace found in Langfuse within timeout.",
        )

    langfuse = Langfuse()
    trace = langfuse.api.trace.get(trace_id)

    span_names = {obs.name for obs in trace.observations}
    scores = {s.name: getattr(s, "value", None) for s in trace.scores}
    score_names = set(scores.keys())

    # Base span misses from the scenario contract.
    missing_spans = set(required_spans - span_names)

    # Root observation input/output checks.
    root_names = set(contract["root_names"])
    root_obs = None
    for obs in trace.observations:
        if getattr(obs, "name", None) in root_names:
            root_obs = obs
            break

    if root_obs is not None:
        root_input = getattr(root_obs, "input", None) or {}
        if not isinstance(root_input, dict) or root_input.get("query_hash") is None:
            missing_spans.add("root_input")

        root_output = getattr(root_obs, "output", None) or {}
        if not isinstance(root_output, dict) or root_output.get("answer_hash") is None:
            missing_spans.add("root_output")
    else:
        # No root observation found; report the primary expected root name.
        missing_spans.add(contract["root_names"][0])

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
        required_spans |= {"node-cache-check"}

    if not is_chitchat and semantic_hit is False:
        # Retrieval path: cache miss → retrieve → grade
        required_spans |= {"node-retrieve", "node-grade"}

        if rerank_applied is True:
            required_spans |= {"node-rerank"}

        if (llm_used is True) and (no_results is False) and ((results_count or 0) > 0):
            # Generation path: generate → cache-store → respond
            required_spans |= {"node-generate", "node-cache-store", "node-respond"}

    # Recompute span misses after branch-aware additions.
    missing_spans |= set(required_spans - span_names)
    missing_scores = set(required_scores - score_names)

    return TraceValidationResult(
        ok=(not missing_spans and not missing_scores),
        trace_id=trace_id,
        missing_spans=missing_spans,
        missing_scores=missing_scores,
    )
