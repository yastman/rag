"""Test .env loading for gdrive_flow entrypoint."""

import importlib
from pathlib import Path

import pytest


pytestmark = pytest.mark.filterwarnings(
    "ignore:This module is deprecated. Use src.ingestion.unified instead.:DeprecationWarning"
)


class TestDotenvLoading:
    """Test that .env variables are loaded before config initialization."""

    def test_voyage_api_key_loaded_from_dotenv(self, tmp_path: Path, monkeypatch):
        """Config should see VOYAGE_API_KEY from .env file when env var not set."""
        # Arrange: create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=test-key-from-dotenv\n")

        # Clear any existing env var
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

        # Act: load dotenv and create config
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)

        # Import AFTER load_dotenv to get fresh defaults
        # Force reimport to pick up new env
        import src.ingestion.gdrive_flow as gf

        importlib.reload(gf)
        config = gf.GDriveFlowConfig()

        # Assert
        assert config.voyage_api_key == "test-key-from-dotenv"

    def test_explicit_env_var_takes_precedence(self, tmp_path: Path, monkeypatch):
        """Explicit env var should override .env file value."""
        # Arrange: .env has one value
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=from-dotenv-file\n")

        # Set explicit env var (should take precedence)
        monkeypatch.setenv("VOYAGE_API_KEY", "from-explicit-export")

        # Act: load dotenv WITHOUT override (default behavior)
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

        import src.ingestion.gdrive_flow as gf

        importlib.reload(gf)
        config = gf.GDriveFlowConfig()

        # Assert: explicit env var wins
        assert config.voyage_api_key == "from-explicit-export"
