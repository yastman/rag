"""FSM coverage tests for ``telegram_bot.dialogs.states`` (issue ***REMOVED***1093).

These tests enforce three contracts that the dialog backlog called out:

1. **State enum coverage** — every documented ``StatesGroup`` exposes the
   expected ``State`` attributes. Catches accidental rename / removal.
2. **Wizard step ordering** — multi-step wizards (funnel, create lead,
   create contact, create task) reference their states in the source
   files in the documented order. Catches re-ordering bugs that would
   silently skip a step.
3. **No dead states** — every ``State`` declared in ``states.py`` is
   referenced by at least one dialog module via ``state=<group>.<name>``.
   Dead states usually mean a refactor left a step orphaned.

The tests parse files as text/AST and never import the aiogram-dialog
runtime, so they run on the fast ``test-unit`` lane without optional
extras.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from aiogram.fsm.state import State, StatesGroup

from telegram_bot.dialogs import states as states_module


DIALOGS_DIR = Path(__file__).resolve().parents[3] / "telegram_bot" / "dialogs"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. State enum coverage
***REMOVED*** ---------------------------------------------------------------------------


***REMOVED*** (StatesGroup class name, expected state attribute names) — locked from ***REMOVED***1093
EXPECTED_STATE_GROUPS: dict[str, tuple[str, ...]] = {
    "ClientMenuSG": ("main",),
    "ManagerMenuSG": ("main",),
    "SettingsSG": ("main", "language", "crm"),
    "FunnelSG": (
        "city",
        "property_type",
        "budget",
        "preferences",
        "pref_floor",
        "pref_view",
        "pref_furnished",
        "pref_promotion",
        "pref_area",
        "pref_complex",
        "pref_section",
        "summary",
        "change_filter",
    ),
    "ViewingSG": ("date",),
    "FaqSG": ("main",),
    "CrmSubmenuSG": ("main",),
    "CRMMenuSG": ("main",),
    "CreateLeadSG": ("name", "budget", "pipeline", "summary"),
    "CreateContactSG": ("first_name", "last_name", "phone", "email", "summary"),
    "CreateTaskSG": ("text", "task_type", "lead_id", "due_date", "summary"),
    "TasksMenuSG": ("main",),
    "MyTasksSG": ("filter", "list"),
    "CreateNoteSG": ("entity_type", "entity_id", "text", "summary"),
    "SearchSG": ("query", "results"),
    "LeadsMenuSG": ("main",),
    "MyLeadsSG": ("main",),
    "SearchLeadsSG": ("query", "results"),
    "ContactsMenuSG": ("main",),
    "SearchContactsSG": ("query", "results"),
    "AIAdvisorSG": ("main", "loading", "result"),
    "CrmQuickActionSG": (
        "waiting_note",
        "waiting_task",
        "edit_task_choose_field",
        "edit_task_text",
        "edit_task_date",
    ),
    "HandoffSG": ("goal", "contact"),
    "FilterSG": (
        "hub",
        "city",
        "rooms",
        "budget",
        "view",
        "area",
        "floor",
        "complex_name",
        "furnished",
        "promotion",
    ),
    "CatalogSG": ("results", "empty", "details"),
    "DemoSG": ("intro", "results"),
}


@pytest.mark.parametrize("group_name,expected_states", list(EXPECTED_STATE_GROUPS.items()))
def test_states_group_exposes_expected_states(
    group_name: str, expected_states: tuple[str, ...]
) -> None:
    """Each StatesGroup must define the documented State attributes (***REMOVED***1093)."""
    cls = getattr(states_module, group_name, None)
    assert cls is not None, f"telegram_bot.dialogs.states must expose {group_name!r} (issue ***REMOVED***1093)."
    assert inspect.isclass(cls) and issubclass(cls, StatesGroup), (
        f"{group_name!r} must be a StatesGroup subclass."
    )
    for state_name in expected_states:
        attr = getattr(cls, state_name, None)
        assert attr is not None, f"{group_name}.{state_name} must be defined (issue ***REMOVED***1093)."
        assert isinstance(attr, State), (
            f"{group_name}.{state_name} must be a State instance, got {type(attr)!r}."
        )


def test_no_unexpected_states_groups_are_silently_dropped() -> None:
    """If a new ``StatesGroup`` is added to ``states.py`` it should also be
    captured by the EXPECTED_STATE_GROUPS contract above. This test fails
    *forward* — it nudges the author to lock in the new group's states.
    """
    declared = {
        name
        for name, value in inspect.getmembers(states_module, inspect.isclass)
        if issubclass(value, StatesGroup) and value is not StatesGroup
    }
    missing = declared - set(EXPECTED_STATE_GROUPS.keys())
    assert not missing, (
        "New StatesGroup(s) found in telegram_bot/dialogs/states.py that are "
        f"not yet pinned by tests/unit/dialogs/test_dialogs_fsm_coverage.py: "
        f"{sorted(missing)!r}. Add their expected State names to "
        "EXPECTED_STATE_GROUPS so transitions stay covered (***REMOVED***1093)."
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. Wizard step ordering — verify source references appear in order
***REMOVED*** ---------------------------------------------------------------------------


def _extract_state_references(file_path: Path, group_name: str) -> list[str]:
    """Return state attr names referenced via ``state=<group>.<attr>`` in order."""
    text = file_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"state\s*=\s*{re.escape(group_name)}\.(\w+)")
    return pattern.findall(text)


WIZARD_STEP_FILES: dict[str, tuple[Path, tuple[str, ...]]] = {
    "CreateLeadSG": (
        DIALOGS_DIR / "crm_leads.py",
        ("name", "budget", "pipeline", "summary"),
    ),
    "CreateContactSG": (
        DIALOGS_DIR / "crm_contacts.py",
        ("first_name", "last_name", "phone", "email", "summary"),
    ),
    "CreateTaskSG": (
        DIALOGS_DIR / "crm_tasks.py",
        ("text", "task_type", "lead_id", "due_date", "summary"),
    ),
}


@pytest.mark.parametrize("group_name", list(WIZARD_STEP_FILES.keys()))
def test_wizard_steps_appear_in_documented_order(group_name: str) -> None:
    """Wizard handlers must register state windows in the documented order."""
    file_path, expected_order = WIZARD_STEP_FILES[group_name]
    assert file_path.exists(), f"Expected dialog file {file_path} to exist"
    refs = _extract_state_references(file_path, group_name)

    ***REMOVED*** Ignore router-style references (e.g. start dialog at first step) by
    ***REMOVED*** de-duplicating consecutive repeats and keeping first appearance only.
    seen: list[str] = []
    for ref in refs:
        if ref in seen:
            continue
        if ref in expected_order:
            seen.append(ref)

    expected_subset = [s for s in expected_order if s in refs]
    assert seen == expected_subset, (
        f"{group_name} wizard step order in {file_path.name!r} drifted from "
        f"the documented sequence.\n  expected (first-appearance order): {expected_subset!r}\n"
        f"  actual: {seen!r}"
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. No dead states — every declared State must be referenced by a dialog
***REMOVED*** ---------------------------------------------------------------------------


def _all_dialog_files() -> list[Path]:
    return sorted(p for p in DIALOGS_DIR.glob("*.py") if p.name not in {"__init__.py", "states.py"})


def _all_production_files() -> list[Path]:
    """Return every ``.py`` under ``telegram_bot/`` except dialog states/init.

    States can legitimately be wired by handler modules (e.g. raw aiogram FSM
    in ``telegram_bot/handlers/crm_callbacks.py``) or by the top-level bot
    module, not only by dialog windows.
    """
    root = DIALOGS_DIR.parent  ***REMOVED*** telegram_bot/
    return sorted(p for p in root.rglob("*.py") if p.name != "states.py")


def _state_is_referenced(group_name: str, state_name: str, dialog_sources: str) -> bool:
    """Loose match: ``<group>.<state>`` appearing anywhere in dialog sources."""
    pattern = re.compile(rf"\b{re.escape(group_name)}\.{re.escape(state_name)}\b")
    return bool(pattern.search(dialog_sources))


***REMOVED*** Known-dead states that pre-date ***REMOVED***1093 and are tracked separately.
***REMOVED*** - ``SearchSG`` was superseded by ``SearchLeadsSG``/``SearchContactsSG`` in ***REMOVED***697
***REMOVED***   but the enum is still imported by ``tests/unit/dialogs/test_crm_foundation.py``.
***REMOVED*** - ``CrmSubmenuSG`` was kept "for backward compatibility" per its docstring and
***REMOVED***   is superseded by ``CRMMenuSG``.
***REMOVED*** Removing them is out of scope for ***REMOVED***1093 — flagged here so the contract is
***REMOVED*** explicit and a future cleanup PR can drop the allowlist + the unused classes.
_EXTERNALLY_REFERENCED_ALLOWLIST: set[tuple[str, str]] = {
    ("SearchSG", "query"),
    ("SearchSG", "results"),
    ("CrmSubmenuSG", "main"),
}


def test_every_declared_state_is_referenced_by_a_dialog() -> None:
    """No dead State definitions — each must be referenced as ``state=...``.

    Helps catch refactors that leave a State enum behind after the window
    was removed. Search scope is the whole ``telegram_bot/`` package because
    a few groups (e.g. ``CrmQuickActionSG``) are still wired through raw
    aiogram FSM in ``telegram_bot/handlers/`` rather than aiogram-dialog
    windows (see ***REMOVED***1232 for the migration roadmap).
    """
    sources = "\n".join(p.read_text(encoding="utf-8") for p in _all_production_files())

    orphaned: list[tuple[str, str]] = []
    for group_name, expected_states in EXPECTED_STATE_GROUPS.items():
        for state_name in expected_states:
            if (group_name, state_name) in _EXTERNALLY_REFERENCED_ALLOWLIST:
                continue
            if not _state_is_referenced(group_name, state_name, sources):
                orphaned.append((group_name, state_name))

    assert not orphaned, (
        "Orphaned States found — declared in states.py but never referenced "
        "by any production module under telegram_bot/. Either wire them into "
        f"a dialog/handler or remove them.\n  Orphans: {orphaned!r}"
    )


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 4. Transition cross-link — each multi-step wizard's terminal state must
***REMOVED***    appear in the same file as the entry state (no cross-file accidents).
***REMOVED*** ---------------------------------------------------------------------------


WIZARD_ENTRY_AND_TERMINAL: dict[str, tuple[Path, str, str]] = {
    "CreateLeadSG": (DIALOGS_DIR / "crm_leads.py", "name", "summary"),
    "CreateContactSG": (DIALOGS_DIR / "crm_contacts.py", "first_name", "summary"),
    "CreateTaskSG": (DIALOGS_DIR / "crm_tasks.py", "text", "summary"),
    "CreateNoteSG": (DIALOGS_DIR / "crm_notes.py", "entity_type", "summary"),
    "FunnelSG": (DIALOGS_DIR / "funnel.py", "city", "summary"),
}


@pytest.mark.parametrize("group_name", list(WIZARD_ENTRY_AND_TERMINAL.keys()))
def test_wizard_entry_and_terminal_in_same_file(group_name: str) -> None:
    """Entry and terminal states of a wizard must live in the same dialog file
    so the FSM transitions are reviewable in one place."""
    file_path, entry, terminal = WIZARD_ENTRY_AND_TERMINAL[group_name]
    assert file_path.exists(), f"Expected dialog file {file_path} to exist"
    refs = _extract_state_references(file_path, group_name)
    assert entry in refs, (
        f"{group_name}.{entry} (entry state) must be wired in {file_path.name!r}; saw refs={refs!r}"
    )
    assert terminal in refs, (
        f"{group_name}.{terminal} (terminal state) must be wired in "
        f"{file_path.name!r}; saw refs={refs!r}"
    )
