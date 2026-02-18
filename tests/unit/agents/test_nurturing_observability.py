"""Tests for nurturing + funnel Langfuse scores (#390)."""

from telegram_bot.scoring import write_langfuse_scores


class FakeLangfuse:
    """Minimal fake Langfuse client that records score_current_trace calls."""

    def __init__(self):
        self._scores: dict[str, object] = {}

    def score_current_trace(self, *, name: str, value: object, **kwargs: object) -> None:
        self._scores[name] = value

    def has_score(self, name: str) -> bool:
        return name in self._scores

    def get_score(self, name: str) -> object:
        return self._scores.get(name)


def test_write_langfuse_scores_includes_nurturing_and_funnel_metrics():
    lf = FakeLangfuse()
    result = {
        "nurturing_batch_size": 12,
        "nurturing_sent_count": 9,
        "funnel_conversion_rate": 0.31,
        "funnel_dropoff_rate": 0.69,
        "latency_stages": {},
    }
    write_langfuse_scores(lf, result)

    assert lf.has_score("nurturing_batch_size")
    assert lf.get_score("nurturing_batch_size") == 12.0
    assert lf.has_score("nurturing_sent_count")
    assert lf.get_score("nurturing_sent_count") == 9.0
    assert lf.has_score("funnel_conversion_rate")
    assert lf.get_score("funnel_conversion_rate") == 0.31
    assert lf.has_score("funnel_dropoff_rate")
    assert lf.get_score("funnel_dropoff_rate") == 0.69


def test_write_langfuse_scores_skips_missing_nurturing_keys():
    lf = FakeLangfuse()
    result = {"latency_stages": {}}
    write_langfuse_scores(lf, result)

    assert not lf.has_score("nurturing_batch_size")
    assert not lf.has_score("funnel_conversion_rate")
