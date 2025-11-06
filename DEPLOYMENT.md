# 🚀 Deployment Guide

> **Production VPS Deployment Workflow**
> **Last updated:** 2025-01-06

---

## 📍 Environments

### Local Development (Windows/WSL)
```yaml
Path: /mnt/c/Users/user/Documents/Сайты/Раг
Purpose: Development, testing, documentation
Git: Full repository with write access
```

### Production (VPS)
```yaml
Path: /srv/contextual_rag
Purpose: Running services (Qdrant, Redis, Telegram Bot)
Git: Clone with deployment branch
Services: Qdrant, Redis, MLflow, Bot
```

---

## 🔄 Deployment Workflow

### Standard Workflow (Development → Production)

```bash
# === LOCAL (Windows/WSL) ===

# 1. Develop and test locally
git checkout -b feature/task-1.2
# Make changes...
pytest tests/

# 2. Commit with conventional commits
git add .
git commit -m "feat(search): replace requests with httpx"

# 3. Push to GitHub
git push origin feature/task-1.2

# 4. Create PR and wait for CI to pass
gh pr create --title "Task 1.2: Migrate to httpx"

# 5. Merge PR after review
gh pr merge --squash


# === VPS SERVER ===

# 6. SSH to VPS
ssh admin@your-vps-ip

# 7. Navigate to project
cd /srv/contextual_rag

# 8. Pull changes
git pull origin main

# 9. Restart services if needed
sudo systemctl restart telegram-bot
# or
docker-compose restart
```

---

## ⚠️ Critical Rules

### DO
- ✅ Always develop locally first
- ✅ Test thoroughly before push
- ✅ Use git for all deployments
- ✅ Backup VPS before major changes
- ✅ Check logs after deployment

### DON'T
- ❌ Edit files directly on VPS
- ❌ Test with production data locally
- ❌ Push untested code
- ❌ Deploy during peak hours
- ❌ Skip backups

---

## 🔧 VPS Deployment Commands

### Quick Reference

```bash
# SSH to VPS
ssh admin@your-vps-ip

# Check services status
sudo systemctl status telegram-bot
docker ps

# Pull latest changes
cd /srv/contextual_rag
git pull

# Restart services
sudo systemctl restart telegram-bot
# or
docker-compose restart

# View logs
sudo journalctl -u telegram-bot -f
docker-compose logs -f

# Check health
curl http://localhost:6333/health  ***REMOVED***
curl http://localhost:5000/health  # MLflow
```

---

## 📦 First Time Setup (VPS)

If setting up VPS from scratch:

```bash
# 1. Clone repository
cd /home/admin
git clone https://github.com/yastman/rag contextual_rag
cd contextual_rag

# 2. Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
nano .env  # Fill real API keys

# 4. Start services
docker-compose up -d  ***REMOVED***, Redis, etc.

# 5. Setup systemd service for bot
sudo cp deployment/telegram-bot.service /etc/systemd/system/
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

---

## 🔍 Troubleshooting

### Common Issues

**Issue:** Changes not reflecting after git pull
```bash
# Solution: Check if service needs restart
sudo systemctl restart telegram-bot
```

**Issue:** Import errors after pull
```bash
# Solution: Update dependencies
pip install -r requirements.txt --upgrade
```

**Issue:** Services not starting
```bash
# Solution: Check logs
sudo journalctl -u telegram-bot -f
docker-compose logs
```

---

## 📊 Monitoring

### Health Checks

```bash
# All services
curl http://localhost:6333/health  ***REMOVED***
curl http://localhost:6379/ping    # Redis
curl http://localhost:5000/health  # MLflow

# Telegram bot
sudo systemctl status telegram-bot

# Resource usage
htop
df -h
free -h
```

---

**Note:** Never run production services on local development machine!
