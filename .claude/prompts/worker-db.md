W-DB: PostgreSQL schema + TranscriptStore for voice calls

CONTEXT:
Branch: feat/voice-bot (already checked out)
Working dir: /home/user/projects/rag-fresh
Plan: /home/user/projects/rag-fresh/docs/plans/2026-02-11-voice-bot-plan.md (Task 4)
Issue: #153

PREREQUISITE: Run "uv sync --all-extras" first to ensure deps are installed.

TASK: Create PostgreSQL schema for call transcripts, Pydantic schemas, and TranscriptStore class.

IMPORTANT CHANGE vs plan:
- Name SQL file 04-voice-schema.sql (NOT 02-voice-schema.sql) to avoid collision with existing 02-cocoindex.sql
- Check docker/postgres/init/ for existing files first

FILES TO CREATE:
- docker/postgres/init/04-voice-schema.sql (call_transcripts table + indexes)
- src/voice/schemas.py (CallStatus enum, CallRequest, CallResponse, TranscriptEntry)
- src/voice/transcript_store.py (PostgreSQL async store using asyncpg)
- src/voice/__init__.py (empty, if not exists)
- tests/unit/voice/__init__.py (empty)
- tests/unit/voice/test_transcript_store.py

IMPLEMENTATION:
Follow the plan closely for:
- SQL schema (call_transcripts table, UUID PK, phone, lead_data JSONB, transcript JSONB array, status, duration)
- 3 indexes: phone, status, created_at DESC
- CallStatus enum (INITIATED, RINGING, ANSWERED, COMPLETED, FAILED, NO_ANSWER)
- TranscriptStore class with asyncpg pool: create_call, update_status, append_transcript, finalize_call, get_call

TESTS:
- tests/unit/voice/test_transcript_store.py - test schemas and store init (no DB needed)
- Run: uv run pytest tests/unit/voice/test_transcript_store.py -v
- Do NOT run broad test directories

COMMIT:
git add docker/postgres/init/04-voice-schema.sql src/voice/schemas.py src/voice/transcript_store.py tests/unit/voice/
If src/voice/__init__.py exists and is not yet committed, add it too.
git commit with message: "feat(voice): add call transcript PostgreSQL schema and store #153"
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

MCP TOOLS:
- Context7: resolve-library-id(libraryName="asyncpg", query="asyncpg pool create_pool execute fetchrow") then query-docs
- Exa: get_code_context_exa("asyncpg create_pool JSONB insert update Python")

LOGGING to /home/user/projects/rag-fresh/logs/worker-db.log (APPEND mode, use >>):
[START] Task 4: PostgreSQL schema
[DONE] Task 4: result summary
[COMPLETE] Worker finished

WEBHOOK (after ALL tasks done, EXACTLY THREE SEPARATE Bash tool calls, NOT combined):
Call 1: TMUX="" tmux send-keys -t "claude:Claude" "W-DB COMPLETE - check logs/worker-db.log"
Call 2: sleep 1
Call 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
