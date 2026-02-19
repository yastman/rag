# Technology Stack

**Analysis Date:** 2026-02-19

## Languages

**Primary:**
- Python 3.12 - Core application (RAG bot, ingestion, API)
- Python 3.11+ minimum - Required via pyproject.toml

**Secondary:**
- YAML - Docker Compose, Makefile, config files
- Fluent - i18n localization (.ftl files via fluentogram)

## Runtime

**Environment:**
- Python 3.12 interpreter
- uv 0.10.0 - Package manager and resolver
- Async/await asyncio - LangGraph, aiogram, aiohttp

**Package Manager:**
- uv - Manages deps, installed from `pyproject.toml` and `uv.lock`
- Lockfile: `uv.lock` (committed to git, refreshed via Renovate)
- Per-service lockfiles: `telegram_bot/uv.lock`, `services/bge-m3-api/uv.lock`, `services/user-base/uv.lock`

## Frameworks

**Core:**
- aiogram 3.25.0 - Telegram bot framework + dispatcher
- aiogram-dialog 2.4.0 - Dialog framework (menus, navigation, widgets)
- langgraph 1.0.3+ <2.0 - LangGraph RAG pipeline state management
- langchain-core 1.2+ - LLM abstractions (embeddings, chat)
- fastapi 0.115.0 - RAG API (voice bot wrapper)
- uvicorn 0.30.0 - ASGI server

**LLM & Inference:**
- langfuse 3.14.0+ - LLM observability and tracing (v3 SDK)
- langfuse.openai.AsyncOpenAI - Wrapped OpenAI SDK with automatic Langfuse tracing
- anthropic - Claude API client (optional)
- openai - OpenAI SDK (base for LiteLLM routing)
- groq - Groq API client (optional)

**ML Models & Embeddings:**
- voyageai 0.3.0+ - Voyage AI embeddings and reranking (optional, legacy)
- FlagEmbedding - BGE-M3 dense + sparse embeddings (local inference, ml-local extra)
- sentence-transformers - Hugging Face transformers wrapper (ml-local extra)
- torch 2.0.0+ (CPU-only via pytorch-cpu index) - PyTorch CPU for local models
- transformers 4.30.0+ - HuggingFace tokenizers in chunking

**Vector Database & Search:**
- qdrant-client 1.16.2+ - Async vector DB client (gRPC + HTTP, batch search, group_by)
- redisvl 0.13.2 - Redis semantic layer

**Caching & State:**
- redis 7.1.0+ - Redis client (async pipelines, TTLCache for rate limiting)
- cachetools 5.0.0+ - TTLCache for throttling middleware
- langgraph-checkpoint-postgres 2.0+ - LangGraph state persistence (Postgres backend)
- langgraph-checkpoint-redis 0.2.0+ - LangGraph state persistence (Redis backend)

**Document Processing & Ingestion:**
- docling 2.70.0+ - PDF/DOCX/CSV parser (ingestion profile)
- docling-core 2.61.0+ - Docling core types
- cocoindex 0.3.28+ - Document chunking and indexing (v3.2.1)
- pymupdf 1.26.0+ - PDF extraction (ingestion profile)
- fastembed 0.7.4+ - Fast embeddings library (ingestion profile)

**Scheduling & Background Jobs:**
- apscheduler 3.11.2+ <4.0 - APScheduler v3 async job scheduling (nurturing, funnel analytics)

**Voice & Communication:**
- livekit-agents 1.4.0+ - LiveKit SDK for voice agents (voice profile)
- livekit-plugins-elevenlabs 1.1+ - ElevenLabs TTS plugin
- livekit-plugins-openai 1.1+ - OpenAI plugin (Whisper STT)
- livekit 1.0+ - LiveKit WebRTC library (voice profile)
- opentelemetry-sdk 1.39.0+ - OpenTelemetry tracing (voice profile)
- opentelemetry-exporter-otlp-proto-http 1.39.0+ - OTLP HTTP exporter (voice profile)

**Database & Persistence:**
- asyncpg 0.31.0+ - Async PostgreSQL driver (CRM lead scoring, funnel metrics)
- psycopg2 - PostgreSQL adapter (Docling, fallback)

**HTTP & Networking:**
- aiohttp 3.13.3+ - Async HTTP client for APIs
- httpx 0.27.0+ - Modern HTTP client (Kommo CRM client)
- requests - Synchronous HTTP client (fallback, ingestion)
- tenacity 8.2.0+ - Exponential backoff retry decorator

**Performance:**
- uvloop 0.21.0+ - 2-4x faster asyncio event loop

**Observability & Logging:**
- python-dotenv - .env file loading (pydantic-settings alternative)
- pydantic-settings 2.0.0+ - Environment variable configuration (BaseSettings)

**Internationalization:**
- fluentogram 1.2.0+ - Fluent i18n integration (@translator for ctx)

**Testing (dev):**
- pytest 8.3.0+ - Test framework
- pytest-asyncio 1.2.0+ - Async test support
- pytest-cov 5.0.0+ - Coverage reporting
- pytest-httpx 0.35.0+ - HTTPX request mocking
- pytest-timeout 2.4.0+ - Test timeout enforcement
- pytest-xdist 3.8.0+ - Parallel test execution (`-n auto`)
- pytest-split 0.11.0+ - Test sharding (CI)
- telethon 1.42.0+ - E2E testing with Telegram userbot API

**Code Quality (dev):**
- ruff 0.6.0+ - Linter + formatter (modern unified tool, replaces flake8/black/isort)
- mypy 1.11.0+ - Static type checker (strict mode in CI)
- pylint 3.2.0+ - Comprehensive linting
- bandit 1.7.9+ - Security linting
- vulture 2.11+ - Dead code detection
- pre-commit 3.8.0+ - Git hooks automation
- click 8.1.7+ - CLI framework (evaluation scripts)

**Documentation (docs extra):**
- mkdocs 1.6.0+ - Documentation generator
- mkdocs-material 9.5.0+ - Material theme
- mkdocstrings[python] 0.25.0+ - Auto API docs from docstrings

**Evaluation (eval extra):**
- mlflow 3.9.0+ - Experiment tracking and model registry
- ragas 0.4.3+ - RAG evaluation metrics (faithfulness, relevance)
- datasets 3.0.0+ - Hugging Face datasets library
- pandas 2.0.0+ - Data analysis

## Configuration

**Environment:**
- `.env.example` - Template with all config variables
- `.env` - Runtime configuration (git-ignored)
- `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY` - Langfuse tracing (optional, disables gracefully)
- `TELEGRAM_BOT_TOKEN` - Telegram bot credential
- `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY` - LLM provider keys
- `REDIS_PASSWORD`, `POSTGRES_PASSWORD` - Database credentials
- Docker profiles control feature activation (bot, ml, obs, ai, eval, ingest, voice)

**Build & Dev:**
- `pyproject.toml` - Project metadata, dependencies, tool config (ruff, mypy, pytest, pylint, bandit, coverage)
- `uv.lock` - Pinned dependency versions (auto-updated via Renovate)
- `Makefile` - Convenience targets (docker-up, test, lint, eval)
- `.pre-commit-config.yaml` - Git hooks (ruff-check, ruff-format, trailing-whitespace, check-yaml)
- `renovate.json` - Mend Renovate auto-dependency updates
- `.github/workflows/ci.yml` - GitHub Actions (lint, test, baseline compare)

**Linting & Formatting:**
- Ruff v0.14.14+ - Single tool: lint (100+ rules) + format (double quotes, 4 spaces)
- Line length: 100 (Black-like)
- Import sorting via isort rules in ruff config
- Per-file ignores for tests, evaluation, legacy code

**Type Checking:**
- MyPy strict mode in CI (Python 3.12)
- Ignore missing imports for some packages
- Per-module overrides for legacy/noisy modules

## Platform Requirements

**Development:**
- Docker & Docker Compose - Container orchestration
- uv installed - Package manager
- Python 3.12 interpreter (managed by uv)
- Linux/macOS/WSL2 - Tested on Linux, WSL2 (VPS at 95.111.252.29)

**Production:**
- VPS: k3s cluster at 95.111.252.29 (admin@...:1654)
- CPU: 4-8 cores
- RAM: 8-16GB (total, shared across services)
- Storage: 100GB+ SSD (for Qdrant vector index, Postgres)
- External: Telegram Bot API, Kommo CRM API, BGE-M3 local API

**Deployment Target:**
- Docker containers (dev: docker-compose.dev.yml; prod: docker-compose.vps.yml, k3s manifests)
- Python 3.12 slim base images (ghcr.io/astral-sh/uv or python:3.12-slim-bookworm)
- uv sync --frozen --no-dev in Docker (layer caching)

---

*Stack analysis: 2026-02-19*
