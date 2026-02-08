# Local Development Setup (Windows + WSL2)

## Prerequisites

- Windows + WSL2 (Ubuntu)
- Docker Desktop with WSL2 backend
- Git + SSH key for GitHub

## 1. WSL2 Resources

Create/edit `C:\Users\<you>\.wslconfig`:
```
[wsl2]
memory=16GB
processors=8
```
Restart WSL: `wsl --shutdown` then reopen terminal.

## 2. Clone

```bash
git clone git@github.com:yastman/rag.git ~/projects/rag-fresh
cd ~/projects/rag-fresh
```

## 3. SSH Key for VPS

```bash
# Copy your VPS key to ~/.ssh/vps_access_key
chmod 600 ~/.ssh/vps_access_key

# Add SSH config
cat >> ~/.ssh/config << 'EOF'
Host vps
    HostName REDACTED_VPS_IP
    Port 1654
    User admin
    IdentityFile ~/.ssh/vps_access_key
    IdentitiesOnly yes
EOF

# Test: ssh vps "hostname"
```

## 4. Environment

```bash
cp .env.example .env
# Edit .env — fill in:
#   TELEGRAM_BOT_TOKEN
#   LITELLM_MASTER_KEY
#   CEREBRAS_API_KEY (or other LLM provider)
```

## 5. Build & Start

```bash
# Core services (postgres, redis, qdrant, bge-m3, user-base, docling)
docker compose --compatibility -f docker-compose.dev.yml build
docker compose --compatibility -f docker-compose.dev.yml up -d

# Wait for BGE-M3 model download (~3 min first time)
docker logs dev-bge-m3 -f
# Wait for "Application startup complete"

# Bot + LiteLLM
docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d
```

## 6. Restore Qdrant Data

```bash
# Download snapshot from VPS
scp -P 1654 -i ~/.ssh/vps_access_key \
  admin@REDACTED_VPS_IP:/srv/backups/qdrant/gdrive_documents_bge_*.snapshot \
  ./data/

# Restore
curl -X POST "http://localhost:6333/collections/gdrive_documents_bge/snapshots/upload" \
  -F "snapshot=@data/gdrive_documents_bge_*.snapshot"

# Verify (should show ~278 points)
curl -s http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool | grep points_count
```

## 7. Pre-commit Hooks

```bash
pip install pre-commit   # or: uv tool install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```

## 8. Deploy to VPS

```bash
# Option A: Via Claude Code
# Just say "deploy" or "задеплой"

# Option B: Via script
./scripts/deploy-vps.sh

# Option C: Manual
git push origin main
ssh vps "cd /opt/rag-fresh && git pull && docker compose --compatibility -f docker-compose.vps.yml up -d --build"
```

## Profiles

| Profile | Services | Command |
|---------|----------|---------|
| (default) | postgres, redis, qdrant, bge-m3, user-base, docling | `docker compose up -d` |
| bot | + litellm, bot | `--profile bot up -d` |
| ingest | + ingestion pipeline | `--profile ingest up -d` |
| ml | + Langfuse, MLflow, ClickHouse, MinIO | `--profile ml up -d` |
| obs | + Loki, Promtail, Alertmanager | `--profile obs up -d` |
| full | Everything | `--profile full up -d` |
