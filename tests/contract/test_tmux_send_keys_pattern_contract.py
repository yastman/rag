"""Contract test: forbid the broken ``tmux send-keys ... Enter`` pattern.

Issues ***REMOVED***1721 and ***REMOVED***1590 document a real bug in swarm worker prompt relays:

    tmux send-keys -t "$ORCH_TARGET" "[DONE] $WORKER_NAME $REPORT_FILE" Enter

The trailing literal ``Enter`` token sends ``\\r``, which Codex TUI does not
interpret as composer submit. The text appears in the input field but is
never sent. The orchestrator and worker deadlock.

The fix is to (1) write text with the literal flag, (2) sleep briefly to let
the TUI process input, and (3) submit with ``C-m`` in a separate call:

    tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
    sleep 0.25
    tmux send-keys -t "$ORCH_TARGET" C-m

The actual orchestration scripts and skills affected by these issues live
*outside* this repository (under ``/home/user/.codex/`` and
``/home/user/.config/opencode/`` per the swarm worker policy plan in
``docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md``).
This test is a forward-looking guardrail: if any swarm-orchestration
documentation, skill, or shell script that *does* land in this repo ever
introduces the broken pattern, this test will fail and surface the
regression before it reaches a worker.

Contract:
    No tracked Markdown file under ``.codex/``, ``skills/``, or
    ``docs/superpowers/`` and no shell script under ``scripts/`` may contain
    a non-comment line whose stripped form starts with ``tmux send-keys``
    and ends with the bare token ``Enter`` (no ``-l`` flag on that line).

Refs ***REMOVED***1721, ***REMOVED***1590.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

***REMOVED*** Directories scanned for the broken pattern. Any subset may be missing in a
***REMOVED*** given checkout (e.g. ``.codex/`` is gitignored on some hosts); missing dirs
***REMOVED*** are silently skipped so the test stays portable.
SCAN_TARGETS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (REPO_ROOT / ".codex", ("*.md", "*.sh")),
    (REPO_ROOT / "skills", ("*.md", "*.sh")),
    (REPO_ROOT / "docs" / "superpowers", ("*.md", "*.sh")),
    (REPO_ROOT / "scripts", ("*.sh",)),
)

***REMOVED*** Match a line that:
***REMOVED***   * contains the verb ``tmux send-keys`` (allowing arbitrary args/quotes)
***REMOVED***   * does NOT contain the ``-l`` literal flag on the same line
***REMOVED***   * ends with the bare token ``Enter`` (optionally followed by a comment
***REMOVED***     or trailing whitespace, but not by another argument)
***REMOVED***
***REMOVED*** Examples that MUST match (broken):
***REMOVED***     tmux send-keys -t "$ORCH" "msg" Enter
***REMOVED***     tmux send-keys -t "$T" Enter
***REMOVED***     tmux send-keys -t "$T" "[DONE]" Enter   ***REMOVED*** trailing comment is ok
***REMOVED***
***REMOVED*** Examples that MUST NOT match (allowed):
***REMOVED***     tmux send-keys -t "$T" -l "msg"
***REMOVED***     tmux send-keys -t "$T" C-m
***REMOVED***     tmux send-keys -t "$T" "Press Enter to continue"   ***REMOVED*** quoted, not a token
***REMOVED***     ***REMOVED*** tmux send-keys ... Enter  (comment line)
_BROKEN = re.compile(
    r"""
    ^\s*                       ***REMOVED*** optional leading indent
    (?!\***REMOVED***)                     ***REMOVED*** not a markdown/bash comment line
    .*\btmux\s+send-keys\b     ***REMOVED*** the verb
    (?!.*\s-l\b)               ***REMOVED*** no -l flag anywhere on this line
    .*\sEnter                  ***REMOVED*** bare Enter token preceded by whitespace
    \s*                        ***REMOVED*** trailing whitespace
    (?:\***REMOVED***.*)?                  ***REMOVED*** optional trailing shell comment
    $
    """,
    re.VERBOSE,
)


def _iter_files() -> list[Path]:
    """Return every file under any existing scan target with a matching glob."""
    files: list[Path] = []
    for root, patterns in SCAN_TARGETS:
        if not root.exists():
            continue
        for pattern in patterns:
            files.extend(p for p in root.rglob(pattern) if p.is_file())
    return sorted(set(files))


def _find_offending_lines(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, line)] for every broken pattern line in ``path``.

    Markdown fenced-code awareness: the ``Enter`` token is bug-relevant only
    when it appears as a real command (inside fenced ``bash``/``sh`` blocks
    or in plain ``.sh`` scripts). Markdown prose lines that mention
    ``tmux send-keys ... Enter`` outside a code fence are treated as
    documentation references and are not flagged.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    is_markdown = path.suffix.lower() == ".md"

    in_code_fence = not is_markdown  ***REMOVED*** .sh files are "always code"
    code_fence_lang: str | None = None
    offenders: list[tuple[int, str]] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if is_markdown:
            stripped = raw.strip()
            if stripped.startswith("```"):
                if not in_code_fence:
                    in_code_fence = True
                    code_fence_lang = stripped.removeprefix("```").strip().lower() or None
                else:
                    in_code_fence = False
                    code_fence_lang = None
                continue
            ***REMOVED*** Only flag matches inside shell-flavoured fenced blocks. Other
            ***REMOVED*** languages (python, yaml, json, ...) cannot execute tmux.
            if not in_code_fence:
                continue
            if code_fence_lang not in (None, "", "bash", "sh", "shell", "console", "zsh"):
                continue

        if _BROKEN.match(raw):
            offenders.append((lineno, raw.rstrip()))

    return offenders


def test_no_broken_tmux_send_keys_enter_pattern() -> None:
    """Fail if any tracked swarm-orchestration file uses the broken pattern.

    Refs ***REMOVED***1721, ***REMOVED***1590.
    """
    offenders: list[str] = []
    for f in _iter_files():
        for lineno, line in _find_offending_lines(f):
            rel = f.relative_to(REPO_ROOT)
            offenders.append(f"  {rel}:{lineno}: {line}")

    if offenders:
        msg = (
            "Broken `tmux send-keys ... Enter` pattern found (refs ***REMOVED***1721, ***REMOVED***1590). "
            "Replace with the three-line form:\n"
            '    tmux send-keys -t "$T" -l "<text>"\n'
            "    sleep 0.25\n"
            '    tmux send-keys -t "$T" C-m\n'
            "Offending lines:\n" + "\n".join(offenders)
        )
        raise AssertionError(msg)


def test_contract_regex_matches_canonical_broken_examples() -> None:
    """Self-test: the regex catches the canonical broken forms from ***REMOVED***1721/***REMOVED***1590."""
    broken_samples = [
        'tmux send-keys -t "$ORCH_TARGET" "[DONE] $WORKER_NAME $REPORT_FILE" Enter',
        'tmux send-keys -t "$T" Enter',
        '    tmux send-keys -t "$T" "msg" Enter',
        'tmux send-keys -t "$T" "msg" Enter   ',
    ]
    for sample in broken_samples:
        assert _BROKEN.match(sample), f"regex failed to flag broken sample: {sample!r}"


def test_contract_regex_ignores_correct_pattern() -> None:
    """Self-test: the regex does NOT flag the corrected three-line pattern."""
    allowed_samples = [
        'tmux send-keys -t "$T" -l "[DONE] $WORKER $REPORT"',
        'tmux send-keys -t "$T" C-m',
        '***REMOVED*** tmux send-keys -t "$T" "msg" Enter   (commented out)',
        'tmux send-keys -t "$T" "Press Enter to continue" C-m',
    ]
    for sample in allowed_samples:
        assert not _BROKEN.match(sample), f"regex wrongly flagged allowed sample: {sample!r}"
