#!/usr/bin/env python3
"""User-runnable helper for issue #1721.

Replaces the broken ``tmux send-keys ... Enter`` pattern with the canonical
three-line form across the swarm orchestration prompt/skill files. The
affected files referenced by issue #1721 live *outside* the rag-fresh
repository, under ``~/.codex/`` and ``~/.config/opencode/skills/``, so this
fix cannot be done by a repo PR alone — running this script on the user's
local machine is the supported path.

The repo also enforces a regression guard
(``tests/contract/test_tmux_send_keys_pattern_contract.py``) so the broken
pattern never lands inside the rag-fresh repository again.

Usage:
    # Default targets: ~/.codex and ~/.config/opencode/skills
    python scripts/swarm_fix_send_keys_pattern.py
    python scripts/swarm_fix_send_keys_pattern.py --dry-run

    # Or pass explicit paths:
    python scripts/swarm_fix_send_keys_pattern.py path/to/skills

The rewrite preserves indentation, target/text arguments, and trailing
newline policy. It is idempotent: running the script twice in a row produces
no further changes. Markdown files are scanned only inside fenced
shell-flavoured code blocks (``bash``/``sh``/``shell``/``console``/``zsh``
or unlabelled), matching the contract test's behaviour.

Refs #1721, #1590.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path


# Forbidden pattern, mirrored from
# tests/contract/test_tmux_send_keys_pattern_contract.py. Kept in lockstep so
# every line the contract test would flag is also a candidate for rewrite by
# this script. The named groups support the rewrite path below.
_BROKEN = re.compile(
    r"""
    ^
    (?P<indent>\s*)
    (?!\#)
    (?P<body>
        .*\btmux\s+send-keys\b
        (?!.*\s-l\b)
        .*?
    )
    \s+Enter
    \s*
    (?P<comment>\#.*)?
    $
    """,
    re.VERBOSE,
)

# Markdown fenced-code languages that count as "shell" for our purposes.
# Empty string covers unlabelled fences (```...```) which are conventionally
# treated as shell in operations runbooks.
_SHELL_FENCE_LANGS: frozenset[str] = frozenset({"", "bash", "sh", "shell", "console", "zsh"})

# Files we touch. JSON/YAML/TXT etc. are not orchestration surfaces and could
# legitimately quote the broken pattern as data.
_SCAN_GLOBS: tuple[str, ...] = ("*.md", "*.sh")

# Default search roots when no path argument is supplied.
DEFAULT_TARGETS: tuple[str, ...] = ("~/.codex", "~/.config/opencode/skills")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_offenders(root: Path | str) -> list[tuple[Path, int, str]]:
    """Return ``(path, lineno, line)`` for every offending line under ``root``.

    ``root`` may be a directory or a single file. Lines are reported in stable
    sorted order by path, then by line number.
    """
    root = Path(root)
    offenders: list[tuple[Path, int, str]] = []
    for path in _iter_target_files(root):
        for lineno, line in _scan_offender_lines(path):
            offenders.append((path, lineno, line))
    return offenders


def fix_file(path: Path | str) -> int:
    """Rewrite offending lines in ``path`` in place; return replacement count.

    Returns ``0`` (no write) if the file contains no offenders.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8", errors="replace")
    new_text, replacements = _rewrite_text(path, original)
    if replacements > 0 and new_text != original:
        path.write_text(new_text, encoding="utf-8")
    return replacements


def fix_directory(root: Path | str, *, dry_run: bool = False) -> tuple[int, int]:
    """Walk ``root`` and apply (or report) fixes. Returns ``(files_touched, replacements)``."""
    root = Path(root)
    files_touched = 0
    replacements_total = 0
    for path in _iter_target_files(root):
        if dry_run:
            offenders = list(_scan_offender_lines(path))
            if offenders:
                files_touched += 1
                replacements_total += len(offenders)
                for lineno, line in offenders:
                    print(f"{path}:{lineno}: {line}")
        else:
            n = fix_file(path)
            if n > 0:
                files_touched += 1
                replacements_total += n
                suffix = "s" if n != 1 else ""
                print(f"FIXED {path} ({n} replacement{suffix})")
    return files_touched, replacements_total


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _iter_target_files(root: Path) -> Iterator[Path]:
    """Yield every shell/markdown file under ``root`` (or just ``root`` itself)."""
    if root.is_file():
        if any(root.match(g) for g in _SCAN_GLOBS):
            yield root
        return
    if not root.exists():
        return
    seen: set[Path] = set()
    for pattern in _SCAN_GLOBS:
        for p in sorted(root.rglob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def _iter_processed_lines(path: Path, lines: Iterable[str]) -> Iterator[tuple[int, str, bool]]:
    """Yield ``(lineno, raw_line, is_in_shell_context)`` for each input line.

    For ``.sh`` files every line is in shell context. For ``.md`` files only
    lines inside a shell-flavoured fenced code block are. Fence-delimiter
    lines themselves are reported as *not* in shell context, so they are
    never matched against the broken-pattern regex.
    """
    is_markdown = path.suffix.lower() == ".md"
    in_fence = not is_markdown
    fence_lang: str | None = None
    for lineno, raw in enumerate(lines, start=1):
        if is_markdown:
            stripped = raw.strip()
            if stripped.startswith("```"):
                if not in_fence:
                    in_fence = True
                    label = stripped.removeprefix("```").strip().lower()
                    fence_lang = label
                else:
                    in_fence = False
                    fence_lang = None
                yield lineno, raw, False
                continue
            if not in_fence:
                yield lineno, raw, False
                continue
            if fence_lang is not None and fence_lang not in _SHELL_FENCE_LANGS:
                yield lineno, raw, False
                continue
        yield lineno, raw, True


def _scan_offender_lines(path: Path) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, raw_line)`` for every offending line in ``path``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, raw, in_shell in _iter_processed_lines(path, text.splitlines()):
        if not in_shell:
            continue
        if _BROKEN.match(raw):
            yield lineno, raw.rstrip()


def _split_send_keys_tokens(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split a tokenised ``tmux send-keys`` invocation into (prefix, text).

    ``prefix`` is the verb plus any flags and their values
    (e.g. ``["tmux", "send-keys", "-t", "$T"]``).
    ``text`` is the trailing positional payload list (often a single quoted
    string, possibly empty).
    """
    if tokens[:2] != ["tmux", "send-keys"]:
        raise ValueError(f"Expected leading 'tmux send-keys', got {tokens[:2]!r}")
    prefix: list[str] = list(tokens[:2])
    rest = tokens[2:]
    i = 0
    # Flags that consume a value. tmux send-keys uses -t <target>; -N/-T
    # historically take a value too; -l/-X/-R/-H/-K/-M are bare flags.
    value_consuming = {"-t", "-T", "-N"}
    while i < len(rest) and rest[i].startswith("-"):
        flag = rest[i]
        prefix.append(flag)
        if flag in value_consuming and i + 1 < len(rest):
            prefix.append(rest[i + 1])
            i += 2
        else:
            i += 1
    return prefix, rest[i:]


def _rewrite_offender(line: str) -> list[str]:
    """Rewrite a single offending line into the canonical 3-line form.

    Returns the replacement lines (no trailing newlines). When the original
    line carried an inline comment, it is preserved on the first replacement
    line so the intent is not lost.
    """
    match = _BROKEN.match(line)
    if not match:
        raise ValueError(f"_rewrite_offender called on a non-offender: {line!r}")
    indent = match.group("indent")
    body = match.group("body")
    trailing_comment = match.group("comment") or ""
    # Tokenise non-POSIX so quotes/dollar-signs/$VARS pass through unchanged.
    try:
        tokens = shlex.split(body, posix=False)
    except ValueError:
        # Unbalanced quote — leave the line untouched rather than corrupt it.
        return [line]
    if tokens[:2] != ["tmux", "send-keys"]:
        # Defensive: regex should have prevented this.
        return [line]
    prefix_tokens, text_tokens = _split_send_keys_tokens(tokens)
    prefix_str = " ".join(prefix_tokens)
    comment_suffix = f"  {trailing_comment}" if trailing_comment else ""
    if text_tokens:
        text_str = " ".join(text_tokens)
        return [
            f"{indent}{prefix_str} -l {text_str}{comment_suffix}",
            f"{indent}sleep 0.25",
            f"{indent}{prefix_str} C-m",
        ]
    # No text payload: the original was just `tmux send-keys -t "$T" Enter`.
    # The submit-only form is one line.
    return [f"{indent}{prefix_str} C-m{comment_suffix}"]


def _rewrite_text(path: Path, text: str) -> tuple[str, int]:
    """Rewrite the contents of ``text`` (read from ``path``); return new text + count."""
    new_lines: list[str] = []
    replacements = 0
    for _lineno, raw, in_shell in _iter_processed_lines(path, text.splitlines()):
        if in_shell and _BROKEN.match(raw):
            new_lines.extend(_rewrite_offender(raw))
            replacements += 1
        else:
            new_lines.append(raw)
    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, replacements


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fix the broken `tmux send-keys ... Enter` pattern in swarm "
            "worker prompts and skill files (issue #1721)."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(f"paths to scan recursively. If omitted, defaults to {', '.join(DEFAULT_TARGETS)}."),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only report offenders; do not modify files",
    )
    args = parser.parse_args(argv)

    paths = args.paths or [os.path.expanduser(p) for p in DEFAULT_TARGETS]

    total_files = 0
    total_reps = 0
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            print(f"warning: skipping nonexistent path: {path}", file=sys.stderr)
            continue
        files, reps = fix_directory(path, dry_run=args.dry_run)
        total_files += files
        total_reps += reps

    verb = "Found" if args.dry_run else "Fixed"
    print(
        f"\n{verb} {total_reps} occurrence(s) across {total_files} file(s).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
