# Config

## Purpose
Navigation index for the folder. Use this page to quickly find files and route into this part of the project.

## Scope
telegram_bot/config

## Note
`services.yaml` and `mini_app.yaml` were previously duplicated here. The canonical copies live in
`src/config/services.yaml` and `src/config/mini_app.yaml` (enforced by `tests/contract/test_content_loader_path_contract.py`, #2747).
`src/services/content_loader.py` reads from `src/config/` directly.

## Parent
- [..](..)