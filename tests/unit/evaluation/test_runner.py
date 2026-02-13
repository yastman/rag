"""Tests for LLM-as-a-Judge batch runner."""

from unittest.mock import MagicMock

from telegram_bot.evaluation.runner import extract_trace_data


_SENTINEL = object()


def _mock_trace(*, input_data=_SENTINEL, output_data=_SENTINEL, scores=None, observations=None):
    """Create a mock Langfuse trace object."""
    t = MagicMock()
    t.id = "trace-123"
    t.input = {"query": "test question"} if input_data is _SENTINEL else input_data
    t.output = {"response": "test answer"} if output_data is _SENTINEL else output_data
    t.scores = scores or []
    t.observations = observations or ["obs-1"]
    return t


def _mock_observation(*, name="node-retrieve", output=_SENTINEL):
    """Create a mock Langfuse observation."""
    obs = MagicMock()
    obs.name = name
    obs.output = (
        {
            "results_count": 3,
            "retrieved_context": [
                {"content": "Doc 1 content", "score": 0.9},
                {"content": "Doc 2 content", "score": 0.7},
            ],
        }
        if output is _SENTINEL
        else output
    )
    return obs


class TestExtractTraceData:
    def test_extracts_query_and_answer(self):
        trace = _mock_trace()
        obs = _mock_observation()
        data = extract_trace_data(trace, [obs])
        assert data is not None
        assert data.query == "test question"
        assert data.answer == "test answer"

    def test_extracts_context_from_observation(self):
        trace = _mock_trace()
        obs = _mock_observation()
        data = extract_trace_data(trace, [obs])
        assert data is not None
        assert "Doc 1 content" in data.context
        assert "Doc 2 content" in data.context

    def test_returns_none_when_no_query(self):
        trace = _mock_trace(input_data={})
        obs = _mock_observation()
        data = extract_trace_data(trace, [obs])
        assert data is None

    def test_returns_none_when_no_answer(self):
        trace = _mock_trace(output_data={})
        obs = _mock_observation()
        data = extract_trace_data(trace, [obs])
        assert data is None

    def test_returns_none_when_no_context(self):
        trace = _mock_trace()
        obs = _mock_observation(output={"results_count": 0})
        data = extract_trace_data(trace, [obs])
        assert data is None

    def test_skips_non_retrieve_observations(self):
        trace = _mock_trace()
        obs_classify = _mock_observation(name="node-classify", output={})
        obs_retrieve = _mock_observation()
        data = extract_trace_data(trace, [obs_classify, obs_retrieve])
        assert data is not None
        assert "Doc 1 content" in data.context

    def test_handles_cache_hit_without_retrieve_observation(self):
        """When cache_hit=True, there is no retrieve observation — context unavailable."""
        trace = _mock_trace()
        obs_cache = _mock_observation(name="node-cache-check", output={"cache_hit": True})
        data = extract_trace_data(trace, [obs_cache])
        assert data is None
