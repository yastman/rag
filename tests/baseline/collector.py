"""Collect metrics from Langfuse v3 API."""

import json
from datetime import datetime
from typing import Any

from langfuse import Langfuse


class LangfuseMetricsCollector:
    """Collect metrics from Langfuse v3 API.

    Uses Langfuse API endpoints:
    - GET /api/public/metrics/daily - aggregated daily usage and cost
    - GET /api/public/metrics (v2) - custom queries with dimensions

    Reference: https://langfuse.com/docs/metrics/features/metrics-api
    """

    def __init__(self, public_key: str, secret_key: str, host: str):
        """Initialize collector with Langfuse credentials.

        Args:
            public_key: Langfuse public key (pk-lf-...)
            secret_key: Langfuse secret key (sk-lf-...)
            host: Langfuse host URL (e.g., http://localhost:3001)
        """
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    def get_daily_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Get aggregated daily usage and cost metrics.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Optional filter by trace name
            limit: Max results (default 30)

        Returns:
            Dict with 'data' array containing daily metrics:
            - date, countTraces, countObservations, totalCost
            - usage: [{model, inputUsage, outputUsage, totalCost}]
        """
        kwargs = {
            "from_timestamp": from_ts.isoformat() + "Z",
            "to_timestamp": to_ts.isoformat() + "Z",
            "limit": limit,
        }
        if trace_name:
            kwargs["trace_name"] = trace_name

        return self.client.api.metrics_daily.get(**kwargs)

    def get_latency_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None,
    ) -> dict[str, Any]:
        """Get latency percentiles via v2 metrics API.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Optional filter by trace name

        Returns:
            Dict with latency p50, p95, cost, and count by model
        """
        filters = []
        if trace_name:
            filters.append(
                {
                    "field": "traceName",
                    "operator": "=",
                    "value": trace_name,
                }
            )

        query = {
            "view": "observations",
            "metrics": [
                {"measure": "latency", "aggregation": "p50"},
                {"measure": "latency", "aggregation": "p95"},
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"},
            ],
            "dimensions": [{"field": "providedModelName"}],
            "filters": filters,
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        return self.client.api.metrics_v_2.get(query=json.dumps(query))

    def get_trace_count(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str,
    ) -> int:
        """Count traces for a specific operation.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Name of trace to count

        Returns:
            Number of traces matching the name
        """
        query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [{"field": "name"}],
            "filters": [{"field": "name", "operator": "=", "value": trace_name}],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        result = self.client.api.metrics.metrics(query=json.dumps(query))

        if result.data:
            return int(result.data[0].get("count_count", 0))
        return 0

    def get_cache_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Get cache hit/miss metrics from trace metadata.

        Traces should have metadata.cache_hit = true/false

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            session_id: Optional session filter

        Returns:
            Dict with hits, misses, hit_rate
        """
        # Query for cache hits
        hits_query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [],
            "filters": [{"field": "metadata.cache_hit", "operator": "=", "value": "true"}],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        # Query for cache misses
        misses_query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [],
            "filters": [{"field": "metadata.cache_hit", "operator": "=", "value": "false"}],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        hits_result = self.client.api.metrics.metrics(query=json.dumps(hits_query))
        misses_result = self.client.api.metrics.metrics(query=json.dumps(misses_query))

        hits = int(hits_result.data[0].get("count_count", 0)) if hits_result.data else 0
        misses = int(misses_result.data[0].get("count_count", 0)) if misses_result.data else 0

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": hit_rate,
        }
