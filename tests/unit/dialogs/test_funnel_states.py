"""Tests for FunnelSG states."""


def test_funnel_sg_has_no_results_state():
    """FunnelSG must NOT have a results state (removed: inline pagination replaced by ReplyKeyboard)."""
    from telegram_bot.dialogs.states import FunnelSG

    assert not hasattr(FunnelSG, "results")


def test_funnel_sg_has_summary_state():
    """FunnelSG must have summary state with search buttons."""
    from telegram_bot.dialogs.states import FunnelSG

    assert hasattr(FunnelSG, "summary")
    assert hasattr(FunnelSG, "change_filter")
