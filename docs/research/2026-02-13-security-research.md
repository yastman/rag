# Security & Guardrails Research — 2026 Best Practices

**Date:** 2026-02-13
**Researcher:** Security Research Team
**Scope:** Issues #226 (Prompt Injection), #227 (Content Filtering), Cost Control

---

## Executive Summary

This research identifies production-ready solutions for securing our LangGraph RAG pipeline:

| Category | Recommended Solution | Integration Complexity | Production-Ready |
|----------|---------------------|----------------------|------------------|
| **Prompt Injection** | NeMo Guardrails + Guardrails AI | Medium | ✅ Yes |
| **Content Filtering** | Detoxify (lightweight) | Low | ✅ Yes |
| **Cost Control** | LiteLLM Budget API | Low | ✅ Yes |

**Key Finding:** All solutions support async/await and integrate naturally as LangGraph nodes.

---

## 1. Prompt Injection Defense

### Option A: NeMo Guardrails (NVIDIA) — RECOMMENDED

**Version:** v0.20.0 (January 2026)
**License:** Apache 2.0
**Python Support:** 3.10-3.13
**Async:** ✅ Full async support (`RunnableRails` implements full Runnable Protocol)

#### Strengths
- **LangGraph-native integration** via `RunnableRails`
- **Colang DSL** for defining safety policies (v1.0 and v2.0 syntax)
- **Multi-layer defense:** input rails, dialog rails, execution rails, output rails
- **Production deployment:** FastAPI server, Docker, NeMo Microservice
- **Observability:** OpenTelemetry tracing, structured logging

#### Weaknesses
- **Streaming limitations:** Token-by-token streaming not preserved in LangGraph nodes (produces single chunks after validation)
- **Enterprise license** required for NIM-based deployment

#### Integration Example

```python
from nemoguardrails import RailsConfig
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails
from langgraph.graph import StateGraph, START
from langchain_openai import ChatOpenAI

# Initialize guardrails
config = RailsConfig.from_path("config/guardrails")
guardrails = RunnableRails(config=config, passthrough=True, verbose=True)

# Wrap LLM with guardrails
llm = ChatOpenAI(model="gpt-4o")
runnable_with_guardrails = prompt | (guardrails | llm)

def chatbot_node(state: State):
    result = runnable_with_guardrails.invoke(state)
    return {"messages": [result]}

# Add to LangGraph
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot_node)
graph_builder.add_edge(START, "chatbot")
```

**Colang Policy Example:**
```yaml
# config/guardrails/config.yml
models:
  - type: main
    engine: openai
    model: gpt-4o

rails:
  input:
    flows:
      - jailbreak detection
      - prompt injection check
  output:
    flows:
      - fact checking
      - toxicity filter
```

**Sources:**
- [NeMo Guardrails GitHub](https://github.com/NVIDIA-NeMo/Guardrails)
- [LangGraph Integration Docs](https://docs.nvidia.com/nemo/guardrails/latest/integration/langchain/langgraph-integration.html)
- [NeMo Guardrails 2026 Overview](https://appsecsanta.com/nemo-guardrails)

---

### Option B: Guardrails AI

**Version:** v0.8.0 (Feb 6, 2026)
**License:** Apache 2.0
**Async:** ✅ Full async support (`guard.ainvoke()`, async streaming)

#### Strengths
- **Validator Hub:** Pre-built validators (toxicity, competitor check, PII detection)
- **Structured data generation** via Pydantic models
- **Streaming support:** Both sync/async streaming with real-time validation
- **Deployment:** Standalone service via Flask/Gunicorn

#### Weaknesses
- **No native LangGraph examples** (requires custom wrapper)
- **Less robust policy DSL** compared to Colang

#### Integration Example

```python
from guardrails import Guard, OnFailAction
from guardrails.hub import CompetitorCheck, ToxicLanguage
import asyncio

# Create guard with validators
guard = Guard().use_many(
    CompetitorCheck(competitors=["OpenAI", "Anthropic"], on_fail=OnFailAction.EXCEPTION),
    ToxicLanguage(threshold=0.5, on_fail=OnFailAction.FILTER)
)

async def validate_node(state: State):
    query = state["messages"][-1]["content"]

    # Async validation with streaming
    fragment_generator = await guard(
        model="gpt-4o",
        messages=[{"role": "user", "content": query}],
        stream=True
    )

    validated_chunks = []
    async for chunk in fragment_generator:
        if chunk.validated_output:
            validated_chunks.append(chunk.validated_output)

    return {"validated_query": "".join(validated_chunks)}
```

**Sources:**
- [Guardrails GitHub](https://github.com/guardrails-ai/guardrails)
- [Async Streaming Docs](https://guardrailsai.com/docs/concepts/async_streaming/)
- [LangGraph Example](https://github.com/langchain-ai/langgraph-guardrails-example)

---

### Option C: Multi-Layer Defense (Research)

Recent research shows **character injection attacks** bypass most guardrails with high success rates. Recommendation:

```python
# Defense-in-depth approach
async def secure_generate_node(state: State):
    query = state["query"]

    # Layer 1: Input sanitization (Detoxify)
    if await is_toxic(query):
        return {"error": "Toxic input detected"}

    # Layer 2: Prompt injection detection (NeMo Guardrails)
    validated = await guardrails.ainvoke({"messages": [query]})

    # Layer 3: Output validation (structured schema)
    result = await llm_with_schema.ainvoke(validated)

    # Layer 4: Fact-checking (execution rail)
    verified = await fact_check(result)

    return {"answer": verified}
```

**Sources:**
- [Multi-layer Defense Gist](https://gist.github.com/andreschauer/e0f958c2a279062559ae8306f946b43d)
- [Bypassing Guardrails Research](https://arxiv.org/html/2504.11168v1)
- [Indirect Prompt Injection](https://www.lakera.ai/blog/indirect-prompt-injection)

---

## 2. Content Filtering

### Detoxify — RECOMMENDED

**Version:** Latest (active as of Jan 2026)
**License:** Apache 2.0
**Models:** PyTorch Lightning + Transformers
**GPU Required:** ❌ No (CPU-compatible, lightweight models available)

#### Strengths
- **Lightweight models:** `original-small` (98.28 AUC, ~30-40MB)
- **Multi-category detection:** toxicity, severe toxicity, obscenity, threat, insult, identity hate
- **Fast inference:** 2-4x faster with ONNX runtime (see `speedtoxify`)
- **Easy integration:** Single function call

#### Weaknesses
- **No async API** (but can wrap with `asyncio.to_thread`)
- **Fixed categories** (not customizable without retraining)

#### Integration Example

```python
from detoxify import Detoxify
import asyncio

# Initialize model once (reuse across requests)
tox_model = Detoxify("original-small")

async def toxicity_filter_node(state: State):
    query = state["messages"][-1]["content"]

    # Run in thread pool to avoid blocking
    results = await asyncio.to_thread(tox_model.predict, query)

    # Check threshold
    if results["toxicity"] > 0.7:
        return {
            "error": "Content violates toxicity policy",
            "scores": results
        }

    return {"toxicity_scores": results, "passed": True}

# Add as LangGraph node
graph.add_node("toxicity_filter", toxicity_filter_node)
graph.add_edge("query_preprocessing", "toxicity_filter")
graph.add_edge("toxicity_filter", "retrieve")
```

#### Performance Optimization

```python
# Use ONNX runtime for 2-4x speedup
from speedtoxify import Speedtoxify

tox_model = Speedtoxify("original-small")  # Auto-converts to ONNX
```

#### FastAPI Wrapper

```python
# For microservice deployment
from fastapi import FastAPI
from detoxify import Detoxify

app = FastAPI()
model = Detoxify("original-small")

@app.post("/detoxify/text/")
async def classify_text(text: str):
    results = await asyncio.to_thread(model.predict, text)
    return {"scores": results, "is_toxic": results["toxicity"] > 0.7}
```

**Sources:**
- [Detoxify GitHub](https://github.com/unitaryai/detoxify)
- [Detoxify API Example](https://github.com/Ceraia/Detoxify-API)
- [Speedtoxify (ONNX)](https://github.com/andylolu2/speedtoxify)
- [Building Safer Chatbots](https://medium.com/@datascientist.lakshmi/building-safer-langchain-chatbots-with-guardrails-and-detoxify-a-complete-open-source-guide-52bdae2dde1b)

---

## 3. Cost Control

### LiteLLM Budget & Rate Limiting — RECOMMENDED

**Version:** Latest (2026)
**Features:** Budget tracking, rate limiting, cost attribution
**Async:** ✅ Full async support

#### Budget Scopes

| Scope | Use Case | Configuration |
|-------|----------|---------------|
| **Global Proxy** | Max spend across all calls | `max_budget` in config.yaml |
| **Teams** | Shared budget for team | `POST /team/new` with `max_budget` |
| **Internal Users** | Per-user budget (persists across keys) | `POST /user/new` with `max_budget` |
| **Virtual Keys** | Per-key budget | `POST /key/new` with `max_budget` |
| **End-Users** | Budget for `/chat/completions` user param | `max_end_user_budget` in config |

#### Rate Limiting

```yaml
# config.yaml
litellm_settings:
  # Global end-user budget
  max_end_user_budget: 10.0  # USD per user

general_settings:
  master_key: sk-1234
```

#### Per-User Budget API

```python
import httpx

# Create user with budget
async def create_user_budget(user_id: str, max_budget: float, duration: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://litellm:4000/user/new",
            headers={"Authorization": "Bearer sk-1234"},
            json={
                "user_id": user_id,
                "max_budget": max_budget,
                "budget_duration": duration,  # "30s", "1h", "7d", "30d"
                "tpm_limit": 10000,
                "rpm_limit": 100
            }
        )
        return response.json()

# Usage
await create_user_budget("user_123", max_budget=5.0, duration="7d")
```

#### Integration with Langfuse

```python
from telegram_bot.observability import get_client

async def track_user_cost(user_id: str, trace_id: str):
    # LiteLLM automatically tracks spend
    # Query via API
    async with httpx.AsyncClient() as client:
        spend = await client.get(
            f"http://litellm:4000/user/info?user_id={user_id}",
            headers={"Authorization": "Bearer sk-1234"}
        )

    # Log to Langfuse
    get_client().score(
        trace_id=trace_id,
        name="user_cost",
        value=spend.json()["spend"],
        data_type="NUMERIC"
    )
```

#### Budget Reset

```yaml
# Automatic reset based on duration
budget_duration: "30d"  # Reset every 30 days

# Manual reset via scheduler
proxy_budget_rescheduler_min_time: 600  # Check every 10 min
```

#### Prometheus Monitoring

```yaml
litellm_settings:
  success_callback: ["prometheus"]
  failure_callback: ["prometheus"]
```

**Metrics:**
- `litellm_remaining_team_budget_metric`
- `litellm_provider_remaining_budget_metric`

**Sources:**
- [Budgets & Rate Limits](https://docs.litellm.ai/docs/proxy/users)
- [End-User Budgets](https://docs.litellm.ai/docs/proxy/customers)
- [Budget Manager](https://docs.litellm.ai/docs/budget_manager)
- [Spend Tracking](https://docs.litellm.ai/docs/proxy/cost_tracking)

---

## 4. Integration with Our Stack

### LangGraph Pipeline Architecture

```python
from langgraph.graph import StateGraph, START
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    toxicity_scores: dict
    guardrail_passed: bool
    user_id: str
    budget_remaining: float

# Build secure pipeline
graph = StateGraph(State)

# Pre-processing guardrails
graph.add_node("toxicity_check", toxicity_filter_node)
graph.add_node("prompt_injection_guard", nemo_guardrails_node)

# Core RAG
graph.add_node("retrieve", retrieve_node)
graph.add_node("generate", generate_node)

# Post-processing
graph.add_node("output_validation", output_guardrails_node)
graph.add_node("cost_tracking", cost_tracking_node)

# Edges
graph.add_edge(START, "toxicity_check")
graph.add_conditional_edges(
    "toxicity_check",
    lambda s: "stop" if s.get("error") else "prompt_injection_guard"
)
graph.add_edge("prompt_injection_guard", "retrieve")
graph.add_edge("retrieve", "generate")
graph.add_edge("generate", "output_validation")
graph.add_edge("output_validation", "cost_tracking")
```

### Langfuse Logging

```python
from telegram_bot.observability import observe, get_client

@observe(name="security_pipeline")
async def secure_rag_pipeline(query: str, user_id: str):
    # All guardrail checks logged as spans
    with observe(name="input_validation"):
        toxicity = await toxicity_filter_node({"messages": [query]})
        injection_check = await nemo_guardrails_node({"messages": [query]})

    # Track security scores
    get_client().score(
        name="toxicity_score",
        value=toxicity["toxicity_scores"]["toxicity"],
        data_type="NUMERIC"
    )

    get_client().score(
        name="guardrail_passed",
        value=1 if injection_check["guardrail_passed"] else 0,
        data_type="NUMERIC"
    )
```

### LiteLLM Integration

Our existing `telegram_bot/services/llm_service.py` already uses LiteLLM. Add budget tracking:

```python
# .env
LITELLM_PROXY_URL=http://litellm:4000
LITELLM_MASTER_KEY=sk-1234

# LLM service config
litellm.set_verbose = False
litellm.drop_params = True

# Pass user_id in metadata
response = await litellm.acompletion(
    model="cerebras/llama3.1-8b",
    messages=[...],
    user=user_id,  # Automatically tracked by LiteLLM
    metadata={
        "user_id": user_id,
        "trace_id": langfuse_trace_id
    }
)
```

---

## 5. Recommendations

### For Issue #226: Prompt Injection Defense

**Recommendation:** Implement **NeMo Guardrails** as primary defense + **Guardrails AI** for structured validation.

**Rationale:**
- NeMo's Colang DSL provides fine-grained control over dialog flows
- Guardrails AI complements with pre-built validators
- Both support async and LangGraph integration

**Implementation Steps:**
1. Create `config/guardrails/` with Colang policies
2. Add `nemo_guardrails_node` before `retrieve_node`
3. Add `guardrails_ai_node` for structured output validation after `generate_node`
4. Log all guardrail decisions to Langfuse

**Estimated Effort:** 3-5 days

---

### For Issue #227: Content Filtering

**Recommendation:** Implement **Detoxify** with ONNX optimization.

**Rationale:**
- Lightweight (30-40MB model)
- No GPU required
- High accuracy (98.28 AUC)
- 2-4x faster with speedtoxify

**Implementation Steps:**
1. Add `detoxify==0.5.2` and `speedtoxify` to `pyproject.toml`
2. Create `toxicity_filter_node` in `telegram_bot/graph/nodes/`
3. Add node after `query_preprocessing_node`
4. Log toxicity scores to Langfuse

**Estimated Effort:** 1-2 days

---

### For Cost Control

**Recommendation:** Enable **LiteLLM budget tracking** per user.

**Rationale:**
- Already using LiteLLM
- Zero-code change (configuration only)
- Automatic spend tracking
- Prometheus metrics

**Implementation Steps:**
1. Update `docker-compose.yml` with LiteLLM proxy
2. Add `max_end_user_budget` to config.yaml
3. Pass `user_id` in LLM calls (already done via Telegram user_id)
4. Add Prometheus dashboard for budget monitoring

**Estimated Effort:** 1 day

---

## 6. Security Research Notes

### Current Threats (2025-2026)

1. **Indirect Prompt Injection:** Attacks target RAG documents, not just user input
   - **Mitigation:** Sanitize retrieved documents before LLM generation
   - **Tool:** NeMo execution rails for fact-checking

2. **Character Injection:** Bypass guardrails with Unicode tricks
   - **Mitigation:** Pre-processing module (normalize text before validation)
   - **Research:** [Unveiling disguised toxicity](https://pmc.ncbi.nlm.nih.gov/articles/PMC11015521/)

3. **AML Evasion:** Adversarial ML attacks transfer to black-box models
   - **Mitigation:** Multi-layer defense (don't rely on single guardrail)
   - **Research:** [Bypassing LLM Guardrails](https://mindgard.ai/resources/bypassing-llm-guardrails-character-and-aml-attacks-in-practice)

### Defense-in-Depth Checklist

- [ ] Input sanitization (Detoxify)
- [ ] Prompt injection detection (NeMo Guardrails)
- [ ] Retrieval filtering (sanitize RAG docs)
- [ ] Output validation (Guardrails AI structured schema)
- [ ] Fact-checking (execution rails)
- [ ] Cost limits (LiteLLM budgets)
- [ ] Observability (Langfuse security scores)

---

## 7. Additional Resources

### Documentation
- [Langfuse Security & Guardrails](https://langfuse.com/docs/security-and-guardrails)
- [Prompt Injection Defenses (GitHub)](https://github.com/tldrsec/prompt-injection-defenses)
- [AI Guardrails Types & Tools](https://www.tredence.com/blog/ai-guardrails-types-tools-detection)

### Datasets
- [Jigsaw Toxic Comment Dataset](https://www.kaggle.com/c/jigsaw-toxic-comment-classification-challenge)
- [RealToxicityPrompts](https://allenai.org/data/real-toxicity-prompts)
- [LLM Safety Benchmarks](https://www.promptfoo.dev/blog/top-llm-safety-bias-benchmarks/)

### Tools
- [LLM Guard](https://llm-guard.com/) — Comprehensive security toolkit
- [Rebuff](https://github.com/protectai/rebuff) — Self-hardening prompt injection detector
- [Lakera Guard](https://www.lakera.ai/) — Commercial prompt injection API

---

**End of Report**
