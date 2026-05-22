"""Tests for get_promotions in content_loader (#628)."""

from telegram_bot.services.content_loader import get_promotions


def test_get_promotions_returns_list() -> None:
    promos = get_promotions()
    assert isinstance(promos, list)
    assert len(promos) > 0


def test_promo_item_has_required_fields() -> None:
    promos = get_promotions()
    for promo in promos:
        assert "title" in promo, f"promo missing title: {promo}"
        assert "text" in promo, f"promo missing text: {promo}"
        assert "emoji" in promo, f"promo missing emoji: {promo}"
