# REPORT: impl-home-botfiles-2a71 (card_2a71ec058138) — Slice 1

**Branch:** fix/card_2a71ec058138-home-botfiles
**Date:** 2026-07-02
**Commit:** e51a8c7b86

---

## Files Moved

### Group A — `telegram_bot/observability/` (new package)

| Old path | New path |
|---|---|
| `telegram_bot/observability.py` (flat shim) | `telegram_bot/observability/__init__.py` (absorbed into package) |
| `telegram_bot/_bot_observability.py` | `telegram_bot/observability/bot_observability.py` |
| `telegram_bot/_bot_state_helpers.py` | `telegram_bot/observability/state_helpers.py` |

**Note:** `telegram_bot/observability.py` was a pre-existing thin shim (`mask_pii`,
`propagate_attributes`). It was converted to a package by promoting it to
`observability/__init__.py`, preserving the full `telegram_bot.observability`
import surface. The comment in `test_runtime_phase1_modules_present_contract.py`
already anticipated this ("converted to a package in ARCH-13").

### Group B — `telegram_bot/lifecycle/` (new package)

| Old path | New path |
|---|---|
| `telegram_bot/_bot_lifecycle.py` | `telegram_bot/lifecycle/lifecycle.py` |
| `telegram_bot/_bot_services.py` | `telegram_bot/lifecycle/services.py` |
| `telegram_bot/_bot_postgres_bootstrap.py` | `telegram_bot/lifecycle/postgres_bootstrap.py` |

---

## Import Updates

### `telegram_bot/bot.py`
- Changed `from . import _bot_lifecycle, _bot_observability, _bot_state_helpers` →
  `from .lifecycle import lifecycle as _bot_lifecycle`,
  `from .observability import bot_observability as _bot_observability`,
  `from .observability import state_helpers as _bot_state_helpers`
- Updated `TYPE_CHECKING` import: `from ._bot_services import Services` → `from .lifecycle.services import Services`
- Updated lazy import: `from ._bot_services import build_services` → `from .lifecycle.services import build_services`
- Updated three `from telegram_bot._bot_postgres_bootstrap import ...` lazy imports → `from telegram_bot.lifecycle.postgres_bootstrap import ...`
- Updated module docstring and method docstrings to reflect new paths

### `telegram_bot/_bot_catalog.py`
- `from telegram_bot._bot_state_helpers import ...` → `from telegram_bot.observability.state_helpers import ...`

### `telegram_bot/_bot_favorites.py`
- `from telegram_bot._bot_state_helpers import _state_apartment_results` → `from telegram_bot.observability.state_helpers import ...`

### `telegram_bot/_bot_query_pipeline.py`
- `from telegram_bot._bot_state_helpers import _state_control_message_id` → `from telegram_bot.observability.state_helpers import ...`

---

## Contract Tests Updated

| Test file | Change |
|---|---|
| `test_bot_observability_extraction_contract.py` | Paths → `observability/bot_observability.py`; module → `telegram_bot.observability.bot_observability` |
| `test_bot_state_helpers_extraction_contract.py` | Paths → `observability/state_helpers.py`; module → `telegram_bot.observability.state_helpers` |
| `test_bot_lifecycle_extraction_contract.py` | Paths → `lifecycle/lifecycle.py`; module → `telegram_bot.lifecycle.lifecycle` |
| `test_bot_postgres_bootstrap_extraction_contract.py` | Paths → `lifecycle/postgres_bootstrap.py`; module → `telegram_bot.lifecycle.postgres_bootstrap` |
| `test_orphaned_scheduler_state_dropped_contract.py` | `BOOTSTRAP` path → `lifecycle/postgres_bootstrap.py` |
| `test_runtime_phase1_modules_present_contract.py` | `PHASE1_MODULES` entry → `telegram_bot/observability/__init__.py` (package __init__) |

---

## Verification Results

```
# All 5 new imports: exit 0
uv run python -c "import telegram_bot.observability.bot_observability, ..."  ✓

# test-core (126 tests): all pass
pytest tests/unit/core/ tests/unit/runtime/ tests/regression/ ...  ✓  126 passed

# Contract gate (scoped)
pytest tests/contract/ -k "extraction or lifecycle or observability" ...
  27 passed, 1 pre-existing failure (test_funnel_lead_scoring_module_deleted — ARCH-06, out of scope)
```

---

## Skipped / Pre-existing Issues

- `test_funnel_lead_scoring_module_deleted` — pre-existing failure on base branch before this PR; `telegram_bot/services/funnel_lead_scoring.py` is a dead-code cleanup tracked under ARCH-06. Not in scope for this slice.
- 7 other pre-existing contract failures (`test_bot_kommo_extraction_contract.py` × 5, `test_dead_code_removed_contract.py`, `test_observability_contextvars_contract.py`) — all pre-existing on base branch, zero new failures introduced.

---

## Other 10 `_bot_*.py` Files (Not Moved — Later Slices)

These remain at `telegram_bot/` root level per the incremental mandate:
`_bot_catalog.py`, `_bot_crm_callbacks.py`, `_bot_error_classification.py`,
`_bot_favorites.py`, `_bot_feedback_handlers.py`, `_bot_handoff.py`,
`_bot_kommo.py`, `_bot_pre_agent.py`, `_bot_query_pipeline.py`, `_bot_streaming.py`
