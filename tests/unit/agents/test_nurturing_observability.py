"""Tests for nurturing + funnel Langfuse scores (#390, #2844)."""

from telegram_bot.scoring import write_pipeline_scores


_FAKE_TRACE_ID = "test-nurturing-trace"


class FakeLangfuse:
    """Minimal fake Langfuse client that records create_score calls (#435)."""

    def __init__(self):
        self._scores: dict[str, object] = {}

    def create_score(self, *, name: str, value: object, **kwargs: object) -> None:
        self._scores[name] = value

    def get_current_trace_id(self) -> str:
        return _FAKE_TRACE_ID

    def has_score(self, name: str) -> bool:
        return name in self._scores

    def get_score(self, name: str) -> object:
        return self._scores.get(name)


def test_write_pipeline_scores_is_noop_for_nurturing_metrics():
    """Tracing removed (#2844): nurturing/funnel keys are not written as scores."""
    lf = FakeLangfuse()
    result = {
        "nurturing_batch_size": 12,
        "nurturing_sent_count": 9,
        "funnel_conversion_rate": 0.31,
        "funnel_dropoff_rate": 0.69,
        "latency_stages": {},
    }
    write_pipeline_scores(lf, result, trace_id=_FAKE_TRACE_ID)

    assert not lf.has_score("nurturing_batch_size")
    assert not lf.has_score("nurturing_sent_count")
    assert not lf.has_score("funnel_conversion_rate")
    assert not lf.has_score("funnel_dropoff_rate")


def test_write_pipeline_scores_skips_missing_nurturing_keys():
    lf = FakeLangfuse()
    result = {"latency_stages": {}}
    write_pipeline_scores(lf, result, trace_id=_FAKE_TRACE_ID)

    assert not lf.has_score("nurturing_batch_size")
    assert not lf.has_score("funnel_conversion_rate")
