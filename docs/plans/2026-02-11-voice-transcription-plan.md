# Voice Message Transcription — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add voice message support to the Telegram RAG bot via OpenAI Whisper API through LiteLLM proxy.

**Architecture:** New `transcribe_node` (10th LangGraph node) receives voice audio bytes, calls Whisper API via the existing `AsyncOpenAI` client (LiteLLM proxy), returns transcribed text that feeds into the existing classify → ... pipeline. Conditional START edge routes voice messages through transcribe, text messages skip it.

**Tech Stack:** aiogram 3.x `F.voice`, OpenAI Whisper API via LiteLLM proxy (:4000), LangGraph StateGraph, Langfuse `@observe`

**Design doc:** `docs/plans/2026-02-11-voice-transcription-design.md`

---

### Task 1: Add whisper model to LiteLLM configs

**Files:**
- Modify: `docker/litellm/config.yaml:5-47` (model_list)
- Modify: `k8s/base/configmaps/litellm-config.yaml:7-48` (model_list)

**Step 1: Add whisper to Docker config**

In `docker/litellm/config.yaml`, add after the last model in `model_list` (after line 46):

```yaml
  # Speech-to-text: Whisper via OpenAI
  - model_name: whisper
    litellm_params:
      model: whisper-1
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      mode: audio_transcription
```

**Step 2: Add whisper to k8s ConfigMap**

In `k8s/base/configmaps/litellm-config.yaml`, add the same block inside `data.config.yaml` model_list (indented 6 spaces):

```yaml
      # Speech-to-text: Whisper via OpenAI
      - model_name: whisper
        litellm_params:
          model: whisper-1
          api_key: os.environ/OPENAI_API_KEY
        model_info:
          mode: audio_transcription
```

**Step 3: Run sync test to verify**

Run: `uv run pytest tests/unit/test_litellm_config_sync.py -v`
Expected: All 3 tests PASS (model_list, router_settings, litellm_settings match)

**Step 4: Commit**

```bash
git add docker/litellm/config.yaml k8s/base/configmaps/litellm-config.yaml
git commit -m "feat(litellm): add whisper-1 model for audio transcription"
```

---

### Task 2: Extend RAGState with voice fields

**Files:**
- Modify: `telegram_bot/graph/state.py:13-93`
- Test: `tests/unit/graph/test_transcribe_node.py` (created in Task 3)

**Step 1: Add voice fields to RAGState TypedDict**

In `telegram_bot/graph/state.py`, add after line 51 (`streaming_enabled: bool`):

```python
    # Voice transcription
    voice_audio: bytes | None
    voice_duration_s: float | None
    stt_text: str | None
    stt_duration_ms: float | None
    input_type: str  # "text" or "voice"
```

**Step 2: Add defaults to make_initial_state**

In `telegram_bot/graph/state.py`, add to the return dict in `make_initial_state()` (after line 92, `"streaming_enabled": False`):

```python
        # Voice transcription
        "voice_audio": None,
        "voice_duration_s": None,
        "stt_text": None,
        "stt_duration_ms": None,
        "input_type": "text",
```

**Step 3: Run existing tests to verify nothing broke**

Run: `uv run pytest tests/unit/graph/ -v --timeout=30`
Expected: All existing graph tests PASS

**Step 4: Commit**

```bash
git add telegram_bot/graph/state.py
git commit -m "feat(state): add voice transcription fields to RAGState"
```

---

### Task 3: Add config settings (SHOW_TRANSCRIPTION, VOICE_LANGUAGE, STT_MODEL)

**Files:**
- Modify: `telegram_bot/config.py:7-285`
- Modify: `telegram_bot/graph/config.py:14-126`

**Step 1: Add voice config to BotConfig**

In `telegram_bot/config.py`, add after `domain_language` field (after line 228):

```python
    # Voice transcription
    show_transcription: bool = Field(
        default=True,
        validation_alias=AliasChoices("show_transcription", "SHOW_TRANSCRIPTION"),
    )
    voice_language: str = Field(
        default="ru",
        validation_alias=AliasChoices("voice_language", "VOICE_LANGUAGE"),
    )
    stt_model: str = Field(
        default="whisper",
        validation_alias=AliasChoices("stt_model", "STT_MODEL"),
    )
```

**Step 2: Add voice settings to GraphConfig**

In `telegram_bot/graph/config.py`, add after `streaming_enabled` field (after line 42):

```python
    show_transcription: bool = True
    voice_language: str = "ru"
    stt_model: str = "whisper"
```

**Step 3: Wire from_env()**

In `telegram_bot/graph/config.py`, add to `from_env()` return (after line 86, `streaming_enabled=...`):

```python
            show_transcription=os.getenv("SHOW_TRANSCRIPTION", "true").lower() == "true",
            voice_language=os.getenv("VOICE_LANGUAGE", "ru"),
            stt_model=os.getenv("STT_MODEL", "whisper"),
```

**Step 4: Wire from BotConfig to GraphConfig in bot.py**

In `telegram_bot/bot.py`, the `GraphConfig` is created in `__init__`. Since `GraphConfig` uses `from_env()` pattern when called from graph nodes directly, and the BotConfig values are passed to build_graph, the env vars will be read. No wiring change needed — `from_env()` reads directly from env.

**Step 5: Verify types pass**

Run: `uv run ruff check telegram_bot/config.py telegram_bot/graph/config.py`
Expected: No errors

**Step 6: Commit**

```bash
git add telegram_bot/config.py telegram_bot/graph/config.py
git commit -m "feat(config): add SHOW_TRANSCRIPTION, VOICE_LANGUAGE, STT_MODEL settings"
```

---

### Task 4: Create transcribe_node

**Files:**
- Create: `telegram_bot/graph/nodes/transcribe.py`
- Test: `tests/unit/graph/test_transcribe_node.py`

**Step 1: Write the failing test**

Create `tests/unit/graph/test_transcribe_node.py`:

```python
"""Tests for transcribe_node — voice-to-text via Whisper API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.state import make_initial_state


def _make_voice_state(audio: bytes = b"fake-ogg-data", duration: float = 5.0) -> dict:
    """Create a state dict with voice_audio populated."""
    state = make_initial_state(user_id=123, session_id="test-abc-20260211", query="")
    state["voice_audio"] = audio
    state["voice_duration_s"] = duration
    state["input_type"] = "voice"
    return state


class TestTranscribeNode:
    @pytest.mark.asyncio
    async def test_transcribe_returns_text(self):
        """transcribe_node calls Whisper API and returns transcribed text."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="Привет мир")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()
        result = await node(state)

        assert result["stt_text"] == "Привет мир"
        assert result["query"] == "Привет мир"
        assert result["stt_duration_ms"] > 0
        mock_llm.audio.transcriptions.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transcribe_sets_messages(self):
        """transcribe_node sets messages with transcribed text."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест запрос")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()
        result = await node(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "тест запрос"

    @pytest.mark.asyncio
    async def test_transcribe_empty_text_raises(self):
        """transcribe_node raises ValueError on empty transcription."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(ValueError, match="Empty transcription"):
            await node(state)

    @pytest.mark.asyncio
    async def test_transcribe_passes_language(self):
        """transcribe_node passes language parameter to Whisper API."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="uk", stt_model="whisper")
        state = _make_voice_state()
        await node(state)

        call_kwargs = mock_llm.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "uk"
        assert call_kwargs["model"] == "whisper"

    @pytest.mark.asyncio
    async def test_transcribe_api_error(self):
        """transcribe_node propagates API errors."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.side_effect = Exception("API timeout")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(Exception, match="API timeout"):
            await node(state)

    @pytest.mark.asyncio
    async def test_transcribe_show_transcription(self):
        """transcribe_node sends transcription preview when show_transcription=True."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")
        mock_message = AsyncMock()

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(
            llm=mock_llm,
            voice_language="ru",
            stt_model="whisper",
            show_transcription=True,
            message=mock_message,
        )
        state = _make_voice_state()
        await node(state)

        mock_message.answer.assert_awaited_once()
        call_args = mock_message.answer.call_args
        assert "тест" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_transcribe_no_preview_when_disabled(self):
        """transcribe_node does not send preview when show_transcription=False."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")
        mock_message = AsyncMock()

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(
            llm=mock_llm,
            voice_language="ru",
            stt_model="whisper",
            show_transcription=False,
            message=mock_message,
        )
        state = _make_voice_state()
        await node(state)

        mock_message.answer.assert_not_awaited()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/graph/test_transcribe_node.py -v`
Expected: FAIL (ImportError — `make_transcribe_node` not found)

**Step 3: Write the implementation**

Create `telegram_bot/graph/nodes/transcribe.py`:

```python
"""transcribe_node — voice-to-text via Whisper API (LiteLLM proxy).

Receives voice audio bytes from RAGState, calls OpenAI Whisper API
through the existing AsyncOpenAI client (LiteLLM proxy), returns
transcribed text that feeds into the classify → ... pipeline.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Any

from telegram_bot.observability import observe

logger = logging.getLogger(__name__)


def make_transcribe_node(
    *,
    llm: Any,
    voice_language: str = "ru",
    stt_model: str = "whisper",
    show_transcription: bool = True,
    message: Any | None = None,
):
    """Create transcribe_node with injected dependencies.

    Args:
        llm: AsyncOpenAI client (same as generate_node uses).
        voice_language: ISO language code for Whisper hint.
        stt_model: Model name in LiteLLM config.
        show_transcription: Send transcription preview to user.
        message: aiogram Message for sending preview.
    """

    @observe(name="transcribe")
    async def transcribe_node(state: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()

        voice_audio = state["voice_audio"]
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

        # Send transcription preview (optional)
        if show_transcription and message is not None:
            try:
                await message.answer(
                    f"\U0001f3a4 _{text}_",
                    parse_mode="Markdown",
                )
            except Exception:
                logger.warning("Failed to send transcription preview", exc_info=True)

        return {
            "stt_text": text,
            "stt_duration_ms": stt_duration_ms,
            "query": text,
            "messages": [{"role": "user", "content": text}],
        }

    return transcribe_node
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/graph/test_transcribe_node.py -v`
Expected: All 7 tests PASS

**Step 5: Run linter**

Run: `uv run ruff check telegram_bot/graph/nodes/transcribe.py tests/unit/graph/test_transcribe_node.py`
Expected: No errors

**Step 6: Commit**

```bash
git add telegram_bot/graph/nodes/transcribe.py tests/unit/graph/test_transcribe_node.py
git commit -m "feat(transcribe): add transcribe_node with Whisper API via LiteLLM"
```

---

### Task 5: Add route_start edge and wire transcribe_node into graph

**Files:**
- Modify: `telegram_bot/graph/edges.py:1-49`
- Modify: `telegram_bot/graph/graph.py:1-185`

**Step 1: Add route_start edge function**

In `telegram_bot/graph/edges.py`, add after the imports (after line 11):

```python
def route_start(
    state: dict[str, Any],
) -> Literal["transcribe", "classify"]:
    """Route at START: voice messages → transcribe, text → classify."""
    if state.get("voice_audio") is not None:
        return "transcribe"
    return "classify"
```

Update the module docstring (line 3-7) to mention `route_start`:

```python
"""Conditional edge functions for RAG LangGraph pipeline.

Four routing functions that control the graph flow:
- route_start: START → transcribe or classify
- route_by_query_type: classify → respond or cache_check
- route_cache: cache_check → respond or retrieve
- route_grade: grade → rerank, rewrite, or generate
"""
```

**Step 2: Wire transcribe_node into build_graph**

In `telegram_bot/graph/graph.py`:

a) Add `route_start` to the import (line 13):
```python
from telegram_bot.graph.edges import route_by_query_type, route_cache, route_grade, route_start
```

b) Add new parameters to `build_graph()` signature (after line 27, `event_stream`):
```python
    show_transcription: bool = True,
    voice_language: str = "ru",
    stt_model: str = "whisper",
```

c) Add transcribe_node import and registration. After line 48 (`from telegram_bot.graph.nodes.rewrite import rewrite_node`), add:
```python
    from telegram_bot.graph.nodes.transcribe import make_transcribe_node
```

After line 53 (classify add_node), add:
```python
    workflow.add_node(
        "transcribe",
        make_transcribe_node(
            llm=llm,
            voice_language=voice_language,
            stt_model=stt_model,
            show_transcription=show_transcription,
            message=message,
        ),
    )
```

d) Replace the direct START → classify edge (line 99):
```python
    # Before:
    workflow.add_edge(START, "classify")

    # After:
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "transcribe": "transcribe",
            "classify": "classify",
        },
    )
    workflow.add_edge("transcribe", "classify")
```

**Step 3: Run all graph tests**

Run: `uv run pytest tests/unit/graph/ tests/integration/test_graph_paths.py -v --timeout=30`
Expected: All existing tests PASS (they use text — no `voice_audio`, so `route_start` → "classify")

**Step 4: Run linter**

Run: `uv run ruff check telegram_bot/graph/edges.py telegram_bot/graph/graph.py`
Expected: No errors

**Step 5: Commit**

```bash
git add telegram_bot/graph/edges.py telegram_bot/graph/graph.py
git commit -m "feat(graph): wire transcribe_node with conditional START edge"
```

---

### Task 6: Add handle_voice handler to bot.py

**Files:**
- Modify: `telegram_bot/bot.py:9,198-323`

**Step 1: Add io import**

In `telegram_bot/bot.py`, add `io` to imports (after line 5):
```python
import io
```

**Step 2: Register voice handler**

In `_register_handlers()` (line 205), add before `self.dp.message(F.text)(self.handle_query)`:

```python
        self.dp.message(F.voice)(self.handle_voice)
```

**Important:** `F.voice` must be registered BEFORE `F.text` because `F.text` won't match voice messages anyway (voice messages have no `.text`), but ordering keeps intent clear.

**Step 3: Add handle_voice method**

Add after `handle_query()` method (after line 323), before `start()`:

```python
    @observe(name="telegram-rag-voice")
    async def handle_voice(self, message: Message):
        """Handle voice message via Whisper STT + LangGraph RAG pipeline."""
        pipeline_start = time.perf_counter()
        assert message.bot is not None
        assert message.from_user is not None
        assert message.voice is not None
        bot = message.bot
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        # Download voice file into memory
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        assert file.file_path is not None
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        voice_bytes = buf.getvalue()

        state = make_initial_state(
            user_id=message.from_user.id,
            session_id=make_session_id("chat", message.chat.id),
            query="",  # will be set by transcribe_node
        )
        state["voice_audio"] = voice_bytes
        state["voice_duration_s"] = float(voice.duration)
        state["input_type"] = "voice"
        state["max_rewrite_attempts"] = self._graph_config.max_rewrite_attempts

        with propagate_attributes(
            session_id=state["session_id"],
            user_id=str(state["user_id"]),
            tags=["telegram", "rag", "voice"],
        ):
            graph = build_graph(
                cache=self._cache,
                embeddings=self._embeddings,
                sparse_embeddings=self._sparse,
                qdrant=self._qdrant,
                reranker=self._reranker,
                llm=self._llm,
                message=message,
                show_transcription=self._graph_config.show_transcription,
                voice_language=self._graph_config.voice_language,
                stt_model=self._graph_config.stt_model,
            )

            try:
                async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
                    result = await graph.ainvoke(state)
            except ValueError as e:
                if "Empty transcription" in str(e):
                    await message.answer("Голосовое сообщение не содержит речи.")
                    return
                raise
            except Exception:
                await message.answer(
                    "Не удалось распознать голосовое сообщение. "
                    "Попробуйте отправить текстом."
                )
                raise

            result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000

            lf = get_client()
            lf.update_current_trace(
                input={"voice_duration_s": voice.duration, "stt_text": result.get("stt_text", "")},
                output={"response": result.get("response", "")},
                metadata={
                    "input_type": "voice",
                    "query_type": result.get("query_type", ""),
                    "cache_hit": result.get("cache_hit", False),
                    "stt_duration_ms": result.get("stt_duration_ms", 0.0),
                },
            )

            _write_langfuse_scores(lf, result)
```

**Step 4: Run linter**

Run: `uv run ruff check telegram_bot/bot.py`
Expected: No errors

**Step 5: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(bot): add handle_voice handler for voice messages"
```

---

### Task 7: Add voice-specific Langfuse scores

**Files:**
- Modify: `telegram_bot/bot.py:39-104` (`_write_langfuse_scores`)

**Step 1: Add voice scores to _write_langfuse_scores**

In `telegram_bot/bot.py`, add after the latency breakdown section (after line 104, before the function ends):

```python
    # --- Voice transcription scores ---
    input_type = result.get("input_type", "text")
    lf.score_current_trace(name="input_type", value=input_type, data_type="CATEGORICAL")

    stt_ms = result.get("stt_duration_ms")
    if stt_ms is not None:
        lf.score_current_trace(name="stt_duration_ms", value=float(stt_ms))

    voice_dur = result.get("voice_duration_s")
    if voice_dur is not None:
        lf.score_current_trace(name="voice_duration_s", value=float(voice_dur))
```

**Step 2: Run existing score tests**

Run: `uv run pytest tests/unit/ -k "langfuse or score" -v --timeout=30`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(scores): add voice transcription Langfuse scores (input_type, stt_duration_ms, voice_duration_s)"
```

---

### Task 8: Add graph path integration test for voice flow

**Files:**
- Modify: `tests/integration/test_graph_paths.py`

**Step 1: Add voice path test**

Add a new test to `tests/integration/test_graph_paths.py` that tests the voice flow:
`START → transcribe → classify → cache_check → retrieve → grade → ...`

The test should:
1. Create a state with `voice_audio=b"fake-ogg"` and `input_type="voice"`
2. Mock the LLM's `audio.transcriptions.create` to return text
3. Verify `transcribe` node was visited
4. Verify the transcribed text was used as the query

**Exact implementation depends on existing test patterns in `test_graph_paths.py`.** Follow the same mock patterns used for `test_path_happy_retrieve_rerank_generate`.

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: All tests PASS (including new voice path test)

**Step 3: Commit**

```bash
git add tests/integration/test_graph_paths.py
git commit -m "test(graph): add voice transcription graph path integration test"
```

---

### Task 9: Final verification

**Step 1: Run full lint + type check**

Run: `make check`
Expected: No errors

**Step 2: Run full unit test suite**

Run: `uv run pytest tests/unit/ -n auto --timeout=30`
Expected: All tests PASS

**Step 3: Run integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`
Expected: All tests PASS (including new voice path)

**Step 4: Verify LiteLLM config sync**

Run: `uv run pytest tests/unit/test_litellm_config_sync.py -v`
Expected: All 3 tests PASS

**Step 5: Commit any fixes, then final commit if needed**

---

## Summary

| Task | Files | Type |
|------|-------|------|
| 1 | litellm configs (2 files) | Config |
| 2 | state.py | State schema |
| 3 | config.py, graph/config.py | Config |
| 4 | transcribe.py + test | Core feature (TDD) |
| 5 | edges.py, graph.py | Graph wiring |
| 6 | bot.py | Handler |
| 7 | bot.py | Langfuse scores |
| 8 | test_graph_paths.py | Integration test |
| 9 | — | Verification |

**New files:** 2 (transcribe.py, test_transcribe_node.py)
**Modified files:** 7
**New dependencies:** 0
**Total estimated tasks:** 9
