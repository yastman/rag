"""Tests for health endpoint registry."""

from __future__ import annotations

from src.observability.health import HEALTH_CHECKS_NON_HTTP, HEALTH_ENDPOINTS


class TestHealthEndpoints:
    def test_health_endpoints_dict_has_critical_services(self) -> None:
        critical = {"rag-api", "bge-m3", "litellm", "qdrant", "langfuse"}
        assert critical.issubset(set(HEALTH_ENDPOINTS.keys()))

    def test_health_endpoint_urls_are_valid(self) -> None:
        for service, url in HEALTH_ENDPOINTS.items():
            assert url.startswith("http"), f"URL for {service} does not start with 'http': {url}"


class TestNonHTTPChecks:
    def test_non_http_checks_exist(self) -> None:
        assert "redis" in HEALTH_CHECKS_NON_HTTP
        assert "postgres" in HEALTH_CHECKS_NON_HTTP
        assert "bot" in HEALTH_CHECKS_NON_HTTP
