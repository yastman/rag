"""Contract: core live E2E must exercise the assistant core directly."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_LIVE_TEST = REPO_ROOT / "tests" / "e2e" / "test_core_live_ingest_answer.py"


def test_core_live_e2e_uses_run_assistant_request_directly() -> None:
    text = CORE_LIVE_TEST.read_text(encoding="utf-8")
    assert "run_assistant_request" in text
    assert "from src.core.assistant import" in text or "from src.core import" in text


def test_core_live_e2e_does_not_import_telegram_adapter() -> None:
    text = CORE_LIVE_TEST.read_text(encoding="utf-8")
    assert "import telegram_bot" not in text
    assert "from telegram_bot" not in text


if __name__ == "__main__":
    test_core_live_e2e_uses_run_assistant_request_directly()
    test_core_live_e2e_does_not_import_telegram_adapter()
