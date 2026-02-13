W-VOICE: Voice Agent + Telegram /call + Integration tests

CONTEXT:
Branch: feat/voice-bot — SWITCH TO IT FIRST: git checkout feat/voice-bot
Working dir: /home/user/projects/rag-fresh
Plan: /home/user/projects/rag-fresh/docs/plans/2026-02-11-voice-bot-plan.md (Tasks 5, 6, 7)
Issue: #153
Previous tasks 1-4 already completed — src/api/, src/voice/schemas.py, src/voice/transcript_store.py, docker-compose.dev.yml all exist.

PREREQUISITE:
1. git checkout feat/voice-bot
2. uv sync --all-extras

== TASK 5: Voice Agent (src/voice/agent.py) ==

Read FIRST:
- /home/user/projects/rag-fresh/src/voice/schemas.py
- /home/user/projects/rag-fresh/src/voice/transcript_store.py
- /home/user/projects/rag-fresh/docs/plans/2026-02-11-voice-bot-plan.md (Task 5 section)

Create src/voice/agent.py:
- VoiceBot(Agent) class with lead validation instructions (Russian)
- @function_tool search_knowledge_base — calls RAG API via httpx POST to RAG_API_URL/query
- AgentServer + @server.rtc_session(agent_name="voice-bot") entrypoint
- AgentSession with: elevenlabs.STT(model="scribe_v2_realtime"), openai.LLM (base_url from LiteLLM), elevenlabs.TTS(model="eleven_turbo_v2_5"), silero.VAD.load()
- _setup_langfuse() — OTEL TracerProvider with OTLPSpanExporter to Langfuse /api/public/otel
- session.generate_reply() for initial greeting

Create src/voice/Dockerfile:
- Multi-stage: ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim builder + python:3.12-slim-bookworm runtime
- CMD: python -m src.voice.agent start

Create tests/unit/voice/test_voice_agent.py:
- test VoiceBot init with/without lead_data
- test function_tool method exists
Run: uv run pytest tests/unit/voice/test_voice_agent.py -v

Commit: git add src/voice/agent.py src/voice/Dockerfile tests/unit/voice/test_voice_agent.py
Message: "feat(voice): add LiveKit voice agent with ElevenLabs STT/TTS and RAG tool #153"

== TASK 6: Telegram /call command ==

Read FIRST:
- /home/user/projects/rag-fresh/telegram_bot/config.py (BotConfig, Field, AliasChoices pattern)
- /home/user/projects/rag-fresh/telegram_bot/bot.py (_register_handlers, _is_admin, existing cmd_ methods)

Modify telegram_bot/config.py — add to BotConfig:
- livekit_url: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_URL", "livekit_url"))
- livekit_api_key: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_API_KEY", "livekit_api_key"))
- livekit_api_secret: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_API_SECRET", "livekit_api_secret"))
- sip_trunk_id: str = Field(default="", validation_alias=AliasChoices("SIP_TRUNK_ID", "sip_trunk_id"))

Modify telegram_bot/bot.py — add cmd_call method:
- Admin-only (/call +380501234567 [description])
- Validate livekit_url and sip_trunk_id configured
- livekit api: CreateRoom, CreateAgentDispatch, CreateSIPParticipant
- Reply with call_id and room_name
- Register in _register_handlers: self.dp.message(Command("call"))(self.cmd_call)

Create tests/unit/test_cmd_call.py:
- test admin check, phone parsing, missing config
Run: uv run pytest tests/unit/test_cmd_call.py -v

Commit: git add telegram_bot/bot.py telegram_bot/config.py tests/unit/test_cmd_call.py
Message: "feat(bot): add /call command for outbound voice calls via LiveKit #153"

== TASK 7: Integration tests ==

Create tests/integration/test_voice_pipeline.py:
- test_rag_api_health (GET /health)
- test_rag_api_query (POST /query)
- test_livekit_server_health
- All marked @pytest.mark.integration, skip if service not running

Commit: git add tests/integration/test_voice_pipeline.py
Message: "test(voice): add integration tests for RAG API and LiveKit #153"

== RULES ==
- Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> in EVERY commit
- git add ONLY specific files, NOT git add -A
- Run ruff check and ruff format on changed files before each commit

MCP TOOLS:
- Context7: resolve-library-id(libraryName="livekit-agents", query="livekit agents AgentSession function_tool") then query-docs
- Exa: get_code_context_exa("livekit-agents python voice bot ElevenLabs STT TTS example 2025")

LOGGING to /home/user/projects/rag-fresh/logs/worker-voice-p3.log (APPEND mode, use >>):
[START] Task N: description
[DONE] Task N: result
[COMPLETE] Worker finished
