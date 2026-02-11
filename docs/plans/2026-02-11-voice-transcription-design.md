# Voice Message Transcription — Design

**Date:** 2026-02-11
**Status:** Approved
**Issue:** TBD

## Summary

Add voice message support to the Telegram RAG bot. Users send voice messages, bot transcribes via OpenAI Whisper API (through LiteLLM proxy), then feeds the text into the existing RAG pipeline.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| STT provider | OpenAI Whisper API via LiteLLM proxy | Единый gateway, cost tracking, Langfuse logging, fallbacks |
| Media scope | `F.voice` only | Минимальный скоуп, без video_note/audio |
| Show transcription | Опционально (`SHOW_TRANSCRIPTION=true`) | Пользователь контролирует, видеть ли распознанный текст |
| Architecture | `transcribe_node` — 10-й нод в LangGraph | Langfuse tracing на уровне нода, чистая архитектура |
| New dependencies | 0 | Всё через существующий AsyncOpenAI SDK + LiteLLM proxy |
| Language | `VOICE_LANGUAGE=ru` | Hardcoded hint повышает точность Whisper для русского |

## Architecture

```
Telegram Voice (.ogg)
    ↓
handle_voice()              ← download .ogg → bytes в state
    ↓
build_graph(has_voice=True) ← условный старт графа
    ↓
┌─────────────────────────────────────────┐
│ LangGraph Pipeline (10 nodes)           │
│                                         │
│ START → transcribe → classify → ...     │
│              ↓                          │
│    [SHOW_TRANSCRIPTION → send preview]  │
│              ↓                          │
│    query = transcribed_text             │
│              ↓                          │
│         classify → cache_check → ...    │
│         (всё как раньше)                │
└─────────────────────────────────────────┘

Text messages: START → classify → ... (transcribe_node skipped)
Voice:         START → transcribe → classify → ...
```

## RAGState Extensions

```python
voice_audio: bytes | None       # ogg данные из Telegram
voice_duration_s: float | None  # длительность аудио (message.voice.duration)
stt_text: str | None            # результат транскрипции
stt_duration_ms: float | None   # время STT вызова
```

## Files to Change

| File | Change |
|------|--------|
| `docker/litellm/config.yaml` | +whisper модель в model_list |
| `k8s/base/configmaps/litellm-config.yaml` | +whisper (синхронно!) |
| `telegram_bot/graph/state.py` | +4 поля: voice_audio, voice_duration_s, stt_text, stt_duration_ms |
| `telegram_bot/graph/nodes/transcribe.py` | **Новый.** ~50 LOC. BytesIO → `llm.audio.transcriptions.create()` → text |
| `telegram_bot/graph/graph.py` | +transcribe_node, conditional edge |
| `telegram_bot/graph/edges.py` | +`route_start()`: voice_audio? → transcribe : classify |
| `telegram_bot/bot.py` | +`handle_voice()`, download .ogg, inject в state |
| `telegram_bot/config.py` | +`SHOW_TRANSCRIPTION`, `VOICE_LANGUAGE` |
| `tests/unit/test_transcribe_node.py` | **Новый.** Mock Whisper API |

## transcribe_node (core logic)

```python
@observe(name="transcribe")
async def transcribe_node(state: RAGState) -> dict:
    start = time.perf_counter()
    buf = io.BytesIO(state["voice_audio"])
    buf.name = "voice.ogg"

    transcript = await llm.audio.transcriptions.create(
        model="whisper",           # → LiteLLM → whisper-1
        file=buf,
        language=voice_language,   # "ru"
    )

    stt_duration_ms = (time.perf_counter() - start) * 1000

    # Показать транскрипцию (опционально)
    if show_transcription and state.get("message"):
        await state["message"].answer(f"🎤 _{transcript.text}_", parse_mode="Markdown")

    return {
        "stt_text": transcript.text,
        "stt_duration_ms": stt_duration_ms,
        "query": transcript.text,
        "messages": [{"role": "user", "content": transcript.text}],
    }
```

## handle_voice() (bot handler)

```python
async def handle_voice(self, message: Message):
    voice = message.voice
    file = await self.bot.get_file(voice.file_id)
    buf = io.BytesIO()
    await self.bot.download_file(file.file_path, destination=buf)

    state = make_initial_state(
        user_id=message.from_user.id,
        session_id=make_session_id("chat", message.chat.id),
        query="",  # будет заполнено transcribe_node
    )
    state["voice_audio"] = buf.getvalue()
    state["voice_duration_s"] = voice.duration

    graph = build_graph(...)  # same as handle_query
    result = await graph.ainvoke(state)
    _write_langfuse_scores(lf, result)
```

## LiteLLM Config Addition

```yaml
# docker/litellm/config.yaml — добавить в model_list:
- model_name: whisper
  litellm_params:
    model: whisper-1
    api_key: os.environ/OPENAI_API_KEY
  model_info:
    mode: audio_transcription
```

## Error Handling

| Scenario | Action |
|----------|--------|
| Whisper API timeout/error | "Не удалось распознать голосовое сообщение. Попробуйте отправить текстом." |
| Empty transcription | "Голосовое сообщение не содержит речи." |
| File too large (>25MB) | Reject before API call: "Голосовое сообщение слишком длинное." |

## Langfuse Scores

| Score | Type | Description |
|-------|------|-------------|
| `stt_duration_ms` | NUMERIC | Время STT вызова |
| `voice_duration_s` | NUMERIC | Длительность аудио |
| `input_type` | CATEGORICAL | "voice" / "text" |

LiteLLM автоматически логирует cost Whisper-вызова в Langfuse.

## Technical Notes

- Telegram voice = `.ogg` (Opus codec) — Whisper API принимает напрямую
- `io.BytesIO` — in-memory, без tmp-файлов на диске
- `buf.name = "voice.ogg"` — OpenAI SDK требует имя файла для определения формата
- `language="ru"` — hint повышает точность для русского языка
- Whisper API limit: 25 MB (~16 мин голосового сообщения при Telegram quality)
- Telegram voice limit: ~20 MB (практический лимит Telegram Bot API)

## Research Sources

- LiteLLM audio transcription docs: `docs.litellm.ai/docs/audio_transcription`
- aiogram 3 voice handler: StackOverflow #77756933
- OpenAI Whisper best practices 2026: `thelinuxcode.com/openai-whisper-in-practice-2026`
- LangGraph voice agent pattern: Medium `@vis_44`
