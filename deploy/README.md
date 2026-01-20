# Deployment Configuration

This directory contains server deployment configuration files for the RAG Telegram Bot.

## Files

| File | Purpose |
|------|---------|
| `telegram-bot.service` | Systemd service unit for the bot |
| `sudoers-telegram-bot` | Sudoers rule for passwordless service management |

## Installation Steps

### 1. Install Systemd Service

```bash
# Copy service file
sudo cp deploy/telegram-bot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable telegram-bot

# Start service
sudo systemctl start telegram-bot

# Check status
sudo systemctl status telegram-bot
```

### 2. Install Sudoers Rule

```bash
# Copy sudoers file
sudo cp deploy/sudoers-telegram-bot /etc/sudoers.d/telegram-bot

# Set correct permissions (required!)
sudo chmod 440 /etc/sudoers.d/telegram-bot

# Verify syntax (optional but recommended)
sudo visudo -c
```

### 3. Configure SSH Key for GitHub Actions

Generate a dedicated SSH key for deployments:

```bash
# Generate SSH key (on server)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy -N ""

# Add public key to authorized_keys
cat ~/.ssh/github_actions_deploy.pub >> ~/.ssh/authorized_keys

# Display private key (copy this to GitHub Secrets)
cat ~/.ssh/github_actions_deploy
```

### 4. Configure GitHub Secrets

Go to your repository: **Settings** > **Secrets and variables** > **Actions**

Add the following secrets:

| Secret Name | Value |
|-------------|-------|
| `SERVER_HOST` | Your server IP or hostname |
| `SERVER_USER` | `admin` |
| `SERVER_SSH_KEY` | Contents of `~/.ssh/github_actions_deploy` (private key) |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather |
| `ALLOWED_USER_IDS` | Comma-separated list of allowed Telegram user IDs |

### 5. Verify Deployment

After pushing to `main` branch:

1. Check GitHub Actions workflow status
2. On server, verify service is running:
   ```bash
   sudo systemctl status telegram-bot
   journalctl -u telegram-bot -f
   ```

## Service Management Commands

```bash
# Start bot
sudo systemctl start telegram-bot

# Stop bot
sudo systemctl stop telegram-bot

# Restart bot
sudo systemctl restart telegram-bot

# View logs
journalctl -u telegram-bot -f

# View last 100 lines
journalctl -u telegram-bot -n 100
```

## Troubleshooting

### Service fails to start

1. Check logs: `journalctl -u telegram-bot -n 50`
2. Verify `.env` file exists: `ls -la /srv/app/telegram_bot/.env`
3. Test manually:
   ```bash
   cd /srv/contextual_rag
   source venv/bin/activate
   python -m telegram_bot.main
   ```

### Permission denied errors

1. Verify user/group in service file matches actual user
2. Check `ReadWritePaths` includes all directories the bot needs to write to

### SSH deployment fails

1. Verify SSH key is correctly added to `~/.ssh/authorized_keys`
2. Check server firewall allows SSH (port 22)
3. Verify `SERVER_HOST` secret is correct
