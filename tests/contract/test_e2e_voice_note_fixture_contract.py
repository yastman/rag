"""Contract tests: synthetic voice-note fixture for Telethon trace gate.

Verifies that:
  1. The fixture file exists at data/test/voice_note_sample.ogg
  2. Its size is >0 and <100 000 bytes (synthetic/non-secret)
  3. The first 4 bytes are b"OggS" (valid OGG container)
  4. .env.example documents E2E_VOICE_NOTE_PATH
  5. The e2e telegram_client reads E2E_VOICE_NOTE_PATH from the environment

Issue: ***REMOVED***1486 — provide voice-note fixture for Telethon trace gate
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Repository root helpers
***REMOVED*** ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_FIXTURE_PATH = _REPO_ROOT / "data" / "test" / "voice_note_sample.ogg"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_TELEGRAM_CLIENT = _REPO_ROOT / "scripts" / "e2e" / "telegram_client.py"
_E2E_CONFIG = _REPO_ROOT / "scripts" / "e2e" / "config.py"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. Fixture file existence
***REMOVED*** ---------------------------------------------------------------------------


def test_voice_note_fixture_exists() -> None:
    """data/test/voice_note_sample.ogg must be present in the repository."""
    assert _FIXTURE_PATH.exists(), (
        f"Fixture not found at {_FIXTURE_PATH}. "
        "Run the fixture generator or check git-add -f data/test/voice_note_sample.ogg."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. Fixture size: >0 and <100 000 bytes
***REMOVED*** ---------------------------------------------------------------------------


def test_voice_note_fixture_size() -> None:
    """Fixture must be non-empty and below 100 KB (synthetic only, no real voice data)."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present — covered by test_voice_note_fixture_exists")
    size = _FIXTURE_PATH.stat().st_size
    assert size > 0, "Fixture file is empty."
    assert size < 100_000, (
        f"Fixture is {size} bytes — exceeds 100 KB limit. "
        "Replace with a shorter synthetic file."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. Valid OGG container magic bytes
***REMOVED*** ---------------------------------------------------------------------------


def test_voice_note_fixture_ogg_magic() -> None:
    """First 4 bytes of the fixture must be b'OggS' (RFC 3533 OGG capture pattern)."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present — covered by test_voice_note_fixture_exists")
    magic = _FIXTURE_PATH.read_bytes()[:4]
    assert magic == b"OggS", (
        f"Fixture does not start with OggS (got {magic!r}). "
        "Regenerate with a proper OGG/Opus encoder."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 4. .env.example documents E2E_VOICE_NOTE_PATH
***REMOVED*** ---------------------------------------------------------------------------


def test_env_example_documents_e2e_voice_note_path() -> None:
    """.env.example must contain E2E_VOICE_NOTE_PATH so developers know to set it."""
    assert _ENV_EXAMPLE.exists(), f".env.example not found at {_ENV_EXAMPLE}"
    content = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "E2E_VOICE_NOTE_PATH" in content, (
        "E2E_VOICE_NOTE_PATH is not documented in .env.example. "
        "Add a commented example entry so developers know about the voice-note fixture."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 5. telegram_client.py / config.py reads E2E_VOICE_NOTE_PATH
***REMOVED*** ---------------------------------------------------------------------------


def test_e2e_config_reads_voice_note_path_env_var() -> None:
    """scripts/e2e/config.py must reference E2E_VOICE_NOTE_PATH to populate voice_note_path."""
    assert _E2E_CONFIG.exists(), f"E2E config not found at {_E2E_CONFIG}"
    content = _E2E_CONFIG.read_text(encoding="utf-8")
    assert "E2E_VOICE_NOTE_PATH" in content, (
        "E2E_VOICE_NOTE_PATH is not referenced in scripts/e2e/config.py. "
        "Add: voice_note_path = os.getenv('E2E_VOICE_NOTE_PATH', 'data/test/voice_note_sample.ogg')"
    )


def test_telegram_client_raises_on_missing_path() -> None:
    """telegram_client.py must guard send_voice_and_wait with a RuntimeError when path is empty."""
    assert _TELEGRAM_CLIENT.exists(), f"Telegram client not found at {_TELEGRAM_CLIENT}"
    content = _TELEGRAM_CLIENT.read_text(encoding="utf-8")
    assert "E2E_VOICE_NOTE_PATH is not set" in content, (
        "telegram_client.py does not raise the expected RuntimeError message. "
        "Scenario 8.1 will fail with an opaque error instead of a clear message."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 6. Integration smoke: env var → config → path round-trip
***REMOVED*** ---------------------------------------------------------------------------


def test_e2e_config_voice_note_path_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """E2EConfig must expose the path set via E2E_VOICE_NOTE_PATH env var."""
    monkeypatch.setenv("E2E_VOICE_NOTE_PATH", str(_FIXTURE_PATH))

    ***REMOVED*** Import after patching env so dataclass field_factory picks it up
    import importlib
    import scripts.e2e.config as _cfg_mod

    importlib.reload(_cfg_mod)
    cfg = _cfg_mod.E2EConfig()
    assert cfg.voice_note_path == str(_FIXTURE_PATH), (
        f"Expected voice_note_path={_FIXTURE_PATH!s}, got {cfg.voice_note_path!r}"
    )
