# Latency Breakdown Implementation Plan (#147)

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add up to 10 granular Langfuse scores to diagnose slow LLM responses with strict semantics: real TTFT/decode/TPS where measurable, explicit unavailable flags otherwise.

**Architecture:** Compute metrics in `generate_node`, propagate via `RAGState`, write as NUMERIC/BOOLEAN Langfuse scores in `bot.py`. `llm_queue_ms` is emitted only when reliable provider timing headers exist. Conditional numeric metrics are skipped when unavailable and paired `*_unavailable` BOOLEAN flags are emitted instead of sentinels.

**Tech Stack:** Python, Langfuse SDK v3 (`score_current_trace` with `data_type`), LangGraph, pytest

**Design doc:** `docs/plans/2026-02-11-latency-breakdown-design.md`

---

### Task 1: Add state fields to RAGState

**Files:**
- Modify: `telegram_bot/graph/state.py`

**Step 1: Add 6 new fields to RAGState TypedDict**

Add after `llm_response_duration_ms: float` (line 44):

```python
    # Latency breakdown (#147)
    llm_decode_ms: float | None
    llm_tps: float | None
    llm_queue_ms: float | None
    llm_timeout: bool
    llm_stream_recovery: bool
    streaming_enabled: bool
```

**Step 2: Add defaults to make_initial_state()**

Add after `"llm_response_duration_ms": 0.0,` (line 78):

```python
        # Latency breakdown (#147)
        "llm_decode_ms": None,
        "llm_tps": None,
        "llm_queue_ms": None,
        "llm_timeout": False,
        "llm_stream_recovery": False,
        "streaming_enabled": False,
```

**Step 3: Verify import and type check**

Run: `uv run python -c "from telegram_bot.graph.state import RAGState, make_initial_state; s = make_initial_state(1, 's', 'q'); print(s['llm_timeout'], s['llm_decode_ms'])"`

Expected: `False None`

**Step 4: Commit**

```bash
git add telegram_bot/graph/state.py
git commit -m "feat(state): add latency breakdown fields #147"
```

---

### Task 2: Write failing tests for decode_ms and tps computation

**Files:**
- Modify: `tests/unit/graph/test_generate_node.py`

**Step 1: Add _MockStreamChunkWithUsage helper class**

Add after `_MockAsyncStream` class (after line 64):

```python
class _MockStreamChunkWithUsage:
    """Final mock streaming chunk that includes token usage."""

    def __init__(self, completion_tokens: int, prompt_tokens: int = 100):
        self.choices = []  # no content in usage-only chunk
        self.model = None
        usage = MagicMock()
        usage.completion_tokens = completion_tokens
        usage.prompt_tokens = prompt_tokens
        usage.total_tokens = prompt_tokens + completion_tokens
        self.usage = usage


class _MockAsyncStreamWithUsage:
    """Async iterator that yields content chunks then a usage-only chunk."""

    def __init__(self, texts: list[str], completion_tokens: int):
        self._chunks: list[Any] = [_MockStreamChunk(t) for t in texts]
        self._chunks.append(_MockStreamChunkWithUsage(completion_tokens))
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk
```

**Step 2: Add test class for latency breakdown metrics**

Add at the end of the file:

```python
class TestGenerateNodeLatencyBreakdown:
    """Test decode_ms, tps, queue_ms, and flag computation (#147)."""

    @pytest.mark.asyncio
    async def test_streaming_computes_decode_ms(self) -> None:
        """Streaming path: decode_ms = response_duration_ms - ttft_ms."""
        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Квартира ", "в Несебре ", "стоит 65000€."]
        mock_client = _make_streaming_client(chunks)

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = True
        mock_config.create_llm.return_value = mock_client

        sent_msg = AsyncMock()
        sent_msg.edit_text = AsyncMock()
        message = AsyncMock()
        message.answer = AsyncMock(return_value=sent_msg)

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        # decode_ms should be computed (response_duration - ttft)
        assert result["llm_decode_ms"] is not None
        assert result["llm_decode_ms"] >= 0
        # streaming_enabled should be True
        assert result["streaming_enabled"] is True

    @pytest.mark.asyncio
    async def test_streaming_with_usage_computes_tps(self) -> None:
        """Streaming with token usage: tps = completion_tokens / (decode_s)."""
        from telegram_bot.graph.nodes.generate import generate_node

        stream = _MockAsyncStreamWithUsage(
            texts=["Квартира ", "стоит ", "65000€."],
            completion_tokens=42,
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = True
        mock_config.create_llm.return_value = mock_client

        sent_msg = AsyncMock()
        sent_msg.edit_text = AsyncMock()
        message = AsyncMock()
        message.answer = AsyncMock(return_value=sent_msg)

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_tps"] is not None
        assert result["llm_tps"] > 0

    @pytest.mark.asyncio
    async def test_non_streaming_decode_and_tps_are_none(self) -> None:
        """Non-streaming: decode_ms and tps are None."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Ответ.", streaming_enabled=False)
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_decode_ms"] is None
        assert result["llm_tps"] is None
        assert result["streaming_enabled"] is False

    @pytest.mark.asyncio
    async def test_streaming_without_usage_tps_is_none(self) -> None:
        """Streaming without token usage: tps is None."""
        from telegram_bot.graph.nodes.generate import generate_node

        # Standard stream without usage chunks
        chunks = ["Hello ", "world."]
        mock_client = _make_streaming_client(chunks)

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = True
        mock_config.create_llm.return_value = mock_client

        sent_msg = AsyncMock()
        sent_msg.edit_text = AsyncMock()
        message = AsyncMock()
        message.answer = AsyncMock(return_value=sent_msg)

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        # decode_ms should still be computed
        assert result["llm_decode_ms"] is not None
        # tps is None because no usage data
        assert result["llm_tps"] is None
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown -v`

Expected: FAIL — `KeyError: 'llm_decode_ms'` (fields not yet returned by generate_node)

---

### Task 3: Implement decode_ms, tps, and streaming_enabled in generate_node

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py`

**Step 1: Update _generate_streaming to track completion_tokens**

Change `_generate_streaming` signature and return type (line 114):

```python
async def _generate_streaming(
    llm: Any,
    config: Any,
    llm_messages: list[dict[str, str]],
    message: Any,
) -> tuple[str, str, float, int | None]:
    """Stream LLM response directly to Telegram via message editing.

    ...existing docstring...

    Returns:
        Tuple of (response_text, actual_model, ttft_ms, completion_tokens).
    """
```

Add `completion_tokens` tracking inside the function. Add `completion_tokens: int | None = None` after `actual_model = config.llm_model` (line 143). Inside the chunk loop, after the model extraction (line 169-170), add:

```python
            if hasattr(chunk, "usage") and chunk.usage is not None:
                ct = getattr(chunk.usage, "completion_tokens", None)
                if ct is not None:
                    completion_tokens = ct
```

Change the return statement (line 194) to:

```python
    return accumulated, actual_model, ttft_ms, completion_tokens
```

**Step 2: Update streaming call sites in generate_node**

Line 270 — successful streaming:

```python
                answer, actual_model, ttft_ms, completion_tokens = await _generate_streaming(
```

Add `completion_tokens` to the variable scope. Initialize at the top of `generate_node` (after `response_obj: Any | None = None`, line 250):

```python
    completion_tokens: int | None = None
```

**Step 3: Compute derived metrics before return**

Replace the return block at lines 366-373. Before the return, add metric computation:

```python
    # --- Latency breakdown (#147) ---
    streaming_was_enabled = bool(message is not None and config.streaming_enabled)
    llm_decode_ms: float | None = None
    llm_tps: float | None = None
    llm_queue_ms: float | None = _extract_queue_ms_from_provider_headers(response_obj)

    if streaming_was_enabled and ttft_ms > 0:
        response_duration_ms = elapsed * 1000
        llm_decode_ms = response_duration_ms - ttft_ms
        if llm_decode_ms < 0:
            llm_decode_ms = 0.0
        if completion_tokens is not None and llm_decode_ms > 0:
            llm_tps = completion_tokens / (llm_decode_ms / 1000)

    return {
        "response": answer,
        "response_sent": response_sent,
        "llm_provider_model": actual_model,
        "llm_ttft_ms": ttft_ms,
        "llm_response_duration_ms": elapsed * 1000,
        "latency_stages": {**state.get("latency_stages", {}), "generate": elapsed},
        # Latency breakdown (#147)
        "llm_decode_ms": llm_decode_ms,
        "llm_tps": llm_tps,
        "llm_queue_ms": llm_queue_ms,
        "llm_timeout": False,
        "llm_stream_recovery": False,
        "streaming_enabled": streaming_was_enabled,
    }
```

Add a small helper in `generate.py`:

```python
def _extract_queue_ms_from_provider_headers(response_obj: Any | None) -> float | None:
    """Return provider-reported queue time in ms, or None if unavailable/unreliable."""
    return None
```

Initial implementation may return `None` until a provider-specific reliable header is verified in runtime responses.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown -v`

Expected: 4 PASS

**Step 5: Run existing tests to verify no regressions**

Run: `uv run pytest tests/unit/graph/test_generate_node.py -v`

Expected: All PASS

**Step 6: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "feat(generate): compute decode_ms, tps, streaming_enabled #147"
```

---

### Task 4: Write failing tests for stream recovery and timeout flags

**Files:**
- Modify: `tests/unit/graph/test_generate_node.py`

**Step 1: Add flag tests to TestGenerateNodeLatencyBreakdown**

```python
    @pytest.mark.asyncio
    async def test_stream_recovery_sets_flags(self) -> None:
        """Streaming fails before content → non-streaming saves → recovery flags set."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback answer."
        mock_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[Exception("stream error"), mock_response],
        )

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = True
        mock_config.create_llm.return_value = mock_client

        message = AsyncMock()
        message.answer = AsyncMock(return_value=AsyncMock())

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_stream_recovery"] is True
        assert result["llm_timeout"] is False
        assert result["streaming_enabled"] is True

    @pytest.mark.asyncio
    async def test_hard_fail_sets_timeout(self) -> None:
        """Complete LLM failure: llm_timeout=True, fallback_used."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unavailable"),
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_timeout"] is True
        assert result["llm_stream_recovery"] is False
        assert result["llm_decode_ms"] is None
        assert result["llm_tps"] is None

    @pytest.mark.asyncio
    async def test_partial_stream_recovery_sets_flags(self) -> None:
        """StreamingPartialDeliveryError → non-streaming fallback: recovery=True."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback complete answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["partial "]),
                mock_fallback_response,
            ],
        )

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = True
        mock_config.create_llm.return_value = mock_client

        sent_msg = AsyncMock()
        sent_msg.edit_text = AsyncMock()
        message = AsyncMock()
        message.answer = AsyncMock(return_value=sent_msg)

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_stream_recovery"] is True
        assert result["llm_timeout"] is False
```

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown::test_stream_recovery_sets_flags tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown::test_hard_fail_sets_timeout tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown::test_partial_stream_recovery_sets_flags -v`

Expected: FAIL — `llm_stream_recovery` is `False` (not yet set on recovery path), `llm_timeout` is `False` (not yet set on hard fail)

---

### Task 5: Implement stream recovery and timeout flags in generate_node

**Files:**
- Modify: `telegram_bot/graph/nodes/generate.py`

**Step 1: Add flag tracking variables**

At the top of `generate_node`, after `completion_tokens: int | None = None`, add:

```python
    stream_recovery = False
    hard_timeout = False
```

**Step 2: Set stream_recovery only when partial-stream fallback is successfully delivered**

In the `except StreamingPartialDeliveryError` block (line 277), set the flag after fallback delivery is attempted (where `delivered` is known):

```python
                stream_recovery = delivered
```

**Step 3: Set stream_recovery only after generic streaming fallback succeeds**

In the `except Exception` block for streaming (line 309), set the flag only after the non-streaming fallback call returns an answer:

```python
                stream_recovery = True
```

**Step 4: Set hard_timeout on the outer except**

In the outer `except Exception as e` block (line 336), after `actual_model = "fallback"`, add:

```python
        hard_timeout = True
        stream_recovery = False
```

**Step 5: Wire flags into return dict**

In the return dict (from Task 3), replace the hardcoded flags:

```python
        "llm_timeout": hard_timeout,
        "llm_stream_recovery": stream_recovery,
```

**Step 6: Run flag tests to verify GREEN**

Run: `uv run pytest tests/unit/graph/test_generate_node.py::TestGenerateNodeLatencyBreakdown -v`

Expected: 7 PASS (4 from Task 2 + 3 from Task 4)

**Step 7: Run ALL generate_node tests**

Run: `uv run pytest tests/unit/graph/test_generate_node.py -v`

Expected: All PASS

**Step 8: Commit**

```bash
git add telegram_bot/graph/nodes/generate.py tests/unit/graph/test_generate_node.py
git commit -m "feat(generate): add stream_recovery and timeout flags #147"
```

---

### Task 6: Write failing tests for score writing paths

**Files:**
- Modify: `tests/unit/test_bot_scores.py`

**Step 1: Update FULL_PIPELINE_RESULT with new fields (streaming path)**

Add to `FULL_PIPELINE_RESULT` dict (after `llm_response_duration_ms` which isn't there — add after `"latency_stages"`):

```python
    # Latency breakdown (#147)
    "llm_ttft_ms": 150.0,
    "llm_response_duration_ms": 450.0,
    "llm_decode_ms": 300.0,
    "llm_tps": 42.5,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": True,
```

Note: `FULL_PIPELINE_RESULT` currently doesn't have `llm_ttft_ms` / `llm_response_duration_ms`. Add these along with the new fields.

**Step 2: Update CACHE_HIT_RESULT and CHITCHAT_RESULT**

Add to both:

```python
    "llm_decode_ms": None,
    "llm_tps": None,
    "llm_queue_ms": None,
    "llm_timeout": False,
    "llm_stream_recovery": False,
    "streaming_enabled": False,
```

**Step 3: Add TestLatencyBreakdownScores test class**

```python
class TestLatencyBreakdownScores:
    """Test latency breakdown score writing (#147)."""

    async def _run_handle_query(self, mock_config, graph_result, mock_lf_client):
        """Helper: run handle_query with mocked graph and Langfuse client."""
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

            await bot.handle_query(_make_message())

        return mock_lf_client

    @pytest.mark.asyncio
    async def test_streaming_path_writes_numeric_and_boolean_scores(self, mock_config):
        """Streaming: writes llm_decode_ms, llm_tps as NUMERIC; boolean flags."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, FULL_PIPELINE_RESULT, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        # NUMERIC scores written
        assert score_map["llm_decode_ms"]["value"] == 300.0
        assert score_map["llm_tps"]["value"] == 42.5

        # BOOLEAN flags
        assert score_map["streaming_enabled"]["value"] == 1
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"
        assert score_map["llm_timeout"]["value"] == 0
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"
        assert score_map["llm_stream_recovery"]["value"] == 0
        assert score_map["llm_stream_recovery"]["data_type"] == "BOOLEAN"

        # queue_unavailable because queue_ms is None
        assert score_map["llm_queue_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["data_type"] == "BOOLEAN"
        # No llm_decode_unavailable (decode_ms was written)
        assert "llm_decode_unavailable" not in score_map

    @pytest.mark.asyncio
    async def test_non_streaming_writes_unavailable_flags(self, mock_config):
        """Non-streaming: writes *_unavailable BOOLEAN flags, skips NUMERIC decode/tps."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        await self._run_handle_query(mock_config, CACHE_HIT_RESULT, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        # NUMERIC scores NOT written
        assert "llm_decode_ms" not in score_map
        assert "llm_tps" not in score_map
        assert "llm_queue_ms" not in score_map

        # Unavailable flags written
        assert score_map["llm_decode_unavailable"]["value"] == 1
        assert score_map["llm_decode_unavailable"]["data_type"] == "BOOLEAN"
        assert score_map["llm_tps_unavailable"]["value"] == 1
        assert score_map["llm_queue_unavailable"]["value"] == 1

        # streaming_enabled = False
        assert score_map["streaming_enabled"]["value"] == 0
        assert score_map["streaming_enabled"]["data_type"] == "BOOLEAN"

    @pytest.mark.asyncio
    async def test_hard_fail_writes_timeout_true(self, mock_config):
        """Hard LLM failure: llm_timeout=1 BOOLEAN."""
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.score_current_trace = MagicMock()

        timeout_result = {
            **CHITCHAT_RESULT,
            "llm_timeout": True,
            "llm_stream_recovery": False,
            "streaming_enabled": False,
            "llm_decode_ms": None,
            "llm_tps": None,
            "llm_queue_ms": None,
        }

        await self._run_handle_query(mock_config, timeout_result, mock_lf)

        calls = mock_lf.score_current_trace.call_args_list
        score_map = {c.kwargs["name"]: c.kwargs for c in calls}

        assert score_map["llm_timeout"]["value"] == 1
        assert score_map["llm_timeout"]["data_type"] == "BOOLEAN"
```

**Step 4: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_bot_scores.py::TestLatencyBreakdownScores -v`

Expected: FAIL — `KeyError: 'llm_decode_ms'` (not yet written by `_write_langfuse_scores`)

---

### Task 7: Implement score writing in bot.py

**Files:**
- Modify: `telegram_bot/bot.py`

**Step 1: Update docstring**

Change `"""Write 14 Langfuse scores` to `"""Write Langfuse scores (14 original + up to 10 latency breakdown)`.

**Step 2: Add latency breakdown score writing**

After the existing `for name, value in scores.items():` loop (line 67), add:

```python
    # --- Latency breakdown (#147) ---
    # Always-written BOOLEAN flags
    lf.score_current_trace(
        name="streaming_enabled",
        value=1 if result.get("streaming_enabled") else 0,
        data_type="BOOLEAN",
    )
    lf.score_current_trace(
        name="llm_timeout",
        value=1 if result.get("llm_timeout") else 0,
        data_type="BOOLEAN",
    )

    # Always-written BOOLEAN diagnostic signal
    lf.score_current_trace(
        name="llm_stream_recovery",
        value=1 if result.get("llm_stream_recovery") else 0,
        data_type="BOOLEAN",
    )

    # Conditional NUMERIC + paired unavailable BOOLEAN flags
    decode_ms = result.get("llm_decode_ms")
    if decode_ms is not None:
        lf.score_current_trace(name="llm_decode_ms", value=float(decode_ms))
    else:
        lf.score_current_trace(name="llm_decode_unavailable", value=1, data_type="BOOLEAN")

    tps = result.get("llm_tps")
    if tps is not None:
        lf.score_current_trace(name="llm_tps", value=float(tps))
    else:
        lf.score_current_trace(name="llm_tps_unavailable", value=1, data_type="BOOLEAN")

    queue_ms = result.get("llm_queue_ms")
    if queue_ms is not None:
        lf.score_current_trace(name="llm_queue_ms", value=float(queue_ms))
    else:
        lf.score_current_trace(name="llm_queue_unavailable", value=1, data_type="BOOLEAN")
```

**Step 3: Run new tests to verify GREEN**

Run: `uv run pytest tests/unit/test_bot_scores.py::TestLatencyBreakdownScores -v`

Expected: 3 PASS

**Step 4: Run ALL score tests (check no regressions)**

Run: `uv run pytest tests/unit/test_bot_scores.py -v`

Expected: All PASS. Note: existing `test_scores_written_full_pipeline` checks for 12 scores with sorted names. It will now have more scores. Update the expected count and name list.

**Step 5: Update existing test expectations**

In `test_scores_written_full_pipeline`, update `expected_names` list and count to include the new scores from the streaming FULL_PIPELINE_RESULT. The exact count depends on the path (streaming = 12 original + streaming_enabled + llm_timeout + llm_stream_recovery + llm_decode_ms + llm_tps + llm_queue_unavailable = 18). Update the `assert mock_lf.score_current_trace.call_count` line accordingly.

**Step 6: Commit**

```bash
git add telegram_bot/bot.py tests/unit/test_bot_scores.py
git commit -m "feat(scores): write latency breakdown scores with BOOLEAN/NUMERIC types #147"
```

---

### Task 8: Verify full test suite and lint

**Files:** none (verification only)

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -x -v --timeout=30`

Expected: All PASS

**Step 2: Run linter and type check**

Run: `make check`

Expected: Clean. Fix any ruff/mypy issues.

**Step 3: Run graph path integration tests**

Run: `uv run pytest tests/integration/test_graph_paths.py -v`

Expected: All 6 PASS (state changes are backward-compatible)

**Step 4: Final commit if any fixes**

```bash
git add -u
git commit -m "fix(lint): resolve type/lint issues from latency breakdown #147"
```

---

### Task 9: Update observability docs

**Files:**
- Modify: `.claude/rules/observability.md`

**Step 1: Update Langfuse Scores table**

Add new scores to the table in "Langfuse Scores" section. Change "14 scores" to "14 + up to 10 latency breakdown scores". Add the 10 new score rows with their types and descriptions.

**Step 2: Commit**

```bash
git add .claude/rules/observability.md
git commit -m "docs(observability): add latency breakdown scores to rules #147"
```

---

## Notes

**stream_options for TPS:** Currently TPS depends on providers sending `usage` in streaming chunks. Not all do. LiteLLM supports `stream_options={"include_usage": True}` for OpenAI-compatible providers. Adding this parameter is a future enhancement — for now, `tps_unavailable=True` is the expected state for most streaming runs until we enable it.

**queue_ms:** Emit `llm_queue_ms` only from verified provider/server timing headers. Otherwise skip numeric score and write `llm_queue_unavailable=1`. No heuristics.

**completion_start_time:** Prefer wrapper auto-capture (`langfuse.openai.AsyncOpenAI`). If missing in traces, set manually on generation update at first token to preserve TTFT fidelity.

**Go/No-Go criteria:** No new validation criteria added. Collect baseline data for 1-2 weeks, then define thresholds for p95 alerts.
