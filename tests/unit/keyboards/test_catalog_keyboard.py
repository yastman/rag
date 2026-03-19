"""Legacy catalog reply keyboard removal contracts."""


def test_build_catalog_keyboard_is_removed() -> None:
    import telegram_bot.keyboards.client_keyboard as mod

    assert not hasattr(mod, "build_catalog_keyboard")


def test_parse_catalog_button_is_removed() -> None:
    import telegram_bot.keyboards.client_keyboard as mod

    assert not hasattr(mod, "parse_catalog_button")
