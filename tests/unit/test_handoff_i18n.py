import pytest

from telegram_bot.middlewares.i18n import create_translator_hub


HANDOFF_KEYS = [
    "handoff-qual-prompt",
    "handoff-goal-buy",
    "handoff-goal-rent",
    "handoff-goal-consult",
    "handoff-budget-prompt",
    "handoff-budget-low",
    "handoff-budget-mid",
    "handoff-budget-high",
    "handoff-budget-unknown",
    "handoff-contact-prompt",
    "handoff-contact-chat",
    "handoff-contact-phone",
    "handoff-connecting",
    "handoff-offline",
    "handoff-manager-joined",
    "handoff-timeout",
    "handoff-closed-client",
    "handoff-closed-topic",
    "handoff-wait-more",
    "handoff-leave-phone",
]


@pytest.mark.parametrize("locale", ["ru", "en", "uk"])
@pytest.mark.parametrize("key", HANDOFF_KEYS)
def test_handoff_key_exists(locale, key):
    hub = create_translator_hub()
    i18n = hub.get_translator_by_locale(locale)
    result = i18n.get(key)
    # Must not return the key itself (means missing translation).
    assert result != key, f"Missing .ftl key '{key}' for locale '{locale}'"
