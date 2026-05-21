# tests/unit/scripts/test_swarm_fix_send_keys_pattern.py
"""Unit tests for ``scripts/swarm_fix_send_keys_pattern.py``.

Issue #1721 (and its older sibling #1590) describes the broken
``tmux send-keys ... Enter`` pattern used by swarm worker prompts and
skill files to wake the orchestrator. The trailing literal ``Enter``
token sends ``\\r``, which Codex TUI does not interpret as composer
submit, and the worker/orchestrator deadlocks.

The repo already ships a regression guard
(``tests/contract/test_tmux_send_keys_pattern_contract.py``) that fails
CI if the broken pattern lands in a tracked Markdown/shell file. The
actual broken files referenced in #1721 live *outside* the repository,
under ``~/.codex/`` and ``~/.config/opencode/skills/``. They cannot be
fixed by a repo PR alone.

This module pins the contract for a *user-runnable helper script*,
``scripts/swarm_fix_send_keys_pattern.py``, that:

1. Finds every offending line in a target directory tree (``.md`` and
   ``.sh`` files, Markdown-aware so fenced code is the only Markdown
   surface checked).
2. Rewrites each offender into the canonical three-line form, preserving
   the existing indentation and the original target/text arguments.
3. Is idempotent (running it twice in a row produces no further
   changes).
4. Supports a non-destructive dry-run mode that only reports.
5. Exposes a small Python API used by the CLI and by these tests.

Refs #1721, #1590.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module loader (the script lives under ``scripts/``, which is not a package)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "swarm_fix_send_keys_pattern.py"


@pytest.fixture(scope="module")
def fix_module():
    """Load ``scripts/swarm_fix_send_keys_pattern.py`` as a module."""
    spec = importlib.util.spec_from_file_location("_swarm_fix_send_keys_pattern", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, SCRIPT_PATH
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Sample texts
# ---------------------------------------------------------------------------

# Canonical broken sample directly from issue #1721's "Affected files" list.
BROKEN_SH = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail
    tmux send-keys -t "$ORCH_TARGET" "[DONE] $WORKER_NAME $REPORT_FILE" Enter
    """
)

# What the canonical broken sample must become after the fix runs. Indentation
# of the original line is preserved; the same target and text-payload are
# reused; the three-line form is written immediately in place of the offender.
FIXED_SH = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail
    tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
    sleep 0.25
    tmux send-keys -t "$ORCH_TARGET" C-m
    """
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# find_offenders: read-only audit
# ---------------------------------------------------------------------------


class TestFindOffenders:
    def test_flags_canonical_sh_offender(self, fix_module, tmp_path):
        target = tmp_path / "wake.sh"
        _write(target, BROKEN_SH)

        offenders = fix_module.find_offenders(tmp_path)

        assert len(offenders) == 1
        path, lineno, line = offenders[0]
        assert path == target
        assert lineno == 3
        assert "Enter" in line
        assert " -l " not in line

    def test_ignores_correct_three_line_form(self, fix_module, tmp_path):
        _write(tmp_path / "ok.sh", FIXED_SH)

        offenders = fix_module.find_offenders(tmp_path)

        assert offenders == []

    def test_ignores_comment_lines(self, fix_module, tmp_path):
        _write(
            tmp_path / "doc.sh",
            '# tmux send-keys -t "$T" "msg" Enter   (commented out)\n',
        )

        offenders = fix_module.find_offenders(tmp_path)

        assert offenders == []

    def test_ignores_quoted_press_enter_prose(self, fix_module, tmp_path):
        _write(
            tmp_path / "ui.sh",
            'tmux send-keys -t "$T" "Press Enter to continue" C-m\n',
        )

        offenders = fix_module.find_offenders(tmp_path)

        assert offenders == []

    def test_markdown_only_flags_inside_shell_fenced_blocks(self, fix_module, tmp_path):
        markdown = textwrap.dedent(
            """\
            # Title

            Inline prose: tmux send-keys -t "$T" "msg" Enter (this is documentation).

            ```python
            # python code, must not be flagged even though Enter appears:
            tmux send-keys -t "$T" "msg" Enter
            ```

            ```bash
            tmux send-keys -t "$T" "[DONE]" Enter
            ```
            """
        )
        target = tmp_path / "guide.md"
        _write(target, markdown)

        offenders = fix_module.find_offenders(tmp_path)

        assert len(offenders) == 1
        path, lineno, _line = offenders[0]
        assert path == target
        # Line 11 is the offender inside the bash fence.
        assert lineno == 11

    def test_recurses_into_subdirectories(self, fix_module, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        _write(nested / "wake.sh", BROKEN_SH)

        offenders = fix_module.find_offenders(tmp_path)

        assert len(offenders) == 1
        assert offenders[0][0] == nested / "wake.sh"

    def test_skips_unrelated_extensions(self, fix_module, tmp_path):
        # JSON/YAML/TXT files are not orchestration surfaces and must be
        # ignored even if they happen to contain the broken pattern in a
        # quoted string.
        _write(
            tmp_path / "config.json",
            '{"hint": "tmux send-keys -t \\"$T\\" \\"msg\\" Enter"}\n',
        )

        offenders = fix_module.find_offenders(tmp_path)

        assert offenders == []


# ---------------------------------------------------------------------------
# fix_file: the rewrite engine
# ---------------------------------------------------------------------------


class TestFixFile:
    def test_canonical_sh_is_rewritten_to_three_line_form(self, fix_module, tmp_path):
        target = tmp_path / "wake.sh"
        _write(target, BROKEN_SH)

        replacements = fix_module.fix_file(target)

        assert replacements == 1
        assert target.read_text(encoding="utf-8") == FIXED_SH

    def test_idempotent_second_run_is_a_noop(self, fix_module, tmp_path):
        target = tmp_path / "wake.sh"
        _write(target, BROKEN_SH)
        fix_module.fix_file(target)
        first_pass = target.read_text(encoding="utf-8")

        replacements = fix_module.fix_file(target)

        assert replacements == 0
        assert target.read_text(encoding="utf-8") == first_pass == FIXED_SH

    def test_preserves_leading_indentation(self, fix_module, tmp_path):
        target = tmp_path / "wake.sh"
        _write(
            target,
            '    tmux send-keys -t "$ORCH" "[DONE]" Enter\n',
        )

        replacements = fix_module.fix_file(target)

        assert replacements == 1
        rewritten = target.read_text(encoding="utf-8")
        # Each of the 3 replacement lines should keep the original 4-space
        # indent.
        for line in rewritten.splitlines():
            assert line == "" or line.startswith("    "), line
        assert '    tmux send-keys -t "$ORCH" -l "[DONE]"' in rewritten
        assert "    sleep 0.25" in rewritten
        assert '    tmux send-keys -t "$ORCH" C-m' in rewritten

    def test_multiple_offenders_in_same_file_are_all_rewritten(self, fix_module, tmp_path):
        target = tmp_path / "multi.sh"
        _write(
            target,
            textwrap.dedent(
                """\
                tmux send-keys -t "$T" "first" Enter
                echo between
                tmux send-keys -t "$T" "second" Enter
                """
            ),
        )

        replacements = fix_module.fix_file(target)

        assert replacements == 2
        rewritten = target.read_text(encoding="utf-8")
        assert rewritten.count("sleep 0.25") == 2
        assert rewritten.count("C-m") == 2
        assert " Enter\n" not in rewritten

    def test_only_rewrites_inside_markdown_fenced_shell_blocks(self, fix_module, tmp_path):
        target = tmp_path / "guide.md"
        original = textwrap.dedent(
            """\
            Prose line: tmux send-keys -t "$T" "msg" Enter (do not touch).

            ```bash
            tmux send-keys -t "$T" "[DONE]" Enter
            ```
            """
        )
        _write(target, original)

        replacements = fix_module.fix_file(target)

        assert replacements == 1
        rewritten = target.read_text(encoding="utf-8")
        # Prose line untouched.
        assert 'Prose line: tmux send-keys -t "$T" "msg" Enter (do not touch).' in rewritten
        # Fenced block rewritten.
        assert 'tmux send-keys -t "$T" -l "[DONE]"' in rewritten
        assert "sleep 0.25" in rewritten
        assert 'tmux send-keys -t "$T" C-m' in rewritten


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


class TestCLI:
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dry_run_reports_offenders_without_modifying_files(self, tmp_path):
        target = tmp_path / "wake.sh"
        _write(target, BROKEN_SH)

        result = self._run("--dry-run", str(tmp_path))

        assert result.returncode == 0, result.stderr
        # The dry-run must mention the offending file and line number.
        assert str(target) in result.stdout
        assert "wake.sh:3" in result.stdout
        # File content must be unchanged.
        assert target.read_text(encoding="utf-8") == BROKEN_SH

    def test_default_invocation_rewrites_in_place(self, tmp_path):
        target = tmp_path / "wake.sh"
        _write(target, BROKEN_SH)

        result = self._run(str(tmp_path))

        assert result.returncode == 0, result.stderr
        assert target.read_text(encoding="utf-8") == FIXED_SH

    def test_clean_tree_exits_zero(self, tmp_path):
        _write(tmp_path / "ok.sh", FIXED_SH)

        result = self._run(str(tmp_path))

        assert result.returncode == 0, result.stderr
