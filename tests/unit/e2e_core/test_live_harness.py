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

    result = asyncio.run(llm.chat.completions.create(model="fake", messages=messages))

    assert "Sunny Beach" in result.choices[0].message.content
    assert "110000" in result.choices[0].message.content
