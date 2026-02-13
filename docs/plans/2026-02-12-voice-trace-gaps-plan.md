# Voice Trace Gaps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 Langfuse tracing gaps in voice pipeline (#158): metadata parity, payload bloat, test coverage.

**Architecture:** Minimal changes in 3 files — `bot.py` (extract shared metadata helper), `transcribe.py` (curated span pattern), `test_bot_scores.py` (voice score test). Follows existing patterns from heavy nodes.

**Tech Stack:** Langfuse Python SDK v3 (`@observe`, `get_client().update_current_span()`, `score_current_trace`)

**References:**
- Issue: #158
- Langfuse SDK v3 docs: `capture_input=False` disables auto-capture, `update_current_span(input=..., output=...)` for curated metadata
- Existing pattern: `retrieve_node` (`telegram_bot/graph/nodes/retrieve.py:22,59-68`)
- Observability rules: `.claude/rules/observability.md` — forbidden keys, curated span table

---

### Task 1: Extract shared trace metadata helper in `bot.py`

**Files:**
- Modify: `telegram_bot/bot.py:457-477` (handle_query metadata), `telegram_bot/bot.py:560-573` (handle_voice metadata)

**Step 1: Write the failing test**

Добавить тест в `tests/unit/test_bot_scores.py` что `handle_voice` и `handle_query` вызывают `update_current_trace` с одинаковым набором metadata ключей.

```python
# tests/unit/test_bot_scores.py — добавить в конец файла

class TestVoiceTraceMetadata:
    """Test that handle_voice writes same metadata keys as handle_query."""

    async def _run_handle_voice(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_voice with mocked graph and Langfuse client."""
        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf_client),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            message = _make_voice_message()
            await bot.handle_voice(message)

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_voice_trace_metadata_has_same_keys_as_text(self, mock_config):
        """handle_voice metadata should contain all keys from handle_query."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        voice_result = {
            **FULL_PIPELINE_RESULT,
            "stt_text": "тест запрос",
            "stt_duration_ms": 250.0,
            "voice_duration_s": 5.0,
            "input_type": "voice",
        }
        await self._run_handle_voice(mock_config, voice_result, mock_lf)

        call_kwargs = mock_lf.update_current_trace.call_args.kwargs
        metadata = call_kwargs["metadata"]

        # All keys from handle_query must be present
        expected_keys = {
            "query_type", "cache_hit", "search_results_count",
            "rerank_applied", "llm_provider_model", "llm_ttft_ms",
            "response_style", "response_difficulty",
            "response_style_reasoning", "response_policy_mode",
            "answer_words", "answer_to_question_ratio",
            # Voice-specific
            "input_type", "stt_duration_ms",
        }
        assert expected_keys.issubset(set(metadata.keys()))
```

Также добавить хелпер `_make_voice_message`:

```python
def _make_voice_message(user_id=123456789, chat_id=987654321):
    """Create mock Telegram voice message."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.bot = MagicMock()
    message.bot.send_chat_action = AsyncMock()
    message.bot.get_file = AsyncMock()
    message.bot.download_file = AsyncMock()
    message.voice = MagicMock()
    message.voice.file_id = "file123"
    message.voice.duration = 5
    file_mock = MagicMock()
    file_mock.file_path = "voice/file.ogg"
    message.bot.get_file.return_value = file_mock
    return message
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_bot_scores.py::TestVoiceTraceMetadata::test_voice_trace_metadata_has_same_keys_as_text -v
```

Expected: FAIL — metadata не содержит `search_results_count`, `rerank_applied` и другие ключи.

**Step 3: Extract `_build_trace_metadata` helper and use in both handlers**

В `telegram_bot/bot.py` добавить helper function перед `handle_query`:

```python
def _build_trace_metadata(result: dict) -> dict[str, Any]:
    """Build shared metadata dict for Langfuse trace (text + voice handlers)."""
    return {
        "input_type": result.get("input_type", "text"),
        "query_type": result.get("query_type", ""),
        "cache_hit": result.get("cache_hit", False),
        "search_results_count": result.get("search_results_count", 0),
        "rerank_applied": result.get("rerank_applied", False),
        "llm_provider_model": result.get("llm_provider_model", ""),
        "llm_ttft_ms": result.get("llm_ttft_ms", 0.0),
        # Response length control (#129)
        "response_style": result.get("response_style"),
        "response_difficulty": result.get("response_difficulty"),
        "response_style_reasoning": result.get("response_style_reasoning"),
        "response_policy_mode": result.get("response_policy_mode"),
        "answer_words": result.get("answer_words"),
        "answer_to_question_ratio": result.get("answer_to_question_ratio"),
        # Voice transcription (#151)
        "stt_duration_ms": result.get("stt_duration_ms"),
    }
```

Обновить `handle_query` (line ~459):

```python
lf.update_current_trace(
    input={"query": message.text},
    output={"response": result.get("response", "")},
    metadata=_build_trace_metadata(result),
)
```

Обновить `handle_voice` (line ~561):

```python
lf.update_current_trace(
    input={
        "voice_duration_s": voice.duration,
        "stt_text": result.get("stt_text", ""),
    },
    output={"response": result.get("response", "")},
    metadata=_build_trace_metadata(result),
)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_bot_scores.py::TestVoiceTraceMetadata -v
```

Expected: PASS

**Step 5: Run full score tests to catch regressions**

```bash
uv run pytest tests/unit/test_bot_scores.py -v
```

Expected: All tests PASS (existing tests unchanged, `update_current_trace` metadata layout changed but tests mock it).

**Step 6: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "fix(observability): unify trace metadata between handle_query and handle_voice #158"
```

---

### Task 2: Add curated span to transcribe node (payload bloat fix)

**Files:**
- Modify: `telegram_bot/graph/nodes/transcribe.py:40` (@observe decorator + curated span)
- Modify: `tests/unit/graph/test_transcribe_node.py` (verify curated span)

**Step 1: Write the failing test**

```python
# tests/unit/graph/test_transcribe_node.py — добавить тест

@pytest.mark.asyncio
async def test_transcribe_writes_curated_span(self):
    """transcribe_node writes curated Langfuse span input/output."""
    mock_llm = AsyncMock()
    mock_llm.audio.transcriptions.create.return_value = MagicMock(text="Привет мир")

    from telegram_bot.graph.nodes.transcribe import make_transcribe_node

    node = make_transcribe_node(
        llm=mock_llm, voice_language="ru", stt_model="whisper",
        show_transcription=False,
    )
    state = _make_voice_state()

    with patch("telegram_bot.graph.nodes.transcribe.get_client") as mock_gc:
        mock_lf = MagicMock()
        mock_gc.return_value = mock_lf
        result = await node(state)

    # Verify curated span was written
    assert mock_lf.update_current_span.call_count == 2  # input + output

    input_call = mock_lf.update_current_span.call_args_list[0]
    input_data = input_call.kwargs["input"]
    assert "voice_language" in input_data
    assert "stt_model" in input_data
    assert "audio_size_bytes" in input_data
    # voice_audio bytes must NOT be in span
    assert "voice_audio" not in str(input_data)

    output_call = mock_lf.update_current_span.call_args_list[1]
    output_data = output_call.kwargs["output"]
    assert "stt_duration_ms" in output_data
    assert "text_length" in output_data
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/graph/test_transcribe_node.py::TestTranscribeNode::test_transcribe_writes_curated_span -v
```

Expected: FAIL — `get_client` not imported/called, `update_current_span` never called.

**Step 3: Implement curated span in transcribe_node**

Modify `telegram_bot/graph/nodes/transcribe.py`:

```python
# Line 16: add get_client to import
from telegram_bot.observability import get_client, observe

# Line 40: add capture_input=False, capture_output=False
@observe(name="transcribe", capture_input=False, capture_output=False)
async def transcribe_node(state: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()

    voice_audio = state["voice_audio"]
    if voice_audio is None:
        raise ValueError("voice_audio is None — transcribe_node requires audio data")

    # Curated span input (no raw bytes!)
    lf = get_client()
    lf.update_current_span(
        input={
            "audio_size_bytes": len(voice_audio),
            "voice_language": voice_language,
            "stt_model": stt_model,
            "voice_duration_s": state.get("voice_duration_s"),
        }
    )

    buf = io.BytesIO(voice_audio)
    buf.name = "voice.ogg"

    transcript = await llm.audio.transcriptions.create(
        model=stt_model,
        file=buf,
        language=voice_language,
    )

    text = transcript.text.strip()
    stt_duration_ms = (time.perf_counter() - start) * 1000

    if not text:
        raise ValueError("Empty transcription from Whisper API")

    logger.info(
        "Voice transcribed: %.0f ms, %d chars, lang=%s",
        stt_duration_ms,
        len(text),
        voice_language,
    )

    # Curated span output
    lf.update_current_span(
        output={
            "stt_duration_ms": round(stt_duration_ms, 1),
            "text_length": len(text),
            "text_preview": text[:120],
        }
    )

    # Send transcription preview (optional)
    if show_transcription and message is not None:
        try:
            await message.answer(
                f"\U0001f3a4 <i>{html.escape(text)}</i>",
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Failed to send transcription preview", exc_info=True)

    return {
        "stt_text": text,
        "stt_duration_ms": stt_duration_ms,
        "query": text,
        "messages": [{"role": "user", "content": text}],
        "voice_audio": None,
    }
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/graph/test_transcribe_node.py -v
```

Expected: All 8 tests PASS (7 existing + 1 new).

**Step 5: Commit**

```bash
git add telegram_bot/graph/nodes/transcribe.py tests/unit/graph/test_transcribe_node.py
git commit -m "fix(observability): curated span in transcribe_node — prevent payload bloat #158"
```

---

### Task 3: Add voice-specific scores test

**Files:**
- Modify: `tests/unit/test_bot_scores.py` (add voice scores test)

**Step 1: Write the test**

```python
# tests/unit/test_bot_scores.py — добавить в class TestScoreWriting

VOICE_PIPELINE_RESULT = {
    **FULL_PIPELINE_RESULT,
    "stt_text": "тест голосовой запрос",
    "stt_duration_ms": 250.0,
    "voice_duration_s": 5.0,
    "input_type": "voice",
}


class TestVoiceScores:
    """Test voice-specific Langfuse scores (#158)."""

    @pytest.mark.asyncio
    async def test_voice_scores_written(self, mock_config):
        """Voice result should emit stt_duration_ms and voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=VOICE_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        score_calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in score_calls}

        # Voice-specific scores must be present
        assert "stt_duration_ms" in score_map
        assert score_map["stt_duration_ms"]["value"] == 250.0

        assert "voice_duration_s" in score_map
        assert score_map["voice_duration_s"]["value"] == 5.0

        assert "input_type" in score_map
        assert score_map["input_type"]["value"] == "voice"
        assert score_map["input_type"]["data_type"] == "CATEGORICAL"

    @pytest.mark.asyncio
    async def test_text_scores_omit_voice_metrics(self, mock_config):
        """Text result should NOT emit stt_duration_ms or voice_duration_s scores."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        bot = _create_bot(mock_config)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=FULL_PIPELINE_RESULT)

        with (
            patch("telegram_bot.bot.build_graph", return_value=mock_graph),
            patch("telegram_bot.bot.get_client", return_value=mock_lf),
            patch("telegram_bot.bot.propagate_attributes") as mock_prop,
            patch("telegram_bot.bot.ChatActionSender") as mock_cas,
        ):
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock()
            mock_cm.__aexit__ = AsyncMock()
            mock_cas.typing.return_value = mock_cm
            mock_prop.return_value.__enter__ = MagicMock()
            mock_prop.return_value.__exit__ = MagicMock()

            await bot.handle_query(_make_message())

        score_names = [c.kwargs["name"] for c in mock_lf.score_current_trace.call_args_list]

        # input_type always written (as "text")
        assert "input_type" in score_names
        # Voice-only scores NOT written for text input
        assert "stt_duration_ms" not in score_names
        assert "voice_duration_s" not in score_names
```

**Step 2: Run tests**

```bash
uv run pytest tests/unit/test_bot_scores.py::TestVoiceScores -v
```

Expected: PASS (scores already written correctly, test confirms it).

**Step 3: Commit**

```bash
git add tests/unit/test_bot_scores.py
git commit -m "test(observability): add voice-specific score tests #158"
```

---

### Task 4: Update observability docs (curated span table)

**Files:**
- Modify: `.claude/rules/observability.md` (add transcribe to curated span table)

**Step 1: Add transcribe_node to the curated span table**

В секции "Payload Bloat Prevention (#143)" добавить строку:

```markdown
| transcribe_node | audio_size_bytes, voice_language, stt_model, voice_duration_s | stt_duration_ms, text_length, text_preview |
```

Обновить число: "5 heavy nodes" → "6 heavy nodes".

**Step 2: Commit**

```bash
git add .claude/rules/observability.md
git commit -m "docs(observability): add transcribe to curated span table #158"
```

---

### Task 5: Lint + full test suite

**Step 1: Run lint**

```bash
uv run ruff check telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py --fix
uv run ruff format telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py
```

**Step 2: Run types**

```bash
uv run mypy telegram_bot/bot.py telegram_bot/graph/nodes/transcribe.py
```

**Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ -x -v --timeout=30
```

Expected: All tests PASS.

**Step 4: Run graph path integration test**

```bash
uv run pytest tests/integration/test_graph_paths.py -v
```

Expected: All 7 tests PASS (including `test_path_voice_transcribe_full_rag`).
