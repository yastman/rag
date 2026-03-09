"""Tests for Mini App YAML config loading."""

from telegram_bot.services.content_loader import load_mini_app_config


def test_load_mini_app_config_returns_questions_and_experts():
    config = load_mini_app_config()
    assert "questions" in config
    assert "experts" in config
    assert len(config["questions"]) == 4
    assert len(config["experts"]) == 5


def test_each_question_has_required_fields():
    config = load_mini_app_config()
    for q in config["questions"]:
        assert "id" in q
        assert "emoji" in q
        assert "title" in q
        assert "prompts" in q
        assert len(q["prompts"]) >= 4


def test_each_expert_has_required_fields():
    config = load_mini_app_config()
    for e in config["experts"]:
        assert "id" in e
        assert "emoji" in e
        assert "name" in e
        assert "system_prompt_key" in e
        assert "prompts" in e
        assert len(e["prompts"]) >= 4


def test_each_question_has_prompts():
    config = load_mini_app_config()
    for q in config["questions"]:
        assert "prompts" in q
        assert len(q["prompts"]) > 0


def test_each_prompt_has_emoji_and_text():
    config = load_mini_app_config()
    for q in config["questions"]:
        for prompt in q["prompts"]:
            assert "emoji" in prompt
            assert "text" in prompt
    for e in config["experts"]:
        for prompt in e["prompts"]:
            assert "emoji" in prompt
            assert "text" in prompt
