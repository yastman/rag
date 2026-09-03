"""Unit tests for the simplification live E2E harness."""

from __future__ import annotations

import asyncio
import os
from unittest import mock

import pytest


def test_load_golden_case_returns_named_case() -> None:
    from tests.e2e_core.live_harness import load_golden_case

    case = load_golden_case("beach_studio_sea_under_120k")

    assert case.id == "beach_studio_sea_under_120k"
    assert case.must_retrieve == ["sunny_beach_studio"]
    assert "Sunny Beach" in case.must_contain


def test_load_golden_case_rejects_unknown_id() -> None:
    from tests.e2e_core.live_harness import load_golden_case

    with pytest.raises(KeyError, match="unknown_case"):
        load_golden_case("unknown_case")


def test_live_env_uses_explicit_overrides() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv

    env = {
        "E2E_CORE_QDRANT_URL": "http://qdrant.local:6333",
        "E2E_CORE_BGE_URL": "http://bge.local:8000",
        "QDRANT_API_KEY": "secret",
    }

    with mock.patch.dict(os.environ, env, clear=True):
        parsed = LiveE2EEnv.from_env()

    assert parsed.qdrant_url == "http://qdrant.local:6333"
    assert parsed.bge_m3_url == "http://bge.local:8000"
    assert parsed.qdrant_api_key == "secret"


def test_live_env_falls_back_to_runtime_urls() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv

    env = {
        "QDRANT_URL": "http://runtime-qdrant:6333",
        "BGE_M3_URL": "http://runtime-bge:8000",
    }

    with mock.patch.dict(os.environ, env, clear=True):
        parsed = LiveE2EEnv.from_env()

    assert parsed.qdrant_url == "http://runtime-qdrant:6333"
    assert parsed.bge_m3_url == "http://runtime-bge:8000"


def test_live_env_reads_real_llm_opt_in() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv

    with mock.patch.dict(os.environ, {"E2E_CORE_REAL_LLM": "1"}, clear=True):
        parsed = LiveE2EEnv.from_env()

    assert parsed.real_llm is True


def test_real_llm_preflight_requires_opt_in_and_provider_env() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv, real_llm_config_errors

    with mock.patch.dict(os.environ, {}, clear=True):
        fake_mode_errors = real_llm_config_errors(LiveE2EEnv.from_env())

    assert fake_mode_errors == []

    env = LiveE2EEnv(qdrant_url="http://qdrant:6333", bge_m3_url="http://bge:8000", real_llm=True)
    with mock.patch.dict(os.environ, {}, clear=True):
        errors = real_llm_config_errors(env)

    assert errors == [
        "E2E_CORE_REAL_LLM=1 is required for real LLM mode",
        "LLM_MODEL is required for real LLM mode",
        "one of CEREBRAS_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_API_KEY is required for real LLM mode",
    ]

    provider_env = {
        "E2E_CORE_REAL_LLM": "1",
        "LLM_MODEL": "gpt-test",
    }
    with mock.patch.dict(os.environ, provider_env, clear=True):
        errors = real_llm_config_errors(env)

    assert errors == [
        "one of CEREBRAS_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or LLM_API_KEY is required for real LLM mode"
    ]


def test_build_live_core_harness_uses_graph_config_for_real_llm() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv, build_live_core_harness

    fake_config = mock.MagicMock()
    fake_config.llm_temperature = 0.7
    fake_config.generate_max_tokens = 1024
    fake_config.streaming_enabled = True
    fake_config.show_sources = True
    fake_config.response_style_enabled = True
    fake_config.response_style_shadow_mode = True

    env = LiveE2EEnv(
        qdrant_url="http://qdrant:6333",
        bge_m3_url="http://bge:8000",
        real_llm=True,
    )

    with (
        mock.patch("tests.e2e_core.live_harness.LiveBGEEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.LiveBGESparseEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.QdrantService"),
        mock.patch("tests.e2e_core.live_harness.GraphConfig.from_env", return_value=fake_config),
    ):
        harness = build_live_core_harness(env, "collection")

    assert harness.dependencies.config is fake_config
    assert fake_config.llm_temperature == 0.0
    assert fake_config.generate_max_tokens == 600
    assert fake_config.streaming_enabled is False
    assert fake_config.show_sources is False
    assert fake_config.response_style_enabled is False
    assert fake_config.response_style_shadow_mode is False


def test_build_live_core_harness_attaches_mock_crm() -> None:
    from tests.e2e_core.live_harness import LiveE2EEnv, MockCrmClient, build_live_core_harness

    crm = MockCrmClient()
    env = LiveE2EEnv(qdrant_url="http://qdrant:6333", bge_m3_url="http://bge:8000")

    with (
        mock.patch("tests.e2e_core.live_harness.LiveBGEEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.LiveBGESparseEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.QdrantService"),
    ):
        harness = build_live_core_harness(env, "collection", crm=crm)

    assert harness.dependencies.crm is crm


def test_build_live_core_harness_accepts_config_override() -> None:
    from tests.e2e_core.live_harness import FailingLLMConfig, LiveE2EEnv, build_live_core_harness

    config = FailingLLMConfig(error_message="provider down")
    env = LiveE2EEnv(qdrant_url="http://qdrant:6333", bge_m3_url="http://bge:8000")

    with (
        mock.patch("tests.e2e_core.live_harness.LiveBGEEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.LiveBGESparseEmbeddings"),
        mock.patch("tests.e2e_core.live_harness.QdrantService"),
    ):
        harness = build_live_core_harness(env, "collection", config=config)

    assert harness.dependencies.config is config


def test_failing_llm_config_raises_provider_error() -> None:
    from tests.e2e_core.live_harness import FailingLLMConfig

    llm = FailingLLMConfig(error_message="provider down").create_llm(auto_trace=False)

    with pytest.raises(TimeoutError, match="provider down"):
        asyncio.run(llm.completion(model="fake", messages=[]))


def test_mock_crm_client_records_writes() -> None:
    from tests.e2e_core.live_harness import MockCrmClient

    crm = MockCrmClient()

    result = asyncio.run(crm.create_lead({"name": "Test Lead"}))

    assert result == {"id": 1, "name": "Test Lead"}
    assert crm.writes == [{"action": "create_lead", "payload": {"name": "Test Lead"}}]


def test_fake_llm_config_builds_grounded_answer_from_context() -> None:
    from tests.e2e_core.live_harness import FakeLLMConfig

    config = FakeLLMConfig()
    llm = config.create_llm(auto_trace=False)

    messages = [
        {"role": "system", "content": "test"},
        {
            "role": "user",
            "content": (
                "Контекст:\n"
                "[Объект 1]\nНазвание: Sunny Beach Studio\nЦена: 110000€\n"
                "Sunny Beach studio near the sea.\n\n"
                "Вопрос: Найди квартиру-студию у моря до 120000 евро\n\n"
                "Ответь на вопрос на основе контекста выше."
            ),
        },
    ]

    result = asyncio.run(llm.completion(model="fake", messages=messages))

    assert "Sunny Beach" in result.choices[0].message.content
    assert "110000" in result.choices[0].message.content


def test_write_case_artifact_writes_lightweight_json(tmp_path) -> None:
    from tests.e2e_core.live_harness import load_golden_case, write_case_artifact

    case = load_golden_case("beach_studio_sea_under_120k")

    with mock.patch.dict(os.environ, {"E2E_CORE_ARTIFACT_DIR": str(tmp_path)}, clear=True):
        artifact_path = write_case_artifact(
            case=case,
            collection_name="test_collection",
            response_text="Sunny Beach Studio costs 110000 EUR.",
            retrieved_doc_ids=["sunny_beach_studio"],
            route="rag_search",
            error_type=None,
        )

    assert artifact_path == tmp_path / "beach_studio_sea_under_120k.json"
    text = artifact_path.read_text(encoding="utf-8")
    assert "test_collection" in text
    assert "Sunny Beach Studio" in text
    assert "sunny_beach_studio" in text
