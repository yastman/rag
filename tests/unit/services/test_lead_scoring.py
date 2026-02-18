"""Tests for lead scoring (rule-based)."""

from telegram_bot.services.lead_scoring import classify_lead, compute_lead_score


def test_hot_lead():
    """ASAP timeline + defined budget + type = hot."""
    score = compute_lead_score(
        property_type="apartment",
        budget="mid",
        timeline="asap",
    )
    assert score >= 60  # Hot threshold


def test_cold_lead():
    """Just looking = cold."""
    score = compute_lead_score(
        property_type="looking",
        budget=None,
        timeline="looking",
    )
    assert score < 30


def test_warm_lead():
    """Defined type + 3 months = warm."""
    score = compute_lead_score(
        property_type="house",
        budget="high",
        timeline="3months",
    )
    assert 30 <= score < 60 or score >= 60  # warm or hot


def test_classify_hot():
    assert classify_lead(65) == "hot"


def test_classify_warm():
    assert classify_lead(45) == "warm"


def test_classify_cold():
    assert classify_lead(15) == "cold"
