# Langfuse Trace Coverage Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining local Langfuse trace coverage work after PR `#1492` by making required app-owned traces structurally complete, then closing the open follow-up issues `#1486`, `#1487`, `#1488`, `#1489`, and `#1490`.

**Architecture:** Keep Langfuse integration SDK-first: app roots use `start_as_current_observation`, child work uses `@observe` or `start_as_current_observation`, trace attributes use `propagate_attributes`, and scores use `create_score` through `write_langfuse_scores`. Execute through `tmux-swarm-orchestration`: one isolated worktree per worker wave, explicit file reservations, signal artifacts, focused checks, and a dedicated read-only PR review worker before merge readiness. Do not turn this into one huge PR; split by runtime risk and file ownership.

**Tech Stack:** Python 3.11+, Langfuse Python SDK v4, aiogram, Telethon, Qdrant Python client, Docker Compose, nginx, pytest, Makefile, tmux, OpenCode swarm workers.

---

## Current State

PR `#1492` is merged and fixed the root output writer for recent text traces.
The latest local Langfuse CLI audit on 2026-05-12 found:

- latest app-owned `telegram-message` traces now have sanitized root output with
  `answer_hash`;
- required score names are present on recent app-owned text traces;
- `telegram-rag-query` and `telegram-rag-supervisor` are present;
- non-chitchat RAG trace `6d15f81fe7a7487028884179e86c880e` has
  `query_type=1`, `rag-pipeline`, retrieval/generation observations, and
  required scores, but still has no `cache-check` or `node-cache-check`;
- `litellm-acompletion` traces remain proxy-owned noise and must not count as
  application coverage;
- `#1307` is currently closed in GitHub, but the remaining acceptance work is
  represented by open issues `#1486` through `#1490`.

SDK research from Context7 and Langfuse docs, current for May 2026:

- use `@observe(...)` or `start_as_current_observation(...)` to create real
  observations;
- use `propagate_attributes(...)` early, before child observations;
- use `update_current_span(...)` only to update the current observation, not to
  create a required child observation;
- use `create_score(trace_id=..., score_id=...)` for idempotent trace scores;
- `set_current_trace_io(...)` is compatibility-oriented trace-level I/O and is
  acceptable here only because the E2E validator still checks trace-level
  sanitized root I/O.

## Scope

This plan covers six delivery waves:

1. `cache-check` SDK observation repair for the post-`#1492` blocker.
2. `#1486`: voice note fixture and voice trace gate readiness.
3. `#1487`: mini-app frontend health so `validate-traces-fast` can run.
4. `#1488`: Qdrant data/schema preflight before Telethon trace E2E.
5. `#1489`: deterministic product-meaningful assertions in no-judge E2E.
6. `#1490`: sanitized latest-trace audit artifact after E2E.

Out of scope:

- VPS, production, SSH, cloud credentials, real CRM writes.
- Replacing Langfuse or adding a custom observability transport.
- Counting flat LiteLLM proxy traces as app coverage.
- Broad refactors of `telegram_bot/bot.py`.
- Running multiple Docker/Langfuse/runtime workers concurrently.

## Swarm Classification

```json
{
  "goal": "Finish local Langfuse trace coverage acceptance through focused PR waves.",
  "decision": "sequential",
  "tasks": [
    {
      "id": "T1",
      "title": "Repair pre-agent cache decision SDK observation",
      "files": [
        "telegram_bot/bot.py",
        "tests/unit/test_bot_handlers.py",
        "tests/unit/agents/test_rag_pipeline.py"
      ],
      "tests": [
        "uv run pytest tests/unit/test_bot_handlers.py::TestHandleQuerySDKAgent::test_pre_agent_cache_miss_emits_cache_check_observation -q",
        "uv run pytest tests/unit/agents/test_rag_pipeline.py -q"
      ],
      "verification": {
        "budget": "focused_plus_optional_runtime",
        "focused": [
          "uv run pytest tests/unit/test_bot_handlers.py -q",
          "uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q"
        ],
        "broad_suite": false,
        "reason": "Hot handler file but narrow observability behavior."
      },
      "depends_on": [],
      "risk": "medium",
      "worker": "W-langfuse-cache-check",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 1,
        "contract": "full"
      }
    },
    {
      "id": "T2",
      "title": "Provide voice note fixture or block with exact external need",
      "files": [
        "scripts/e2e/config.py",
        "scripts/e2e/telegram_client.py",
        "scripts/e2e/test_scenarios.py",
        "tests/unit/e2e/test_telegram_client_voice.py",
        "tests/unit/e2e/test_voice_transcription_scenarios.py",
        "docs/LOCAL-DEVELOPMENT.md"
      ],
      "tests": [
        "uv run pytest tests/unit/e2e/test_telegram_client_voice.py tests/unit/e2e/test_voice_transcription_scenarios.py -q"
      ],
      "verification": {
        "budget": "focused_plus_optional_runtime",
        "focused": [],
        "broad_suite": false,
        "reason": "Voice runtime depends on local Telegram credentials and a non-secret audio fixture."
      },
      "depends_on": ["T1"],
      "risk": "medium",
      "worker": "W-1486-voice-fixture",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 1,
        "contract": "full"
      }
    },
    {
      "id": "T3",
      "title": "Fix mini-app frontend health for validate-traces-fast",
      "files": [
        "mini_app/frontend/Dockerfile",
        "mini_app/frontend/nginx.conf",
        "tests/unit/mini_app/test_frontend_runtime_contract.py",
        "compose.yml",
        "compose.dev.yml",
        "tests/unit/test_makefile_contract.py"
      ],
      "tests": [
        "uv run pytest tests/unit/mini_app/test_frontend_runtime_contract.py tests/unit/test_makefile_contract.py -q",
        "COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services"
      ],
      "verification": {
        "budget": "focused_plus_runtime",
        "focused": [],
        "broad_suite": false,
        "reason": "Docker/Compose/Langfuse worker counts as 2 slots and must run alone."
      },
      "depends_on": ["T1"],
      "risk": "medium",
      "worker": "W-1487-miniapp-health",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 2,
        "contract": "full"
      }
    },
    {
      "id": "T4",
      "title": "Add Qdrant data preflight to E2E trace gate",
      "files": [
        "scripts/e2e/qdrant_preflight.py",
        "scripts/e2e/runner.py",
        "scripts/e2e/config.py",
        "Makefile",
        "tests/unit/e2e/test_qdrant_preflight.py",
        "tests/unit/test_makefile_contract.py"
      ],
      "tests": [
        "uv run pytest tests/unit/e2e/test_qdrant_preflight.py tests/unit/test_makefile_contract.py -q"
      ],
      "verification": {
        "budget": "focused_plus_optional_runtime",
        "focused": [],
        "broad_suite": false,
        "reason": "Preflight is pure local validation with mocked unit coverage; live Qdrant is optional."
      },
      "depends_on": ["T1"],
      "risk": "medium",
      "worker": "W-1488-qdrant-preflight",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 1,
        "contract": "full"
      }
    },
    {
      "id": "T5",
      "title": "Make no-judge Telethon scenarios product-meaningful",
      "files": [
        "scripts/e2e/claude_judge.py",
        "scripts/e2e/runner.py",
        "scripts/e2e/report_generator.py",
        "scripts/e2e/test_scenarios.py",
        "tests/unit/e2e/test_passthrough_judge.py",
        "tests/unit/e2e/test_corpus_e2e_config.py"
      ],
      "tests": [
        "uv run pytest tests/unit/e2e/test_passthrough_judge.py tests/unit/e2e/test_corpus_e2e_config.py -q"
      ],
      "verification": {
        "budget": "focused_only",
        "focused": [],
        "broad_suite": false,
        "reason": "Deterministic text assertions do not require live services."
      },
      "depends_on": ["T4"],
      "risk": "medium",
      "worker": "W-1489-product-assertions",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 1,
        "contract": "full"
      }
    },
    {
      "id": "T6",
      "title": "Add latest-trace audit artifact command",
      "files": [
        "scripts/e2e/langfuse_latest_trace_audit.py",
        "Makefile",
        "tests/unit/e2e/test_langfuse_latest_trace_audit.py",
        "tests/unit/test_makefile_contract.py",
        "docs/runbooks/LANGFUSE_TRACING_GAPS.md"
      ],
      "tests": [
        "uv run pytest tests/unit/e2e/test_langfuse_latest_trace_audit.py tests/unit/test_makefile_contract.py -q"
      ],
      "verification": {
        "budget": "focused_plus_optional_runtime",
        "focused": [],
        "broad_suite": false,
        "reason": "Audit artifact can be unit-tested with fixture JSON; live Langfuse run is optional."
      },
      "depends_on": ["T1", "T4", "T5"],
      "risk": "medium",
      "worker": "W-1490-latest-trace-audit",
      "route": {
        "worker_type": "implementation",
        "agent": "pr-worker",
        "slot_weight": 1,
        "contract": "full"
      }
    }
  ],
  "waves": [
    ["W-langfuse-cache-check"],
    ["W-1486-voice-fixture"],
    ["W-1487-miniapp-health"],
    ["W-1488-qdrant-preflight"],
    ["W-1489-product-assertions"],
    ["W-1490-latest-trace-audit"],
    ["W-final-runtime-verify"],
    ["W-readonly-pr-review"]
  ],
  "reserved_files_by_worker": {
    "W-langfuse-cache-check": [
      "telegram_bot/bot.py",
      "tests/unit/test_bot_handlers.py",
      "tests/unit/agents/test_rag_pipeline.py"
    ],
    "W-1486-voice-fixture": [
      "scripts/e2e/config.py",
      "scripts/e2e/telegram_client.py",
      "scripts/e2e/test_scenarios.py",
      "tests/unit/e2e/test_telegram_client_voice.py",
      "tests/unit/e2e/test_voice_transcription_scenarios.py",
      "docs/LOCAL-DEVELOPMENT.md"
    ],
    "W-1487-miniapp-health": [
      "mini_app/frontend/Dockerfile",
      "mini_app/frontend/nginx.conf",
      "tests/unit/mini_app/test_frontend_runtime_contract.py",
      "compose.yml",
      "compose.dev.yml",
      "tests/unit/test_makefile_contract.py"
    ],
    "W-1488-qdrant-preflight": [
      "scripts/e2e/qdrant_preflight.py",
      "scripts/e2e/runner.py",
      "scripts/e2e/config.py",
      "Makefile",
      "tests/unit/e2e/test_qdrant_preflight.py",
      "tests/unit/test_makefile_contract.py"
    ],
    "W-1489-product-assertions": [
      "scripts/e2e/claude_judge.py",
      "scripts/e2e/runner.py",
      "scripts/e2e/report_generator.py",
      "scripts/e2e/test_scenarios.py",
      "tests/unit/e2e/test_passthrough_judge.py",
      "tests/unit/e2e/test_corpus_e2e_config.py"
    ],
    "W-1490-latest-trace-audit": [
      "scripts/e2e/langfuse_latest_trace_audit.py",
      "Makefile",
      "tests/unit/e2e/test_langfuse_latest_trace_audit.py",
      "tests/unit/test_makefile_contract.py",
      "docs/runbooks/LANGFUSE_TRACING_GAPS.md"
    ]
  },
  "final_integration": "orchestrator",
  "why_not_parallel": "The waves share Makefile, runner, e2e report contracts, Docker services, and Langfuse runtime state. Runtime/Docker/Langfuse workers count as 2 slots and should not contend with other live-service workers."
}
```

## File Structure

### Modify

- `telegram_bot/bot.py`
  - Add SDK-native `cache-check` observation for the pre-agent cache decision
    path that currently bypasses `_cache_check()` in `rag_pipeline()`.
  - Do not broaden the handler refactor.

- `tests/unit/test_bot_handlers.py`
  - Add focused regression coverage proving pre-agent cache MISS emits a
    `cache-check` observation while preserving existing miss -> agent/direct
    flow.

- `scripts/e2e/config.py`
  - Add E2E preflight configuration knobs for Qdrant collection names, minimum
    point counts, required vector names, and optional default voice fixture path.

- `scripts/e2e/qdrant_preflight.py`
  - New sanitized preflight for required Qdrant collections and vector schema.

- `scripts/e2e/claude_judge.py`
  - Keep LLM judge behavior intact.
  - Replace no-judge pass-through with deterministic local checks for response
    presence, expected keywords, expected filters, and generic fallback
    rejection.

- `scripts/e2e/report_generator.py`
  - Include deterministic assertion details and audit artifact pointers without
    printing raw Qdrant payloads.

- `scripts/e2e/runner.py`
  - Wire Qdrant preflight before live Telegram sends.
  - Preserve `--no-judge` but make it deterministic, not "any non-empty text".

- `scripts/e2e/langfuse_latest_trace_audit.py`
  - New sanitized latest-trace audit command with CLI-first behavior and SDK
    fallback where practical.

- `Makefile`
  - Add preflight/audit hooks for `e2e-test-traces-core` or separate explicit
    targets when preserving failure status requires it.

- `mini_app/frontend/Dockerfile`
  - Ensure nginx runtime temp directories exist and are writable by user
    `101:101`.

- `mini_app/frontend/nginx.conf`
  - Keep temp paths under `/tmp`; do not reintroduce `/var/cache/nginx`.

- `tests/unit/e2e/*`, `tests/unit/mini_app/*`, `tests/unit/test_makefile_contract.py`
  - Focused unit and contract tests for the above.

### Create

- `scripts/e2e/qdrant_preflight.py`
- `tests/unit/e2e/test_qdrant_preflight.py`
- `scripts/e2e/langfuse_latest_trace_audit.py`
- `tests/unit/e2e/test_langfuse_latest_trace_audit.py`
- Optional only if approved and small: `tests/fixtures/e2e/voice_property_search.ogg`

### Do Not Modify

- Production deploy scripts.
- VPS/k8s manifests unless a worker finds a direct contract break and signals
  blocked before expanding scope.
- `.env`, Telegram session files, SSH/cloud credentials, or real CRM paths.

## Task 0: Orchestration Setup For Each Wave

**Files:**
- Create: `.codex/prompts/<worker-name>.md`
- Modify: `.signals/active-workers.jsonl`
- Create in each worktree: `.signals/<worker-name>.json`

- [ ] **Step 1: Confirm orchestration state**

Run:

```bash
git status --short
scripts/registry_state.py --registry .signals/active-workers.jsonl || true
tmux list-windows | rg 'W-' || true
```

Expected: existing dirty files are understood. Current known dirty files in the
main checkout are unrelated to product implementation and must not be reverted:

- `.opencode/skills/gh-pr-review/SKILL.md`
- `docs/superpowers/plans/2026-05-12-langfuse-trace-coverage-phase1-plan.md`
- `docs/superpowers/plans/2026-05-12-issue-1493-bge-m3-query-vector-bundle.md`

- [ ] **Step 2: Capture orchestrator routing identity**

Run:

```bash
ORCH_PANE=$(tmux display-message -p '#{pane_id}')
tmux display-message -p -t "$ORCH_PANE" '#{pane_id} #{pane_dead}'
tmux display-message -p '#{window_id} #{window_index}'
```

Expected: pane id matches and `pane_dead` is `0`.

- [ ] **Step 3: Create one worktree per wave**

Use a unique branch per issue/wave:

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
WT_PATH="${PROJECT_ROOT}-wt-<wave-name>"
git worktree add "$WT_PATH" -b fix/<issue-or-topic> dev
mkdir -p "$WT_PATH/.signals" "$WT_PATH/logs" "$PROJECT_ROOT/.codex/prompts" "$PROJECT_ROOT/.signals"
touch "$PROJECT_ROOT/.signals/active-workers.jsonl"
```

Expected: each worker has a dedicated worktree and branch.

- [ ] **Step 4: Write a full worker prompt**

Each prompt must include:

```markdown
WORKER MODEL: opencode-go/kimi-k2.6
Required OpenCode skills: swarm-pr-finish
Branch/base: fix/<issue-or-topic> based on dev
Worktree: <absolute WT_PATH>
Signal file: <absolute WT_PATH>/.signals/<worker-name>.json
Docs lookup policy: no web search. Use local docs and the SDK facts pasted in this prompt. If external docs are required, stop and signal blocked.
Reserved files:
- <exact file list>
Acceptance:
- <exact checks>
Completion:
- Commit changes.
- Open or update a PR against dev.
- Write DONE/FAILED/BLOCKED JSON to the signal file.
```

- [ ] **Step 5: Validate and launch prompt**

Run:

```bash
${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py --contract full .codex/prompts/<worker-name>.md
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
OPENCODE_REQUIRED_SKILLS=swarm-pr-finish \
SWARM_LOCAL_ONLY=1 \
${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  --name <worker-name> \
  --worktree "$WT_PATH" \
  --prompt ".codex/prompts/<worker-name>.md"
```

Expected: visible tmux worker window starts and registry records runner,
prompt SHA, worktree, pane/window routing, branch/base, reserved files, and
signal path.

- [ ] **Step 6: Review every PR with a read-only review worker**

After each runtime/code PR reaches a candidate head SHA, launch:

```bash
OPENCODE_AGENT=pr-review \
OPENCODE_MODEL=opencode-go/deepseek-v4-pro \
OPENCODE_REQUIRED_SKILLS=gh-pr-review,swarm-pr-finish \
SWARM_LOCAL_ONLY=1 \
${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  --name <worker-name>-review \
  --worktree "$WT_PATH" \
  --prompt ".codex/prompts/<worker-name>-review.md"
```

Expected: read-only review worker reports APPROVED or named blockers. Fixes
must go through a separate `pr-review-fix` worker on the same PR branch.

## Task 1: Repair Pre-Agent Cache Decision Observation

**Files:**
- Modify: `telegram_bot/bot.py`
- Test: `tests/unit/test_bot_handlers.py`
- Optional Test: `tests/unit/agents/test_rag_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add a focused test near the existing pre-agent cache MISS tests:

```python
async def test_pre_agent_cache_miss_emits_cache_check_observation(self, mock_config):
    bot = PropertyBot(mock_config)
    self._setup_pre_agent_cache_miss(bot)

    observation = MagicMock()
    observation.__enter__.return_value = observation
    observation.__exit__.return_value = None
    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = "trace-pre-agent-miss"
    mock_lf.start_as_current_observation.return_value = observation

    with patch("telegram_bot.bot.get_client", return_value=mock_lf):
        await bot.handle_query_sdk_agent(
            message=self._message("2-комн в Солнечный берег до 120к"),
            locale="ru",
        )

    mock_lf.start_as_current_observation.assert_any_call(
        as_type="span",
        name="cache-check",
        input=ANY,
    )
    assert any(
        call.kwargs.get("output", {}).get("cache_hit") is False
        for call in observation.update.call_args_list
    )
```

Adjust helper names to match the local test class. The assertion must prove a
real SDK observation is created; asserting `update_current_span(...)` is not
enough.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestHandleQuerySDKAgent::test_pre_agent_cache_miss_emits_cache_check_observation -q
```

Expected: FAIL because no `start_as_current_observation(name="cache-check")`
call exists on the pre-agent cache miss path.

- [ ] **Step 3: Implement minimal SDK-native observation**

In `telegram_bot/bot.py`, wrap the pre-agent semantic cache decision with a
real SDK span. Keep payload safe and bounded:

```python
cache_obs_input = {
    "query_len": len(user_text),
    "query_type": query_type,
    "cache_scope": "rag",
    "agent_role": role,
    "filter_sensitive": filter_signal.is_filter_sensitive,
    "has_filter_signature": filter_signature is not None,
    "contextual_query": contextual_query,
}
with get_client().start_as_current_observation(
    as_type="span",
    name="cache-check",
    input=cache_obs_input,
) as cache_obs:
    if contextual_query or (filter_signal.is_filter_sensitive and filter_signature is None):
        rag_result_store["semantic_cache_already_checked"] = True
        cache_obs.update(
            output={
                "cache_hit": False,
                "skipped": True,
                "skip_reason": "contextual_or_unresolved_filter",
            }
        )
    else:
        check_start = time.perf_counter()
        cached = await self._cache.check_semantic(...)
        rag_result_store["pre_agent_cache_check_ms"] = (
            time.perf_counter() - check_start
        ) * 1000
        rag_result_store["semantic_cache_already_checked"] = True
        cache_obs.update(
            output={
                "cache_hit": bool(cached),
                "semantic_cache_already_checked": True,
                "duration_ms": round(rag_result_store["pre_agent_cache_check_ms"], 1),
            }
        )
```

Implementation notes:

- Use the existing local variables in the pre-agent block.
- Do not include raw `user_text`, chat id, user id, Telegram payloads, or cached
  response text in the observation payload.
- If `get_client()` or the observation call raises, do not break Telegram
  handling. Match the repo's existing best-effort observability pattern.
- Do not relax `scripts/e2e/langfuse_trace_validator.py`.
- Do not alias `cache-semantic-check` to `cache-check`; that would hide the
  missing product-level decision observation.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::TestHandleQuerySDKAgent::test_pre_agent_cache_miss_emits_cache_check_observation -q
uv run pytest tests/unit/test_bot_handlers.py -q
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Optional runtime gate**

If local bot, Langfuse, Telegram credentials, Redis, Qdrant, BGE-M3, and
LiteLLM are already available, run:

```bash
RUN_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1
langfuse --env .env api traces list \
  --from-timestamp "$RUN_START" \
  --name telegram-message \
  --order-by timestamp.desc \
  --limit 6 \
  --fields core,io,scores,observations,metrics \
  --json > /tmp/rag-fresh-cache-check-postfix.json
```

Summarize only ids, timestamps, output null state, score names, and observation
booleans. Do not print raw input/output values.

Expected for non-chitchat traces: `has_cache_check=true`.

- [ ] **Step 6: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix(observability): trace pre-agent cache decisions"
```

## Task 2: Voice Note Fixture For Scenario 8.1 (#1486)

**Files:**
- Modify: `scripts/e2e/config.py`
- Modify: `scripts/e2e/telegram_client.py`
- Modify: `scripts/e2e/test_scenarios.py`
- Test: `tests/unit/e2e/test_telegram_client_voice.py`
- Test: `tests/unit/e2e/test_voice_transcription_scenarios.py`
- Modify docs: `docs/LOCAL-DEVELOPMENT.md`
- Optional Create: `tests/fixtures/e2e/voice_property_search.ogg`

- [ ] **Step 1: Decide fixture availability**

Worker must first check whether a non-secret, small, license-safe voice fixture
already exists:

```bash
find tests scripts docs -iname '*voice*' -o -iname '*.ogg' -o -iname '*.oga' -o -iname '*.opus'
```

Expected:

- If a suitable fixture exists, use it.
- If not, do not invent raw user audio. Signal `BLOCKED` unless the user has
  provided or approved a generated synthetic speech fixture.

- [ ] **Step 2: Add or wire default fixture path**

If a fixture is available, update `E2EConfig.voice_note_path` to allow an
explicit env override and a repo default:

```python
voice_note_path: str = field(
    default_factory=lambda: os.getenv(
        "E2E_VOICE_NOTE_PATH",
        "tests/fixtures/e2e/voice_property_search.ogg",
    )
)
```

If no fixture is committed, keep the env-required behavior and improve the
error message with the exact documented path.

- [ ] **Step 3: Write tests**

Cover:

- voice scenario `8.1` still has `delivery="voice"`;
- missing fixture gives a clear error;
- default fixture path is used only when the file exists or the worker has
  committed the fixture.

Run:

```bash
uv run pytest tests/unit/e2e/test_telegram_client_voice.py tests/unit/e2e/test_voice_transcription_scenarios.py -q
```

Expected: PASS.

- [ ] **Step 4: Update docs**

In `docs/LOCAL-DEVELOPMENT.md`, document:

```bash
export E2E_VOICE_NOTE_PATH=tests/fixtures/e2e/voice_property_search.ogg
make e2e-test-traces-core
```

Also document that the file must be a non-secret local test fixture and that
session files or private Telegram audio must not be committed.

- [ ] **Step 5: Commit or block**

If fixed:

```bash
git add scripts/e2e/config.py scripts/e2e/telegram_client.py scripts/e2e/test_scenarios.py tests/unit/e2e/test_telegram_client_voice.py tests/unit/e2e/test_voice_transcription_scenarios.py docs/LOCAL-DEVELOPMENT.md tests/fixtures/e2e/voice_property_search.ogg
git commit -m "test(e2e): provide voice note trace fixture"
```

If no fixture is available, write `BLOCKED` signal with the exact external ask:
"Need a non-secret OGG/OGA voice note saying a property-search query suitable
for scenario 8.1, approved for repository test use."

## Task 3: Mini-App Frontend Health For validate-traces-fast (#1487)

**Files:**
- Modify: `mini_app/frontend/Dockerfile`
- Modify: `mini_app/frontend/nginx.conf`
- Test: `tests/unit/mini_app/test_frontend_runtime_contract.py`
- Optional Modify: `compose.yml`
- Optional Modify: `compose.dev.yml`
- Test: `tests/unit/test_makefile_contract.py`

- [ ] **Step 1: Write runtime contract test**

Add assertions that:

- `nginx.conf` uses temp paths under `/tmp`;
- Dockerfile creates those directories;
- Dockerfile sets ownership for `101:101`;
- Dockerfile still runs `USER 101:101`.

Example:

```python
def test_frontend_nginx_temp_dirs_are_created_for_unprivileged_runtime():
    dockerfile = Path("mini_app/frontend/Dockerfile").read_text()
    nginx_conf = Path("mini_app/frontend/nginx.conf").read_text()
    for path in [
        "/tmp/client_temp",
        "/tmp/proxy_temp",
        "/tmp/fastcgi_temp",
        "/tmp/uwsgi_temp",
        "/tmp/scgi_temp",
    ]:
        assert path in nginx_conf
        assert path in dockerfile
    assert "chown -R 101:101" in dockerfile
    assert "USER 101:101" in dockerfile
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/mini_app/test_frontend_runtime_contract.py -q
```

Expected: FAIL if Dockerfile does not create/chown nginx temp dirs.

- [ ] **Step 3: Fix Dockerfile**

Add before `USER 101:101`:

```dockerfile
RUN mkdir -p \
    /tmp/client_temp \
    /tmp/proxy_temp \
    /tmp/fastcgi_temp \
    /tmp/uwsgi_temp \
    /tmp/scgi_temp \
    && chown -R 101:101 \
    /tmp/client_temp \
    /tmp/proxy_temp \
    /tmp/fastcgi_temp \
    /tmp/uwsgi_temp \
    /tmp/scgi_temp
```

If live logs still show `/tmp/nginx/client_temp`, inspect the built image's
`/etc/nginx/nginx.conf`; this likely means a stale image or different config,
not the checked-in `nginx.conf`.

- [ ] **Step 4: Run focused checks**

```bash
uv run pytest tests/unit/mini_app/test_frontend_runtime_contract.py tests/unit/test_makefile_contract.py -q
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
```

Expected: PASS and `mini-app-frontend` appears once in rendered services.

- [ ] **Step 5: Optional runtime verification**

Only when no other runtime worker is active:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility build mini-app-frontend
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --wait mini-app-api mini-app-frontend
curl -fsS http://127.0.0.1:8091/health
```

Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add mini_app/frontend/Dockerfile mini_app/frontend/nginx.conf tests/unit/mini_app/test_frontend_runtime_contract.py tests/unit/test_makefile_contract.py
git commit -m "fix(docker): keep mini app nginx temp paths writable"
```

## Task 4: Qdrant Data Preflight For E2E Trace Gate (#1488)

**Files:**
- Create: `scripts/e2e/qdrant_preflight.py`
- Modify: `scripts/e2e/config.py`
- Modify: `scripts/e2e/runner.py`
- Modify: `Makefile`
- Test: `tests/unit/e2e/test_qdrant_preflight.py`
- Test: `tests/unit/test_makefile_contract.py`

- [ ] **Step 1: Write tests for preflight behavior**

Test cases:

- missing `gdrive_documents_bge` fails with sanitized remediation;
- `gdrive_documents_bge` below minimum count fails;
- missing `dense` or `colbert` vector fails;
- `apartments` below minimum count fails;
- no payload contents are printed.

Example assertions:

```python
def test_preflight_fails_when_collection_missing(mock_qdrant):
    mock_qdrant.collection_exists.return_value = False
    result = run_preflight(client=mock_qdrant, collections=[...])
    assert not result.ok
    assert "gdrive_documents_bge" in result.message
    assert "payload" not in result.message.lower()
```

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/unit/e2e/test_qdrant_preflight.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement preflight module**

Implement a small module with typed results:

```python
@dataclass(frozen=True)
class CollectionRequirement:
    name: str
    min_points: int
    required_vectors: frozenset[str]

@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    message: str
    checked: list[dict[str, object]]
```

Default requirements:

- `gdrive_documents_bge`: min points from `E2E_QDRANT_MIN_DOC_POINTS`, default
  `1`, required vectors `dense,colbert`;
- `apartments`: min points from `E2E_QDRANT_MIN_APARTMENT_POINTS`, default `1`,
  required vectors `dense,colbert`.

Use `qdrant_client.QdrantClient` and `collection_exists()` /
`get_collection()`. Print collection names, counts, and vector names only.

- [ ] **Step 4: Wire runner and Makefile**

In `scripts/e2e/runner.py`, run preflight before connecting to Telegram when
the selected scenarios include RAG/apartment/voice trace scenarios. Add a
`--skip-qdrant-preflight` flag only for local debugging, default false.

In `Makefile`, keep `e2e-test-traces-core` explicit and ensure the target still
uses:

```make
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1 --scenario 8.1
```

If preflight is run inside runner, no extra Makefile command is required beyond
contract tests for the target.

- [ ] **Step 5: Run focused checks**

```bash
uv run pytest tests/unit/e2e/test_qdrant_preflight.py tests/unit/test_makefile_contract.py -q
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
```

Expected: PASS.

- [ ] **Step 6: Optional live preflight**

```bash
uv run python -m scripts.e2e.qdrant_preflight
```

Expected: PASS on local Qdrant with sanitized output similar to:

```text
Qdrant E2E preflight OK: gdrive_documents_bge points=352 vectors=dense,colbert; apartments points=297 vectors=dense,colbert
```

- [ ] **Step 7: Commit**

```bash
git add scripts/e2e/qdrant_preflight.py scripts/e2e/config.py scripts/e2e/runner.py Makefile tests/unit/e2e/test_qdrant_preflight.py tests/unit/test_makefile_contract.py
git commit -m "test(e2e): preflight qdrant data for trace gate"
```

## Task 5: Deterministic Product Assertions In No-Judge Mode (#1489)

**Files:**
- Modify: `scripts/e2e/claude_judge.py`
- Modify: `scripts/e2e/report_generator.py`
- Optional Modify: `scripts/e2e/test_scenarios.py`
- Test: `tests/unit/e2e/test_passthrough_judge.py`
- Test: `tests/unit/e2e/test_corpus_e2e_config.py`

- [ ] **Step 1: Write failing tests**

Add tests for no-judge behavior:

```python
async def test_no_judge_fails_missing_expected_keyword():
    scenario = TestScenario(
        id="x",
        name="keyword",
        query="Какие требования для визы Digital Nomad?",
        group=TestGroup.IMMIGRATION,
        expected_keywords=["digital", "nomad", "виза"],
    )
    judge = PassthroughJudge(E2EConfig())
    result = await judge.evaluate(scenario, "Ответ про недвижимость")
    assert not result.passed
    assert "missing keyword" in result.summary.lower()
```

Also cover:

- response that contains expected keywords passes;
- generic fallback text fails for RAG/property scenarios;
- expected filters fail when answer omits city/price/rooms evidence;
- chitchat can pass with response presence only or looser keyword checks.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/unit/e2e/test_passthrough_judge.py -q
```

Expected: FAIL because no-judge currently passes any non-empty response.

- [ ] **Step 3: Implement deterministic no-judge checks**

Keep class name `PassthroughJudge` if many callers expect it, but change
semantics to deterministic local validation:

```python
def _contains_any_keyword(response: str, keywords: list[str]) -> bool:
    lowered = response.lower()
    return any(keyword.lower() in lowered for keyword in keywords)

def _generic_fallback_detected(response: str) -> bool:
    lowered = response.lower()
    bad_markers = [
        "не нашел информацию",
        "попробуйте переформулировать",
        "не удалось найти",
        "сервис временно недоступен",
    ]
    return any(marker in lowered for marker in bad_markers)
```

For `ExpectedFilters`, require lightweight evidence:

- `price_max=120000`: response contains `120`, `120к`, `120 000`, or a lower
  euro price marker;
- `city="Солнечный берег"`: response contains `солнеч`;
- `rooms=2`: response contains `2`, `двух`, or `2-ком`;
- `distance_to_sea_max=300`: response contains `300`, `м`, `мор`, or `пляж`.

Do not parse Qdrant payloads. This is a response-level deterministic gate, not
a search engine test.

- [ ] **Step 4: Include assertion details in reports**

Add an optional field to `TestResult`, for example:

```python
deterministic_checks: dict[str, object] | None = None
```

Populate JSON reports with pass/fail details. Keep raw response behavior
unchanged for existing report consumers.

- [ ] **Step 5: Run focused checks**

```bash
uv run pytest tests/unit/e2e/test_passthrough_judge.py tests/unit/e2e/test_corpus_e2e_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/e2e/claude_judge.py scripts/e2e/report_generator.py scripts/e2e/test_scenarios.py tests/unit/e2e/test_passthrough_judge.py tests/unit/e2e/test_corpus_e2e_config.py
git commit -m "test(e2e): enforce deterministic product checks"
```

## Task 6: Latest Trace Audit Artifact (#1490)

**Files:**
- Create: `scripts/e2e/langfuse_latest_trace_audit.py`
- Modify: `Makefile`
- Test: `tests/unit/e2e/test_langfuse_latest_trace_audit.py`
- Test: `tests/unit/test_makefile_contract.py`
- Modify: `docs/runbooks/LANGFUSE_TRACING_GAPS.md`

- [ ] **Step 1: Write failing tests**

Use fixture dicts, not live Langfuse:

```python
def test_audit_redacts_io_and_reports_required_coverage(tmp_path):
    traces = [
        {
            "id": "trace-1",
            "name": "telegram-message",
            "input": {"query_hash": "abc", "query_preview": "redacted"},
            "output": {"answer_hash": "def"},
            "scores": [{"name": "query_type", "value": 1}],
            "observations": [{"name": "telegram-rag-query"}, {"name": "cache-check"}],
        }
    ]
    report = build_audit_report(traces, output_dir=tmp_path)
    text = report.read_text()
    assert "query_preview" not in text
    assert "trace-1" in text
    assert "cache-check" in text
```

Cover:

- proxy `litellm-acompletion` classified as proxy noise;
- missing root output exits non-zero;
- missing `cache-check` for `query_type != 0` exits non-zero;
- artifact path is `.artifacts/langfuse-local-audit/<timestamp>/latest-traces.md`.

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/unit/e2e/test_langfuse_latest_trace_audit.py -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement audit module**

Implement:

```python
def summarize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": trace.get("id"),
        "name": trace.get("name"),
        "timestamp": trace.get("timestamp"),
        "input_keys": sorted((trace.get("input") or {}).keys()),
        "output_keys": sorted((trace.get("output") or {}).keys()),
        "output_is_null": trace.get("output") is None,
        "score_names": sorted(score_name(s) for s in trace.get("scores") or []),
        "observation_names": sorted({o.get("name") for o in trace.get("observations") or []}),
    }
```

CLI behavior:

- Prefer `langfuse --env .env api traces list ... --json` when the CLI exists.
- Use SDK fallback if CLI is unavailable.
- Accept `--from-timestamp`, `--limit`, `--output-dir`.
- Never print raw `input`, `output`, Telegram text, chat IDs, session strings,
  or Qdrant payloads.

- [ ] **Step 4: Add Make target**

Add a target:

```make
.PHONY: e2e-audit-langfuse-latest

e2e-audit-langfuse-latest: ## Write sanitized latest Langfuse trace audit artifact
	@mkdir -p .artifacts/langfuse-local-audit
	uv run python -m scripts.e2e.langfuse_latest_trace_audit
```

Do not force this target to run after every local `e2e-test-traces-core` until
failure status preservation is tested. If wiring into the core target, capture
runner exit status and audit exit status separately and return non-zero if
either fails.

- [ ] **Step 5: Run focused checks**

```bash
uv run pytest tests/unit/e2e/test_langfuse_latest_trace_audit.py tests/unit/test_makefile_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Optional live audit**

```bash
uv run python -m scripts.e2e.langfuse_latest_trace_audit --limit 6
```

Expected: creates `.artifacts/langfuse-local-audit/<timestamp>/latest-traces.md`
and exits non-zero if required app-owned traces are incomplete.

- [ ] **Step 7: Commit**

```bash
git add scripts/e2e/langfuse_latest_trace_audit.py Makefile tests/unit/e2e/test_langfuse_latest_trace_audit.py tests/unit/test_makefile_contract.py docs/runbooks/LANGFUSE_TRACING_GAPS.md
git commit -m "test(observability): add latest trace audit artifact"
```

## Task 7: Final Runtime Verification Wave

**Files:**
- Read-only unless a named blocker is assigned to a review-fix worker.

- [ ] **Step 1: Ensure services are not contended**

Before runtime checks, ensure no other runtime/Docker/Langfuse worker is active.
Runtime workers count as 2 slots.

Run:

```bash
scripts/registry_state.py --registry .signals/active-workers.jsonl || true
tmux list-windows | rg 'W-' || true
```

- [ ] **Step 2: Verify local service health**

Run only in local/test environment:

```bash
curl -fsS http://localhost:3001/api/public/health
curl -fsS http://localhost:4000/health/readiness
curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:8000/health
```

Expected: local Langfuse, LiteLLM, Qdrant, and BGE-M3 are healthy. Do not print
secrets.

- [ ] **Step 3: Restart bot only if code changed**

If the bot was already running before these PRs, restart the bot. Do not
restart Langfuse unless its own services are unhealthy.

Native:

```bash
make bot
```

Docker bot only, if using container runtime:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility build bot
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate bot
```

- [ ] **Step 4: Run text-only trace gate**

```bash
RUN_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1
```

Expected: PASS.

- [ ] **Step 5: Run full core trace gate**

Only after `#1486` has a valid voice fixture:

```bash
make e2e-test-traces-core
```

Expected: PASS for scenarios `0.1`, `6.3`, `7.1`, and `8.1`.

- [ ] **Step 6: Run validate-traces-fast**

Only after `#1487` is fixed:

```bash
make validate-traces-fast
```

Expected: no mini-app health pre-validation failure; trace validation runs.

- [ ] **Step 7: Run latest trace audit**

```bash
uv run python -m scripts.e2e.langfuse_latest_trace_audit --from-timestamp "$RUN_START" --limit 12
```

Expected:

- artifact created under `.artifacts/langfuse-local-audit/<timestamp>/latest-traces.md`;
- app-owned `telegram-message` traces have non-null sanitized output;
- non-chitchat traces have `cache-check` or `node-cache-check`;
- required score names are present;
- LiteLLM proxy traces are classified as proxy noise;
- no raw input/output values are printed.

- [ ] **Step 8: Review and close loop**

For each merged PR:

```bash
gh issue comment <issue> --body "Fixed in PR #<pr>. Verification: <commands or blocker>."
gh issue close <issue>
```

If a live gate is blocked by local credentials or missing user-provided voice
fixture, leave the issue open and add a precise blocker comment.

## Required PR Review Gate

Every code/runtime PR from this plan must get:

1. Worker DONE signal with changed files, commit SHA, PR URL, commands, skipped
   checks and reasons.
2. Orchestrator bounded diff review.
3. Dedicated read-only `pr-review` worker on the current PR head SHA.
4. Review-fix worker for named blockers only.
5. Fresh read-only review after any review-fix wave.

Do not merge on tests alone.

## Final Acceptance Criteria

This plan is complete when:

- recent text RAG `telegram-message` traces have sanitized root input/output,
  required scores, `telegram-rag-query`, `telegram-rag-supervisor`, and
  `cache-check` or `node-cache-check` when `query_type != 0`;
- `#1486` is fixed or explicitly blocked on a user-approved non-secret voice
  fixture;
- `#1487` no longer blocks `make validate-traces-fast` before trace validation;
- `#1488` fails early with actionable sanitized Qdrant data/schema preflight
  errors;
- `#1489` no-judge mode fails non-empty but unmeaningful responses;
- `#1490` produces sanitized latest-trace audit artifacts;
- final runtime verification has been run, or each skipped live check has an
  exact local blocker.
