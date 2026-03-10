"""Tests for FunnelSG states (#932-#936)."""


def test_funnel_sg_has_results_state():
    """FunnelSG must have a results state for list view."""
    from telegram_bot.dialogs.states import FunnelSG

    assert hasattr(FunnelSG, "results")
