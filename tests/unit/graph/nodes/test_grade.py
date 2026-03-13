"""Unit tests for grade_node."""

from types import SimpleNamespace

import pytest

from telegram_bot.graph.nodes.grade import grade_node


@pytest.mark.asyncio
async def test_grade_node_returns_not_relevant_when_documents_empty() -> None:
    result = await grade_node({"documents": [], "latency_stages": {"retrieve": 0.1}})
    assert result["documents_relevant"] is False
    assert result["grade_confidence"] == 0.0
    assert result["skip_rerank"] is False
    assert result["score_improved"] is False
    assert "grade" in result["latency_stages"]


@pytest.mark.asyncio
async def test_grade_node_uses_thresholds_and_skip_rerank(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = SimpleNamespace(
        relevance_threshold_rrf=0.01,
        skip_rerank_threshold=0.02,
        score_improvement_delta=0.005,
    )
    monkeypatch.setattr(
        "telegram_bot.graph.config.GraphConfig.from_env",
        lambda: fake_config,
    )

    state = {
        "documents": [{"score": 0.03}, {"score": 0.02}],
        "grade_confidence": 0.01,
        "latency_stages": {},
    }
    result = await grade_node(state)

    assert result["documents_relevant"] is True
    assert result["skip_rerank"] is True
    assert result["grade_confidence"] == 0.03
    assert result["score_improved"] is True


@pytest.mark.asyncio
async def test_grade_node_handles_non_dict_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = SimpleNamespace(
        relevance_threshold_rrf=0.5,
        skip_rerank_threshold=0.7,
        score_improvement_delta=0.1,
    )
    monkeypatch.setattr(
        "telegram_bot.graph.config.GraphConfig.from_env",
        lambda: fake_config,
    )

    result = await grade_node({"documents": [None, "bad", 123], "latency_stages": {}})
    assert result["documents_relevant"] is False
    assert result["grade_confidence"] == 0.0
    assert result["score_improved"] is False
