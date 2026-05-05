# deploy/

Server deployment configuration for the RAG Telegram Bot.

## Files

| File | Purpose |
|------|---------|
| `telegram-bot.service` | Systemd service unit for the bot |
| `sudoers-telegram-bot` | Sudoers rule for passwordless service management |

## Quick start

1. Copy the service file and reload systemd:
   ```bash
   sudo cp deploy/telegram-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now telegram-bot
   ```

2. Copy the sudoers file:
   ```bash
   sudo cp deploy/sudoers-telegram-bot /etc/sudoers.d/telegram-bot
   sudo chmod 440 /etc/sudoers.d/telegram-bot
   sudo visudo -c
   ```

3. Configure GitHub Secrets for CI/CD:
   - `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`
   - `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`

## Service management

```bash
sudo systemctl start telegram-bot
sudo systemctl stop telegram-bot
sudo systemctl restart telegram-bot
sudo journalctl -u telegram-bot -f
```

## Related

- [`DOCKER.md`](../DOCKER.md) — Docker Compose profiles and local runtime
- [`k8s/README.md`](../k8s/README.md) — k3s manifests and overlays
- [`docs/LOCAL-DEVELOPMENT.md`](../docs/LOCAL-DEVELOPMENT.md) — Local setup guide
