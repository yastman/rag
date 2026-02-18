"""Rule-based lead scoring for sales funnel."""

from __future__ import annotations


# Points per funnel answer
_TIMELINE_SCORES = {
    "asap": 40,
    "3months": 25,
    "6months": 15,
    "looking": 5,
}

_BUDGET_BONUS = 20  # Any defined budget
_TYPE_BONUS = 10  # Any defined property type (not "looking")


def compute_lead_score(
    *,
    property_type: str | None = None,
    budget: str | None = None,
    timeline: str | None = None,
) -> int:
    """Compute lead score (0-100) from funnel answers."""
    score = 0

    if timeline:
        score += _TIMELINE_SCORES.get(timeline, 0)

    if budget:
        score += _BUDGET_BONUS

    if property_type and property_type != "looking":
        score += _TYPE_BONUS

    return min(score, 100)


def classify_lead(score: int) -> str:
    """Classify lead by score: hot (>=60), warm (30-59), cold (<30)."""
    if score >= 60:
        return "hot"
    if score >= 30:
        return "warm"
    return "cold"
