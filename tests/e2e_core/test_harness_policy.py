"""Hermetic policy tests for the #3414 live harness.

No services are contacted here: these tests pin the run-namespace contract,
the local-endpoint guard, the required-mode (never-skip) policy, the
report-artifact opt-in, the deterministic provider adapters, and the
no-fake-SDK guarantee.
"""

import json
import sys
from unittest.mock import MagicMock

import pytest

from tests.e2e_core.live_harness import (
    DeterministicSTT,
    DeterministicTelegramTransport,
    LiveE2EEnv,
    RunNamespace,
    compose_project_name,
    guard_service_skip,
    no_fake_sdk_modules,
    required_mode,
    validate_report_artifact,
    write_case_artifact,
)
from tests.e2e_core.qdrant_helpers import HarnessSafetyError


# ---------------------------------------------------------------------------
# RunNamespace — one run ID, per-worker UUID resources, isolated compose project
# ---------------------------------------------------------------------------


class TestRunNamespace:
    def test_resolve_generates_twelve_hex_run_id_by_default(self, monkeypatch):
        monkeypatch.delenv("E2E_RUN_ID", raising=False)
        ns = RunNamespace.resolve(worker="main")
        assert len(ns.run_id) == 12
        int(ns.run_id, 16)

    def test_resolve_honors_explicit_run_id(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "0f1e2d3c4b5a")
        ns = RunNamespace.resolve(worker="main")
        assert ns.run_id == "0f1e2d3c4b5a"

    def test_compose_project_is_bound_to_the_run(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "0f1e2d3c4b5a")
        ns = RunNamespace.resolve(worker="main")
        assert ns.compose_project == "rag-e2e-0f1e2d3c4b5a"

    def test_compose_project_name_helper(self):
        assert compose_project_name("0f1e2d3c4b5a") == "rag-e2e-0f1e2d3c4b5a"

    def test_two_xdist_workers_get_disjoint_resource_names(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "0f1e2d3c4b5a")
        gw0 = RunNamespace.resolve(worker="gw0")
        gw1 = RunNamespace.resolve(worker="gw1")
        assert gw0.qdrant_collection != gw1.qdrant_collection
        assert gw0.redis_prefix != gw1.redis_prefix
        assert gw0.redis_db != gw1.redis_db
        assert gw0.postgres_schema != gw1.postgres_schema

    def test_worker_resources_are_namespaced_under_the_run(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "0f1e2d3c4b5a")
        ns = RunNamespace.resolve(worker="gw0")
        assert ns.qdrant_collection.startswith("rag_e2e_0f1e2d3c4b5a_gw0_")
        assert ns.redis_prefix.startswith("rag_e2e:0f1e2d3c4b5a:gw0:")
        assert ns.postgres_schema.startswith("rag_e2e_0f1e2d3c4b5a_gw0")

    def test_redis_db_mapping_is_deterministic_and_small_workers_disjoint(self):
        dbs = [RunNamespace.redis_db_for_worker(w) for w in ("main", "gw0", "gw1", "gw2")]
        assert dbs[0] == 1
        assert len(set(dbs)) == len(dbs)
        for db in dbs:
            assert 1 <= db <= 15  # default Redis has 16 databases (0..15)

    def test_postgres_schema_is_identifier_safe(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "0f1e2d3c4b5a")
        ns = RunNamespace.resolve(worker="gw1")
        assert ns.postgres_schema == "rag_e2e_0f1e2d3c4b5a_gw1"
        assert all(ch.isalnum() or ch == "_" for ch in ns.postgres_schema)

    def test_invalid_explicit_run_id_is_rejected(self, monkeypatch):
        monkeypatch.setenv("E2E_RUN_ID", "not-a-run-id")
        with pytest.raises(HarnessSafetyError):
            RunNamespace.resolve(worker="main")


# ---------------------------------------------------------------------------
# Local-endpoint guard — production-shaped endpoints are rejected
# ---------------------------------------------------------------------------


class TestLocalEndpointGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:6333",
            "http://localhost:8000",
            "http://[::1]:6333",
            "redis://:secret@127.0.0.1:6379/2",
            "redis://localhost:6379/0",
            "postgresql://postgres:pw@127.0.0.1:5432/realestate",
            "postgresql://postgres:pw@localhost:5432/realestate",
        ],
    )
    def test_loopback_endpoints_accepted(self, url):
        LiveE2EEnv.assert_safe_local_url(url, label="probe")

    @pytest.mark.parametrize(
        "url",
        [
            "https://qdrant.production.example.com:6333",
            "http://10.1.2.3:6333",
            "http://192.168.0.10:8000",
            "redis://:secret@redis.internal:6379/0",
            "postgresql://postgres:pw@db.production.example.com:5432/realestate",
        ],
    )
    def test_remote_endpoints_rejected(self, url):
        with pytest.raises(HarnessSafetyError):
            LiveE2EEnv.assert_safe_local_url(url, label="probe")

    def test_env_construction_rejects_remote_endpoints(self, monkeypatch):
        monkeypatch.setenv("QDRANT_URL", "https://qdrant.production.example.com")
        monkeypatch.delenv("E2E_HARNESS_ALLOW_REMOTE", raising=False)
        with pytest.raises(HarnessSafetyError):
            LiveE2EEnv.from_env()

    def test_explicit_escape_hatch_allows_remote(self, monkeypatch):
        monkeypatch.setenv("QDRANT_URL", "https://qdrant.production.example.com")
        monkeypatch.setenv("BGE_M3_URL", "http://127.0.0.1:8000")
        monkeypatch.setenv("E2E_HARNESS_ALLOW_REMOTE", "1")
        env = LiveE2EEnv.from_env()
        assert env.qdrant_url == "https://qdrant.production.example.com"


# ---------------------------------------------------------------------------
# Required mode — service problems fail, they never skip
# ---------------------------------------------------------------------------


class TestRequiredModePolicy:
    def test_required_mode_off_by_default(self, monkeypatch):
        monkeypatch.delenv("E2E_HARNESS_REQUIRED", raising=False)
        monkeypatch.delenv("E2E_CORE_STRICT", raising=False)
        assert required_mode() is False

    def test_required_mode_on(self, monkeypatch):
        monkeypatch.setenv("E2E_HARNESS_REQUIRED", "1")
        assert required_mode() is True

    def test_legacy_strict_flag_maps_to_required(self, monkeypatch):
        monkeypatch.delenv("E2E_HARNESS_REQUIRED", raising=False)
        monkeypatch.setenv("E2E_CORE_STRICT", "1")
        assert required_mode() is True

    def test_guard_fails_in_required_mode(self, monkeypatch):
        monkeypatch.setenv("E2E_HARNESS_REQUIRED", "1")
        with pytest.raises(pytest.fail.Exception):
            guard_service_skip("Qdrant unavailable")

    def test_guard_skips_in_optional_mode(self, monkeypatch):
        monkeypatch.delenv("E2E_HARNESS_REQUIRED", raising=False)
        monkeypatch.delenv("E2E_CORE_STRICT", raising=False)
        with pytest.raises(pytest.skip.Exception):
            guard_service_skip("Qdrant unavailable")

    def test_required_mode_env_propagates_to_live_env(self, monkeypatch):
        monkeypatch.setenv("E2E_HARNESS_REQUIRED", "1")
        monkeypatch.setenv("BGE_M3_URL", "http://127.0.0.1:8000")
        env = LiveE2EEnv.from_env()
        assert env.required is True


# ---------------------------------------------------------------------------
# Report artifacts are opt-in (default: nothing is written)
# ---------------------------------------------------------------------------


class TestReportArtifactsOptIn:
    def _case(self):
        from tests.e2e_core.live_harness import GoldenCase

        return GoldenCase(
            id="case_x",
            query="q",
            must_retrieve=[],
            must_contain=[],
            must_not_contain=[],
            answer_policy="grounded",
        )

    def test_no_artifact_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("E2E_CORE_ARTIFACT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        result = write_case_artifact(
            case=self._case(),
            collection_name="rag_e2e_0f1e2d3c4b5a_main_00112233",
            response_text="r",
            retrieved_doc_ids=[],
            route="rag_search",
            error_type=None,
        )
        assert result is None
        assert not (tmp_path / ".artifacts").exists()

    def test_artifact_written_only_when_opted_in(self, tmp_path, monkeypatch):
        artifact_dir = tmp_path / "artifacts"
        monkeypatch.setenv("E2E_CORE_ARTIFACT_DIR", str(artifact_dir))
        path = write_case_artifact(
            case=self._case(),
            collection_name="rag_e2e_0f1e2d3c4b5a_main_00112233",
            response_text="r",
            retrieved_doc_ids=["d1"],
            route="rag_search",
            error_type=None,
        )
        assert path is not None and path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["case"]["id"] == "case_x"

    def test_validate_report_artifact(self, tmp_path, monkeypatch):
        monkeypatch.setenv("E2E_CORE_ARTIFACT_DIR", str(tmp_path))
        path = write_case_artifact(
            case=self._case(),
            collection_name="c",
            response_text="r",
            retrieved_doc_ids=[],
            route="rag_search",
            error_type=None,
        )
        assert validate_report_artifact(path) is True
        assert validate_report_artifact(tmp_path / "missing.json") is False


# ---------------------------------------------------------------------------
# Deterministic provider adapters (Telegram / STT) — no network
# ---------------------------------------------------------------------------


class TestDeterministicAdapters:
    async def test_deterministic_stt_returns_canned_text(self):
        stt = DeterministicSTT(transcript="двушка до 100 тысяч у моря")
        out = await stt.transcribe(b"\x00\x01fake-audio")
        assert out == "двушка до 100 тысяч у моря"
        assert stt.calls == 1
        again = await stt.transcribe(b"\x00\x01fake-audio")
        assert again == out  # deterministic
        assert stt.calls == 2

    async def test_deterministic_telegram_transport_records_outgoing(self):
        transport = DeterministicTelegramTransport()
        message_id = await transport.send_message(chat_id=42, text="карточка объекта")
        assert message_id.startswith("det-")
        await transport.send_message(chat_id=42, text="второе сообщение")
        assert [m.text for m in transport.sent] == ["карточка объекта", "второе сообщение"]
        assert transport.sent[0].chat_id == 42

    def test_crm_and_llm_adapters_remain_available(self):
        from tests.e2e_core.live_harness import FakeLLMConfig, MockCrmClient

        crm = MockCrmClient()
        assert hasattr(crm, "create_lead")
        assert FakeLLMConfig().llm_model == "fake-live-e2e"


# ---------------------------------------------------------------------------
# No fake SDKs in sys.modules
# ---------------------------------------------------------------------------


class TestNoFakeSdkModules:
    @staticmethod
    def _clear_sdk_modules(monkeypatch: pytest.MonkeyPatch) -> None:
        """Sandbox the checked names (other conftests may mock them globally)."""
        for name in ("aiogram", "aiogram_dialog", "fluentogram", "fluent_compiler"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    def test_absent_sdk_modules_are_not_offenders(self, monkeypatch):
        self._clear_sdk_modules(monkeypatch)
        assert no_fake_sdk_modules() == []

    def test_mocked_aiogram_is_detected(self, monkeypatch):
        self._clear_sdk_modules(monkeypatch)
        sys.modules["aiogram"] = MagicMock()
        assert no_fake_sdk_modules() == ["aiogram"]

    def test_real_aiogram_is_not_an_offender(self, monkeypatch):
        self._clear_sdk_modules(monkeypatch)
        try:
            import aiogram  # noqa: F401
        except ImportError:
            pytest.skip("aiogram not installed in this environment selection")
        assert "aiogram" not in no_fake_sdk_modules()


# ---------------------------------------------------------------------------
# BGE runtime verification contract (pure checks, no network here)
# ---------------------------------------------------------------------------


class TestBGERuntimeVerificationContract:
    def test_health_payload_with_model_loaded_passes(self):
        from tests.e2e_core.live_harness import health_model_loaded

        assert health_model_loaded({"status": "ok", "model_loaded": True}) is True
        assert health_model_loaded({"status": "ok", "model_loaded": False}) is False
        assert health_model_loaded({}) is False

    def test_dense_payload_dimension_check(self):
        from tests.e2e_core.live_harness import dense_dimension

        payload = {"dense_vecs": [[0.1] * 1024]}
        assert dense_dimension(payload) == 1024
        assert dense_dimension({"dense_vecs": [[0.1] * 7]}) == 7
        assert dense_dimension({"dense_vecs": []}) == 0
        assert dense_dimension({}) == 0
