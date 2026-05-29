"""Langfuse prompt + score-config inventory (#2222 / Epic M).

Read-only audit that surfaces drift between what the code references and what
actually lives in Langfuse:

* **Prompts** — code calls ``get_prompt("<name>")`` /
  ``get_prompt_with_config("<name>")``. Compared against
  ``langfuse.api.prompts.list()``:
    - ``local_only``  : code references a prompt that does NOT exist in
      Langfuse -> the SDK silently falls back to the hardcoded ``fallback=``
      string. A real drift the operator should fix (create the prompt or drop
      the reference).
    - ``remote_only`` : a prompt exists in Langfuse but nothing fetches it
      (orphan / cleanup candidate).
* **Score configs** — code emits scores via ``score_current_trace(name=...)``
  in ``src/scoring.py``. Compared against ``langfuse.api.score_configs.get()``:
    - ``local_only``  : score emitted with no Score Config in Langfuse (no UI
      data-type / categories).
    - ``remote_only`` : a Score Config with no emitter.

Usage::

    uv run python -m scripts.audit.langfuse_inventory            # human report
    uv run python -m scripts.audit.langfuse_inventory --json     # machine-readable
    uv run python -m scripts.audit.langfuse_inventory --strict   # exit 1 on prompt local_only

The script is best-effort: a Langfuse fetch failure degrades to an empty
remote set (so the report still shows code-side names) and never raises.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

# Prompt-name source: first positional string arg to these callables.
_PROMPT_FETCH_FUNCS = {"get_prompt", "get_prompt_with_config"}

# Default code roots to scan for prompt references.
_DEFAULT_CODE_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "mini_app",
)

_SKIP_PATH_FRAGMENTS = ("/tests/", "/.venv/", "/__pycache__/", "/archive/")


@dataclass
class InventoryDiff:
    """Partition of code-referenced vs remote-present names."""

    local_only: set[str] = field(default_factory=set)
    remote_only: set[str] = field(default_factory=set)
    both: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Code scanning (pure)
# ---------------------------------------------------------------------------


def _first_literal_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant):
        value = call.args[0].value
        if isinstance(value, str):
            return value
    return None


def _call_func_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def scan_code_prompt_names(roots: list[Path]) -> set[str]:
    """Return prompt names passed as the first string literal to
    ``get_prompt`` / ``get_prompt_with_config`` across ``roots``."""
    names: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if any(frag in str(py_file) for frag in _SKIP_PATH_FRAGMENTS):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if _call_func_name(node) in _PROMPT_FETCH_FUNCS:
                    literal = _first_literal_arg(node)
                    if literal:
                        names.add(literal)
    return names


def scan_code_score_names(scoring_py: Path) -> set[str]:
    """Return score names emitted via ``score_*(name="...")`` in scoring.py."""
    names: set[str] = set()
    if not scoring_py.exists():
        return names
    try:
        tree = ast.parse(scoring_py.read_text(encoding="utf-8"))
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = _call_func_name(node) or ""
        if "score" not in fname.lower():
            continue
        for kw in node.keywords:
            if (
                kw.arg == "name"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                names.add(kw.value.value)
    return names


def diff_inventory(*, code: set[str], remote: set[str]) -> InventoryDiff:
    """Partition names into local_only / remote_only / both."""
    return InventoryDiff(
        local_only=code - remote,
        remote_only=remote - code,
        both=code & remote,
    )


# ---------------------------------------------------------------------------
# Remote fetch (best-effort, mocked in tests)
# ---------------------------------------------------------------------------


def _paginate(fetch, **kwargs) -> list[Any]:
    """Collect ``.data`` across pages using ``.meta.total_pages``."""
    out: list[Any] = []
    page = 1
    while True:
        resp = fetch(page=page, limit=100, **kwargs)
        out.extend(getattr(resp, "data", []) or [])
        meta = getattr(resp, "meta", None)
        total_pages = getattr(meta, "total_pages", 1) or 1
        if page >= total_pages:
            break
        page += 1
    return out


def fetch_remote_prompt_names(client: Any) -> set[str]:
    """Return the set of prompt names from ``langfuse.api.prompts.list()``."""
    try:
        items = _paginate(client.api.prompts.list)
        names: set[str] = set()
        for prompt in items:
            name = getattr(prompt, "name", None)
            if isinstance(name, str) and name:
                names.add(name)
        return names
    except Exception:
        return set()


def fetch_remote_score_config_names(client: Any) -> set[str]:
    """Return the set of Score Config names from
    ``langfuse.api.score_configs.get()``."""
    try:
        items = _paginate(client.api.score_configs.get)
        names: set[str] = set()
        for config in items:
            name = getattr(config, "name", None)
            if isinstance(name, str) and name:
                names.add(name)
        return names
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _section(title: str, diff: InventoryDiff) -> list[str]:
    lines = [
        f"## {title}",
        f"  in both code & Langfuse : {len(diff.both)}",
        f"  code only (DRIFT)       : {len(diff.local_only)}",
    ]
    for n in sorted(diff.local_only):
        lines.append(f"      - {n}")
    lines.append(f"  Langfuse only (orphan)  : {len(diff.remote_only)}")
    for n in sorted(diff.remote_only):
        lines.append(f"      - {n}")
    return lines


def format_report(*, prompt_diff: InventoryDiff, score_diff: InventoryDiff) -> str:
    lines = ["# Langfuse inventory (#2222)", ""]
    lines += _section("PROMPTS", prompt_diff)
    lines.append("")
    lines += _section("SCORE CONFIGS", score_diff)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_client() -> Any | None:
    try:
        from langfuse import get_client

        client = get_client()
        return client if hasattr(client, "api") else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Langfuse prompt + score-config inventory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when code references a prompt missing from Langfuse",
    )
    args = parser.parse_args(argv)

    code_prompts = scan_code_prompt_names(list(_DEFAULT_CODE_ROOTS))
    code_scores = scan_code_score_names(REPO_ROOT / "src" / "scoring.py")

    client = _build_client()
    remote_prompts = fetch_remote_prompt_names(client) if client else set()
    remote_scores = fetch_remote_score_config_names(client) if client else set()

    prompt_diff = diff_inventory(code=code_prompts, remote=remote_prompts)
    score_diff = diff_inventory(code=code_scores, remote=remote_scores)

    if args.json:
        print(
            json.dumps(
                {
                    "prompts": {
                        "local_only": sorted(prompt_diff.local_only),
                        "remote_only": sorted(prompt_diff.remote_only),
                        "both": sorted(prompt_diff.both),
                    },
                    "score_configs": {
                        "local_only": sorted(score_diff.local_only),
                        "remote_only": sorted(score_diff.remote_only),
                        "both": sorted(score_diff.both),
                    },
                    "langfuse_reachable": client is not None,
                },
                indent=2,
            )
        )
    else:
        print(format_report(prompt_diff=prompt_diff, score_diff=score_diff))
        if client is None:
            print("\n(note: Langfuse client unavailable — remote sets empty)")

    if args.strict and prompt_diff.local_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
