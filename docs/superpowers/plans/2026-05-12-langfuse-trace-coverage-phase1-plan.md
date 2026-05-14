# Langfuse Trace Coverage Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `#1485` text-only Langfuse trace gate deterministic and green for scenarios `0.1`, `6.3`, and `7.1`.

**Architecture:** Keep the Langfuse integration SDK-first. The Telegram middleware owns app-level root traces, child work uses `@observe`, root response I/O uses SDK trace I/O helpers, and required scores stay centralized through `write_langfuse_scores`. Execution must be coordinated by `tmux-swarm-orchestration`: workers run in dedicated worktrees, reserve files, commit their work, and a separate read-only PR review worker reviews the runtime/code PR before merge readiness.

**Tech Stack:** Python 3.11+, Langfuse Python SDK v4, aiogram, Telethon E2E runner, pytest, tmux, OpenCode swarm workers.

---

## Scope

This plan implements Phase 1 from:

- Spec: `docs/superpowers/specs/2026-05-12-langfuse-trace-coverage-design.md`
- Issue: `#1485`
- Parent issue: `#1307`
- Related PR: `#1491`

This plan does not implement:

- `#1486` voice-note fixture for scenario `8.1`;
- `#1487` `validate-traces-fast` / mini-app health fix;
- `#1488` Qdrant data preflight;
- `#1489` product-meaningful scenario checks;
- `#1490` latest-trace audit artifact.

## Swarm Execution Contract

Classification: `one_worker` implementation wave, followed by a dedicated
read-only PR review worker. The code changes are coupled enough that parallel
implementation workers would create unnecessary conflicts across the validator,
runtime send paths, and tests.

Orchestrator responsibilities:

- use `$tmux-swarm-orchestration`;
- create and validate a dedicated implementation worktree;
- reserve files before launch;
- launch a visible OpenCode worker with `OPENCODE_AGENT=pr-worker`,
  `OPENCODE_MODEL=opencode-go/kimi-k2.6`,
  `OPENCODE_REQUIRED_SKILLS=swarm-pr-finish`, and `SWARM_LOCAL_ONLY=1`;
- review the worker diff and command evidence;
- run any missing focused checks locally if needed;
- launch a separate read-only `pr-review` worker on the current PR head SHA
  before merge/readiness.

Implementation worker responsibilities:

- use OpenCode-visible skill `swarm-pr-finish`;
- work only in the assigned worktree;
- do not read `.env`, production credentials, SSH, cloud credentials, or real
  CRM write paths;
- do not use web search or external docs lookup;
- implement only the reserved Phase 1 files;
- commit and open/update a PR against `dev`;
- write a DONE/FAILED/BLOCKED signal artifact with command evidence.

Runtime validation worker responsibilities, if launched later:

- read-only unless explicitly assigned a review-fix wave;
- treat local Telegram credentials and service availability as external gates;
- do not print secrets, chat IDs, session strings, or raw Telegram payloads.

## File Structure

### Modify

- `scripts/e2e/langfuse_trace_validator.py`
  - Owns Telethon E2E Langfuse validation.
  - Add cache-check alias resolution if `#1491` is not already in the base.
  - Add deterministic invalid `query_type` score handling.
  - Keep score enforcement in this validator for Phase 1.

- `tests/unit/e2e/test_langfuse_trace_validator.py`
  - Add focused regression tests for:
    - `cache-check` satisfying `node-cache-check`;
    - missing root output failing;
    - missing required scores failing;
    - invalid/non-numeric `query_type` failing.

- `telegram_bot/services/telegram_formatting.py`
  - Keep the existing SDK-first root output writer.
  - Make the output recording helper public only if another runtime module must
    call it directly.

- `tests/unit/test_telegram_formatting.py`
  - Update tests if the helper is made public.
  - Keep existing tests for `set_current_trace_io`, fallback to
    `update_current_span`, and safe output payload shape.

- `telegram_bot/services/generate_response.py`
  - Ensure streaming paths that send directly with `message.answer()` also
    record sanitized root output through the shared helper.

- `tests/unit/services/test_generate_response.py`
  - Add tests that streaming direct delivery records root output when
    `response_sent=True`.
  - Add a negative delivery test that root output is not recorded when final
    delivery fails and downstream sender must send the response.

- `telegram_bot/bot.py`
  - Ensure the SDK-agent/DraftStreamer path records sanitized root output when
    it finalizes a response without `send_html_messages`.
  - Avoid broad refactors in this large file.

- `tests/unit/test_bot_scores.py` or `tests/unit/test_bot_handlers.py`
  - Add a focused test only if `bot.py` changes need a direct regression guard.

### Do Not Modify In Phase 1

- `Makefile` target `e2e-test-traces-core`; it still includes voice scenario
  `8.1` and belongs to Phase 2 after `#1486`.
- `scripts/validate_traces.py`; score enforcement for `validate-traces-fast`
  is not part of Phase 1.
- Docker, Compose, k8s, or deployment files.

## Reserved Files

For the implementation worker:

- `scripts/e2e/langfuse_trace_validator.py`
- `tests/unit/e2e/test_langfuse_trace_validator.py`
- `telegram_bot/services/telegram_formatting.py`
- `tests/unit/test_telegram_formatting.py`
- `telegram_bot/services/generate_response.py`
- `tests/unit/services/test_generate_response.py`
- `telegram_bot/bot.py`
- `tests/unit/test_bot_scores.py`
- `tests/unit/test_bot_handlers.py`

The worker should touch `telegram_bot/bot.py`, `tests/unit/test_bot_scores.py`,
or `tests/unit/test_bot_handlers.py` only if the root output gap is confirmed in
the SDK-agent/DraftStreamer path. Otherwise leave them unchanged.

## Task 0: Launch Swarm Implementation Worker

**Files:**
- Create: `.codex/prompts/worker-1485-langfuse-trace-contract.md`
- Create: implementation worktree outside the main checkout
- Modify: `.signals/active-workers.jsonl`

- [ ] **Step 1: Confirm clean orchestration state**

Run:

```bash
git status --short
scripts/registry_state.py --registry .signals/active-workers.jsonl || true
tmux list-windows | rg 'W-' || true
```

Expected: no uncommitted product-code changes in the main checkout; any active
worker windows are understood before launching a new worker.

- [ ] **Step 2: Capture and validate orchestrator pane**

Run:

```bash
ORCH_PANE=$(tmux display-message -p '#{pane_id}')
tmux display-message -p -t "$ORCH_PANE" '#{pane_id} #{pane_dead}'
```

Expected: output contains the same pane id and `0` for `pane_dead`.

- [ ] **Step 3: Create worker worktree**

Run:

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
WT_PATH="${PROJECT_ROOT}-wt-1485-langfuse-trace"
git worktree add "$WT_PATH" -b fix/1485-langfuse-trace-contract dev
mkdir -p "$WT_PATH/logs" "$WT_PATH/.signals" "$PROJECT_ROOT/.codex/prompts" "$PROJECT_ROOT/.signals"
touch "$PROJECT_ROOT/.signals/active-workers.jsonl"
```

Expected: worktree exists at `$WT_PATH` on branch
`fix/1485-langfuse-trace-contract`.

- [ ] **Step 4: Write worker prompt**

Set the signal path and create
`.codex/prompts/worker-1485-langfuse-trace-contract.md` with a shell heredoc so
`$WT_PATH` and `$SIGNAL_FILE` expand to absolute paths:

```bash
SIGNAL_FILE="$WT_PATH/.signals/worker-1485-langfuse-trace-contract.json"
cat > "$PROJECT_ROOT/.codex/prompts/worker-1485-langfuse-trace-contract.md" <<EOF
```

Prompt body:

```markdown
# Worker: #1485 Langfuse Trace Contract

WORKER MODEL: opencode-go/kimi-k2.6
Required OpenCode skills: swarm-pr-finish
Branch/base: fix/1485-langfuse-trace-contract based on dev
Worktree: $WT_PATH
Signal file: $SIGNAL_FILE
Docs lookup policy: forbidden. Do not use web search, web fetch, Context7, Exa,
or external docs. Use only local repo files and the spec/plan listed below.

You are not alone in the codebase. Do not revert edits made by others. Stay
within reserved files unless you find a true blocker and explain it in the
signal artifact before expanding scope.

Goal: implement Phase 1 from
docs/superpowers/plans/2026-05-12-langfuse-trace-coverage-phase1-plan.md.

Read first:
- docs/superpowers/specs/2026-05-12-langfuse-trace-coverage-design.md
- docs/superpowers/plans/2026-05-12-langfuse-trace-coverage-phase1-plan.md
- docs/engineering/sdk-registry.md section for langfuse

Reserved files:
- scripts/e2e/langfuse_trace_validator.py
- tests/unit/e2e/test_langfuse_trace_validator.py
- telegram_bot/services/telegram_formatting.py
- tests/unit/test_telegram_formatting.py
- telegram_bot/services/generate_response.py
- tests/unit/services/test_generate_response.py
- telegram_bot/bot.py
- tests/unit/test_bot_scores.py
- tests/unit/test_bot_handlers.py

Implementation requirements:
- Keep Langfuse SDK-first. Use existing SDK helpers and existing scoring helper.
- Do not add a custom observability transport.
- Do not modify Makefile, scripts/validate_traces.py, Docker, Compose, k8s, or
  deployment files.
- Do not read or print .env, secrets, Telegram session strings, chat IDs, CRM
  identifiers, SSH, cloud credentials, or production data.
- If PR #1491 is not present in this branch, implement equivalent alias support
  for cache-check/node-cache-check.
- If PR #1491 behavior is already present, do not duplicate it. Keep the alias
  tests and move directly to invalid `query_type`, root output, and streaming
  delivery work.
- Add tests before implementation where feasible.
- Commit changes with focused commit messages.
- Open or update a PR against dev.

Required checks:
- uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
- uv run pytest tests/unit/test_telegram_formatting.py -q
- uv run pytest tests/unit/services/test_generate_response.py -q
- Run narrower bot handler/score tests only if you touch telegram_bot/bot.py.

Optional runtime gate if local services and Telegram credentials are already
available:
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1

Completion:
- Write DONE/FAILED/BLOCKED JSON to $SIGNAL_FILE with summary, changed files,
  commits, PR URL/number if opened, commands run, skipped checks and reasons.
- Wake the orchestrator pane using the swarm-pr-finish contract.
```

Close the heredoc:

```bash
EOF
```

Expected: prompt contains absolute worktree and signal paths.

- [ ] **Step 5: Launch worker through tmux-swarm**

Run:

```bash
PROMPT_FILE="$PROJECT_ROOT/.codex/prompts/worker-1485-langfuse-trace-contract.md"
SIGNAL_FILE="$WT_PATH/.signals/worker-1485-langfuse-trace-contract.json"
ORCH_PANE="$ORCH_PANE" \
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
OPENCODE_VARIANT= \
OPENCODE_REQUIRED_SKILLS=swarm-pr-finish \
SWARM_LOCAL_ONLY=1 \
/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  "W-1485-langfuse-trace" "$WT_PATH" "$PROMPT_FILE"
```

Expected: launcher creates a visible tmux worker window and launch metadata
under `.signals/`.

- [ ] **Step 6: Return control without polling**

Expected: after launch metadata is valid, wait for worker wake-up events rather
than polling transcripts.

## Task 1: Validator Alias And Deterministic Branch Rules

**Files:**
- Modify: `scripts/e2e/langfuse_trace_validator.py:23-34`
- Modify: `scripts/e2e/langfuse_trace_validator.py:147-173`
- Modify: `scripts/e2e/langfuse_trace_validator.py:277-321`
- Test: `tests/unit/e2e/test_langfuse_trace_validator.py`

- [ ] **Step 1: Add failing alias test if missing**

Add a helper in `tests/unit/e2e/test_langfuse_trace_validator.py`:

```python
def _score(name: str, value: object):
    return type("Score", (), {"name": name, "value": value})


def _obs(name: str):
    return type("Obs", (), {"name": name})


def _required_scores(**overrides: object) -> list[type]:
    values: dict[str, object] = {
        "query_type": 1.0,
        "latency_total_ms": 1500.0,
        "semantic_cache_hit": True,
        "embeddings_cache_hit": False,
        "search_cache_hit": False,
        "rerank_applied": False,
        "rerank_cache_hit": False,
        "results_count": 0.0,
        "no_results": True,
        "llm_used": False,
    }
    values.update(overrides)
    return [_score(name, value) for name, value in values.items()]
```

Then add:

```python
def test_validator_accepts_cache_check_alias_for_node_cache_check(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = _required_scores(semantic_cache_hit=True)

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert result.ok, (
        f"Validation failed: missing_spans={result.missing_spans}, "
        f"missing_scores={result.missing_scores}"
    )
    assert "node-cache-check" not in result.missing_spans
```

- [ ] **Step 2: Run alias test and confirm failure**

Run:

```bash
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py::test_validator_accepts_cache_check_alias_for_node_cache_check -q
```

Expected before implementation: FAIL with `node-cache-check` in
`missing_spans`, unless PR `#1491` is already in the branch.

- [ ] **Step 3: Implement alias resolution**

In `scripts/e2e/langfuse_trace_validator.py`, add near `SCORE_NAMES`:

```python
OBSERVATION_ALIAS_GROUPS = {
    "node-cache-check": {"node-cache-check", "cache-check"},
}
```

Add helper after `_as_float`:

```python
def _resolve_missing_observations(
    required_observations: set[str], span_names: set[str]
) -> set[str]:
    missing: set[str] = set()
    for required in required_observations:
        aliases = OBSERVATION_ALIAS_GROUPS.get(required, {required})
        if not (aliases & span_names):
            missing.add(required)
    return missing
```

Replace both direct set subtractions:

```python
missing_spans = _resolve_missing_observations(required_observations, span_names)
```

and:

```python
missing_spans |= _resolve_missing_observations(required_observations, span_names)
```

- [ ] **Step 4: Run alias test and full validator unit file**

Run:

```bash
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py::test_validator_accepts_cache_check_alias_for_node_cache_check -q
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
```

Expected: PASS.

- [ ] **Step 5: Add invalid query_type tests**

Add tests:

```python
def test_validator_fails_when_query_type_score_is_non_numeric(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = _required_scores(query_type="GENERAL")

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok
    assert "query_type" in result.missing_scores


def test_validator_fails_when_query_type_score_is_missing(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = [
        score for score in _required_scores() if score.name != "query_type"
    ]

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=True,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok
    assert "query_type" in result.missing_scores
```

- [ ] **Step 6: Run invalid query_type tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py::test_validator_fails_when_query_type_score_is_non_numeric tests/unit/e2e/test_langfuse_trace_validator.py::test_validator_fails_when_query_type_score_is_missing -q
```

Expected before implementation: at least the non-numeric case FAILS because
`query_type` name exists and is not currently treated as invalid.

- [ ] **Step 7: Implement invalid score handling**

In `validate_latest_trace`, compute `missing_scores` before branch-specific
pass/fail return:

```python
missing_scores = set(required_scores - score_names)
query_type_raw = scores.get("query_type")
query_type = _as_float(query_type_raw)
if "query_type" in score_names and query_type is None:
    missing_scores.add("query_type")
```

Keep branch behavior deterministic:

```python
is_chitchat = (query_type == 0.0) if query_type is not None else bool(should_skip_rag)
```

Do not allow this fallback to make the scenario pass when `query_type` is
missing or invalid; `missing_scores` must remain non-empty.

- [ ] **Step 8: Run validator tests**

Run:

```bash
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit validator changes**

Run:

```bash
git add scripts/e2e/langfuse_trace_validator.py tests/unit/e2e/test_langfuse_trace_validator.py
git commit -m "fix(e2e): harden Langfuse trace validator contract"
```

Expected: commit created.

## Task 2: Root Output Recording For Direct Streaming Delivery

**Files:**
- Modify: `telegram_bot/services/telegram_formatting.py:148-221`
- Modify: `tests/unit/test_telegram_formatting.py:1-150`
- Modify: `telegram_bot/services/generate_response.py:326-460`
- Test: `tests/unit/services/test_generate_response.py`

- [ ] **Step 1: Make the root output helper public**

In `telegram_bot/services/telegram_formatting.py`, rename the implementation
helper to `record_langfuse_response_output` and keep a compatibility alias:

```python
def record_langfuse_response_output(answer_text: str | None, chunks_count: int) -> None:
    """Best-effort update of the current Langfuse trace/span output after a send."""
    lf = get_client()
    if lf is None:
        return

    output = build_safe_output_payload(answer_text, chunks_count)
    set_trace_io = getattr(lf, "set_current_trace_io", None)
    if callable(set_trace_io):
        try:
            set_trace_io(output=output)
            return
        except Exception:
            logger.debug(
                "set_current_trace_io failed, falling back to update_current_span",
                exc_info=True,
            )

    update_span = getattr(lf, "update_current_span", None)
    if callable(update_span):
        try:
            update_span(output=output)
        except Exception:
            logger.debug("update_current_span failed", exc_info=True)


_record_langfuse_response_output = record_langfuse_response_output
```

Update `send_html_messages` to call the public name:

```python
record_langfuse_response_output(answer_text, len(html_messages))
```

- [ ] **Step 2: Update formatting tests for public helper**

In `tests/unit/test_telegram_formatting.py`, import both names if needed and
add:

```python
def test_private_output_helper_alias_points_to_public_helper():
    from telegram_bot.services import telegram_formatting

    assert (
        telegram_formatting._record_langfuse_response_output
        is telegram_formatting.record_langfuse_response_output
    )
```

Update patches in send tests from:

```python
"telegram_bot.services.telegram_formatting._record_langfuse_response_output"
```

to:

```python
"telegram_bot.services.telegram_formatting.record_langfuse_response_output"
```

- [ ] **Step 3: Run formatting tests**

Run:

```bash
uv run pytest tests/unit/test_telegram_formatting.py -q
```

Expected: PASS.

- [ ] **Step 4: Add failing generate_response streaming output test**

In `tests/unit/services/test_generate_response.py`, update
`test_generate_response_streaming_sets_response_sent_and_message_ref`:

```python
with patch(
    "telegram_bot.services.generate_response.record_langfuse_response_output"
) as mock_record_output:
    result = await generate_response(
        query="Стриминг?",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Стриминг?"}],
    )

mock_record_output.assert_called_once_with("Часть 1 Часть 2", 1)
```

Add a negative test near `test_streaming_answer_failure_degrades_gracefully`:

```python
async def test_generate_response_streaming_does_not_record_output_when_delivery_fails() -> None:
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Ответ без доставки")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    message = AsyncMock()
    message.chat = MagicMock(id=999)
    message.bot = bot
    message.answer = AsyncMock(side_effect=RuntimeError("telegram send failed"))

    with patch(
        "telegram_bot.services.generate_response.record_langfuse_response_output"
    ) as mock_record_output:
        result = await generate_response(
            query="Тест ошибки доставки",
            documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
            config=config,
            lf_client=lf,
            message=message,
            raw_messages=[{"role": "user", "content": "Тест ошибки доставки"}],
        )

    assert result["response_sent"] is False
    mock_record_output.assert_not_called()
```

- [ ] **Step 5: Run generate_response tests and confirm failure**

Run:

```bash
uv run pytest tests/unit/services/test_generate_response.py::test_generate_response_streaming_sets_response_sent_and_message_ref tests/unit/services/test_generate_response.py::test_generate_response_streaming_does_not_record_output_when_delivery_fails -q
```

Expected before implementation: first test FAILS because the new helper is not
called or not imported in `generate_response.py`.

- [ ] **Step 6: Record output after successful streaming final send**

In `telegram_bot/services/generate_response.py`, import the helper:

```python
from telegram_bot.services.telegram_formatting import (
    build_reply_parameters,
    format_answer_html,
    record_langfuse_response_output,
)
```

If imports are currently separate, follow the local import style and avoid
duplicates.

In `_generate_streaming`, after a successful final `message.answer`, record
output only when `sent_msg is not None`:

```python
if sent_msg is not None:
    record_langfuse_response_output(final_text, 1)
```

Also record output in the partial delivery path only when `sent_msg is not
None`, before raising `StreamingPartialDeliveryError`:

```python
if sent_msg is not None:
    record_langfuse_response_output(final_text, 1)
raise StreamingPartialDeliveryError(sent_msg, final_text) from None
```

Do not record output when Telegram final delivery fails and `response_sent`
will be `False`; downstream sender owns the final root output in that case.

- [ ] **Step 7: Run generate_response tests**

Run:

```bash
uv run pytest tests/unit/services/test_generate_response.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit root-output changes**

Run:

```bash
git add telegram_bot/services/telegram_formatting.py tests/unit/test_telegram_formatting.py telegram_bot/services/generate_response.py tests/unit/services/test_generate_response.py
git commit -m "fix(observability): record root output for streaming responses"
```

Expected: commit created.

## Task 3: SDK-Agent DraftStreamer Output Gap

**Files:**
- Modify only if needed: `telegram_bot/bot.py:3300-3391`
- Test only if needed: `tests/unit/test_bot_handlers.py`

- [ ] **Step 1: Check whether DraftStreamer bypasses output recording**

Inspect `telegram_bot/bot.py:3336-3367`. If `DraftStreamer.finalize(...)`
sends the final user-visible response without calling `send_html_messages`,
then it bypasses `record_langfuse_response_output`.

Expected: if it bypasses the shared sender, continue this task. If not, record
the finding in the worker signal and skip the remaining task steps.

- [ ] **Step 2: Add failing bot handler test only if the gap exists**

Find the existing response-sent tests around
`tests/unit/test_bot_handlers.py::TestResponseSentFlag` and add a focused test:

```python
async def test_sdk_agent_draftstreamer_records_langfuse_root_output(self, mock_config):
    # Follow the existing test setup in TestResponseSentFlag.
    # Patch DraftStreamer.finalize to succeed.
    # Patch telegram_bot.bot.record_langfuse_response_output.
    # Exercise _handle_query_supervisor with response_text and private chat.
    # Assert record_langfuse_response_output called with response_text and chunk count.
```

Use existing fixtures and helpers in the file; do not build a new bot harness
from scratch.

- [ ] **Step 3: Run the new bot handler test and confirm failure**

Run the exact test node added in Step 2:

```bash
uv run pytest tests/unit/test_bot_handlers.py::test_sdk_agent_draftstreamer_records_langfuse_root_output -q
```

Expected before implementation: FAIL because output recording is not called.

- [ ] **Step 4: Implement minimal DraftStreamer recording**

In `telegram_bot/bot.py`, import the helper next to local formatting imports:

```python
from telegram_bot.services.telegram_formatting import (
    build_html_messages,
    record_langfuse_response_output,
    send_html_messages,
)
```

After successful `draft_streamer.finalize(...)`, call:

```python
record_langfuse_response_output(response_text, len(html_messages))
```

If the code falls back to `send_html_messages`, do not duplicate output
recording; `send_html_messages` already owns it.

- [ ] **Step 5: Run bot handler test**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::test_sdk_agent_draftstreamer_records_langfuse_root_output -q
```

Expected: PASS.

- [ ] **Step 6: Commit if files changed**

Run:

```bash
git add telegram_bot/bot.py tests/unit/test_bot_handlers.py
git commit -m "fix(observability): record root output for draft-streamed replies"
```

Expected: commit created if this task changed files. If no gap was found, do
not create an empty commit.

## Task 4: Focused Verification

**Files:**
- No source edits unless a verification failure reveals a scoped bug.

- [ ] **Step 1: Run focused validator tests**

Run:

```bash
uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
```

Expected: PASS.

- [ ] **Step 2: Run formatting tests**

Run:

```bash
uv run pytest tests/unit/test_telegram_formatting.py -q
```

Expected: PASS.

- [ ] **Step 3: Run generate_response tests**

Run:

```bash
uv run pytest tests/unit/services/test_generate_response.py -q
```

Expected: PASS.

- [ ] **Step 4: Run bot-specific tests only if bot.py changed**

Run:

```bash
uv run pytest tests/unit/test_bot_handlers.py::test_sdk_agent_draftstreamer_records_langfuse_root_output -q
```

Expected: PASS.

- [ ] **Step 5: Run combined focused suite**

Run:

```bash
uv run pytest \
  tests/unit/e2e/test_langfuse_trace_validator.py \
  tests/unit/test_telegram_formatting.py \
  tests/unit/services/test_generate_response.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Optional text-only runtime gate**

Run only if local Langfuse stack, bot, and Telegram credentials/session are
already available:

```bash
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1
```

Expected: PASS for text scenarios. If skipped, document the exact blocker in
the worker signal and PR body. Do not run full `make e2e-test-traces-core` as a
Phase 1 pass/fail gate while `#1486` is open.

## Task 5: Worker PR And Signal

**Files:**
- Modify: PR body only
- Create: worker signal JSON

- [ ] **Step 1: Inspect final diff**

Run:

```bash
git status --short
git diff --stat dev...HEAD
git diff --check
```

Expected: no unstaged changes unless intentionally left for commit; `git diff
--check` passes.

- [ ] **Step 2: Open or update PR**

Run:

```bash
gh pr create \
  --base dev \
  --head fix/1485-langfuse-trace-contract \
  --title "fix(observability): harden #1307 text trace contract" \
  --body "$(cat <<'EOF'
## Summary
- harden Telethon Langfuse validator for cache-check aliases and invalid query_type scores
- ensure directly delivered streaming responses write sanitized root output
- keep Phase 1 score enforcement in the E2E trace validator

## Scope
Phase 1 for #1485 only. Does not close #1307 because #1486/#1487/#1488/#1489/#1490 remain separate follow-ups.

## Validation
- [ ] uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q
- [ ] uv run pytest tests/unit/test_telegram_formatting.py -q
- [ ] uv run pytest tests/unit/services/test_generate_response.py -q
- [ ] text-only E2E trace gate, if local credentials/services available

Fixes #1485
Refs #1307
EOF
)"
```

If a PR already exists for the branch, use `gh pr edit` to update the body
instead.

- [ ] **Step 3: Write DONE signal**

Write JSON to the assigned signal file:

```json
{
  "status": "done",
  "worker": "W-1485-langfuse-trace",
  "runner": "opencode",
  "summary": "Implemented Phase 1 Langfuse text trace contract fixes.",
  "changed_files": [
    "scripts/e2e/langfuse_trace_validator.py",
    "tests/unit/e2e/test_langfuse_trace_validator.py",
    "telegram_bot/services/telegram_formatting.py",
    "tests/unit/test_telegram_formatting.py",
    "telegram_bot/services/generate_response.py",
    "tests/unit/services/test_generate_response.py"
  ],
  "commands": [
    "uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q",
    "uv run pytest tests/unit/test_telegram_formatting.py -q",
    "uv run pytest tests/unit/services/test_generate_response.py -q"
  ],
  "skipped_checks": [],
  "pr": "replace with actual PR URL, or use null if blocked before PR creation",
  "ts": "replace with current UTC ISO-8601 timestamp"
}
```

Expected: signal validates and worker wakes the orchestrator.

## Task 6: Orchestrator Review And Dedicated PR Review Worker

**Files:**
- No direct source edits unless a tiny cleanup is required after review.

- [ ] **Step 1: Validate worker artifacts**

Run:

```bash
scripts/validate_worker_signal.py --signal "$SIGNAL_FILE" --registry .signals/active-workers.jsonl --worker W-1485-langfuse-trace || true
PR_NUMBER=1234  # replace with the actual PR number before running
gh pr view "$PR_NUMBER" --json headRefOid,headRefName,baseRefName,files,statusCheckRollup,url
```

Expected: signal and PR metadata match the worker branch, reserved files, and
claimed checks.

- [ ] **Step 2: Inspect bounded diff personally**

Run:

```bash
gh pr diff "$PR_NUMBER" -- scripts/e2e/langfuse_trace_validator.py tests/unit/e2e/test_langfuse_trace_validator.py telegram_bot/services/telegram_formatting.py tests/unit/test_telegram_formatting.py telegram_bot/services/generate_response.py tests/unit/services/test_generate_response.py
```

Expected: diff matches this plan; no unrelated refactors or secret/raw payload
logging.

- [ ] **Step 3: Run focused checks locally if worker evidence is incomplete**

Run missing commands from Task 4 in the orchestrator checkout or a clean review
worktree.

Expected: PASS or documented blocker.

- [ ] **Step 4: Launch read-only PR review worker**

Use `$tmux-swarm-orchestration` to launch a separate worker:

```bash
OPENCODE_AGENT=pr-review
OPENCODE_MODEL=opencode-go/deepseek-v4-pro
OPENCODE_REQUIRED_SKILLS=gh-pr-review,swarm-pr-finish
```

Reserved files: none. The worker is read-only.

Prompt requirements:

- review PR `$PR_NUMBER` at current head SHA;
- verify SDK-first Langfuse usage;
- verify no raw Telegram payloads/secrets are traced;
- verify Phase 1 scope only;
- verify tests and runtime gate evidence;
- report blockers separately from advisory improvements.

Expected: PR review worker returns DONE JSON with `Approved` or concrete
blockers.

- [ ] **Step 5: Handle review outcome**

If review finds blockers, launch a separate `pr-review-fix` worker on the same
PR branch with only named blocker files reserved. After fixes, launch a fresh
read-only review worker for the new head SHA.

If review approves, proceed to merge/readiness decision according to repo
policy.

## Final Acceptance Criteria

Phase 1 is complete when:

- PR `#1491` behavior is present either by merge or equivalent implementation;
- missing root output fails validator tests;
- missing required scores fail validator tests;
- invalid/non-numeric `query_type` fails validator tests;
- `cache-check` satisfies `node-cache-check`;
- streaming direct delivery records sanitized root output;
- focused unit tests pass;
- text-only runtime gate is run or skipped with a precise local blocker;
- a dedicated read-only PR review worker has approved the current head SHA or
  all review blockers have been fixed and re-reviewed.

## Phase 1 Runtime Gate

Use this command only when local services and Telegram credentials are ready:

```bash
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1
```

Do not use full `make e2e-test-traces-core` as the Phase 1 pass/fail command
because it includes voice scenario `8.1`, which belongs to `#1486`.
