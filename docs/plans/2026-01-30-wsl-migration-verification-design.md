# WSL Migration Verification Design

**Date:** 2026-01-30
**Status:** Ready for implementation
**Output:** `scripts/verify_wsl_migration.py` + Makefile target

## Goal

Verify that the project works correctly after migrating to native WSL2 filesystem. Automated script with Markdown report.

## Verification Categories

### 1. Environment
| Check | Expected |
|-------|----------|
| Python version | 3.12.x |
| Python path | `/home/user/projects/rag-fresh/.venv/bin/python` |
| Filesystem | Native (not `/mnt/`) |
| .env file | Exists and readable |

### 2. Docker Services
| Service | Port | Health |
|---------|------|--------|
| dev-qdrant | 6333 | healthy |
| dev-redis | 6379 | healthy |
| dev-langfuse | 3001 | healthy |
| dev-litellm | 4000 | healthy |
| dev-mlflow | 5000 | healthy |
| dev-bot | - | healthy |
| dev-clickhouse | 8123 | healthy |
| dev-minio | 9090 | healthy |
| dev-postgres | 5432 | healthy |
| dev-redis-langfuse | 6380 | healthy |
| dev-langfuse-worker | - | running |

### 3. Unit Tests
- Run: `pytest tests/unit/ -q`
- Expected: ~1670 tests pass
- Record execution time (informational)

### 4. Integration Tests
| Check | Method |
|-------|--------|
| Redis ping | `redis-cli ping` |
| Redis set/get | Write and read test key |
| Qdrant collection | `GET /collections/contextual_bulgaria_voyage` |
| Qdrant search | Test vector query |
| Voyage API | `embed_query()` if API key present |

### 5. Bot Smoke Test
| Check | Method |
|-------|--------|
| Import services | `from telegram_bot.services import *` |
| VoyageService init | Constructor without error |
| QdrantService init | Constructor without error |
| CacheService init | Constructor without error |

## Implementation

### File: `scripts/verify_wsl_migration.py`

```python
#!/usr/bin/env python3
"""WSL Migration Verification Script."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    duration_ms: float | None = None
    category: str = ""

class VerificationRunner:
    def __init__(self, output_dir: Path = Path("docs")):
        self.output_dir = output_dir
        self.results: list[CheckResult] = []

    def check_environment(self) -> list[CheckResult]: ...
    def check_docker_services(self) -> list[CheckResult]: ...
    def check_unit_tests(self) -> list[CheckResult]: ...
    def check_integration(self) -> list[CheckResult]: ...
    def check_bot_smoke(self) -> list[CheckResult]: ...

    def run_all(self) -> bool: ...
    def print_results(self) -> None: ...
    def save_report(self) -> Path: ...

def main():
    runner = VerificationRunner()
    success = runner.run_all()
    report_path = runner.save_report()
    print(f"\nReport saved: {report_path}")
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

### Makefile Target

```makefile
verify-wsl:  ## Verify WSL migration
	python scripts/verify_wsl_migration.py
```

### Report Format

Output file: `docs/YYYY-MM-DD-wsl-migration-verification.md`

```markdown
# WSL Migration Verification Report

**Date:** 2026-01-30 15:30:00
**Result:** ✓ PASSED (18/18 checks)

## Summary

| Category | Passed | Failed |
|----------|--------|--------|
| Environment | 4 | 0 |
| Docker Services | 11 | 0 |
| Unit Tests | 1 | 0 |
| Integration | 4 | 0 |
| Bot Smoke | 3 | 0 |

## Details

### Environment
- ✓ Python 3.12.8 at /home/user/projects/rag-fresh/.venv/bin/python
- ✓ Native filesystem (ext4)
- ✓ .env loaded (15 variables)
- ✓ Working directory: /home/user/projects/rag-fresh

### Docker Services
- ✓ dev-qdrant: healthy
- ✓ dev-redis: healthy
...

### Unit Tests
- ✓ 1670 passed in 45.2s

### Integration
- ✓ Redis ping: 0.8ms
- ✓ Qdrant collection: 192 vectors
- ✓ Voyage embed: ok

### Bot Smoke
- ✓ Services import: ok
- ✓ VoyageService: initialized
- ✓ QdrantService: initialized

## Versions

| Component | Version |
|-----------|---------|
| Python | 3.12.8 |
| Docker | 24.0.7 |
| qdrant-client | 1.12.0 |
| redis | 5.2.1 |
```

## Error Handling

- Each check is isolated — failure in one doesn't stop others
- Timeouts: 30s for unit tests, 5s for service checks
- Skip integration checks if Docker not running
- Skip Voyage API check if no API key

## Implementation Tasks

1. Create `scripts/verify_wsl_migration.py` with all checks
2. Add `verify-wsl` target to Makefile
3. Run verification and save report
4. Commit both script and report

## Success Criteria

- All 18 checks pass
- Report generated in `docs/`
- Script is reusable for future verifications
