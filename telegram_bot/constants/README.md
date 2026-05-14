# Telegram Bot Constants

## Purpose

Shared constant values used by bot dialogs, handlers, and services.

## Files

- `apartment_constants.py` — apartment filter options, canonical city names, and aliases used by:
  - `telegram_bot/services/filter_extractor.py`
  - `telegram_bot/services/apartment_filter_extractor.py`
  - `telegram_bot/dialogs/filter_constants.py`
  - corresponding tests in `tests/unit`

## Related

- [Telegram bot index](../README.md)
- [Services](../services/README.md) for business logic
- [Dialogs](../dialogs/README.md) for UI/state transitions that consume these constants
