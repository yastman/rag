***REMOVED*** 🚀 Deployment Guide

> **Production VPS Deployment Workflow**
> **Last updated:** 2025-01-06

---

***REMOVED******REMOVED*** 📍 Environments

***REMOVED******REMOVED******REMOVED*** Local Development (Windows/WSL)
```yaml
Path: /mnt/c/Users/user/Documents/Сайты/Раг
Purpose: Development, testing, documentation
Git: Full repository with write access
```

***REMOVED******REMOVED******REMOVED*** Production (VPS)
```yaml
Path: /srv/rag-fresh
Purpose: Running services (Qdrant, Redis, Telegram Bot)
Git: Clone with deployment branch
Services: Qdrant, Redis, MLflow, Bot
```

---

***REMOVED******REMOVED*** 🔄 Deployment Workflow

***REMOVED******REMOVED******REMOVED*** Standard Workflow (Development → Production)

```bash
***REMOVED*** === LOCAL (Windows/WSL) ===

***REMOVED*** 1. Develop and test locally
git checkout -b feature/task-1.2
***REMOVED*** Make changes...
pytest tests/

***REMOVED*** 2. Commit with conventional commits
git add .
git commit -m "feat(search): replace requests with httpx"

***REMOVED*** 3. Push to GitHub
git push origin feature/task-1.2

***REMOVED*** 4. Create PR and wait for CI to pass
gh pr create --title "Task 1.2: Migrate to httpx"

***REMOVED*** 5. Merge PR after review
gh pr merge --squash


***REMOVED*** === VPS SERVER ===

***REMOVED*** 6. SSH to VPS
ssh admin@your-vps-ip

***REMOVED*** 7. Navigate to project
cd /srv/rag-fresh

***REMOVED*** 8. Pull changes
git pull origin main

***REMOVED*** 9. Restart services if needed
sudo systemctl restart telegram-bot
***REMOVED*** or
docker-compose restart
```

---

***REMOVED******REMOVED*** ⚠️ Critical Rules

***REMOVED******REMOVED******REMOVED*** DO
- ✅ Always develop locally first
- ✅ Test thoroughly before push
- ✅ Use git for all deployments
- ✅ Backup VPS before major changes
- ✅ Check logs after deployment

***REMOVED******REMOVED******REMOVED*** DON'T
- ❌ Edit files directly on VPS
- ❌ Test with production data locally
- ❌ Push untested code
- ❌ Deploy during peak hours
- ❌ Skip backups

---

***REMOVED******REMOVED*** 🔧 VPS Deployment Commands

***REMOVED******REMOVED******REMOVED*** Quick Reference

```bash
***REMOVED*** SSH to VPS
ssh admin@your-vps-ip

***REMOVED*** Check services status
sudo systemctl status telegram-bot
docker ps

***REMOVED*** Pull latest changes
cd /srv/rag-fresh
git pull

***REMOVED*** Restart services
sudo systemctl restart telegram-bot
***REMOVED*** or
docker-compose restart

***REMOVED*** View logs
sudo journalctl -u telegram-bot -f
docker-compose logs -f

***REMOVED*** Check health
curl http://localhost:6333/health  ***REMOVED*** Qdrant
curl http://localhost:5000/health  ***REMOVED*** MLflow
```

---

***REMOVED******REMOVED*** 📦 First Time Setup (VPS)

If setting up VPS from scratch:

```bash
***REMOVED*** 1. Clone repository
cd /home/admin
git clone https://github.com/yastman/rag rag-fresh
cd rag-fresh

***REMOVED*** 2. Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

***REMOVED*** 3. Configure environment
cp .env.example .env
nano .env  ***REMOVED*** Fill real API keys

***REMOVED*** 4. Start services
docker-compose up -d  ***REMOVED*** Qdrant, Redis, etc.

***REMOVED*** 5. Setup systemd service for bot
sudo cp deployment/telegram-bot.service /etc/systemd/system/
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

---

***REMOVED******REMOVED*** 🔍 Troubleshooting

***REMOVED******REMOVED******REMOVED*** Common Issues

**Issue:** Changes not reflecting after git pull
```bash
***REMOVED*** Solution: Check if service needs restart
sudo systemctl restart telegram-bot
```

**Issue:** Import errors after pull
```bash
***REMOVED*** Solution: Update dependencies
pip install -r requirements.txt --upgrade
```

**Issue:** Services not starting
```bash
***REMOVED*** Solution: Check logs
sudo journalctl -u telegram-bot -f
docker-compose logs
```

---

***REMOVED******REMOVED*** 📊 Monitoring

***REMOVED******REMOVED******REMOVED*** Health Checks

```bash
***REMOVED*** All services
curl http://localhost:6333/health  ***REMOVED*** Qdrant
curl http://localhost:6379/ping    ***REMOVED*** Redis
curl http://localhost:5000/health  ***REMOVED*** MLflow

***REMOVED*** Telegram bot
sudo systemctl status telegram-bot

***REMOVED*** Resource usage
htop
df -h
free -h
```

---

**Note:** Never run production services on local development machine!
