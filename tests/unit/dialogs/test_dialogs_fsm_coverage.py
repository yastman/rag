"""FSM coverage tests for ``telegram_bot/dialogs/states`` (#3390).

These tests enforce two contracts:

1. **State enum coverage** — every live ``StatesGroup`` exposes the
   expected ``State`` attributes. Catches accidental rename / removal.
2. **No dead states** — every ``State`` declared in ``states.py`` is
   referenced by at least one production module via ``<Group>.<state>``.
   There is no allowlist: a state that loses its owner must be deleted
   from ``states.py``, not grandfathered (issue #3390).

The tests parse files as text/AST and never import the aiogram-dialog
runtime, so they run on the fast ``test-unit`` lane without optional
extras.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest
from aiogram.fsm.state import State, StatesGroup

from telegram_bot.dialogs import states as states_module


DIALOGS_DIR = Path(__file__).resolve().parents[3] / "telegram_bot" / "dialogs"
_NOISE_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".worktrees",
    }
)


# ---------------------------------------------------------------------------
# 1. State enum coverage
# ---------------------------------------------------------------------------


# (StatesGroup class name, expected state attribute names) — live groups only.
EXPECTED_STATE_GROUPS: dict[str, tuple[str, ...]] = {
    "ClientMenuSG": ("main",),
    "SettingsSG": ("main", "language"),
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
    """Each live StatesGroup must define the documented State attributes."""
    cls = getattr(states_module, group_name, None)
    assert cls is not None, f"telegram_bot.dialogs.states must expose {group_name!r}."
    assert inspect.isclass(cls) and issubclass(cls, StatesGroup), (
        f"{group_name!r} must be a StatesGroup subclass."
    )
    for state_name in expected_states:
        attr = getattr(cls, state_name, None)
        assert attr is not None, f"{group_name}.{state_name} must be defined."
        assert isinstance(attr, State), (
            f"{group_name}.{state_name} must be a State instance, got {type(attr)!r}."
        )


def _declared_state_groups() -> dict[str, type]:
    """Every ``StatesGroup`` subclass declared in ``telegram_bot/dialogs/states.py``."""
    return {
        name: value
        for name, value in inspect.getmembers(states_module, inspect.isclass)
        if issubclass(value, StatesGroup) and value is not StatesGroup
    }


def test_no_unexpected_states_groups_are_silently_dropped() -> None:
    """If a new ``StatesGroup`` is added to ``states.py`` it should also be
    captured by the EXPECTED_STATE_GROUPS contract above. This test fails
    *forward* — it nudges the author to lock in the new group's states.
    """
    declared = set(_declared_state_groups())
    missing = declared - set(EXPECTED_STATE_GROUPS.keys())
    assert not missing, (
        "New StatesGroup(s) found in telegram_bot/dialogs/states.py that are "
        f"not yet pinned by tests/unit/dialogs/test_dialogs_fsm_coverage.py: "
        f"{sorted(missing)!r}. Add their expected State names to "
        "EXPECTED_STATE_GROUPS so transitions stay covered."
    )


# ---------------------------------------------------------------------------
# 2. Wizard step ordering — verify source references appear in order
# ---------------------------------------------------------------------------


def _extract_state_references(file_path: Path, group_name: str) -> list[str]:
    """Return state attr names referenced via ``state=<group>.<attr>`` in order."""
    text = file_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"state\s*=\s*{re.escape(group_name)}\.(\w+)")
    return pattern.findall(text)


# ---------------------------------------------------------------------------
# 3. No dead states — every declared State must be referenced by a
#    production module (positive contract, no allowlist — issue #3390)
# ---------------------------------------------------------------------------


def _all_production_files() -> list[Path]:
    """Return every ``.py`` under ``telegram_bot/`` except dialog states.

    States can legitimately be wired by handler modules (e.g. raw aiogram FSM
    in ``telegram_bot/handlers/catalog.py``) or by dialog window modules, not
    only by one of them.

    We filter out third-party / cache directories so a stray virtualenv at
    ``telegram_bot/.venv/`` (gitignored but easy to create accidentally with
    ``python -m venv`` from the wrong cwd) doesn't pull ~80 MB of stdlib +
    dep source into the regex search and time the test out.
    """
    root = DIALOGS_DIR.parent  # telegram_bot/
    return sorted(
        p
        for p in root.rglob("*.py")
        if p.name != "states.py" and _NOISE_PARTS.isdisjoint(p.relative_to(root).parts)
    )


def _state_is_referenced(group_name: str, state_name: str, dialog_sources: str) -> bool:
    """Loose match: ``<group>.<state>`` appearing anywhere in dialog sources."""
    pattern = re.compile(rf"\b{re.escape(group_name)}\.{re.escape(state_name)}\b")
    return bool(pattern.search(dialog_sources))


def _declared_states(group_cls: type) -> list[str]:
    """State attribute names declared on a StatesGroup subclass."""
    return [name for name, value in inspect.getmembers(group_cls) if isinstance(value, State)]


def test_every_declared_state_is_referenced_by_a_dialog() -> None:
    """No dead State definitions — each must be referenced as ``<Group>.<state>``.

    Positive contract (#3390): the scan covers every ``StatesGroup`` declared
    in ``states.py`` and carries no allowlist. A State that is no longer
    wired by any dialog/handler module must be deleted from ``states.py``,
    not exempted here.
    """
    sources = "\n".join(p.read_text(encoding="utf-8") for p in _all_production_files())

    orphaned: list[str] = []
    for group_name, group_cls in sorted(_declared_state_groups().items()):
        for state_name in _declared_states(group_cls):
            if not _state_is_referenced(group_name, state_name, sources):
                orphaned.append(f"{group_name}.{state_name}")

    assert not orphaned, (
        "Orphaned States found — declared in states.py but never referenced "
        "by any production module under telegram_bot/. Either wire them into "
        f"a dialog/handler or delete them (issue #3390).\n  Orphans: {orphaned!r}"
    )


def test_all_production_files_excludes_noise_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "telegram_bot"
    dialogs = root / "dialogs"
    dialogs.mkdir(parents=True)
    real_file = root / "handlers.py"
    real_file.write_text("# production\n", encoding="utf-8")
    for part in _NOISE_PARTS:
        noise_file = root / part / "noise.py"
        noise_file.parent.mkdir(parents=True, exist_ok=True)
        noise_file.write_text("# ignored\n", encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "DIALOGS_DIR", dialogs)

    assert _all_production_files() == [real_file]


# ---------------------------------------------------------------------------
# 4. Transition cross-link — each multi-step wizard's terminal state must
#    appear in the same file as the entry state (no cross-file accidents).
# ---------------------------------------------------------------------------


WIZARD_ENTRY_AND_TERMINAL: dict[str, tuple[Path, str, str]] = {
    "FunnelSG": (DIALOGS_DIR / "funnel" / "_windows.py", "city", "summary"),
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
