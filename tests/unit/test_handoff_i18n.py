import pytest

from telegram_bot.middlewares.i18n import create_translator_hub


HANDOFF_KEYS = [
    "handoff-qual-prompt",
    "handoff-goal-search",
    "handoff-goal-services",
    "handoff-goal-consult",
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

HANDOFF_KEY_KWARGS = {
    "handoff-offline": {"start": 9, "end": 18},
    "handoff-manager-joined": {"name": "Manager"},
}


def _strip_bidi_isolates(text: str) -> str:
    return text.replace("\u2068", "").replace("\u2069", "")


@pytest.mark.parametrize("locale", ["ru", "en", "uk"])
@pytest.mark.parametrize("key", HANDOFF_KEYS)
def test_handoff_key_exists(locale, key):
    hub = create_translator_hub()
    i18n = hub.get_translator_by_locale(locale)
    result = i18n.get(key, **HANDOFF_KEY_KWARGS.get(key, {}))
    # Must not return the key itself (means missing translation).
    assert result != key, f"Missing .ftl key '{key}' for locale '{locale}'"


@pytest.mark.parametrize("locale", ["ru", "en", "uk"])
def test_handoff_offline_renders_business_hours(locale):
    hub = create_translator_hub()
    i18n = hub.get_translator_by_locale(locale)

    result = _strip_bidi_isolates(i18n.get("handoff-offline", start=9, end=18))

    assert "9:00" in result
    assert "18:00" in result


@pytest.mark.parametrize("locale", ["ru", "en", "uk"])
def test_handoff_manager_joined_renders_manager_name(locale):
    hub = create_translator_hub()
    i18n = hub.get_translator_by_locale(locale)

    result = i18n.get("handoff-manager-joined", name="Manager")

    assert "Manager" in result
