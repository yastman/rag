# Local Runtime And Telegram E2E Index

Fast lookup for local bot/runtime tasks. Canonical command details live in
[`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md); Docker service truth lives
in [`../../DOCKER.md`](../../DOCKER.md).

| Goal / Symptom | Canonical Doc | Focused Check |
|---|---|---|
| Run dev Docker stack (local or remote host) | [`../../DOCKER.md`](../../DOCKER.md) | `make docker-up` (or `make remote-*` targets for SSH-accessible Docker hosts) |
| Bootstrap local services for native bot iteration | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#7-minimal-stack-fast-iteration) | `make local-up && make test-bot-health` |
| Run the bot natively from `.env` | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#7-minimal-stack-fast-iteration) | `make bot` |
| Check the bot username behind the current token | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#1-bootstrap-workspace) | `curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"` and inspect `.result.username` |
| Configure Telegram E2E userbot credentials | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#1-bootstrap-workspace) | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `E2E_BOT_USERNAME` |
| Create or refresh the Telethon session | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#1-bootstrap-workspace) and [`../../tests/README.md`](../../tests/README.md#e2e) | `uv run python -m scripts.e2e.auth --phone ... --code ...` |
| Smoke test Telegram bot response through Telethon | [`../../tests/README.md`](../../tests/README.md#e2e) | `uv run python -m scripts.e2e.quick_test` |
| `make bot` fails with polling lock busy | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#10-common-issues) | Stop the Docker bot container or wait for Redis lock TTL |
| Telethon session file exists but is not authorized | [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md#10-common-issues) | Refresh with `scripts.e2e.auth` |

Runtime reminders:

- `E2E_BOT_USERNAME` must match the bot behind `TELEGRAM_BOT_TOKEN`; otherwise
  Telethon messages the wrong bot.
- Do not include angle brackets in shell values. Use `--code 12345`, not
  `--code <12345>`.
- Only one process can poll a Telegram bot token. Stop Docker bot containers
  before running native `make bot` with the same token.
