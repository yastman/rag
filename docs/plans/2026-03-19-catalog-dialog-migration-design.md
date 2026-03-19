# Catalog Dialog Migration Design

Date: 2026-03-19
Branch: `dev`
Scope: `telegram_bot/` client navigation, catalog browsing, filters, result flow

## Completion Note

Implemented on branch `feat/1035-catalog-dialog-migration`.

Completed cutover:

- added shared `catalog_runtime` storage via `telegram_bot/services/catalog_session.py`
- added dialog-owned catalog shell in `telegram_bot/dialogs/catalog.py`
- moved funnel, demo, and filter apply flows to `CatalogSG`
- kept cards/media as ordinary bot messages via `telegram_bot/services/catalog_rendering.py`
- removed `CatalogBrowsingSG` and the active reply-keyboard catalog path
- removed `build_catalog_keyboard(...)` and `parse_catalog_button(...)`
- removed active `catalog_router` registration from `telegram_bot/bot.py`

Regression areas checked:

- root menu reset-stack navigation
- funnel handoff into catalog dialog
- demo text/voice handoff into catalog dialog
- filter apply returning into catalog dialog
- dialog-native pagination and home navigation
- removal of legacy reply-keyboard catalog ownership

## Dependency Baseline

The migration should target the current upstream SDK baseline instead of freezing around older local assumptions.

- `aiogram==3.26.0`
- `aiogram-dialog==2.5.0`

Why this baseline:

- `aiogram 3.26.0` includes support for Telegram Bot API 9.5
- `aiogram-dialog 2.5.0` is the latest GitHub release at the time of this design
- stable `aiogram-dialog` docs still describe the same core model this migration is built around:
  - `Dialog`
  - `Window`
  - widgets
  - transitions

The migration should not be designed around legacy reply-keyboard glue added under older SDK assumptions if the current supported dialog surfaces already cover the navigation model we want.

## Purpose

This design defines the target migration path from the current mixed client UI model to a single dialog-driven client flow.

The current state is structurally inconsistent:

- root client navigation is already dialog-based
- funnel and filter flows are dialog-based
- catalog browsing still relies on `ReplyKeyboardMarkup`
- catalog result messages and card messages are mixed with legacy text-button routing

This creates a permanent mismatch between state ownership and UI ownership. The result is fragile navigation, duplicate menus, stale dialog messages, and jerky transitions between dialog messages and reply keyboards.

The target state is not "make the hybrid smoother". The target state is:

- one canonical client navigation model: `aiogram-dialog`
- one canonical catalog session/runtime shared by all entry points
- catalog cards and media preserved as ordinary bot messages in chat history
- no `ReplyKeyboardMarkup` in the client flow

## Design Goals

Primary goals:

- Make client navigation dialog-native end to end.
- Preserve the existing card and media experience as closely as possible.
- Keep card messages in chat history instead of treating the catalog as a single fully re-rendered message.
- Remove the long-term dependency on `catalog_router` text-button browsing.

Secondary goals:

- Reduce UX jumps by eliminating primitive switching.
- Reuse current business logic and service layer as much as possible.
- Keep migration reversible at the phase boundary, but not indefinitely hybrid.

Non-goals:

- Rewriting apartment search business logic.
- Replacing `_send_property_card(...)`.
- Converting the catalog into a single-message GUI.
- Adding new catalog features during migration.

## Current Architecture

Current flow ownership is split across incompatible primitives:

- `ClientMenuSG.main` is the dialog root in `telegram_bot/dialogs/client_menu.py`
- `FunnelSG` starts a search, then closes the dialog and enters `CatalogBrowsingSG.browsing`
- `CatalogBrowsingSG.browsing` is not a dialog flow; it is a message-router state used by `catalog_router`
- `FilterSG` is a dialog, but it returns to the legacy browsing state
- catalog actions such as `more`, `home`, `filters`, `bookmarks`, `manager`, and free-text search are routed through `F.text` handlers

This is the key mistake in migration order: the primitive changed at the root before catalog state ownership changed underneath it.

## Target Architecture

The target model is dialog orchestration with message-based content history.

`aiogram-dialog` owns:

- client root navigation
- catalog session lifecycle
- result navigation
- pagination
- filter entry and return
- home/back transitions
- dialog stack ownership

Ordinary bot messages remain responsible for:

- property cards
- media groups
- status/history messages already visible in chat

This means the new catalog is not "one dialog message that contains every result". Instead:

- one dialog control message acts as the current navigation surface
- result cards are emitted as ordinary chat messages
- those card messages remain in history whenever possible

This keeps navigation canonical while preserving the current media-heavy catalog UX.

## Architectural Principles

1. One navigation primitive per client flow.
2. Dialog owns state; content messages do not own navigation.
3. Result history may remain in chat, but control state must remain singular.
4. Legacy adapters are allowed only during the results-flow migration window.
5. No new features land in the legacy catalog path.
6. Legacy `ReplyKeyboard` catalog code must have explicit deletion criteria.

## Runtime Model

Introduce a dedicated catalog runtime/session object as the only source of truth for catalog state.

Recommended shape:

- `query`
- `source`
  - `funnel`
  - `demo`
  - `free_text`
  - `bookmarks`
- `filters`
- `view_mode`
  - `cards`
  - `list`
- `total`
- `shown_count`
- `next_offset`
- `shown_item_ids`
- `current_item_id`
- `bookmarks_context`
- `origin_context`
  - minimal metadata needed to return correctly to root or parent flow
- `history_message_ids`
  - optional bookkeeping for control/status messages only

This runtime must be shared by:

- funnel search handoff
- demo search handoff
- filter apply/return
- pagination
- future detail navigation

Business services stay where they are. The migration changes orchestration and UI ownership, not apartment search logic.

## New State Model

Do not evolve `CatalogBrowsingSG`.

Add a new dialog state group, for example:

- `CatalogSG.results`
- `CatalogSG.empty`
- `CatalogSG.details`

Optional later state:

- `CatalogSG.confirm_exit`

`FilterSG` may remain separate, but it should return to `CatalogSG.results`, not to `CatalogBrowsingSG.browsing`.

`CatalogBrowsingSG` remains only as a temporary adapter target during the transition phase and must be deleted after cutover.

## UI Model

The new catalog UI should be split into two layers:

1. Control layer
- one stable dialog message
- navigation and control actions only
- actions such as `more`, `filters`, `home`, `back`, `bookmarks`, `manager`, `viewing`

2. Content layer
- property cards
- media groups
- list-mode text results
- informational status messages when needed

This preserves the current result presentation while removing the reply-keyboard dependency.

The control layer should emulate the current action structure from `main` and catalog mode, but it does not need to mimic Telegram's persistent bottom keyboard chrome.

## Two-Phase Migration

### Phase 1: Extract Catalog Core And Introduce Dialog Results Flow

Goal:

- make dialog the canonical owner of catalog state
- keep a short-lived adapter for legacy entry points

Work:

- create shared catalog runtime/session helpers
- create shared result loader helpers
- create `CatalogSG` and its control message
- switch funnel handoff from `CatalogBrowsingSG.browsing` to `CatalogSG.results`
- switch demo handoff from `CatalogBrowsingSG.browsing` to `CatalogSG.results`
- make `FilterSG` read/write the new catalog runtime and return to `CatalogSG.results`
- keep cards/media sending logic unchanged
- keep a thin adapter only where old text-driven handlers still need to delegate into the new core

Adapter rules:

- adapter exists only during Phase 1
- adapter gets no new features
- adapter delegates into the new catalog core instead of owning behavior

### Phase 2: Remove Legacy Catalog Path

Goal:

- remove the old reply-keyboard browsing path completely

Work:

- delete `build_catalog_keyboard()`
- delete `CatalogBrowsingSG.browsing`
- delete `catalog_router` handlers that exist only for reply-keyboard browsing
- remove reply-keyboard cleanup glue added during hybrid fixes
- make `CatalogSG` the only catalog navigation path

## File-Level Design

### `telegram_bot/dialogs/states.py`

Add:

- `CatalogSG.results`
- `CatalogSG.empty`
- `CatalogSG.details`

Remove later:

- `CatalogBrowsingSG`

### `telegram_bot/dialogs/client_menu.py`

Keep as root dialog.

Change top-level catalog entry actions so they start or reset into the new catalog session entrypoint rather than the legacy browsing state.

The menu layout and labels should remain close to the current client UX.

### `telegram_bot/dialogs/funnel.py`

Remove direct handoff into `CatalogBrowsingSG.browsing`.

Instead:

- build funnel filters
- call shared catalog session bootstrap
- emit first-page results through shared result sender
- start `CatalogSG.results`

`funnel` should stop knowing about reply-keyboard catalog mechanics.

### `telegram_bot/dialogs/filter_dialog.py`

Remove return-to-legacy-browsing behavior.

Instead:

- read current catalog runtime on start
- write updated filters back into catalog runtime
- call shared reload helper
- return to `CatalogSG.results`

`FilterSG` should remain a child dialog, not a second catalog owner.

### `telegram_bot/handlers/demo_handler.py`

Remove direct transition to `CatalogBrowsingSG.browsing`.

Instead:

- extract filters
- bootstrap/update shared catalog runtime
- emit first results through shared helpers
- start `CatalogSG.results`

### `telegram_bot/handlers/catalog_router.py`

Phase 1:

- keep only as a temporary compatibility adapter if still needed
- delegate behavior into shared catalog core
- do not add new product behavior here

Phase 2:

- delete the file or reduce it to non-catalog responsibilities only

### New module: `telegram_bot/dialogs/catalog.py`

Introduce the new dialog shell for catalog control flow.

Responsibilities:

- render the control message
- expose buttons for `more`, `filters`, `home`, `manager`, `viewing`, `bookmarks`
- handle dialog-native transitions
- use shared runtime helpers instead of embedding search logic directly

### New module: `telegram_bot/services/catalog_session.py`

Introduce a thin orchestration service for catalog session state.

Responsibilities:

- initialize runtime from funnel/demo/free-text/bookmarks entry
- update filters
- load next page
- track shown ids and pagination cursor
- expose readonly session data for dialog getters

This must not absorb Telegram-specific transport code.

### Optional new module: `telegram_bot/services/catalog_rendering.py`

If extraction pays off, centralize:

- first-page result sending
- next-page sending
- list-mode formatting
- card-mode sending

This avoids continuing to duplicate result emission across funnel, demo, filter dialog, and catalog navigation.

## Temporary Adapter Design

The temporary adapter exists to bridge entry points during Phase 1, not to preserve hybrid UX.

Allowed adapter behavior:

- translate old handler input into calls into the new catalog session/runtime
- call shared render helpers
- hand control back to `CatalogSG`

Disallowed adapter behavior:

- new business logic
- new keyboard layouts
- parallel ownership of catalog state
- long-term persistence after Phase 1 stabilization

Deletion trigger:

- funnel, demo, filters, and pagination all use `CatalogSG`
- no client catalog scenario requires `ReplyKeyboard`
- targeted regression suite passes without legacy adapter coverage

## Error Handling

Catalog flow should fail in controlled dialog-native ways:

- if session bootstrap fails, return to root or show a dedicated empty/error state
- if result loading fails during pagination, keep current control state and show a small failure message
- if a child flow such as filters returns malformed data, preserve the previous catalog runtime instead of partially overwriting it
- if card sending fails for one item, continue rendering remaining items where safe and record the failure

The dialog stack must remain valid even when result emission partially fails.

## Testing Strategy

Testing should follow the migration phases.

Phase 1 tests:

- root entry starts `CatalogSG.results`
- funnel handoff initializes catalog runtime correctly
- demo handoff initializes catalog runtime correctly
- `FilterSG` returns to `CatalogSG.results`
- pagination updates runtime and sends the next page
- `home` and `back` work through dialog transitions, not reply keyboards
- cards remain emitted as ordinary messages

Phase 2 tests:

- no production path depends on `CatalogBrowsingSG.browsing`
- no production path builds catalog `ReplyKeyboardMarkup`
- `catalog_router` legacy handlers are gone or inert

Regression areas:

- bookmarks context
- viewing launch from catalog
- manager handoff from catalog
- list mode versus card mode
- free-text search while already in catalog

## Acceptance Criteria

The migration is complete when all of the following are true:

- client root, funnel, catalog browsing, filters, pagination, and home/back transitions are dialog-owned
- the catalog no longer relies on `ReplyKeyboardMarkup`
- cards and media are still emitted as ordinary messages and remain in chat history
- no duplicate root/catalog menus appear during transitions
- `catalog_router` is removed from the client catalog path
- `CatalogBrowsingSG` is deleted

## Recommended Execution Order

1. Add `CatalogSG` states and the shared catalog runtime helpers.
2. Extract shared result loading and sending helpers.
3. Move funnel handoff to the new runtime plus `CatalogSG.results`.
4. Move demo handoff to the new runtime plus `CatalogSG.results`.
5. Rewire `FilterSG` to reload and return into `CatalogSG.results`.
6. Implement dialog-native pagination, home, and related control actions.
7. Stabilize tests for all client catalog entry points.
8. Delete `build_catalog_keyboard()`, `CatalogBrowsingSG`, and legacy `catalog_router` path.

## Decision Summary

The correct migration strategy is:

- not a big bang rewrite
- not a long-lived hybrid
- not a single-message catalog GUI

It is a two-phase migration with a short-lived adapter:

- extract catalog core first
- move results flow to dialog
- preserve card/media history as ordinary chat messages
- then remove the reply-keyboard legacy path completely
