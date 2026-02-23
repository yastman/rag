"""Trace coverage contract tests for issue #609."""

from pathlib import Path


def test_ingestion_cli_has_observe_on_run_and_preflight() -> None:
    """Ingestion CLI entrypoints must be wrapped with observe spans."""
    source = Path("src/ingestion/unified/cli.py").read_text(encoding="utf-8")

    assert '@observe(name="ingestion-cli-run"' in source
    assert '@observe(name="ingestion-cli-preflight"' in source
