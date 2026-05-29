"""OTEL Resource attributes contract (#2227 / Epic Q).

Pre-#2227 every Langfuse trace carried only ``service.name`` (via
``OTEL_SERVICE_NAME``). It had no ``service.version`` (so Langfuse UI
"Aggregate by version" / release-regression dashboards were empty), no
``deployment.environment`` (OTEL semantic attribute, distinct from the
Langfuse-specific ``environment``), and no ``service.namespace`` (cannot
group bot+rag-api+bge-m3 as one logical app).

``tests/contract/test_env_example_completeness_contract.py`` even claimed
``OTEL_RESOURCE_ATTRIBUTES`` was "set per-service in compose", but a grep of
``compose*.yml`` returned zero hits — contract promise vs reality drift.

SDK-native fix (two complementary mechanisms):

1. ``Langfuse(release=...)`` — the Langfuse-native release tag that powers
   the "Aggregate by version" dashboard. Resolved from ``LANGFUSE_RELEASE``
   env, falling back to the installed package version (mirrors the existing
   ``src/observability_sentry.py::_resolve_release`` pattern).

2. ``OTEL_RESOURCE_ATTRIBUTES`` env — the OTEL SDK reads this natively via
   ``OTELResourceDetector`` inside ``Resource.create()``. We *merge*
   ``service.version`` / ``service.namespace`` / ``deployment.environment``
   into whatever the operator already set, so a compose-level override is
   preserved.

These tests pin both helpers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_langfuse_singleton():
    import src.observability as observability

    observability._reset_langfuse_client_for_tests()
    yield
    observability._reset_langfuse_client_for_tests()


def _parse_resource_attrs(raw: str) -> dict[str, str]:
    """Parse an ``OTEL_RESOURCE_ATTRIBUTES`` string into a dict."""
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, val = pair.split("=", 1)
        out[key.strip()] = val.strip()
    return out


class TestResolveRelease:
    def test_returns_langfuse_release_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.observability as observability

        monkeypatch.setenv("LANGFUSE_RELEASE", "v2.14.0-abc1234")
        assert observability._resolve_release() == "v2.14.0-abc1234"

    def test_falls_back_to_package_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.observability as observability

        monkeypatch.delenv("LANGFUSE_RELEASE", raising=False)
        release = observability._resolve_release()
        # Either a package version string or the explicit unknown sentinel,
        # never None / empty (so Langfuse always has a release to group by).
        assert isinstance(release, str)
        assert release

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.observability as observability

        monkeypatch.setenv("LANGFUSE_RELEASE", "  v1.2.3  ")
        assert observability._resolve_release() == "v1.2.3"


class TestEnsureOtelResourceAttributes:
    def test_sets_service_namespace_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        import src.observability as observability

        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
        observability._ensure_otel_resource_attributes()
        attrs = _parse_resource_attrs(os.environ["OTEL_RESOURCE_ATTRIBUTES"])
        assert attrs.get("service.namespace") == "rag"

    def test_sets_service_version_from_release(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        import src.observability as observability

        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
        monkeypatch.setenv("LANGFUSE_RELEASE", "v9.9.9")
        observability._ensure_otel_resource_attributes()
        attrs = _parse_resource_attrs(os.environ["OTEL_RESOURCE_ATTRIBUTES"])
        assert attrs.get("service.version") == "v9.9.9"

    def test_sets_deployment_environment_from_tracing_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        import src.observability as observability

        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
        monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "production")
        observability._ensure_otel_resource_attributes()
        attrs = _parse_resource_attrs(os.environ["OTEL_RESOURCE_ATTRIBUTES"])
        assert attrs.get("deployment.environment") == "production"

    def test_preserves_operator_set_attributes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A compose-level OTEL_RESOURCE_ATTRIBUTES must NOT be clobbered."""
        import os

        import src.observability as observability

        monkeypatch.setenv(
            "OTEL_RESOURCE_ATTRIBUTES",
            "service.version=operator-set,host.name=vps-1,custom.tag=keep",
        )
        observability._ensure_otel_resource_attributes()
        attrs = _parse_resource_attrs(os.environ["OTEL_RESOURCE_ATTRIBUTES"])
        # Operator-set keys win; our defaults only fill the gaps.
        assert attrs["service.version"] == "operator-set"
        assert attrs["host.name"] == "vps-1"
        assert attrs["custom.tag"] == "keep"
        # service.namespace was absent -> we fill it.
        assert attrs["service.namespace"] == "rag"

    def test_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        import src.observability as observability

        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
        observability._ensure_otel_resource_attributes()
        first = os.environ["OTEL_RESOURCE_ATTRIBUTES"]
        observability._ensure_otel_resource_attributes()
        second = os.environ["OTEL_RESOURCE_ATTRIBUTES"]
        assert _parse_resource_attrs(first) == _parse_resource_attrs(second)

    def test_empty_compose_value_is_overridden_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """compose may emit ``service.version=`` when ${GIT_SHA} is unset.
        An empty value must be treated as absent so the package-version
        fallback fills it (#2227)."""
        import os

        import src.observability as observability

        monkeypatch.setenv(
            "OTEL_RESOURCE_ATTRIBUTES",
            "service.version=,deployment.environment=,service.namespace=rag",
        )
        monkeypatch.delenv("LANGFUSE_RELEASE", raising=False)
        observability._ensure_otel_resource_attributes()
        attrs = _parse_resource_attrs(os.environ["OTEL_RESOURCE_ATTRIBUTES"])
        assert attrs["service.version"]


class TestInitializeLangfusePassesRelease:
    def test_release_forwarded_to_langfuse_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.observability as observability

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.setenv("LANGFUSE_RELEASE", "v3.3.3")

        captured: dict = {}

        def _fake_langfuse(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with (
            patch.object(observability, "Langfuse", side_effect=_fake_langfuse),
            patch.object(observability, "sync_langfuse_model_definitions", return_value=0),
            patch("src.observability_otel.activate_otel_instrumentations"),
        ):
            observability.initialize_langfuse(force=True)

        assert captured.get("release") == "v3.3.3"

    def test_resource_attributes_set_during_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        import src.observability as observability

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

        with (
            patch.object(observability, "Langfuse", return_value=MagicMock()),
            patch.object(observability, "sync_langfuse_model_definitions", return_value=0),
            patch("src.observability_otel.activate_otel_instrumentations"),
        ):
            observability.initialize_langfuse(force=True)

        assert "service.namespace" in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
