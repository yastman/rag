W-API: Create RAG API — FastAPI wrapper around LangGraph

CONTEXT:
Branch: feat/voice-bot (already checked out)
Working dir: /home/user/projects/rag-fresh
Plan: /home/user/projects/rag-fresh/docs/plans/2026-02-11-voice-bot-plan.md (Task 2)
Issue: #153

PREREQUISITE: Run "uv sync --all-extras" first to ensure deps are installed.

TASK: Create FastAPI wrapper around existing LangGraph pipeline exposed as POST /query endpoint.

IMPORTANT CHANGES vs plan:
1. Use GraphConfig factory methods where available instead of manual service construction
2. QdrantService needs full init params: url, collection_name, api_key (from env), timeout (from config)
3. BGEM3HybridEmbeddings needs timeout param from GraphConfig
4. Add cross-trace support: accept optional langfuse_trace_id in QueryRequest, pass to propagate_attributes

FILES TO CREATE:
- src/api/__init__.py (empty)
- src/api/main.py (FastAPI app with POST /query, GET /health)
- src/api/schemas.py (QueryRequest, QueryResponse pydantic models)
- src/api/Dockerfile
- tests/unit/api/__init__.py (empty)
- tests/unit/api/test_rag_api.py

IMPLEMENTATION GUIDANCE:
Read these files first to understand interfaces:
- telegram_bot/graph/graph.py — build_graph() signature
- telegram_bot/graph/config.py — GraphConfig fields and factory methods
- telegram_bot/graph/state.py — make_initial_state() signature
- telegram_bot/observability.py — observe, get_client, propagate_attributes

For src/api/main.py:
- Use asynccontextmanager lifespan for service init/cleanup
- GraphConfig.from_env() for config
- graph.ainvoke(state) for non-streaming execution
- message=None parameter to build_graph for non-streaming mode
- Extract response from result dict

For Dockerfile:
- Base: ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim
- Multi-stage build (builder + runtime)
- CMD: uvicorn src.api.main:app --host 0.0.0.0 --port 8080

TESTS:
- tests/unit/api/test_rag_api.py — test schemas (QueryRequest, QueryResponse)
- Run: uv run pytest tests/unit/api/test_rag_api.py -v
- Do NOT run broad test directories

COMMIT:
git add src/api/ tests/unit/api/
git commit with message: "feat(api): add FastAPI RAG API endpoint for voice and multi-channel access #153"
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

MCP TOOLS:
- Context7: resolve-library-id(libraryName="fastapi", query="FastAPI lifespan async context manager") then query-docs
- Exa: get_code_context_exa("FastAPI lifespan asynccontextmanager pattern 2025") for best practices

LOGGING to /home/user/projects/rag-fresh/logs/worker-api.log (APPEND mode, use >>):
[START] Task 2: RAG API
[DONE] Task 2: result summary
[COMPLETE] Worker finished

WEBHOOK (after ALL tasks done, execute EXACTLY THREE SEPARATE Bash tool calls, do NOT combine):
Call 1: TMUX="" tmux send-keys -t "claude:Claude" "W-API COMPLETE — check logs/worker-api.log"
Call 2: sleep 1
Call 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
IMPORTANT: Use window NAME "Claude", NOT index number.
