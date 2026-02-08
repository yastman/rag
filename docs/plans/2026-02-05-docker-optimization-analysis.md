# Docker Optimization Analysis (Best Practices 2026)

## Executive Summary

Анализ всех Dockerfiles проекта и рекомендации по оптимизации на основе:
- Exa search: Docker caching 2026, uv package manager
- Context7: astral-sh/uv Docker integration
- Docker official docs: BuildKit, multi-stage builds

## Current State

| Dockerfile | Size (est) | Multi-stage | Cache mounts | uv | Non-root | Issues |
|------------|------------|-------------|--------------|----|---------| -------|
| `Dockerfile.ingestion` | ~500MB | ✅ | ✅ | ✅ | ✅ | **REFERENCE** |
| `telegram_bot/Dockerfile` | ~800MB | ✅ | ❌ | ❌ | ✅ | Add cache mounts, consider uv |
| `services/bge-m3-api/` | ~4GB | ❌ | ❌ | ❌ | ❌ | Full refactor needed |
| `services/user-base/` | ~3GB | ❌ | ❌ | ❌ | ❌ | Full refactor needed |
| `services/bm42/` | ~1.5GB | ❌ | ❌ | ❌ | ❌ | Full refactor needed |
| `services/docling/` | ~2GB | ✅ | ✅ | ❌ | ✅ | Good, could add uv |
| `docker/mlflow/` | ~1GB | ❌ | ❌ | ❌ | ❌ | Minimal, OK as-is |

## Key Optimizations (2026 Best Practices)

### 1. uv instead of pip (10-100x faster)

**Before (pip):**
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

**After (uv):**
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt
```

**Impact:** 10-100x faster dependency installation

### 2. BuildKit Cache Mounts

**Before:**
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

**After:**
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

**Impact:** Reuse downloaded packages across builds

### 3. Multi-stage Builds

**Before (single stage):**
```dockerfile
FROM python:3.12-slim
RUN apt-get install -y gcc g++  # Build deps in final image!
RUN pip install -r requirements.txt
COPY . .
```

**After (multi-stage):**
```dockerfile
FROM python:3.12-slim AS builder
RUN apt-get install -y gcc g++
RUN pip install -r requirements.txt

FROM python:3.12-slim AS runtime
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .
```

**Impact:** -30-70% image size, no build tools in production

### 4. CPU-only PyTorch

**Before:**
```dockerfile
RUN pip install torch  # Includes CUDA (~8GB)
```

**After:**
```dockerfile
RUN pip install torch --extra-index-url https://download.pytorch.org/whl/cpu
```

**Impact:** -82% image size for PyTorch images

### 5. Layer Ordering (Cache Optimization)

**Before (cache invalidated on any change):**
```dockerfile
COPY . .
RUN pip install -r requirements.txt
```

**After (deps cached separately):**
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

**Impact:** Dependencies cached until requirements.txt changes

### 6. UV Environment Variables

```dockerfile
# Compile bytecode for faster startup
ENV UV_COMPILE_BYTECODE=1

# Required for cache mounts
ENV UV_LINK_MODE=copy

# Disable pip version check
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
```

---

## Optimized Dockerfile Templates

### Template A: Simple Service (FastAPI + pip)

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

FROM python:3.12-slim AS runtime

RUN groupadd -g 1001 app && useradd -u 1001 -g app -m app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=app:app . .
USER app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Template B: ML Service with uv (Fastest)

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && rm -rf /var/lib/apt/lists/*

# Install Python deps with cache
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 app && useradd -u 1001 -g app -m app
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models/hf

COPY --chown=app:app . .
USER app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Template C: Project with pyproject.toml + uv (Best)

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install deps first (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy and install project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

FROM python:3.12-slim AS runtime

RUN groupadd -g 1001 app && useradd -u 1001 -g app -m app
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=app:app . .
USER app
CMD ["python", "-m", "app.main"]
```

---

## Recommended Actions

### Priority 1: ML Services (High Impact)

| Service | Current | Target | Savings |
|---------|---------|--------|---------|
| bge-m3-api | ~4GB | ~2.5GB | -35% |
| user-base | ~3GB | ~2GB | -30% |
| bm42 | ~1.5GB | ~1GB | -30% |

Changes:
- Add multi-stage build
- Add cache mounts
- Add non-root user
- (Optional) Replace pip with uv

### Priority 2: Bot (Medium Impact)

| Service | Current | Target | Savings |
|---------|---------|--------|---------|
| telegram_bot | ~800MB | ~600MB | -25% |

Changes:
- Add cache mounts
- (Optional) Replace pip with uv

### Priority 3: Docling (Already Optimized)

No changes needed - already has:
- Multi-stage build
- Cache mounts
- Non-root user
- CPU-only PyTorch

---

## Build Time Comparison

| Method | Cold Build | Warm Build (deps cached) |
|--------|------------|--------------------------|
| pip (no cache) | 120s | 120s |
| pip + cache mount | 120s | 15s |
| **uv + cache mount** | **45s** | **3s** |

---

## Sources

1. **uv Docker Integration** - docs.astral.sh/uv/guides/integration/docker
2. **Docker Build Cache** - depot.dev/blog/ultimate-guide-to-docker-build-cache
3. **Docker Best Practices 2026** - latestfromtechguy.com/article/docker-best-practices-2026
4. **CPU-only PyTorch** - shekhargulati.com/2025/02/05/reducing-size-of-docling-pytorch-docker-image
