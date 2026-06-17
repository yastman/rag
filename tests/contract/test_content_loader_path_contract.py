"""Contract: src/services/content_loader.py must not reference telegram_bot/ path (#2747).

The shared src/ module must resolve YAML configs from src/config/, not from
the Telegram adapter's directory layout. This ensures the module is reusable
outside the bot context.
"""

from __future__ import annotations

from pathlib import Path

import src.services.content_loader as content_loader_mod


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_config_dir_does_not_reference_telegram_bot() -> None:
    """_CONFIG_DIR must not contain 'telegram_bot' in its resolved path."""
    config_dir = content_loader_mod._CONFIG_DIR
    assert "telegram_bot" not in str(config_dir), (
        f"#2747: src/services/content_loader._CONFIG_DIR references telegram_bot/: "
        f"{config_dir!r}. Move YAML configs to src/config/ and update the path."
    )


def test_content_loader_config_dir_uses_src_config() -> None:
    """_CONFIG_DIR must resolve to src/config/, not telegram_bot/config/."""
    config_dir = content_loader_mod._CONFIG_DIR
    src_config = REPO_ROOT / "src" / "config"
    assert config_dir == src_config, (
        f"#2747: _CONFIG_DIR should be {src_config!r}, got {config_dir!r}"
    )


def test_src_config_yaml_files_exist() -> None:
    """services.yaml and mini_app.yaml must exist in src/config/."""
    src_config = REPO_ROOT / "src" / "config"
    assert (src_config / "services.yaml").exists(), (
        "#2747: src/config/services.yaml missing — move it from telegram_bot/config/"
    )
    assert (src_config / "mini_app.yaml").exists(), (
        "#2747: src/config/mini_app.yaml missing — move it from telegram_bot/config/"
    )
