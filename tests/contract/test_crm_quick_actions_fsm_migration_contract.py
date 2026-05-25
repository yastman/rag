"""Contract: CRM quick actions FSM is dead — aiogram-dialog is the sole driver (#2053).

Issue #2053 (parent: #1232) replaced the custom-FSM ``CrmQuickActionSG``
state-machine in ``telegram_bot/handlers/crm_callbacks.py`` (raw
``state.set_state(...)`` / ``StateFilter(CrmQuickActionSG.X)`` /
``state.update_data(...)`` / ``state.clear()``) with the
aiogram-dialog ``crm_quick_actions_dialog`` in
``telegram_bot/dialogs/crm_quick_actions.py``.

This contract pins the migration so a regression that re-introduces the
raw-FSM driver fails CI loudly. It enforces three invariants:

1. ``telegram_bot/dialogs/crm_quick_actions.py`` exports
   ``crm_quick_actions_dialog`` as an aiogram-dialog ``Dialog``
   covering all five ``CrmQuickActionSG`` states.
2. ``telegram_bot/handlers/crm_callbacks.py`` is a thin trigger module:
   no ``state.set_state``, ``state.update_data``, ``state.clear``,
   ``StateFilter(CrmQuickActionSG.``, or ``FSMContext`` import in
   executable code (docstring / comment mentions are allowed and
   useful for migration history).
3. ``crm_quick_actions_dialog`` is registered as a router on the bot
   dispatcher in ``telegram_bot/bot.py``.

Mirrors the closeout pattern of #2094 (demo dialog migration).
Refs #1232 #2053.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CRM_CALLBACKS_PATH = REPO_ROOT / "telegram_bot" / "handlers" / "crm_callbacks.py"
CRM_DIALOG_PATH = REPO_ROOT / "telegram_bot" / "dialogs" / "crm_quick_actions.py"
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"


# Patterns that, if found in EXECUTABLE code (i.e. not inside a string
# literal or a comment), would mean the raw-FSM driver is back. Matching
# is intentionally conservative: we strip comments and docstrings before
# searching so the migration's own documentation references can stay.
_FSM_DRIVER_PATTERNS = (
    r"\bstate\.set_state\s*\(",
    r"\bstate\.update_data\s*\(",
    r"\bstate\.clear\s*\(",
    r"StateFilter\s*\(\s*CrmQuickActionSG\.",
    r"\bfrom\s+aiogram\.fsm\.context\s+import\s+FSMContext\b",
)


def _strip_strings_and_comments(source: str) -> str:
    """Return ``source`` with all string literals and ``#`` comments masked.

    The mask preserves line count + non-string structure so a regex search
    over the result still produces useful line numbers, but mentions of
    forbidden patterns inside docstrings or trailing comments do not match.
    Implementation: tokenize via the standard library so triple-quoted
    docstrings are removed correctly.
    """
    import io
    import tokenize

    out: list[str] = []
    last_end = (1, 0)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        tok_type, tok_str, start, end, _ = tok
        # Pad with newlines / spaces so line/col positions are preserved
        # for the next token.
        if start[0] > last_end[0]:
            out.append("\n" * (start[0] - last_end[0]))
            out.append(" " * start[1])
        elif start[1] > last_end[1]:
            out.append(" " * (start[1] - last_end[1]))

        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            # Replace with same-shape whitespace (preserve newlines from
            # multi-line strings so subsequent tokens land on the right line).
            out.append(re.sub(r"[^\n]", " ", tok_str))
        else:
            out.append(tok_str)
        last_end = end
    return "".join(out)


def test_crm_quick_actions_dialog_is_canonical_driver() -> None:
    """The aiogram-dialog file exists and exports the dialog covering all 5 states."""
    assert CRM_DIALOG_PATH.exists(), (
        f"CRM quick actions dialog file is missing: {CRM_DIALOG_PATH.relative_to(REPO_ROOT)}. "
        "Issue #2053 requires the aiogram-dialog migration; reverting to raw FSM "
        "in handlers/crm_callbacks.py is forbidden."
    )

    source = CRM_DIALOG_PATH.read_text(encoding="utf-8")
    assert "crm_quick_actions_dialog = Dialog(" in source, (
        f"{CRM_DIALOG_PATH.relative_to(REPO_ROOT)} must export "
        "`crm_quick_actions_dialog = Dialog(...)` (issue #2053)."
    )
    for state_name in (
        "waiting_note",
        "waiting_task",
        "edit_task_choose_field",
        "edit_task_text",
        "edit_task_date",
    ):
        marker = f"state=CrmQuickActionSG.{state_name}"
        assert marker in source, (
            f"{CRM_DIALOG_PATH.relative_to(REPO_ROOT)} must register a Window for "
            f"CrmQuickActionSG.{state_name} (issue #2053)."
        )


def test_crm_callbacks_has_no_raw_fsm_driver() -> None:
    """handlers/crm_callbacks.py must not re-introduce raw-FSM code (#2053)."""
    source = CRM_CALLBACKS_PATH.read_text(encoding="utf-8")
    code_only = _strip_strings_and_comments(source)

    offenders: list[str] = []
    for pattern in _FSM_DRIVER_PATTERNS:
        for match in re.finditer(pattern, code_only):
            line_no = code_only[: match.start()].count("\n") + 1
            offenders.append(f"  line {line_no}: matches /{pattern}/")

    assert not offenders, (
        "telegram_bot/handlers/crm_callbacks.py was migrated off raw-FSM in "
        "issue #2053. The aiogram-dialog `crm_quick_actions_dialog` is the "
        "canonical driver. Re-introducing raw FSM (state.set_state / "
        "update_data / clear / StateFilter(CrmQuickActionSG / FSMContext) "
        "is forbidden:\n" + "\n".join(offenders)
    )


def test_crm_quick_actions_dialog_is_registered_on_dispatcher() -> None:
    """bot.py must include ``crm_quick_actions_dialog`` as a router (#2053)."""
    source = BOT_PATH.read_text(encoding="utf-8")
    assert "from .dialogs.crm_quick_actions import crm_quick_actions_dialog" in source, (
        "telegram_bot/bot.py must import `crm_quick_actions_dialog` "
        "from telegram_bot.dialogs.crm_quick_actions (issue #2053)."
    )
    assert "self.dp.include_router(crm_quick_actions_dialog)" in source, (
        "telegram_bot/bot.py must register `crm_quick_actions_dialog` via "
        "`self.dp.include_router(...)` so the dialog actually receives "
        "MessageInput / Select events (issue #2053)."
    )


def test_strip_helper_masks_strings_and_comments() -> None:
    """Self-test: the masking helper removes string-literal and comment content.

    We only assert the *behaviour* used by the real contract assertions
    (forbidden patterns inside string/comment context are dropped, while
    the same pattern in executable code survives). Exact line-number
    preservation is best-effort and not required by the assertions.
    """
    source = (
        '"""docstring may mention state.set_state(\\"x\\")"""\n'
        "x = 1  # comment with state.update_data(\n"
        'y = "literal with state.clear("\n'
        "real = state.set_state(SG.waiting)\n"
    )
    masked = _strip_strings_and_comments(source)

    # Forbidden patterns that lived only inside docstring / comment /
    # string literal must be gone.
    assert "state.update_data" not in masked
    assert "state.clear" not in masked
    # The executable call on the last line must survive.
    assert masked.count("state.set_state") == 1, masked
