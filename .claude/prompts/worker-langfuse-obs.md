W-LANGFUSE: Add Langfuse observability for SummarizationNode + latency separation

Working dir: /repo
Branch: 154-featmemory-short-term-conversation-memory-redis-checkpointer-+-langmem-sdk (already checked out)
Issue: #154

SKILLS:
- /verification-before-completion before final commit

CONTEXT:
SummarizationNode was just added to graph.py by another worker (respond -> summarize -> END).
The node works functionally but lacks observability integration:
1. No Langfuse tracing on the LLM call inside SummarizationNode
2. No @observe span on the summarize node
3. pipeline_wall_ms in bot.py includes summarization time, inflating latency_total_ms

YOUR TASKS (3 changes, ~20 lines total):

TASK 1: Add CallbackHandler to summarize model (graph.py)
File: telegram_bot/graph/graph.py
Function: _create_summarize_model()
Current code creates ChatOpenAI without Langfuse tracing.
Fix: add langfuse.langchain.CallbackHandler to ChatOpenAI callbacks.
IMPORTANT: CallbackHandler must be created inside the function (not module-level) to respect LANGFUSE_ENABLED.
Pattern:
  from telegram_bot.observability import LANGFUSE_ENABLED
  callbacks = []
  if LANGFUSE_ENABLED:
      from langfuse.langchain import CallbackHandler
      callbacks.append(CallbackHandler())
  return ChatOpenAI(..., callbacks=callbacks)

TASK 2: Wrap summarize node with @observe (graph.py)
File: telegram_bot/graph/graph.py
Where SummarizationNode is added to workflow (around line 131).
Instead of adding summarize directly, wrap it:
  from telegram_bot.observability import observe
  @observe(name="node-summarize", capture_input=False, capture_output=False)
  async def summarize_wrapper(state):
      return await summarize(state)
  workflow.add_node("summarize", summarize_wrapper)
This adds a span "node-summarize" in Langfuse trace, consistent with other nodes (node-classify, node-retrieve, etc.)

TASK 3: Separate user-perceived latency from pipeline total (bot.py)
File: telegram_bot/bot.py
In handle_query() after ainvoke (around line 431):
  result["pipeline_wall_ms"] = (time.perf_counter() - pipeline_start) * 1000
  # User-perceived latency excludes post-respond summarization
  summarize_s = result.get("latency_stages", {}).get("summarize", 0)
  result["user_perceived_wall_ms"] = result["pipeline_wall_ms"] - (summarize_s * 1000)

In handle_voice() same pattern (around line 526).

In _write_langfuse_scores():
  Change: scores["latency_total_ms"] = result.get("user_perceived_wall_ms", total_ms)
  Add: new score for summarize time:
    summarize_ms = result.get("latency_stages", {}).get("summarize", 0) * 1000
    if summarize_ms > 0:
        lf.score_current_trace(name="summarize_ms", value=summarize_ms)

TESTS:
- uv run pytest tests/unit/graph/test_summarize_node.py -v
- uv run pytest tests/integration/test_graph_paths.py -v
- uv run ruff check telegram_bot/graph/graph.py telegram_bot/bot.py
- uv run ruff format telegram_bot/graph/graph.py telegram_bot/bot.py

Source -> test mapping:
  telegram_bot/graph/graph.py -> tests/unit/graph/test_summarize_node.py, tests/integration/test_graph_paths.py
  telegram_bot/bot.py -> tests/unit/test_bot_handlers.py

COMMIT: feat(memory): add Langfuse observability for SummarizationNode #154
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

LOGGING to /repo/logs/worker-langfuse-obs.log (APPEND):
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (after ALL tasks complete):
Execute EXACTLY THREE SEPARATE Bash tool calls (DO NOT combine with && or ;):
Call 1: TMUX="" tmux send-keys -t "claude:Claude" "W-LANGFUSE COMPLETE — check logs/worker-langfuse-obs.log"
Call 2: sleep 1
Call 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
IMPORTANT: Use window NAME, NOT index.
