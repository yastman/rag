"""Static contract tests for scripts/test_bot_health.sh."""

from pathlib import Path


SCRIPT = Path("scripts/test_bot_health.sh")


def test_test_bot_health_uses_native_bot_preflight() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "telegram_bot.config" in text
    assert "telegram_bot.preflight" in text
    assert "check_dependencies" in text


def test_test_bot_health_does_not_reference_custom_helper_module() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "scripts.test_bot_health" not in text, (
        "test_bot_health.sh must call the existing bot preflight directly instead of "
        "routing through a custom helper module"
    )


def test_test_bot_health_explicitly_gates_litellm() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '"litellm"' in text and "_check_single_dep" in text, (
        "test_bot_health.sh must explicitly fail when LiteLLM is unavailable, "
        "because bot startup treats it as optional but the local health contract does not"
    )
