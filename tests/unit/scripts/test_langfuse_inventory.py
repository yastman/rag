"""Unit tests for scripts/audit/langfuse_inventory.py (#2222 / Epic M).

The inventory script surfaces drift between what the code references and what
actually exists in Langfuse:

* **Prompts**: code calls ``get_prompt("<name>")`` / ``get_prompt_with_config(
  "<name>")``. The script compares those names against
  ``langfuse.api.prompts.list()``:
    - ``local_only``  -> code references a prompt that does NOT exist in
      Langfuse (the SDK silently uses the hardcoded ``fallback=`` instead —
      a real drift the operator should know about).
    - ``remote_only`` -> a prompt exists in Langfuse but no code path fetches
      it (orphan / candidate for cleanup).
* **Score configs**: code emits scores via ``score_current_trace(name=...)``
  in ``src/scoring.py``. The script compares those against
  ``langfuse.api.score_configs.get()`` so operators can spot scores emitted
  without a configured Score Config (no UI metadata / data-type) and configs
  with no emitter.

These tests pin the pure functions (code scan + diff + report). The live
Langfuse fetch is mocked.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


inventory = pytest.importorskip(
    "scripts.audit.langfuse_inventory",
    reason="inventory script under test",
)


class TestScanCodePromptNames:
    def test_finds_get_prompt_literal(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text(
            "from x import get_prompt\n"
            "def g():\n"
            "    return get_prompt('generate', fallback='...')\n"
        )
        names = inventory.scan_code_prompt_names([tmp_path])
        assert "generate" in names

    def test_finds_get_prompt_with_config_literal(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text(
            "def g(pm):\n    return pm.get_prompt_with_config('client_agent', cache_ttl=60)\n"
        )
        names = inventory.scan_code_prompt_names([tmp_path])
        assert "client_agent" in names

    def test_ignores_non_literal_first_arg(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def g(name):\n    return get_prompt(name)\n")
        names = inventory.scan_code_prompt_names([tmp_path])
        assert names == set()

    def test_skips_tests_and_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("get_prompt('should_skip')\n")
        (tmp_path / "real.py").write_text("get_prompt('keep')\n")
        names = inventory.scan_code_prompt_names([tmp_path])
        assert "keep" in names
        assert "should_skip" not in names


class TestDiffInventory:
    def test_partitions_local_remote_both(self) -> None:
        diff = inventory.diff_inventory(
            code={"a", "b", "c"},
            remote={"b", "c", "d"},
        )
        assert diff.local_only == {"a"}
        assert diff.remote_only == {"d"}
        assert diff.both == {"b", "c"}

    def test_empty_sets(self) -> None:
        diff = inventory.diff_inventory(code=set(), remote=set())
        assert diff.local_only == set()
        assert diff.remote_only == set()
        assert diff.both == set()


class TestFetchRemotePromptNames:
    def test_paginates_and_collects_names(self) -> None:
        client = MagicMock()

        page1 = MagicMock()
        page1.data = [MagicMock(name="p"), MagicMock(name="p")]
        page1.data[0].name = "generate"
        page1.data[1].name = "client_agent"
        page1.meta = MagicMock(total_pages=2)

        page2 = MagicMock()
        page2.data = [MagicMock()]
        page2.data[0].name = "manager_agent"
        page2.meta = MagicMock(total_pages=2)

        client.api.prompts.list.side_effect = [page1, page2]

        names = inventory.fetch_remote_prompt_names(client)
        assert names == {"generate", "client_agent", "manager_agent"}
        assert client.api.prompts.list.call_count == 2

    def test_returns_empty_on_error(self) -> None:
        client = MagicMock()
        client.api.prompts.list.side_effect = RuntimeError("network down")
        # Best-effort: a failed fetch yields an empty set, never raises.
        assert inventory.fetch_remote_prompt_names(client) == set()


class TestFetchRemoteScoreConfigNames:
    def test_collects_config_names(self) -> None:
        client = MagicMock()
        page = MagicMock()
        c1 = MagicMock()
        c1.name = "confidence_score"
        c2 = MagicMock()
        c2.name = "grounded"
        page.data = [c1, c2]
        page.meta = MagicMock(total_pages=1)
        client.api.score_configs.get.return_value = page

        names = inventory.fetch_remote_score_config_names(client)
        assert names == {"confidence_score", "grounded"}

    def test_returns_empty_on_error(self) -> None:
        client = MagicMock()
        client.api.score_configs.get.side_effect = RuntimeError("boom")
        assert inventory.fetch_remote_score_config_names(client) == set()


class TestBuildClient:
    def test_disabled_langfuse_client_is_treated_as_unavailable(self) -> None:
        with patch.dict("sys.modules", {"langfuse": MagicMock()}):
            import langfuse

            langfuse.get_client.return_value = SimpleNamespace()

            assert inventory._build_client() is None


class TestFormatReport:
    def test_report_lists_drift_sections(self) -> None:
        prompt_diff = inventory.diff_inventory(
            code={"generate", "missing_prompt"}, remote={"generate", "orphan"}
        )
        score_diff = inventory.diff_inventory(
            code={"confidence_score"}, remote={"confidence_score", "unused_cfg"}
        )
        report = inventory.format_report(prompt_diff=prompt_diff, score_diff=score_diff)
        assert "missing_prompt" in report  # local_only prompt (drift!)
        assert "orphan" in report  # remote_only prompt
        assert "unused_cfg" in report  # remote_only score config
        # Headline counts present
        assert "PROMPTS" in report.upper()
        assert "SCORE" in report.upper()
