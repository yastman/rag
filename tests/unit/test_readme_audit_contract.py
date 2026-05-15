"""
Static contract test for README audit findings.

Prevents stale README drift by asserting that reserved README files
match current source-tree facts.
"""

import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class TestServicesReadme:
    def test_no_stale_file_references(self):
        text = _read("telegram_bot/services/README.md")
        stale = [
            "cache.py",
            "query_router.py",
            "cesc.py",
            "retriever.py",
            "user_context.py",
            "embeddings.py",
        ]
        for name in stale:
            assert f"[{name}]" not in text, f"Stale file reference {name} found"


class TestVoiceReadme:
    def test_voicebot_import_check(self):
        text = _read("src/voice/README.md")
        assert "VoiceBot" in text
        assert "PropertyVoiceAgent" not in text


class TestIngestionReadme:
    def test_no_pdf_parser_reference(self):
        text = _read("src/ingestion/README.md")
        assert "pdf_parser.py" not in text

    def test_status_command_not_colbert_status(self):
        text = _read("src/ingestion/README.md")
        assert "colbert-status" not in text
        assert "python -m src.ingestion.unified.cli status" in text


class TestUnifiedReadme:
    def test_watch_mode_is_run_watch(self):
        text = _read("src/ingestion/unified/README.md")
        assert "python -m src.ingestion.unified.cli run --watch" in text
        # standalone "watch" as a subcommand should not appear
        lines = text.splitlines()
        for line in lines:
            if "cli watch" in line and "run --watch" not in line:
                pytest.fail(f"Standalone watch command found: {line}")

    def test_backfill_colbert_command(self):
        text = _read("src/ingestion/unified/README.md")
        assert "backfill-colbert" in text
        assert "colbert-backfill" not in text


class TestTelegramBotReadme:
    def test_state_py_not_state_contract_py(self):
        text = _read("telegram_bot/README.md")
        assert "telegram_bot/graph/state.py" in text
        assert "telegram_bot/graph/state_contract.py" not in text


class TestRetrievalReadme:
    def test_exports_match_actual_init(self):
        text = _read("src/retrieval/README.md")
        assert "SearchResult" not in text
        assert "rerank_results" not in text
        assert "search engine classes" in text


class TestDocsReadme:
    def test_missing_root_docs_indexed(self):
        text = _read("docs/README.md")
        required = [
            "BOT_INTERNAL_STRUCTURE.md",
            "ONBOARDING.md",
            "ONBOARDING_CHECKLIST.md",
            "TROUBLESHOOTING_CACHE.md",
            "ADD_NEW_RAG_NODE.md",
        ]
        for name in required:
            assert name in text, f"Missing doc index entry for {name}"


class TestDataDemoReadme:
    def test_explicit_not_committed_wording(self):
        text = _read("data/demo/README.md")
        assert "not committed" in text or "not tracked" in text
