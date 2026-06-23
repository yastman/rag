"""Contract: alert-driven runbooks for #1960-#1964 exist and reference every named alert.

Sub-issues #1960-#1964 split out of #1957 require five operational runbooks under
``docs/runbooks/`` with explicit alert coverage. Each runbook must:

* live under ``docs/runbooks/<NAME>.md`` (canonical filenames below);
* contain every alert name listed in the issue body so an on-call operator can
  ``grep`` straight from the alert payload to a remediation section;
* be linked from ``docs/runbooks/README.md`` so it shows up in the index.

The mapping below is the source of truth used both by this contract and by
the runbook authors. Update it in lock-step with the runbook bodies.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS_DIR = REPO_ROOT / "docs" / "runbooks"
README = RUNBOOKS_DIR / "README.md"


# Issue -> (runbook filename, [alert names that must appear verbatim]).
RUNBOOKS: dict[int, tuple[str, tuple[str, ...]]] = {
    1960: (
        "TELEGRAM_BOT_FAILURE.md",
        (
            "BotContainerDown",
            "BotHighErrorRate",
            "BotCriticalError",
            "TelegramAPIError",
            "BotRestarted",
            "QueryProcessingError",
            "SlowBotResponse",
            "BotMemoryWarning",
        ),
    ),
    1961: (
        "EMBEDDING_SERVICE_FAILURE.md",
        (
            "BGEServiceDown",
            "BM42ServiceDown",
            "EmbeddingServiceError",
            "BGEEmbedRetryFromBot",
            "BGEEmbedErrorFromBot",
            "VoyageRateLimited",
        ),
    ),
    1962: (
        "DOCLING_FAILURE.md",
        (
            "DoclingDown",
            "DoclingOOM",
            "DoclingConversionFailed",
            "DoclingError",
        ),
    ),
    1963: (
        "MINIO_FAILURE.md",
        (
            "MinioDown",
            "MinioDiskFull",
            "MinioCorruption",
            "MinioHealingFailed",
            "MinioError",
        ),
    ),
    1964: (
        "LIGHTRAG_FAILURE.md",
        (
            "LightRAGDown",
            "LightRAGError",
            "LightRAGAPIError",
        ),
    ),
}


@pytest.mark.parametrize("issue_number", sorted(RUNBOOKS))
def test_runbook_file_exists(issue_number: int) -> None:
    filename, _ = RUNBOOKS[issue_number]
    path = RUNBOOKS_DIR / filename
    assert path.exists(), (
        f"#{issue_number}: runbook docs/runbooks/{filename} is missing. "
        "Sub-issues #1960-#1964 require alert-driven runbooks under this path."
    )


@pytest.mark.parametrize("issue_number", sorted(RUNBOOKS))
def test_runbook_covers_named_alerts(issue_number: int) -> None:
    filename, alerts = RUNBOOKS[issue_number]
    path = RUNBOOKS_DIR / filename
    if not path.exists():
        pytest.skip(f"runbook {filename} missing — see test_runbook_file_exists")
    text = path.read_text(encoding="utf-8")
    missing = [name for name in alerts if name not in text]
    assert not missing, (
        f"#{issue_number}: docs/runbooks/{filename} must mention every alert from the issue "
        f"verbatim (so operators can grep from an alert payload). Missing names: {missing}"
    )


@pytest.mark.parametrize("issue_number", sorted(RUNBOOKS))
def test_runbook_indexed_in_readme(issue_number: int) -> None:
    filename, _ = RUNBOOKS[issue_number]
    text = README.read_text(encoding="utf-8")
    assert f"({filename})" in text or f"]({filename})" in text, (
        f"#{issue_number}: docs/runbooks/README.md must link to {filename} so it appears in "
        "the operator index."
    )
