# SDK-Native Client Root Navigation Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move client root navigation to a single SDK-native flow so top-level navigation always resets the active scenario instead of leaking mixed FSM/dialog state.

**Architecture:** Make `aiogram-dialog` the canonical client navigation shell. Clients should enter through `ClientMenuSG.main` (`LaunchMode.ROOT`), and every top-level navigation action should either start a dialog with `StartMode.RESET_STACK` or explicitly close the current dialog before dispatching existing business logic. Keep business services intact; replace navigation glue, not the domain logic. Preserve `ReplyKeyboard` as a fallback-only path for no-dialog recovery (`cmd_start(..., dialog_manager=None)`, cancel middleware, emergency recovery), not as the primary client root.

**Tech Stack:** aiogram 3.26.0, aiogram-dialog 2.4.0, pytest, uv

> **Review note (2026-03-19):** `Context7` confirmed the relevant SDK surfaces for this plan: `Dialog` registration via `dp.include_router(dialog)`, handler/widget starts via `dialog_manager.start(..., mode=StartMode.RESET_STACK)`, `Start(..., mode=StartMode.RESET_STACK)`, and `FSMContext.clear()` for full FSM reset. `Exa`/official docs also support keeping a fallback keyboard path instead of turning legacy menu handlers into a no-op.

---

### Task 1: Lock the SDK-first target behavior in tests

**Files:**
- Modify: `tests/unit/dialogs/test_menu_routing.py`
- Modify: `tests/unit/dialogs/test_menu_wiring.py`
- Modify: `tests/unit/dialogs/test_client_menu.py`
- Create: `tests/unit/dialogs/test_client_root_navigation.py`

**Step 1: Write the failing tests**

Add tests for these target behaviors:

```python
async def test_cmd_start_client_starts_client_menu_dialog(mock_config):
    from telegram_bot.dialogs.states import ClientMenuSG

    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 42
    message.from_user.first_name = "Test"
    message.answer = AsyncMock()

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None
        bot._resolve_user_role = AsyncMock(return_value="client")

        await bot.cmd_start(message, dialog_manager=dialog_manager)

    dialog_manager.start.assert_awaited_once()
    assert dialog_manager.start.call_args.args[0] == ClientMenuSG.main
```

```python
def test_client_menu_dialog_is_registered():
    import ast
    from pathlib import Path

    tree = ast.parse(Path("telegram_bot/bot.py").read_text())
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "client_menu_dialog"
        for node in ast.walk(tree)
    )
```

Do **not** add a test that turns `handle_menu_button(...)` into a no-op. Existing fallback invariants in `tests/unit/dialogs/test_menu_wiring.py` should stay in place, because `ReplyKeyboard` remains the explicit no-dialog recovery path after this migration.

```python
async def test_root_menu_button_from_nested_flow_uses_reset_stack():
    from aiogram_dialog import StartMode
    from telegram_bot.dialogs.states import ClientMenuSG

    manager = AsyncMock()
    await on_back_to_main_menu(MagicMock(), MagicMock(), manager)
    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_client_root_navigation.py
```

Expected: FAIL because `/start` still sends `ReplyKeyboardMarkup`, `client_menu_dialog` is not yet registered on the dispatcher, and there is no shared root-reset entrypoint yet.

**Step 3: Write the minimal implementation**

No production code in this task. Only commit the failing tests.

**Step 4: Run tests to verify they fail**

Run the same command from Step 2.

Expected: FAIL with assertions pointing at legacy client root routing.

**Step 5: Commit**

```bash
git add \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_client_root_navigation.py
git commit -m "test: lock sdk-native client root navigation"
```


### Task 2: Make `client_menu_dialog` the canonical client root

**Files:**
- Modify: `telegram_bot/bot.py`
- Modify: `telegram_bot/dialogs/client_menu.py`
- Modify: `tests/unit/dialogs/test_menu_routing.py`
- Modify: `tests/unit/dialogs/test_menu_wiring.py`

**Step 1: Write the failing test**

If not already covered precisely enough in Task 1, add a focused test:

```python
async def test_cmd_start_client_uses_reset_stack_for_client_menu(mock_config):
    from aiogram_dialog import StartMode
    from telegram_bot.dialogs.states import ClientMenuSG

    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 42
    message.from_user.first_name = "Test"

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None
        bot._resolve_user_role = AsyncMock(return_value="client")

        await bot.cmd_start(message, dialog_manager=dialog_manager)

    dialog_manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_menu_routing.py::test_cmd_start_client_uses_reset_stack_for_client_menu
```

Expected: FAIL because `cmd_start` still answers with `build_client_keyboard(...)`.

**Step 3: Write minimal implementation**

In `telegram_bot/bot.py`, register `client_menu_dialog` in `_setup_dialogs()` alongside the other dialog routers (not ad hoc inside command handlers):

```python
from aiogram_dialog import StartMode

from .dialogs.client_menu import client_menu_dialog
from .dialogs.states import ClientMenuSG

...
self.dp.include_router(client_menu_dialog)

if role == "client" and dialog_manager is not None:
    await dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
    return
```

In `telegram_bot/dialogs/client_menu.py`, make top-level `Start(...)` widgets explicit:

```python
from aiogram_dialog import StartMode

Start(
    Format("{btn_search}"),
    id="funnel",
    state=FunnelSG.city,
    mode=StartMode.RESET_STACK,
)
```

Apply the same explicit `mode=StartMode.RESET_STACK` to the `faq` and `settings` starts.

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_wiring.py
```

Expected: PASS for the updated `/start` and dialog registration assertions.

**Step 5: Commit**

```bash
git add telegram_bot/bot.py telegram_bot/dialogs/client_menu.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_menu_wiring.py
git commit -m "feat: make client menu dialog the canonical root"
```


### Task 3: Add a reusable SDK root-navigation entrypoint for nested dialogs

**Files:**
- Create: `telegram_bot/dialogs/root_nav.py`
- Modify: `telegram_bot/dialogs/faq.py`
- Modify: `telegram_bot/dialogs/settings.py`
- Modify: `telegram_bot/dialogs/viewing.py`
- Modify: `telegram_bot/dialogs/handoff.py`
- Modify: `telegram_bot/dialogs/funnel.py`
- Modify: `telegram_bot/dialogs/filter_dialog.py`
- Modify: `telegram_bot/locales/ru/messages.ftl`
- Modify: `telegram_bot/locales/uk/messages.ftl`
- Modify: `telegram_bot/locales/en/messages.ftl`
- Modify: `tests/unit/dialogs/test_client_root_navigation.py`

**Step 1: Write the failing test**

Add focused tests for at least these cases:

```python
async def test_funnel_main_menu_button_resets_to_client_root():
    from aiogram_dialog import StartMode
    from telegram_bot.dialogs.root_nav import on_back_to_main_menu
    from telegram_bot.dialogs.states import ClientMenuSG

    manager = AsyncMock()
    await on_back_to_main_menu(MagicMock(), MagicMock(), manager)
    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

```python
def test_filter_dialog_contains_main_menu_button():
    from telegram_bot.dialogs.filter_dialog import filter_dialog

    button_ids = [
        getattr(widget, "widget_id", "")
        for window in filter_dialog.windows.values()
        for widget in _iter_widgets(window)
    ]
    assert "main_menu" in button_ids
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/unit/dialogs/test_client_root_navigation.py
```

Expected: FAIL because there is no shared root-nav helper and the affected dialogs do not expose a consistent root reset control.

**Step 3: Write minimal implementation**

Create `telegram_bot/dialogs/root_nav.py`:

```python
from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Format

from telegram_bot.dialogs.states import ClientMenuSG


async def on_back_to_main_menu(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    await manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)


def root_menu_button(widget_id: str = "main_menu") -> Button:
    return Button(Format("{btn_main_menu}"), id=widget_id, on_click=on_back_to_main_menu)
```

Add a single i18n key for that label in `telegram_bot/locales/{ru,uk,en}/messages.ftl` (for example, `main-menu = ...`) and extend the touched dialog getters to provide `btn_main_menu=i18n.get("main-menu")` with sensible fallbacks when `i18n` is absent.

Use that button only in client dialogs that currently strand the user outside the root shell. Start with `faq`, `settings`, `filter_dialog`, `viewing`, and `funnel`; touch `handoff` only if product review confirms it also needs a direct return-to-root control.

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_root_navigation.py \
  tests/unit/dialogs/test_faq.py \
  tests/unit/dialogs/test_settings.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/dialogs/test_viewing.py \
  tests/unit/dialogs/test_funnel.py
```

Expected: PASS, with all touched dialogs exposing a shared reset-to-root button.

**Step 5: Commit**

```bash
git add \
  telegram_bot/dialogs/root_nav.py \
  telegram_bot/dialogs/faq.py \
  telegram_bot/dialogs/settings.py \
  telegram_bot/dialogs/viewing.py \
  telegram_bot/dialogs/handoff.py \
  telegram_bot/dialogs/funnel.py \
  telegram_bot/dialogs/filter_dialog.py \
  tests/unit/dialogs/test_client_root_navigation.py
git commit -m "feat: add shared sdk root navigation for client dialogs"
```


### Task 4: Bridge legacy catalog entrypoints to the new SDK root without leaking FSM data

**Files:**
- Modify: `telegram_bot/handlers/catalog_router.py`
- Modify: `tests/unit/test_catalog_handler.py`
- Modify: `tests/unit/dialogs/test_client_root_navigation.py`

**Step 1: Write the failing test**

Add a focused regression:

```python
async def test_catalog_exit_starts_client_root_with_reset_stack():
    from aiogram_dialog import StartMode
    from telegram_bot.dialogs.states import ClientMenuSG
    from telegram_bot.handlers.catalog_router import handle_catalog_exit

    state = AsyncMock()
    dialog_manager = AsyncMock()
    message = MagicMock()

    await handle_catalog_exit(message, state, dialog_manager=dialog_manager)

    state.clear.assert_awaited_once()
    dialog_manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/unit/test_catalog_handler.py::TestCatalogExitHandler::test_catalog_exit_starts_client_root_with_reset_stack
```

Expected: FAIL because `handle_catalog_exit(...)` currently uses `state.set_state(None)` and replies with `build_client_keyboard()`.

**Step 3: Write minimal implementation**

Update the handler signature and implementation:

```python
async def handle_catalog_exit(
    message: Message,
    state: FSMContext,
    dialog_manager: DialogManager | None = None,
) -> None:
    await state.clear()
    if dialog_manager is not None:
        from telegram_bot.dialogs.states import ClientMenuSG

        await dialog_manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)
        return
    await message.answer("Вы вернулись в главное меню 🏠", reply_markup=build_client_keyboard())
```

Keep the keyboard fallback only for environments where `dialog_manager` is unavailable.

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q tests/unit/test_catalog_handler.py tests/unit/dialogs/test_client_root_navigation.py
```

Expected: PASS, proving the current leak path now rejoins the SDK root.

**Step 5: Commit**

```bash
git add telegram_bot/handlers/catalog_router.py \
  tests/unit/test_catalog_handler.py \
  tests/unit/dialogs/test_client_root_navigation.py
git commit -m "fix: route catalog exit through sdk client root"
```


### Task 5: Codify ReplyKeyboard as fallback-only after parity is proven

**Files:**
- Modify: `tests/unit/dialogs/test_menu_wiring.py`
- Modify: `tests/unit/dialogs/test_menu_routing.py`
- Modify: `tests/unit/keyboards/test_client_keyboard.py`
- Modify: `tests/unit/middlewares/test_fsm_cancel.py`
- Modify: `telegram_bot/bot.py` (only if comments/logging still describe ReplyKeyboard as the primary client root)

**Step 1: Write or update regression tests**

Codify the intended fallback behavior rather than deleting it. Keep or add assertions that:

```python
async def test_cmd_start_without_dialog_manager_keeps_reply_keyboard_fallback(mock_config):
    from aiogram.types import ReplyKeyboardMarkup
    ...
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)
```

Reuse the existing `FSMCancelMiddleware` and `handle_menu_button(...)` fallback tests instead of trying to zero out `MENU_BUTTONS`.

**Step 2: Run tests to verify the fallback contract stays explicit**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/keyboards/test_client_keyboard.py \
  tests/unit/middlewares/test_fsm_cancel.py
```

Expected: PASS once Tasks 1-4 are complete; this task exists to prevent over-correction.

**Step 3: Write minimal implementation**

Do **not** zero out `MENU_BUTTONS` and do **not** turn `handle_menu_button(...)` into a no-op. The desired end-state is narrower:

- normal client root entrypoints (`/start`, catalog exit, nested dialog "main menu" buttons) prefer SDK-owned navigation;
- `ReplyKeyboard` remains functional for explicit no-dialog fallback paths;
- any wording/comments in `telegram_bot/bot.py` that still describe ReplyKeyboard as the primary client root should be updated to "fallback-only".

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/keyboards/test_client_keyboard.py \
  tests/unit/middlewares/test_fsm_cancel.py \
  tests/unit/test_catalog_handler.py
```

Expected: PASS, with ReplyKeyboard preserved as a tested fallback mechanism rather than a dead path.

**Step 5: Commit**

```bash
git add telegram_bot/bot.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/keyboards/test_client_keyboard.py \
  tests/unit/middlewares/test_fsm_cancel.py
git commit -m "test: codify reply keyboard fallback invariants"
```


### Task 6: Run focused validation, then full repo validation

**Files:**
- Modify: `docs/plans/2026-03-19-sdk-native-client-root-navigation.md`

**Step 1: Run focused dialog/navigation suites**

Run:

```bash
uv run pytest -q \
  tests/unit/dialogs/test_client_menu.py \
  tests/unit/dialogs/test_client_root_navigation.py \
  tests/unit/dialogs/test_menu_routing.py \
  tests/unit/dialogs/test_menu_wiring.py \
  tests/unit/dialogs/test_faq.py \
  tests/unit/dialogs/test_settings.py \
  tests/unit/dialogs/test_filter_dialog.py \
  tests/unit/dialogs/test_viewing.py \
  tests/unit/dialogs/test_funnel.py \
  tests/unit/keyboards/test_client_keyboard.py \
  tests/unit/middlewares/test_fsm_cancel.py \
  tests/unit/test_catalog_handler.py
```

Expected: PASS

**Step 2: Run project checks from AGENTS**

Run:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Expected: PASS

**Step 3: Update plan status note**

Append a short implementation note to this plan with:

```markdown
## Validation Notes
- [x] Focused dialog/navigation tests passed
- [x] `make check` passed
- [x] `make test-unit` passed

Implementation note on 2026-03-19:
- `client_menu_dialog` is now registered as the canonical client root and `/start` routes clients to `ClientMenuSG.main` with `StartMode.RESET_STACK` when `dialog_manager` is available.
- Added shared SDK root navigation in `telegram_bot/dialogs/root_nav.py`; client dialogs now expose a `main_menu` reset button that clears FSM state and restarts the root dialog.
- Catalog exit now clears FSM state and rejoins the SDK client root when `dialog_manager` is present, while preserving the ReplyKeyboard fallback path for no-dialog recovery.
```

**Step 4: Commit**

```bash
git add docs/plans/2026-03-19-sdk-native-client-root-navigation.md
git commit -m "docs: record sdk-native client navigation validation"
```
