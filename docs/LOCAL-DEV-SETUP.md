# Local Dev Setup (WSL2)

This file is kept as a short WSL2 note. Canonical setup is now:
- `docs/LOCAL-DEVELOPMENT.md`
- `DOCKER.md`

## WSL2 Baseline

1. Ensure Docker Desktop uses WSL2 backend.
2. Optional `.wslconfig` baseline:

```ini
[wsl2]
memory=16GB
processors=8
```

3. In repo root:

```bash
uv sync
cp .env.example .env
make docker-up
make docker-bot-up
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Use canonical docs above for profile-specific details (ML/voice/ingestion/monitoring).
