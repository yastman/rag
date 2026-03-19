# Catalog Reply Keyboard Navigation Design

Date: 2026-03-19
Branch: `dev`
Scope: `telegram_bot/` catalog navigation, filters, pagination, reply keyboard ownership

## Purpose

This design replaces the current mixed catalog navigation model with a single catalog-specific reply keyboard.

The immediate product problem is clear:

- catalog screens currently expose two navigation surfaces at once
- inline dialog controls duplicate the lower menu visually
- inline actions work while reply-keyboard actions in `catalog-state` do not
- users can interact with stale dialog control messages after filter and pagination handoffs

The target state is not a custom routing hack. The target state is a standard `aiogram` and `aiogram-dialog` architecture with responsibilities redistributed around the product UX contract.

## Decision

Catalog remains SDK-managed for state and lifecycle, but catalog navigation UI is standardized on `ReplyKeyboardMarkup`.

This means:

- `CatalogSG` and FSM/dialog runtime remain the source of truth for catalog state
- `FilterSG`, `FunnelSG`, handoff, and lifecycle remain on `aiogram-dialog`
- `aiogram` FSM remains the standard state and transport layer
- `ReplyKeyboardMarkup` is used only as the Telegram UI primitive for catalog navigation

Short form:

This is not a rollback to custom routing. It is an SDK-based architecture with reply-keyboard navigation instead of dialog inline controls.

## Product Contract

The catalog has exactly one navigation surface.

That surface is a dedicated catalog reply keyboard with these actions:

- `Показать ещё`
- `Фильтры`
- `Избранное`
- `Запись на осмотр`
- `Написать менеджеру`
- `Главное меню`

Contract rules:

- inline control buttons must not be rendered by `CatalogSG`
- catalog entry, re-entry, filtering, and pagination must always end with the catalog reply keyboard visible
- exit from catalog must restore the ordinary client reply keyboard
- catalog actions must not depend on callback-only paths

## Historical Baseline

The behavioral reference for the reply-keyboard catalog flow is not the current `origin/main`.

The current `origin/main` already contains the dialog-owned catalog migration:

- `CatalogSG` renders inline controls
- catalog actions are wired through dialog callbacks
- free text inside catalog is handled by the dialog flow itself
- `telegram_bot/handlers/catalog_router.py` is already reduced to a compatibility stub

The working lower-menu baseline lives in the pre-migration catalog path, specifically before commit `e218fb19`.

That historical path is useful as a behavior reference for:

- `build_catalog_keyboard(...)`
- `parse_catalog_button(...)`
- explicit `Показать ещё`
- text-first routing of catalog actions before free-text search
- reply-keyboard exit back to the main client menu

It is not the implementation target as-is.

## Design Goals

Primary goals:

- eliminate duplicate navigation surfaces
- make lower-menu catalog actions work reliably in `catalog-state`
- keep catalog state, transitions, and filter lifecycle on SDK primitives
- preserve the existing `Показать ещё` interaction instead of switching to autoload

Secondary goals:

- minimize code churn by preserving current catalog runtime helpers
- keep transport and service boundaries intact
- make catalog navigation behavior testable through text-action routing

Non-goals:

- rewriting apartment search logic
- rewriting card rendering or media delivery
- removing `CatalogSG` or `FilterSG`
- introducing auto-pagination

## Architectural Principle

Catalog remains SDK-managed by state and lifecycle, but navigation UI for the catalog is standardized on `ReplyKeyboardMarkup` because that is the target UX contract.

More concretely:

- SDK manages state, transitions, lifecycle, and render orchestration
- reply keyboard provides the only user action channel while catalog is active
- no second inline control layer is allowed in parallel

## Target Architecture

### State Ownership

`CatalogSG` continues to own catalog runtime and session continuity. The runtime shape already used by the dialog migration remains valid:

- `query`
- `source`
- `filters`
- `view_mode`
- `total`
- `shown_count`
- `next_offset`
- `shown_item_ids`
- `bookmarks_context`
- `origin_context`

`FilterSG` continues to read from and write to that runtime. `FunnelSG` and other catalog entry points continue to hand off into catalog through SDK state transitions.

This design does not restore `CatalogBrowsingSG.browsing` as the primary catalog owner. The old browsing state is only a historical reference for behavior, not for current state ownership.

### UI Ownership

`CatalogSG` stops rendering inline controls in `results` and `empty` windows.

The only catalog controls become reply-keyboard buttons produced by a dedicated catalog keyboard builder. This keyboard is a transport-layer UI primitive, not a source of business state.

### Action Routing

Catalog actions arrive as ordinary `Message.text` values and are parsed through a dedicated catalog action parser before any free-text search handling runs.

Routing order:

1. If message text matches a catalog button, dispatch the corresponding catalog action.
2. Otherwise, treat the text as a free-text catalog query.

This ordering is mandatory. Without it, reply-keyboard taps like `Фильтры` or `Главное меню` will continue to be misclassified as search text.

The parser and dispatch contract should be borrowed from the pre-migration catalog path, but the active owner remains the current `CatalogSG` runtime rather than the old `CatalogBrowsingSG` plus per-field FSM payload.

## Module-Level Change Set

### `telegram_bot/dialogs/catalog.py`

Change the dialog from a dialog-owned control shell to a state-owning catalog surface.

Required edits:

- remove inline `Group/Button` controls from `CatalogSG.results`
- remove inline `Group/Button` controls from `CatalogSG.empty`
- keep `MessageInput`, but change dispatch behavior
- introduce a single text-action entry point that first checks catalog actions and only then falls back to free-text search
- keep existing runtime helpers such as pagination and runtime storage

`on_catalog_more`, `on_catalog_filters`, `on_catalog_home`, and similar functions may remain as internal action handlers, but they should be called from text-action routing rather than widget callbacks.

This file is the primary place to absorb the old reply-keyboard behavior contract. The design should not reintroduce a separate state-owning legacy router if the same routing can be handled against the active `CatalogSG` session.

### `telegram_bot/keyboards/`

Add a dedicated catalog keyboard module, either by extending [client_keyboard.py](/home/user/projects/rag-fresh/telegram_bot/keyboards/client_keyboard.py) or creating a sibling module.

Required responsibilities:

- `build_catalog_keyboard(...)`
- `parse_catalog_button(...)`
- stable action IDs for catalog-only actions
- localized label lookup where needed

This must remain separate from the ordinary client keyboard. Catalog actions are not global client actions.

These functions can be restored conceptually from the pre-migration implementation, but should be adapted to the current dialog-runtime model instead of reviving the full legacy module layout unchanged.

### `telegram_bot/handlers/catalog_router.py`

Do not restore the old router wholesale as the primary catalog implementation.

Two acceptable outcomes:

- keep `catalog_router.py` as a compatibility stub and route catalog reply-keyboard actions inside `CatalogSG`
- restore only a minimal router layer that delegates into current `CatalogSG` helpers and current catalog runtime

Unacceptable outcome:

- reviving `CatalogBrowsingSG` plus duplicated legacy state fields as a second source of truth alongside `CatalogSG`

### Catalog Render Path

Every successful catalog render path must explicitly ensure the catalog keyboard is visible.

This includes:

- first catalog entry
- catalog refresh after filter apply
- `Показать ещё`
- empty catalog result state
- repeat free-text search while still inside catalog

Preferred structure:

- keep `telegram_bot/services/catalog_rendering.py` focused on result rendering
- add a thin orchestration wrapper in `telegram_bot/` that invokes rendering and then applies the correct reply keyboard

This preserves service boundaries by keeping Telegram keyboard concerns out of low-level rendering services.

### Exit Path

Any catalog exit action such as `Главное меню` must:

- reset or leave catalog state in a known safe form
- restore the ordinary client keyboard
- avoid leaving stale dialog shells behind

## Event Flow

### Enter Catalog

Entry points such as funnel search, demo search, or free-text catalog search build or update `catalog_runtime`, render results, and show the catalog reply keyboard.

### Filter From Catalog

When the user taps `Фильтры` in the reply keyboard:

- the catalog action router dispatches to filter handoff
- `FilterSG` opens through the existing dialog lifecycle
- no catalog inline shell remains in chat

### Apply Filters

`FilterSG.on_apply()` updates runtime, renders results or empty state, and restores the catalog reply keyboard as part of the common render path.

### Show More

When the user taps `Показать ещё`:

- catalog action routing calls the existing pagination loader
- the next batch of results is rendered
- runtime is updated
- the catalog reply keyboard remains visible

### Exit To Main Menu

When the user taps `Главное меню`:

- catalog action routing exits the catalog path
- ordinary client keyboard is restored
- no inline catalog controls remain available

## Testing Strategy

Minimum regression coverage:

- catalog windows do not render inline controls
- reply-keyboard text `Показать ещё` routes to pagination
- reply-keyboard text `Фильтры` opens `FilterSG`
- reply-keyboard text `Главное меню` exits catalog and restores the client keyboard
- free text that is not a catalog action still works as a catalog query
- filter apply returns to catalog with the catalog keyboard visible
- empty-state catalog flow also shows the catalog keyboard

Tests should update the existing dialog suite instead of creating a parallel legacy suite.

Primary targets:

- `tests/unit/dialogs/test_catalog_dialog.py`
- `tests/unit/dialogs/test_filter_dialog.py`
- `tests/unit/test_catalog_handler.py`
- any keyboard/parser unit tests required for catalog actions

## Rollout Notes

This design intentionally reverses one part of the earlier catalog migration: dialog no longer owns the catalog control surface. That change is acceptable because the prior design violated the current product UX contract.

It does not reverse the entire migration.

What is reused from history:

- the old reply-keyboard behavior contract
- the old action taxonomy for catalog controls
- the old text-first routing order

What is explicitly not restored from history:

- `CatalogBrowsingSG` as the main catalog state owner
- duplicated legacy FSM keys such as separate `apartment_offset` and related parallel state when `catalog_runtime` already exists
- a second transport path that competes with the active dialog runtime

What does not change:

- SDK ownership of state
- dialog-based filter lifecycle
- shared catalog runtime
- current render pipeline for cards and list output

What does change:

- catalog navigation becomes reply-keyboard only
- catalog actions are text-routed before free-text search handling
- inline control duplication is removed at the source

## Acceptance Criteria

The design is complete when all of the following are true:

- no inline catalog control buttons are rendered in `CatalogSG`
- catalog uses a dedicated reply keyboard while active
- lower-menu catalog actions work inside `catalog-state`
- `Показать ещё` remains an explicit button-driven action
- filter handoff and return keep the same SDK lifecycle behavior
- exit from catalog restores the ordinary client keyboard
- no parallel UI channel remains for the same catalog actions
