***REMOVED*** Local Development Setup (Windows + WSL2)

***REMOVED******REMOVED*** Prerequisites

- Windows + WSL2 (Ubuntu)
- Docker Desktop with WSL2 backend
- Git + SSH key for GitHub

***REMOVED******REMOVED*** 1. WSL2 Resources

Create/edit `C:\Users\<you>\.wslconfig`:
```
[wsl2]
memory=16GB
processors=8
```
Restart WSL: `wsl --shutdown` then reopen terminal.

***REMOVED******REMOVED*** 2. Clone

```bash
git clone git@github.com:yastman/rag.git ~/projects/rag-fresh
cd ~/projects/rag-fresh
```

***REMOVED******REMOVED*** 3. SSH Key for VPS

```bash
***REMOVED*** Copy your VPS key to ~/.ssh/vps_access_key
chmod 600 ~/.ssh/vps_access_key

***REMOVED*** Add SSH config
cat >> ~/.ssh/config << 'EOF'
Host vps
    HostName REDACTED_VPS_IP
    Port 1654
    User admin
    IdentityFile ~/.ssh/vps_access_key
    IdentitiesOnly yes
EOF

***REMOVED*** Test: ssh vps "hostname"
```

***REMOVED******REMOVED*** 4. Environment

```bash
cp .env.example .env
***REMOVED*** Edit .env — fill in:
***REMOVED***   TELEGRAM_BOT_TOKEN
***REMOVED***   LITELLM_MASTER_KEY
***REMOVED***   CEREBRAS_API_KEY (or other LLM provider)
```

***REMOVED******REMOVED*** 5. Build & Start

```bash
***REMOVED*** Core services (postgres, redis, qdrant, bge-m3, user-base, docling)
docker compose --compatibility -f docker-compose.dev.yml build
docker compose --compatibility -f docker-compose.dev.yml up -d

***REMOVED*** Wait for BGE-M3 model download (~3 min first time)
docker logs dev-bge-m3 -f
***REMOVED*** Wait for "Application startup complete"

***REMOVED*** Bot + LiteLLM
docker compose --compatibility -f docker-compose.dev.yml --profile bot up -d
```

***REMOVED******REMOVED*** 6. Restore Qdrant Data

```bash
***REMOVED*** Download snapshot from VPS
scp -P 1654 -i ~/.ssh/vps_access_key \
  admin@REDACTED_VPS_IP:/srv/backups/qdrant/gdrive_documents_bge_*.snapshot \
  ./data/

***REMOVED*** Restore
curl -X POST "http://localhost:6333/collections/gdrive_documents_bge/snapshots/upload" \
  -F "snapshot=@data/gdrive_documents_bge_*.snapshot"

***REMOVED*** Verify (should show ~278 points)
curl -s http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool | grep points_count
```

***REMOVED******REMOVED*** 7. Pre-commit Hooks

```bash
pip install pre-commit   ***REMOVED*** or: uv tool install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```

***REMOVED******REMOVED*** 8. Deploy to VPS

```bash
***REMOVED*** Option A: Via Claude Code
***REMOVED*** Just say "deploy" or "задеплой"

***REMOVED*** Option B: Via script
./scripts/deploy-vps.sh

***REMOVED*** Option C: Manual
git push origin main
ssh vps "cd /opt/rag-fresh && git pull && docker compose --compatibility -f docker-compose.vps.yml up -d --build"
```

***REMOVED******REMOVED*** Profiles

| Profile | Services | Command |
|---------|----------|---------|
| (default) | postgres, redis, qdrant, bge-m3, user-base, docling | `docker compose up -d` |
| bot | + litellm, bot | `--profile bot up -d` |
| ingest | + ingestion pipeline | `--profile ingest up -d` |
| ml | + Langfuse, MLflow, ClickHouse, MinIO | `--profile ml up -d` |
| obs | + Loki, Promtail, Alertmanager | `--profile obs up -d` |
| full | Everything | `--profile full up -d` |
