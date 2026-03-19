# Catalog Dialog Migration Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the client catalog `ReplyKeyboard` browsing path with a dialog-owned catalog flow while preserving the current card/media result experience in chat history.

**Architecture:** Introduce a shared catalog runtime as the single source of truth for query, filters, pagination, and result bookkeeping. Build a new `CatalogSG` dialog as a control shell for results navigation, filters, and home/back transitions, while keeping property cards and media as ordinary bot messages. Use a short-lived compatibility adapter during the results-flow migration, then delete the legacy `CatalogBrowsingSG` and `catalog_router` browsing path.

**Tech Stack:** Python 3.12, aiogram 3.26.0, aiogram-dialog 2.5.0, pytest, Ruff, uv

## Completion Note

Completed on branch `feat/1035-catalog-dialog-migration`.

Actual files added:

- `telegram_bot/dialogs/catalog.py`
- `telegram_bot/services/catalog_session.py`
- `telegram_bot/services/catalog_rendering.py`
- `tests/unit/dialogs/test_catalog_dialog.py`
- `tests/unit/dialogs/test_dialog_dependency_baseline.py`
- `tests/unit/services/test_catalog_session.py`
- `tests/unit/services/test_catalog_rendering.py`

Actual cutover point:

- `funnel`, `demo`, and `filter_dialog` now write `catalog_runtime` and start `CatalogSG`
- ordinary result messages are sent first, then `CatalogSG` owns the control shell
- `CatalogBrowsingSG`, active catalog reply-keyboard handling, and `build_catalog_keyboard(...)` were removed

Deviation from the original execution order:

- once `CatalogSG` plus runtime handoff were stable, the temporary compatibility adapter was reduced to an inert module and the active legacy path was removed directly instead of being kept alive for longer

---

## Preflight

Read before implementation:

- `docs/plans/2026-03-19-catalog-dialog-migration-design.md`
- `telegram_bot/AGENTS.override.md`
- `telegram_bot/dialogs/client_menu.py`
- `telegram_bot/dialogs/funnel.py`
- `telegram_bot/dialogs/filter_dialog.py`
- `telegram_bot/handlers/demo_handler.py`
- `telegram_bot/handlers/catalog_router.py`

Suggested setup:

```bash
git worktree add ../rag-fresh-catalog-dialog dev
cd ../rag-fresh-catalog-dialog
uv sync
```

Baseline commands:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_client_root_navigation.py \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/test_catalog_handler.py \
  tests/unit/keyboards/test_catalog_keyboard.py
```

Expected: baseline passes or any existing failures are recorded before edits start.

Dependency baseline to enforce before migration:

- upgrade `aiogram` to `3.26.0`
- upgrade `aiogram-dialog` to `2.5.0`

Rationale:

- `aiogram 3.26.0` release notes explicitly include Telegram Bot API 9.5 support
- `aiogram-dialog 2.5.0` is the latest GitHub release at the time of this plan
- stable `aiogram-dialog` documentation still matches the architectural model used here: `Dialog -> Window -> widgets -> transitions`

### Task 0: Upgrade SDK Dependencies To The Target Baseline

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: any pinned dependency manifest that still constrains `aiogram` or `aiogram-dialog`
- Test: `tests/unit/dialogs/test_client_menu.py`
- Test: `tests/unit/dialogs/test_menu_routing.py`
- Test: `tests/unit/dialogs/test_filter_dialog.py`

**Step 1: Write the failing dependency assertions**

Add or update a small dependency contract test:

```python
def test_dialog_dependency_baseline() -> None:
    import aiogram
    import aiogram_dialog

    assert aiogram.__version__ == "3.26.0"
    assert aiogram_dialog.__version__ == "2.5.0"
```

If the project does not expose `__version__` reliably for one dependency, replace it with a lockfile assertion test or skip this test and enforce the version only through the lockfile diff. Do not invent a brittle runtime assertion if the package does not support it.

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q -k dialog_dependency_baseline
```

Expected: FAIL if the environment is still on older SDK versions.

**Step 3: Upgrade the minimal dependency set**

Update dependency constraints so the migration runs on:

```toml
aiogram = "==3.26.0"
aiogram-dialog = "==2.5.0"
```

Refresh the lockfile:

```bash
uv lock
uv sync
```

Do not upgrade unrelated libraries in this task.

**Step 4: Run focused SDK sanity tests**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_filter_dialog.py
```

Expected: PASS on the upgraded dependency baseline, or failures are captured as migration prerequisites.

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: upgrade aiogram and aiogram-dialog baseline"
```

### Task 1: Lock The New Catalog Runtime Contract In Tests

**Files:**
- Create: `tests/unit/services/test_catalog_session.py`
- Modify: `telegram_bot/dialogs/states.py`

**Step 1: Write the failing tests**

Add tests for a new runtime module that becomes the single source of truth:

```python
from telegram_bot.services.catalog_session import (
    CatalogRuntime,
    build_catalog_runtime,
    update_catalog_runtime_page,
)


def test_build_catalog_runtime_sets_expected_defaults() -> None:
    runtime = build_catalog_runtime(
        query="funnel:varna",
        source="funnel",
        filters={"city": "varna"},
        view_mode="cards",
        results=[{"id": "a1"}, {"id": "a2"}],
        total=24,
        next_offset=10,
        shown_item_ids=["a1", "a2"],
    )

    assert runtime["query"] == "funnel:varna"
    assert runtime["source"] == "funnel"
    assert runtime["filters"] == {"city": "varna"}
    assert runtime["view_mode"] == "cards"
    assert runtime["shown_count"] == 2
    assert runtime["total"] == 24
    assert runtime["next_offset"] == 10
```

```python
def test_update_catalog_runtime_page_accumulates_shown_ids() -> None:
    runtime = {
        "shown_count": 2,
        "shown_item_ids": ["a1", "a2"],
        "total": 24,
        "next_offset": 10,
    }

    updated = update_catalog_runtime_page(
        runtime,
        results=[{"id": "a3"}, {"id": "a4"}],
        total=24,
        next_offset=20,
        shown_item_ids=["a3", "a4"],
    )

    assert updated["shown_count"] == 4
    assert updated["shown_item_ids"] == ["a1", "a2", "a3", "a4"]
    assert updated["next_offset"] == 20
```

Add a state test in `telegram_bot/dialogs/states.py` consumers that requires a new `CatalogSG`:

```python
def test_catalog_states_exist() -> None:
    from telegram_bot.dialogs.states import CatalogSG

    assert hasattr(CatalogSG, "results")
    assert hasattr(CatalogSG, "empty")
    assert hasattr(CatalogSG, "details")
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/services/test_catalog_session.py
```

Expected: FAIL because `catalog_session.py` and `CatalogSG` do not exist yet.

**Step 3: Write minimal implementation**

Create `telegram_bot/services/catalog_session.py` with a typed runtime shape:

```python
class CatalogRuntime(TypedDict, total=False):
    query: str
    source: str
    filters: dict[str, Any]
    view_mode: str
    total: int
    shown_count: int
    next_offset: float | None
    shown_item_ids: list[str]
    current_item_id: str | None
    bookmarks_context: bool
    origin_context: dict[str, Any]
```

Add helper builders:

```python
def build_catalog_runtime(...): ...
def update_catalog_runtime_page(...): ...
```

Add `CatalogSG` states in `telegram_bot/dialogs/states.py`.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q tests/unit/services/test_catalog_session.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/services/catalog_session.py \
  telegram_bot/dialogs/states.py \
  tests/unit/services/test_catalog_session.py
git commit -m "feat: add catalog runtime contract"
```


### Task 2: Extract Shared Result Sending Helpers

**Files:**
- Create: `telegram_bot/services/catalog_rendering.py`
- Modify: `tests/unit/dialogs/test_funnel.py`
- Modify: `tests/unit/dialogs/test_demo_catalog.py`
- Create: `tests/unit/services/test_catalog_rendering.py`

**Step 1: Write the failing tests**

Add focused tests for shared rendering behavior:

```python
async def test_send_catalog_results_cards_uses_property_card_sender() -> None:
    property_bot = MagicMock()
    property_bot._send_property_card = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()

    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=[{"id": "a1"}, {"id": "a2"}],
        total_count=20,
        view_mode="cards",
        shown_start=1,
        telegram_id=42,
    )

    assert property_bot._send_property_card.await_count == 2
```

```python
async def test_send_catalog_results_list_mode_sends_formatted_text() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    with patch("telegram_bot.services.catalog_rendering.format_apartment_list", return_value="LIST"):
        await send_catalog_results(
            message=message,
            property_bot=None,
            results=[{"id": "a1"}],
            total_count=20,
            view_mode="list",
            shown_start=1,
            telegram_id=42,
        )

    message.answer.assert_awaited_once_with("LIST", parse_mode="HTML")
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/services/test_catalog_rendering.py
```

Expected: FAIL because `catalog_rendering.py` does not exist.

**Step 3: Write minimal implementation**

Create `telegram_bot/services/catalog_rendering.py` and centralize:

```python
async def send_catalog_results(
    *,
    message: Message,
    property_bot: Any,
    results: list[dict[str, Any]],
    total_count: int,
    view_mode: str,
    shown_start: int,
    telegram_id: int,
) -> None:
    ...
```

Use existing behavior:

- `list` mode uses `format_apartment_list(...)`
- `cards` mode loops through `property_bot._send_property_card(...)`
- no `ReplyKeyboardMarkup`

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q tests/unit/services/test_catalog_rendering.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/services/catalog_rendering.py \
  tests/unit/services/test_catalog_rendering.py
git commit -m "feat: extract shared catalog rendering helpers"
```


### Task 3: Add The New Catalog Dialog Shell

**Files:**
- Create: `telegram_bot/dialogs/catalog.py`
- Modify: `telegram_bot/bot.py`
- Modify: `tests/unit/dialogs/test_client_menu.py`
- Create: `tests/unit/dialogs/test_catalog_dialog.py`

**Step 1: Write the failing tests**

Add dialog-level tests:

```python
def test_catalog_dialog_has_results_window() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog
    from telegram_bot.dialogs.states import CatalogSG

    assert CatalogSG.results in catalog_dialog.windows
```

```python
def test_catalog_results_window_has_expected_control_buttons() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog
    from telegram_bot.dialogs.states import CatalogSG

    window = catalog_dialog.windows[CatalogSG.results]
    widget_ids = {getattr(w, "widget_id", None) for w in window.keyboard.widgets}
    assert "catalog_more" in widget_ids
    assert "catalog_filters" in widget_ids
    assert "catalog_home" in widget_ids
```

Add a dispatcher registration test if needed:

```python
def test_catalog_dialog_is_registered_in_bot_setup() -> None:
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_catalog_dialog.py
```

Expected: FAIL because `catalog_dialog` is not yet defined or registered.

**Step 3: Write minimal implementation**

Create `telegram_bot/dialogs/catalog.py` with:

- getter reading catalog runtime from `FSMContext`
- `CatalogSG.results` window
- `CatalogSG.empty` window
- placeholder `CatalogSG.details` window
- control buttons:
  - `more`
  - `filters`
  - `bookmarks`
  - `viewing`
  - `manager`
  - `home`

Register `catalog_dialog` in bot dialog setup.

Do not wire legacy entry points yet; only make the dialog exist and be renderable.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_catalog_dialog.py \
  tests/unit/dialogs/test_client_menu.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/catalog.py \
  telegram_bot/bot.py \
  tests/unit/dialogs/test_catalog_dialog.py \
  tests/unit/dialogs/test_client_menu.py
git commit -m "feat: add catalog dialog shell"
```


### Task 4: Move Funnel Handoff To CatalogSG

**Files:**
- Modify: `telegram_bot/dialogs/funnel.py`
- Modify: `tests/unit/dialogs/test_funnel.py`
- Modify: `tests/unit/dialogs/test_funnel_crm_integration.py`

**Step 1: Write the failing tests**

Replace legacy handoff assertions:

```python
async def test_on_summary_search_starts_catalog_dialog_results() -> None:
    manager = build_manager_with_state_and_services()
    callback = build_callback()

    await on_summary_search(callback, MagicMock(widget_id="search_cards"), manager)

    manager.start.assert_awaited()
    assert manager.start.call_args.args[0] == CatalogSG.results
```

```python
async def test_on_summary_search_does_not_set_catalog_browsing_state() -> None:
    state = AsyncMock()
    manager = build_manager_with_state(state)

    await on_summary_search(...)

    state.set_state.assert_not_awaited()
```

```python
async def test_on_summary_search_bootstraps_catalog_runtime() -> None:
    state = AsyncMock()
    manager = build_manager_with_state(state)

    await on_summary_search(...)

    update_call = state.update_data.await_args.kwargs
    assert "catalog_runtime" in update_call
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_funnel.py -k 'summary_search'
```

Expected: FAIL because funnel still writes `CatalogBrowsingSG.browsing` and catalog reply keyboard state.

**Step 3: Write minimal implementation**

In `telegram_bot/dialogs/funnel.py`:

- stop importing `build_catalog_keyboard`
- stop setting `CatalogBrowsingSG.browsing`
- build a runtime via `build_catalog_runtime(...)`
- store it under `catalog_runtime`
- call `send_catalog_results(...)`
- start `CatalogSG.results` with `StartMode.RESET_STACK`

Keep:

- lead scoring persistence
- existing filter construction
- card/list rendering behavior

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/dialogs/test_funnel_crm_integration.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/funnel.py \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/dialogs/test_funnel_crm_integration.py
git commit -m "feat: route funnel results through catalog dialog"
```


### Task 5: Move Demo Search Handoff To CatalogSG

**Files:**
- Modify: `telegram_bot/handlers/demo_handler.py`
- Modify: `telegram_bot/dialogs/demo.py`
- Modify: `tests/unit/dialogs/test_demo_catalog.py`
- Modify: `tests/unit/handlers/test_demo_handler.py`
- Modify: `tests/unit/handlers/test_demo_search.py`

**Step 1: Write the failing tests**

Change demo expectations from legacy browsing state to dialog-driven runtime:

```python
async def test_run_demo_search_stores_catalog_runtime() -> None:
    state = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()

    await _run_demo_search(..., state=state, ...)

    kwargs = state.update_data.await_args.kwargs
    assert "catalog_runtime" in kwargs
```

```python
async def test_dialog_demo_search_starts_catalog_results() -> None:
    manager = AsyncMock()
    callback = MagicMock()

    await _dialog_search(callback, MagicMock(), manager)

    manager.start.assert_awaited()
    assert manager.start.call_args.args[0] == CatalogSG.results
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/handlers/test_demo_search.py
```

Expected: FAIL because demo still enters `CatalogBrowsingSG.browsing` and uses catalog reply keyboard semantics.

**Step 3: Write minimal implementation**

In both `telegram_bot/handlers/demo_handler.py` and `telegram_bot/dialogs/demo.py`:

- stop setting `CatalogBrowsingSG.browsing`
- build/store `catalog_runtime`
- send results through `send_catalog_results(...)`
- start `CatalogSG.results`

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/handlers/test_demo_search.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/handlers/demo_handler.py \
  telegram_bot/dialogs/demo.py \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/handlers/test_demo_search.py
git commit -m "feat: route demo results through catalog dialog"
```


### Task 6: Rewire FilterSG To Catalog Runtime And Dialog Return

**Files:**
- Modify: `telegram_bot/dialogs/filter_dialog.py`
- Modify: `tests/unit/dialogs/test_filter_dialog.py`
- Modify: `tests/unit/test_catalog_handler.py`

**Step 1: Write the failing tests**

Add tests that require filter apply to return into `CatalogSG.results`:

```python
async def test_filter_apply_updates_catalog_runtime() -> None:
    state = AsyncMock()
    manager = build_filter_manager_with_state(state)
    callback = MagicMock(message=MagicMock())

    await on_apply(callback, MagicMock(), manager)

    kwargs = state.update_data.await_args.kwargs
    assert "catalog_runtime" in kwargs
```

```python
async def test_filter_apply_starts_catalog_results() -> None:
    manager = build_filter_manager()

    await on_apply(callback, MagicMock(), manager)

    manager.start.assert_awaited()
    assert manager.start.call_args.args[0] == CatalogSG.results
```

```python
async def test_filter_apply_does_not_build_catalog_reply_keyboard() -> None:
    with patch("telegram_bot.keyboards.client_keyboard.build_catalog_keyboard") as build_kb:
        await on_apply(...)
    build_kb.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_filter_dialog.py
```

Expected: FAIL because filter apply still sends results with `build_catalog_keyboard(...)` and returns via legacy behavior.

**Step 3: Write minimal implementation**

In `telegram_bot/dialogs/filter_dialog.py`:

- read current `catalog_runtime`
- update `filters`, `shown_count`, `next_offset`, `shown_item_ids`
- reload results through the shared search/render helpers
- start `CatalogSG.results`
- remove catalog reply keyboard usage

Keep `FilterSG` itself as a child dialog.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/test_catalog_handler.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/filter_dialog.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/test_catalog_handler.py
git commit -m "feat: return filters into catalog dialog flow"
```


### Task 7: Add Dialog-Native Catalog Controls For More, Home, Manager, Viewing, And Bookmarks

**Files:**
- Modify: `telegram_bot/dialogs/catalog.py`
- Modify: `tests/unit/dialogs/test_catalog_dialog.py`
- Modify: `tests/unit/dialogs/test_client_root_navigation.py`

**Step 1: Write the failing tests**

Add control-action tests:

```python
async def test_catalog_more_loads_next_page_and_updates_runtime() -> None:
    manager = build_catalog_manager()
    callback = MagicMock(message=MagicMock(), from_user=MagicMock(id=42))

    await on_catalog_more(callback, MagicMock(), manager)

    manager.middleware_data["state"].update_data.assert_awaited()
```

```python
async def test_catalog_home_uses_reset_stack_to_client_root() -> None:
    manager = AsyncMock()

    await on_catalog_home(MagicMock(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

```python
async def test_catalog_manager_uses_existing_manager_handler_without_reply_keyboard() -> None:
    ...
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_catalog_dialog.py
```

Expected: FAIL because handlers are not yet wired.

**Step 3: Write minimal implementation**

In `telegram_bot/dialogs/catalog.py`:

- implement `on_catalog_more`
- implement `on_catalog_filters`
- implement `on_catalog_home`
- implement `on_catalog_manager`
- implement `on_catalog_viewing`
- implement `on_catalog_bookmarks`

All of these must:

- use the shared catalog runtime
- avoid `ReplyKeyboardMarkup`
- preserve ordinary card/history messages

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_catalog_dialog.py \
  tests/unit/dialogs/test_client_root_navigation.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/catalog.py \
  tests/unit/dialogs/test_catalog_dialog.py \
  tests/unit/dialogs/test_client_root_navigation.py
git commit -m "feat: add dialog-native catalog controls"
```


### Task 8: Add A Thin Legacy Adapter And Remove ReplyKeyboard Ownership From The Catalog Path

**Files:**
- Modify: `telegram_bot/handlers/catalog_router.py`
- Modify: `tests/unit/test_catalog_handler.py`
- Modify: `tests/unit/keyboards/test_catalog_keyboard.py`
- Modify: `tests/unit/keyboards/test_client_keyboard.py`

**Step 1: Write the failing tests**

Add tests that force the legacy path to delegate instead of owning behavior:

```python
async def test_catalog_router_more_delegates_to_catalog_core() -> None:
    with patch("telegram_bot.handlers.catalog_router.load_next_catalog_page", new=AsyncMock()) as load_page:
        await handle_catalog_more(message, state, property_bot=property_bot)
    load_page.assert_awaited_once()
```

```python
def test_catalog_keyboard_is_no_longer_used_by_catalog_flow() -> None:
    from pathlib import Path

    source = Path("telegram_bot/dialogs/funnel.py").read_text()
    assert "build_catalog_keyboard" not in source
```

Do not delete the keyboard helper yet in this task. First make it unused by the migrated flow.

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/unit/test_catalog_handler.py
```

Expected: FAIL because `catalog_router` still owns legacy browsing behavior.

**Step 3: Write minimal implementation**

Change `telegram_bot/handlers/catalog_router.py` into a temporary adapter:

- delegate page loading into shared catalog helpers
- delegate free-text search into catalog runtime bootstrap
- do not build or depend on catalog reply keyboard for migrated flows

Any still-needed compatibility code must be explicitly marked temporary.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/test_catalog_handler.py \
  tests/unit/keyboards/test_catalog_keyboard.py \
  tests/unit/keyboards/test_client_keyboard.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/handlers/catalog_router.py \
  tests/unit/test_catalog_handler.py \
  tests/unit/keyboards/test_catalog_keyboard.py \
  tests/unit/keyboards/test_client_keyboard.py
git commit -m "refactor: reduce catalog router to compatibility adapter"
```


### Task 9: Remove Legacy CatalogBrowsingSG And ReplyKeyboard Catalog Path

**Files:**
- Modify: `telegram_bot/dialogs/states.py`
- Modify: `telegram_bot/keyboards/client_keyboard.py`
- Modify: `telegram_bot/handlers/catalog_router.py`
- Modify: `telegram_bot/bot.py`
- Modify: `tests/unit/test_catalog_handler.py`
- Modify: `tests/unit/keyboards/test_catalog_keyboard.py`
- Modify: `tests/unit/dialogs/test_demo_catalog.py`
- Modify: `tests/unit/dialogs/test_funnel.py`

**Step 1: Write the failing tests**

Add deletion-oriented tests:

```python
def test_catalog_browsing_state_is_removed() -> None:
    from telegram_bot.dialogs import states

    assert not hasattr(states, "CatalogBrowsingSG")
```

```python
def test_build_catalog_keyboard_is_removed() -> None:
    import telegram_bot.keyboards.client_keyboard as mod

    assert not hasattr(mod, "build_catalog_keyboard")
```

```python
def test_bot_no_longer_registers_catalog_reply_keyboard_path() -> None:
    source = Path("telegram_bot/bot.py").read_text()
    assert "CatalogBrowsingSG.browsing" not in source
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/test_catalog_handler.py \
  tests/unit/keyboards/test_catalog_keyboard.py
```

Expected: FAIL because legacy state and helper still exist.

**Step 3: Write minimal implementation**

Delete or fully remove:

- `CatalogBrowsingSG`
- `build_catalog_keyboard(...)`
- catalog reply-keyboard parsing for browsing
- reply-keyboard cleanup glue that only existed because of the hybrid model

If `catalog_router.py` becomes empty or irrelevant, remove it from the active client path.

**Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_client_root_navigation.py \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/test_catalog_handler.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/states.py \
  telegram_bot/keyboards/client_keyboard.py \
  telegram_bot/handlers/catalog_router.py \
  telegram_bot/bot.py \
  tests/unit/test_catalog_handler.py \
  tests/unit/keyboards/test_catalog_keyboard.py \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/dialogs/test_funnel.py
git commit -m "refactor: remove legacy catalog reply keyboard path"
```


### Task 10: Run Full Validation And Update The Design Record

**Files:**
- Modify: `docs/plans/2026-03-19-catalog-dialog-migration-design.md`
- Modify: `docs/plans/2026-03-19-catalog-dialog-migration-implementation-plan.md`

**Step 1: Write the validation checklist into the design docs**

Add a completion note section summarizing:

- what changed
- what legacy path was removed
- which regressions were checked

**Step 2: Run repo checks**

Run:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Expected: PASS

Also run a focused catalog set:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_client_root_navigation.py \
  tests/unit/dialogs/test_catalog_dialog.py \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/dialogs/test_demo_catalog.py \
  tests/unit/handlers/test_demo_handler.py \
  tests/unit/handlers/test_demo_search.py \
  tests/unit/test_catalog_handler.py \
  tests/unit/services/test_catalog_session.py \
  tests/unit/services/test_catalog_rendering.py
```

Expected: PASS

**Step 3: Write final documentation updates**

Update the design and plan docs with:

- actual filenames added
- actual cutover point
- any deviations from plan

**Step 4: Commit**

```bash
git add \
  docs/plans/2026-03-19-catalog-dialog-migration-design.md \
  docs/plans/2026-03-19-catalog-dialog-migration-implementation-plan.md
git commit -m "docs: finalize catalog dialog migration plan and validation"
```
