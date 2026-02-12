"""Collect metrics from Langfuse v3 API, Qdrant, and Redis."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import redis
from langfuse import Langfuse


@dataclass
class SessionMetrics:
    """Metrics computed from per-trace observation data."""

    trace_count: int = 0
    llm_calls: int = 0

    # Latency (ms) — computed from GENERATION observations
    llm_latency_p50_ms: float = 0.0
    llm_latency_p95_ms: float = 0.0

    # Cost
    total_cost_usd: float = 0.0
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0

    # Cache
    cache_hit_rate: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0


def _percentile(sorted_values: list[float], pct: int) -> float:
    """Compute percentile from pre-sorted values (linear interpolation)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (pct / 100) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


class LangfuseMetricsCollector:
    """Collect metrics from Langfuse v3 API.

    Uses per-trace observation data via:
    - api.trace.list(session_id=..., tags=...)
    - api.observations.get_many(trace_id=..., type="GENERATION")
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str,
        redis_url: str = "redis://localhost:6379",
        qdrant_url: str = "http://localhost:6333",
    ):
        """Initialize collector with Langfuse credentials.

        Args:
            public_key: Langfuse public key (pk-lf-...)
            secret_key: Langfuse secret key (sk-lf-...)
            host: Langfuse host URL (e.g., http://localhost:3001)
            redis_url: Redis connection URL for infrastructure metrics
            qdrant_url: Qdrant base URL for infrastructure metrics
        """
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        self.redis_url = redis_url
        self.qdrant_url = qdrant_url

    # ========== Per-Trace Session Metrics ==========

    def _fetch_all_traces(
        self,
        *,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list:
        """Fetch all traces matching filters, handling pagination."""
        all_traces: list = []
        page = 1
        while True:
            result = self.client.api.trace.list(
                session_id=session_id,
                tags=tags,
                limit=limit,
                page=page,
            )
            all_traces.extend(result.data)
            if not result.meta or not result.meta.next_page:
                break
            page = result.meta.next_page
        return all_traces

    def collect_session_metrics(
        self,
        *,
        session_id: str | None = None,
        tag: str | None = None,
    ) -> SessionMetrics:
        """Fetch traces + observations for a session/tag, compute metrics locally.

        Args:
            session_id: Filter by Langfuse session_id (for current CI run).
            tag: Filter by Langfuse tag (for baseline).

        Returns:
            SessionMetrics with aggregated observation-level data.

        Raises:
            ValueError: If neither session_id nor tag is provided.
        """
        if not session_id and not tag:
            msg = "At least one of session_id or tag must be provided"
            raise ValueError(msg)

        traces = self._fetch_all_traces(
            session_id=session_id,
            tags=[tag] if tag else None,
        )

        if not traces:
            return SessionMetrics()

        latencies_ms: list[float] = []
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        cache_hits = 0
        cache_misses = 0

        for trace in traces:
            # Cache from trace metadata
            cache_hit = (trace.metadata or {}).get("cache_hit")
            if cache_hit is True:
                cache_hits += 1
            elif cache_hit is False:
                cache_misses += 1

            for obs in self._fetch_all_observations(trace_id=trace.id):
                llm_calls += 1

                # Latency (skip if timestamps missing)
                if obs.start_time and obs.end_time:
                    delta = (obs.end_time - obs.start_time).total_seconds() * 1000
                    latencies_ms.append(delta)

                # Cost (None → 0)
                total_cost += obs.calculated_total_cost or 0.0

                # Tokens (None usage → 0)
                if obs.usage:
                    total_input_tokens += obs.usage.input or 0
                    total_output_tokens += obs.usage.output or 0

        # Compute percentiles
        p50 = 0.0
        p95 = 0.0
        if latencies_ms:
            sorted_lat = sorted(latencies_ms)
            p50 = _percentile(sorted_lat, 50)
            p95 = _percentile(sorted_lat, 95)

        cache_total = cache_hits + cache_misses
        cache_rate = cache_hits / cache_total if cache_total > 0 else 0.0

        return SessionMetrics(
            trace_count=len(traces),
            llm_calls=llm_calls,
            llm_latency_p50_ms=p50,
            llm_latency_p95_ms=p95,
            total_cost_usd=total_cost,
            llm_tokens_input=total_input_tokens,
            llm_tokens_output=total_output_tokens,
            cache_hit_rate=cache_rate,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )

    def _fetch_all_observations(self, *, trace_id: str, limit: int = 50) -> list:
        """Fetch all GENERATION observations for a trace, handling pagination."""
        observations: list = []
        page = 1
        while True:
            result = self.client.api.observations.get_many(
                trace_id=trace_id,
                type="GENERATION",
                page=page,
                limit=limit,
            )
            observations.extend(result.data)
            if not result.meta or not result.meta.next_page:
                break
            page = result.meta.next_page
        return observations

    def _update_trace_tags(self, *, trace_id: str, tags: list[str]) -> None:
        """Update trace tags via available SDK/public API surface.

        SDK v3.12 does not expose `api.trace.update`, so we fall back to a direct PATCH
        through the generated API client's authenticated HTTP transport.
        """
        trace_api = self.client.api.trace
        if hasattr(trace_api, "update"):
            trace_api.update(trace_id=trace_id, tags=tags)
            return

        response = trace_api._client_wrapper.httpx_client.request(  # type: ignore[attr-defined]
            f"api/public/traces/{trace_id}",
            method="PATCH",
            json={"tags": tags},
        )
        if not 200 <= response.status_code < 300:
            msg = f"Failed to update trace tags for {trace_id}: {response.status_code}"
            raise RuntimeError(msg)

    def tag_session_traces(self, *, session_id: str, tag: str) -> int:
        """Apply a tag to all traces in a session.

        Returns:
            Number of traces that were updated with the tag.
        """
        traces = self._fetch_all_traces(session_id=session_id)
        tagged = 0
        for trace in traces:
            existing_tags = list(trace.tags or [])
            if tag in existing_tags:
                continue
            existing_tags.append(tag)
            self._update_trace_tags(trace_id=trace.id, tags=existing_tags)
            tagged += 1
        return tagged

    # ========== Infrastructure Metrics ==========

    async def collect_infrastructure_metrics(self) -> dict[str, Any]:
        """Collect Redis INFO + Qdrant /metrics for baseline.

        Returns:
            Dict with redis and qdrant metrics, plus timestamp.
        """
        metrics: dict[str, Any] = {"timestamp": datetime.now().isoformat()}

        # Redis INFO stats
        if self.redis_url:
            try:
                r = redis.from_url(self.redis_url, decode_responses=True)
                info_memory = r.info("memory")
                info_stats = r.info("stats")
                r.close()

                hits = info_stats.get("keyspace_hits", 0)
                misses = info_stats.get("keyspace_misses", 0)
                total = hits + misses

                metrics["redis"] = {
                    "keyspace_hits": hits,
                    "keyspace_misses": misses,
                    "hit_rate": round(hits / total * 100, 2) if total > 0 else 0,
                    "evicted_keys": info_stats.get("evicted_keys", 0),
                    "used_memory_mb": info_memory.get("used_memory", 0) / (1024 * 1024),
                    "used_memory_peak_mb": info_memory.get("used_memory_peak", 0) / (1024 * 1024),
                    "maxmemory_mb": info_memory.get("maxmemory", 0) / (1024 * 1024),
                }
            except Exception as e:
                metrics["redis"] = {"error": str(e)}

        # Qdrant /metrics endpoint
        if self.qdrant_url:
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(f"{self.qdrant_url}/metrics", timeout=5.0)
                    metrics["qdrant_raw"] = resp.text[:2000]
                except Exception as e:
                    metrics["qdrant_error"] = str(e)

        return metrics

    @staticmethod
    def get_qdrant_metrics(qdrant_url: str = "http://localhost:6333") -> dict[str, Any]:
        """Scrape Qdrant Prometheus /metrics endpoint.

        Args:
            qdrant_url: Qdrant base URL

        Returns:
            Dict with key Qdrant metrics
        """
        try:
            resp = httpx.get(f"{qdrant_url}/metrics", timeout=5.0)
            resp.raise_for_status()
            text = resp.text

            def extract(name: str) -> float:
                match = re.search(rf"^{name}\s+([\d.e+-]+)", text, re.MULTILINE)
                return float(match.group(1)) if match else 0.0

            return {
                "grpc_responses_total": extract("app_info_grpc_responses_total"),
                "rest_responses_total": extract("app_info_rest_responses_total"),
                "collections_total": extract("app_info_collections_total"),
                "points_total": extract("app_info_points_total"),
                "available": True,
            }
        except Exception:
            return {"available": False}

    @staticmethod
    def get_redis_metrics(
        redis_url: str = "redis://localhost:6379",
    ) -> dict[str, Any]:
        """Collect Redis INFO memory and stats.

        Args:
            redis_url: Redis connection URL

        Returns:
            Dict with memory usage, evictions, hit/miss stats
        """
        try:
            r = redis.from_url(redis_url, decode_responses=True)
            info_memory = r.info("memory")
            info_stats = r.info("stats")
            r.close()

            return {
                "used_memory_mb": info_memory.get("used_memory", 0) / (1024 * 1024),
                "used_memory_peak_mb": info_memory.get("used_memory_peak", 0) / (1024 * 1024),
                "maxmemory_mb": info_memory.get("maxmemory", 0) / (1024 * 1024),
                "evicted_keys": info_stats.get("evicted_keys", 0),
                "keyspace_hits": info_stats.get("keyspace_hits", 0),
                "keyspace_misses": info_stats.get("keyspace_misses", 0),
                "available": True,
            }
        except Exception:
            return {"available": False}
