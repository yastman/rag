"""Contract: no raw aiogram FSM in ``telegram_bot/handlers/`` outside documented exceptions (#1232).

Umbrella issue #1232 required migrating bot handler modules from raw
aiogram FSM (``StatesGroup`` + ``state.set_state(...)`` /
``state.update_data(...)`` / ``state.clear()``) to aiogram-dialog. The
migration was delivered across three child issues plus one explicit
design exception:

* ``handlers/crm_callbacks.py`` — migrated in #2053 (now drives
  ``crm_quick_actions_dialog``; pinned by
  ``tests/contract/test_crm_quick_actions_fsm_migration_contract.py``).
* ``handlers/demo_handler.py`` — migrated in #2054 (now drives
  ``demo_dialog``).
* ``handlers/phone_collector.py`` — **documented design exception**
  (#2055): the lead-capture flow needs
  ``KeyboardButton(request_contact=True)`` rendered via
  ``ReplyKeyboardMarkup`` for one-tap contact share. aiogram-dialog
  renders inline keyboards only and has no ``request_contact`` widget,
  so a "consistency refactor" would force users to type their phone
  manually and measurably reduces opt-in rate.
* ``handlers/handoff.py`` — **single-state guard** wrapping the
  aiogram-dialog ``HandoffSG``. The ``HandoffStates.active`` state is a
  re-entry flag (so a second ``/start`` does not re-launch
  qualification), not an FSM that drives a conversation.

This contract pins the migration so a regression that re-introduces a
raw FSM driver in any *other* handler module fails CI loudly. Each
exempted handler must continue to document its rationale in the module
docstring; the contract greps for the issue marker as a tripwire so
removing the rationale also fails the test (which is a useful prompt to
either restore the rationale or close the exception).

Refs #1232 #2053 #2054 #2055.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDLERS_DIR = REPO_ROOT / "telegram_bot" / "handlers"


# Files exempted from the no-raw-FSM rule, plus the issue marker that
# must remain in the module docstring as evidence of the design rationale.
# A regression that drops the rationale is treated as the same kind of
# drift as a regression that re-introduces raw FSM elsewhere.
EXEMPTED_HANDLERS: dict[str, frozenset[str]] = {
    # phone_collector keeps raw FSM because aiogram-dialog cannot render
    # `KeyboardButton(request_contact=True)` via `ReplyKeyboardMarkup`.
    # Documented in #2055.
    "phone_collector.py": frozenset({"#1232", "#2055"}),
    # handoff carries one guard state (`HandoffStates.active`) so the
    # qualification flow is not re-entered while a manager handoff is in
    # progress. Qualification UI itself runs in `dialogs/handoff.py`
    # (`HandoffSG`).
    "handoff.py": frozenset({"HandoffSG"}),
}


# Patterns that count as "raw FSM driver" code — declaring a state
# machine or pushing the user into a state are the dangerous shapes.
# ``state.clear()`` is intentionally NOT in this list: clearing FSM
# state is a legitimate cleanup operation that any handler may need
# (the canonical example is the ``/clear`` command in
# ``command_handlers.py``, which resets aiogram-dialog and the
# underlying FSM in one shot). Matched against *executable* code only
# — docstrings, comments, and string literals are masked out so the
# same patterns can appear in migration-history notes without tripping
# the contract.
_RAW_FSM_PATTERNS = (
    "StatesGroup",
    "state.set_state",
    "state.update_data",
)


def _strip_strings_and_comments(source: str) -> str:
    """Mask string literals and ``#`` comments in ``source``.

    The mask preserves overall character offsets per line (newlines are
    kept as-is) so a regex/substring search over the result still
    produces useful line numbers, but mentions of the forbidden
    patterns inside docstrings or trailing comments do not match.
    """
    import io
    import re
    import tokenize

    out: list[str] = []
    last_end = (1, 0)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        tok_type, tok_str, start, end, _ = tok
        if start[0] > last_end[0]:
            out.append("\n" * (start[0] - last_end[0]))
            out.append(" " * start[1])
        elif start[1] > last_end[1]:
            out.append(" " * (start[1] - last_end[1]))

        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            out.append(re.sub(r"[^\n]", " ", tok_str))
        else:
            out.append(tok_str)
        last_end = end
    return "".join(out)


def _module_docstring(path: Path) -> str:
    """Return the module-level docstring or empty string."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return ""
    return ast.get_docstring(tree) or ""


def _handler_files() -> list[Path]:
    """Return every regular ``.py`` file under ``telegram_bot/handlers/``."""
    return sorted(p for p in HANDLERS_DIR.glob("*.py") if p.name != "__init__.py")


def test_handlers_dir_exists() -> None:
    """Sanity: the handlers directory must exist where we expect it."""
    assert HANDLERS_DIR.is_dir(), (
        f"Expected {HANDLERS_DIR.relative_to(REPO_ROOT)} to be a directory; "
        f"the contract scans it for raw-FSM regressions."
    )


def test_no_raw_fsm_outside_exemptions() -> None:
    """Each non-exempted handler must contain no raw-FSM driver code (#1232)."""
    offenders: list[str] = []
    for path in _handler_files():
        if path.name in EXEMPTED_HANDLERS:
            continue
        masked = _strip_strings_and_comments(path.read_text(encoding="utf-8"))
        for pattern in _RAW_FSM_PATTERNS:
            if pattern in masked:
                idx = masked.index(pattern)
                line = masked[:idx].count("\n") + 1
                offenders.append(f"  telegram_bot/handlers/{path.name}:{line} contains {pattern!r}")

    assert not offenders, (
        "Raw aiogram FSM detected in a handler module that is not on the "
        "exemption allowlist. Issue #1232 requires aiogram-dialog for "
        "user-facing handler flows. If a new exception is justified, add "
        "the file to EXEMPTED_HANDLERS in this test with the issue marker, "
        "and document the rationale in the module docstring (see "
        "phone_collector.py for the canonical example).\n" + "\n".join(offenders)
    )


def test_exempted_handlers_keep_their_rationale_marker() -> None:
    """Each exempted handler must reference its design-decision issue in the docstring."""
    offenders: list[str] = []
    for filename, expected_markers in EXEMPTED_HANDLERS.items():
        path = HANDLERS_DIR / filename
        if not path.exists():
            offenders.append(f"  {filename}: file missing — exemption is stale")
            continue
        docstring = _module_docstring(path)
        if not docstring:
            offenders.append(f"  {filename}: no module docstring; cannot verify rationale")
            continue
        missing = [m for m in expected_markers if m not in docstring]
        if missing:
            offenders.append(
                f"  {filename}: docstring missing rationale marker(s) {sorted(missing)!r}"
            )

    assert not offenders, (
        "Exempted handlers must keep their rationale marker in the module "
        "docstring. The marker is the contract's evidence that the "
        "exception is intentional. If the rationale changed, update both "
        "the docstring and EXEMPTED_HANDLERS:\n" + "\n".join(offenders)
    )


def test_exemption_list_is_minimal() -> None:
    """The exemption list must not grow without an explicit code review.

    This is a *forward-only* guardrail: the count is pinned to the
    current accepted set (2 files). Adding a new exemption forces a
    same-PR update to this number, which forces a reviewer to consider
    whether the exception is really justified.
    """
    expected_count = 2
    actual_count = len(EXEMPTED_HANDLERS)
    assert actual_count == expected_count, (
        f"EXEMPTED_HANDLERS has {actual_count} entries but the contract "
        f"is pinned at {expected_count}. If you intentionally added or "
        "removed an exception, update `expected_count` in the same PR "
        "with a comment justifying the change."
    )
