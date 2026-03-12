"""Tests for FunnelSG states."""


def test_funnel_sg_has_results_state():
    """FunnelSG must have a results State for the results preview window (#935)."""
    from telegram_bot.dialogs.states import FunnelSG

    assert hasattr(FunnelSG, "results"), "FunnelSG must have 'results' State (#935)"


def test_funnel_sg_has_summary_state():
    """FunnelSG must have summary state with search buttons."""
    from telegram_bot.dialogs.states import FunnelSG

    assert hasattr(FunnelSG, "summary")
    assert hasattr(FunnelSG, "change_filter")
