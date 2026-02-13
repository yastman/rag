# MCP, Graph RAG & Agent Patterns Research — 2026 Best Practices

**Research Date:** 2026-02-13
**Researcher:** MCP & Graph RAG Specialist
**Context:** Issue #232 (MCP), #234 (Graph RAG), #228 (HITL)

---

## Executive Summary

This research synthesizes the state of MCP servers, Graph RAG frameworks, and LangGraph human-in-the-loop patterns as of February 2026. Key findings:

- **MCP:** FastMCP 3.0 is production-ready with 70% market share; official SDK provides low-level control
- **Graph RAG:** LightRAG offers 6,000x cost reduction vs Microsoft GraphRAG with minimal accuracy tradeoff
- **HITL:** LangGraph `interrupt()` + Redis checkpointer enables Telegram callback integration
- **A2A:** Google's Agent2Agent protocol (v0.3) is gaining traction but still early for production

---

## 1. MCP Server Implementation

### 1.1 Official Python SDK

**Version:** [mcp 1.7.1](https://pypi.org/project/mcp/1.7.1/) (as of Feb 2026)

**Repository:** [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)

**Documentation:** [Official MCP Python SDK Docs](https://modelcontextprotocol.github.io/python-sdk/)

**Transport Options:**
- **stdio:** For local CLI tools (e.g., Claude Desktop)
- **SSE (Server-Sent Events):** For web-based clients
- **Streamable HTTP:** For production REST APIs

**Code Example (Wrapping RAG Tools):**

```python
from mcp import Server, Tool
from langchain.chains import RetrievalQA
from langchain_community.vectorstores import Chroma

# Initialize MCP server
server = Server("rag-mcp-server")

# Define RAG tool
@server.tool()
async def search_documents(query: str) -> str:
    """Search indexed documents using RAG."""
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=vector_store.as_retriever(),
        return_source_documents=True
    )
    result = qa_chain({"query": query})
    return result["result"]

# Run server
if __name__ == "__main__":
    server.run()
```

**Auth/Access Control:**
- FastMCP 3.0 introduced **authorization controls** (Jan 19, 2026)
- Official SDK supports custom middleware for auth
- Pattern: Sign "Agent Cards" (JSON capability discovery) for trusted servers

**Resources:**
- [RAG MCP Server Tutorial](https://medium.com/data-science-in-your-pocket/rag-mcp-server-tutorial-89badff90c00)
- [Integrating Agentic RAG with MCP](https://becomingahacker.org/integrating-agentic-rag-with-mcp-servers-technical-implementation-guide-1aba8fd4e442)
- [MCP Server for RAG (Qdrant)](https://lobehub.com/mcp/amornpan-py-mcp-qdrant-rag)

---

### 1.2 FastMCP

**Version:** [3.0.0b2](https://pypi.org/project/fastmcp/) (Feb 7, 2026 pre-release) | Stable: [v2.x](https://github.com/jlowin/fastmcp)

**Repository:** [jlowin/fastmcp](https://github.com/jlowin/fastmcp)

**Market Share:** 70% of MCP servers across all languages (as of Feb 2026)

**Key Features (v3.0):**
- Component versioning
- Authorization controls
- OpenTelemetry integration (observability!)
- Multiple provider types (KV stores, vector DBs, etc.)

**Code Example:**

```python
from fastmcp import FastMCP

mcp = FastMCP("my-rag-server")

@mcp.tool()
def search_qdrant(query: str, collection: str = "legal_documents") -> dict:
    """Search Qdrant collection with hybrid retrieval."""
    # Your Qdrant search logic here
    results = qdrant_client.search(
        collection_name=collection,
        query_vector=embeddings.encode(query),
        limit=5
    )
    return {"results": [r.payload for r in results]}

if __name__ == "__main__":
    mcp.run()
```

**When to Use FastMCP:**
- Rapid prototyping (high-level abstractions)
- Standard RAG/tool wrapping patterns
- Need OpenTelemetry out-of-the-box

**When to Use Official SDK:**
- Custom transport protocols
- Low-level control over MCP lifecycle
- Integration with existing frameworks (LangChain, LlamaIndex)

**Resources:**
- [FastMCP Tutorial (2026)](https://www.firecrawl.dev/blog/fastmcp-tutorial-building-mcp-servers-python)
- [How to Create MCP Server in Python](https://gofastmcp.com/tutorials/create-mcp-server)
- [FastMCP PyPI](https://pypi.org/project/fastmcp/)

---

### 1.3 Client Integration in LangGraph

**Pattern:** MCP Client → LangGraph Tool Node

```python
from mcp.client import ClientSession, StdioServerParameters
from langchain.tools import StructuredTool
from langgraph.prebuilt import ToolNode

# Connect to MCP server
async with ClientSession(StdioServerParameters(command="python", args=["mcp_server.py"])) as session:
    await session.initialize()

    # Convert MCP tools to LangChain tools
    tools = []
    for tool_name in session.list_tools():
        tool_def = session.get_tool(tool_name)
        tools.append(StructuredTool.from_function(
            func=lambda q: session.call_tool(tool_name, {"query": q}),
            name=tool_name,
            description=tool_def["description"]
        ))

    # Use in LangGraph
    tool_node = ToolNode(tools)
```

**Resources:**
- [Build a RAG MCP Server](https://medium.com/@matteo28/how-to-build-a-rag-mcp-server-3c514a265207)
- [RAG vs MCP Guide](https://www.digitalocean.com/community/tutorials/engineers-guide-rag-vs-mcp-llms)

---

### 1.4 Recommendation for Issue #232

**Approach:** Dual implementation strategy

1. **FastMCP for RAG Tools (Primary)**
   - Wrap existing Qdrant search, reranker, cache layers as MCP tools
   - Use FastMCP 2.x (stable) initially, migrate to 3.0 when stable
   - Enable OpenTelemetry → Langfuse integration

2. **Official SDK for Custom Integrations**
   - Reserve for future needs (SSE transport for web UI, custom auth)
   - Use for debugging/low-level control

**Next Steps:**
- Prototype RAG MCP server with FastMCP wrapping `search_documents`, `rerank_results`, `cache_lookup`
- Test integration in LangGraph graph (new `mcp_tools` node)
- Deploy as separate service (Docker container, stdio transport)

---

## 2. Graph RAG

### 2.1 Framework Comparison

| Feature | LightRAG | Microsoft GraphRAG | nano-graphrag |
|---------|----------|-------------------|---------------|
| **Cost/Query** | <100 tokens, 1 API call | `communities × tokens_per_community` (massive) | Similar to LightRAG |
| **Speed** | ~20-30ms faster than RAG | Slower (community clustering) | Fast (lightweight) |
| **Accuracy** | High (dual-level retrieval) | 10% better on relational QA | Comparable to LightRAG |
| **Incremental Updates** | ~50% faster (graph union) | Expensive (rebuild communities) | Fast (no clustering) |
| **Production Readiness** | ✅ (EMNLP 2025 paper) | ⚠️ (high infra costs) | ✅ (simple, hackable) |
| **Use Case** | Balanced speed + depth | Global thematic queries | Learning, prototyping |
| **Storage** | Neo4j, PG+AGE, in-memory | Azure Cosmos DB, Neo4j | Flexible |
| **Python Package** | [lightrag-hku](https://pypi.org/project/lightrag-hku/) | [graphrag](https://pypi.org/project/graphrag/) | [nano-graphrag](https://github.com/gusye1234/nano-graphrag) |

**Resources:**
- [GraphRAG vs LightRAG Breakdown](https://lilys.ai/en/notes/get-your-first-users-20260207/graphrag-lightrag-comparison)
- [LightRAG Official Repo](https://github.com/HKUDS/LightRAG)
- [nano-graphrag GitHub](https://github.com/gusye1234/nano-graphrag)
- [Comparative Analysis](https://www.maargasystems.com/2025/05/12/understanding-graphrag-vs-lightrag-a-comparative-analysis-for-enhanced-knowledge-retrieval/)

---

### 2.2 LightRAG Architecture

**Key Innovation:** Dual-level retrieval (low + high)

```
Document → Entity/Relation Extraction → Knowledge Graph
                ↓
         [LOW level: entities]
         [HIGH level: relations]
                ↓
Query → Retrieve subgraphs → Merge neighbors → Multi-hop reasoning
```

**Storage Requirements (Production):**
- **KV_STORAGE:** LLM cache, text chunks, document metadata
- **VECTOR_STORAGE:** Entity vectors, relation vectors, chunk vectors
- **GRAPH_STORAGE:** Neo4j (recommended) > PostgreSQL + AGE plugin

**Deployment:**
- 16GB+ RAM, GPU for embeddings
- 1-2 weeks setup (integration + testing + team training)
- Docker deployment supported

**Resources:**
- [LightRAG Setup Guide](https://mernstackdev.com/lightrag-setup/)
- [Analytics Vidhya Tutorial](https://www.analyticsvidhya.com/blog/2025/01/lightrag/)

---

### 2.3 Hybrid Retrieval Pattern (Vector + Graph)

**Router Design:** Binary classification (when to use graph vs vector)

```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Train on (query, label) pairs: "lexical_search" vs "vector_search" vs "graph_search"
router_model = AutoModelForSequenceClassification.from_pretrained("roberta-base", num_labels=3)

def route_query(query: str) -> str:
    """Route query to vector, lexical, or graph search."""
    inputs = tokenizer(query, return_tensors="pt")
    logits = router_model(**inputs).logits
    prediction = logits.argmax(dim=-1).item()
    return ["lexical", "vector", "graph"][prediction]

# In LangGraph
if route_query(state["query"]) == "graph":
    return "graph_retrieve_node"
else:
    return "vector_retrieve_node"
```

**Qdrant + Graph Integration:**
- **Phase 1:** Qdrant vector search → candidate documents
- **Phase 2:** Neo4j graph expansion → related entities/docs
- **Phase 3:** RRF fusion of results

**Example:** [GraphRAG Hybrid (Neo4j + Qdrant)](https://github.com/rileylemm/graphrag-hybrid)

**Qdrant Hybrid Query API:**
```python
# Multi-stage retrieval with prefetch
results = qdrant_client.query(
    collection_name="docs",
    query=QueryRequest(
        prefetch=[
            Prefetch(
                query=sparse_vector,
                using="sparse",
                limit=100
            )
        ],
        query=dense_vector,
        limit=10
    )
)
```

**Resources:**
- [Qdrant Hybrid Search Guide](https://qdrant.tech/articles/hybrid-search/)
- [GraphRAG with Qdrant and Neo4j](https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/)
- [Router Pattern Tutorial](https://huggingface.co/blog/timofeyk/hybrid-ecommerce-search-roberta-classifier)

---

### 2.4 Recommendation for Issue #234

**Phased Approach:**

**Phase 1 (Q1 2026):** Proof-of-concept with nano-graphrag
- Lightweight, easy to understand codebase
- Test on small subset (Bulgarian property docs)
- Validate router pattern (graph vs vector)

**Phase 2 (Q2 2026):** Production LightRAG
- Deploy Neo4j for graph storage
- Integrate with existing Qdrant vector search
- Router: RoBERTa classifier trained on query logs

**Phase 3 (Q3 2026):** Hybrid pipeline
- LangGraph conditional edges based on router
- Combine Qdrant dense/sparse + Neo4j graph expansion
- Evaluate with RAGAS (faithfulness, relevance)

**When to Use Graph vs Vector:**
- **Graph:** Multi-hop reasoning ("влияние субъекта А на субъекта Б через субъект В")
- **Vector:** Semantic similarity, single-hop retrieval

---

## 3. Human-in-the-Loop (LangGraph)

### 3.1 LangGraph `interrupt()` API

**Core Mechanism:**
- Pause graph execution at any node
- Save state snapshot to checkpointer (Redis, Postgres, etc.)
- Resume with user input via `Command(resume=...)`

**Two Approaches:**

#### Static Interrupts (compile-time)

```python
from langgraph.graph import StateGraph

graph = StateGraph(State)
graph.add_node("research", research_node)
graph.add_node("decide", decide_node)
graph.add_edge("research", "decide")

# Interrupt BEFORE decide_node
app = graph.compile(
    checkpointer=redis_checkpointer,
    interrupt_before=["decide"]
)

# Later: resume with user input
app.invoke(Command(resume="approved"), config={"thread_id": "123"})
```

#### Dynamic Interrupts (runtime)

```python
from langgraph.types import interrupt

def agent_node(state: State):
    # ... do some work ...

    if state["needs_approval"]:
        # Pause and request user input
        user_input = interrupt("Do you approve this action?")
        state["user_approval"] = user_input

    return state
```

**Resources:**
- [LangChain: How to wait for user input](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/)
- [Making HITL Easier with interrupt()](https://blog.langchain.com/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt/)
- [LangGraph interrupt() Tutorial](https://medium.com/@areebahmed575/langgraphs-interrupt-function-the-simpler-way-to-build-human-in-the-loop-agents-faef98891a92)

---

### 3.2 Telegram Callback Integration Pattern

**Architecture:**
1. LangGraph graph interrupts → saves to Redis checkpointer
2. Bot sends Telegram inline keyboard (callback buttons)
3. User clicks button → callback_query handler
4. Resume graph with `Command(resume=...)`

**Code Example:**

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from langgraph.checkpoint.redis import AsyncRedisSaver
from langgraph.graph import StateGraph
from langgraph.types import Command

# Setup checkpointer
redis_checkpointer = AsyncRedisSaver.from_conn_string("redis://localhost:6379")

# Graph with interrupt
graph = StateGraph(State)
graph.add_node("generate", generate_node)
app = graph.compile(
    checkpointer=redis_checkpointer,
    interrupt_before=["generate"]  # Ask user before generating
)

# Telegram bot handler
async def handle_query(update, context):
    user_id = update.effective_user.id
    query = update.message.text

    # Invoke graph (will interrupt)
    thread_id = f"user_{user_id}"
    state = await app.ainvoke({"query": query}, {"thread_id": thread_id})

    # Send approval buttons
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve:{thread_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"reject:{thread_id}")]
    ]
    await update.message.reply_text(
        "Ready to generate. Approve?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Callback handler
async def handle_callback(update, context):
    query = update.callback_query
    action, thread_id = query.data.split(":")

    # Resume graph
    if action == "approve":
        result = await app.ainvoke(
            Command(resume="approved"),
            {"thread_id": thread_id}
        )
        await query.message.reply_text(result["output"])
    else:
        await query.message.reply_text("Generation cancelled.")
```

**Resources:**
- [LangGraph Telegram Bot Example](https://github.com/francescofano/langgraph-telegram-bot)
- [Architecting HITL Agents](https://medium.com/data-science-collective/architecting-human-in-the-loop-agents-interrupts-persistence-and-state-management-in-langgraph-fa36c9663d6f)

---

### 3.3 State Persistence (Redis Checkpointer)

**Package:** [langgraph-checkpoint-redis](https://pypi.org/project/langgraph-checkpoint-redis/)

**Implementations:**
- `RedisSaver` / `AsyncRedisSaver`: Full checkpoint history
- `ShallowRedisSaver` / `AsyncShallowRedisSaver`: Latest checkpoint only (lower memory)

**Setup:**

```python
from langgraph.checkpoint.redis import AsyncRedisSaver

# Initialize checkpointer
checkpointer = AsyncRedisSaver.from_conn_string(
    "redis://localhost:6379",
    ttl=86400  # 24h TTL for checkpoints
)

# Compile graph
app = graph.compile(checkpointer=checkpointer)

# Thread ID = conversation persistence key
config = {
    "thread_id": f"user_{user_id}",
    "checkpoint_ns": "telegram_bot"
}
```

**Checkpoint Structure:**
- `values`: Current state (query, documents, output, etc.)
- `next`: Next nodes to execute
- `config`: Thread ID, checkpoint namespace
- `tasks`: Pending execution tasks
- `metadata`: Custom data (user_id, session_id, etc.)

**Timeout Handling:**
- Set Redis TTL on checkpoints (e.g., 1 hour for approval)
- Implement cleanup task: delete stale threads
- Notify user if checkpoint expired

**Resources:**
- [Redis Developer: LangGraph Redis](https://github.com/redis-developer/langgraph-redis)
- [LangGraph & Redis Blog](https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence/)
- [Agent Memory with LangGraph and Redis](https://redis.io/tutorials/what-is-agent-memory-example-using-langgraph-and-redis/)

---

### 3.4 Recommendation for Issue #228

**Implementation Plan:**

1. **Add Redis Checkpointer to Graph**
   - Install `langgraph-checkpoint-redis`
   - Replace in-memory checkpointer with `AsyncRedisSaver`
   - Set TTL = 1 hour for approval checkpoints

2. **Add Interrupt Before Generate Node**
   - Static interrupt: `interrupt_before=["generate"]`
   - Or dynamic: `interrupt()` in `grade_node` if confidence < 0.7

3. **Telegram Callback Buttons**
   - Show retrieved context + proposed answer
   - Buttons: "✅ Send", "✏️ Rewrite", "❌ Cancel"

4. **Resume Logic**
   - "Send" → `Command(resume="approved")`
   - "Rewrite" → `Command(resume="rewrite", update={"query": new_query})`
   - "Cancel" → Delete checkpoint

**Use Cases:**
- Low confidence answers (grade_score < 0.7)
- Sensitive queries (legal advice)
- User explicitly requests review (`/ask_with_review`)

---

## 4. Agent-to-Agent (A2A) Protocol

### 4.1 Google A2A Protocol Overview

**Version:** 0.3 (released July 31, 2025)

**Governance:** Originally Google, now Linux Foundation

**Adoption:** 150+ organizations (as of Feb 2026)

**Key Features (v0.3):**
- **gRPC support** (in addition to HTTP)
- **Signed security cards** (cryptographic agent identity)
- **Extended Python SDK** support
- **Agent Cards:** JSON capability discovery
- **Task Management:** Defined lifecycle states (pending, running, completed, failed)
- **Agent Collaboration:** Context + instruction sharing
- **UI Negotiation:** Adapts to different client capabilities

**Resources:**
- [A2A Protocol Upgrade Announcement](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade)
- [Announcing A2A](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- [Linux Foundation Launch](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)
- [A2A Official Site](https://a2a-protocol.org/latest/)
- [ADK with A2A](https://google.github.io/adk-docs/a2a/)

---

### 4.2 Relationship to MCP

**Complementary, Not Competing:**
- **MCP:** Connects agents to **tools/context** (server → client pattern)
- **A2A:** Connects agents to **other agents** (peer-to-peer pattern)

**Use Cases:**
- **MCP:** RAG tools, database queries, API calls
- **A2A:** Multi-agent orchestration, task delegation, hierarchical agents

**Example Architecture:**

```
User → Agent A (orchestrator)
          ↓ (A2A)
       Agent B (specialist) ← (MCP) → RAG Server
          ↓ (A2A)
       Agent C (writer)
```

**Resources:**
- [What is A2A Protocol? (IBM)](https://www.ibm.com/think/topics/agent2agent-protocol)
- [A2A Purchasing Concierge Codelab](https://codelabs.developers.google.com/intro-a2a-purchasing-concierge)

---

### 4.3 Maturity Assessment

**Production Readiness:** ⚠️ Early Adopter Phase

| Aspect | Status |
|--------|--------|
| Specification Stability | 🟡 v0.3 (still evolving) |
| Python SDK | 🟢 Available (ADK) |
| Industry Adoption | 🟡 150+ orgs, few production cases |
| Documentation | 🟡 Growing, but scattered |
| Tooling/Ecosystem | 🔴 Limited (no Langfuse/Langsmith integration yet) |
| Security | 🟢 Signed cards (v0.3) |

**Comparison to MCP:**
- MCP: 70% of servers use FastMCP → **mature ecosystem**
- A2A: 150 orgs signed up → **early momentum, unproven**

**Watch for:**
- Production case studies (2026 Q2-Q3)
- LangChain/LlamaIndex integration
- Observability tooling (Langfuse, etc.)

---

### 4.4 Recommendation

**Short-term (2026 Q1-Q2):** Monitor, don't implement

- A2A is promising but not production-ready for our use case
- MCP solves our immediate needs (RAG tools, context)
- Focus on MCP implementation first

**Medium-term (2026 Q3-Q4):** Evaluate for multi-agent workflows

- If we build multi-bot orchestration (e.g., PropertyBot → LegalBot → SummaryBot)
- A2A could enable bot-to-bot task delegation
- Wait for v1.0 and production case studies

**Alternative:** LangGraph multi-agent patterns (built-in)
- Use LangGraph conditional edges for agent routing
- State-based handoffs (no protocol overhead)
- Better observability (Langfuse integration)

---

## Summary of Recommendations

| Component | Recommended Approach | Priority | ETA |
|-----------|---------------------|----------|-----|
| **MCP Server** | FastMCP 2.x wrapping RAG tools | 🔴 High | 2026-03 |
| **Graph RAG** | Phased: nano-graphrag → LightRAG + Neo4j | 🟡 Medium | 2026-06 |
| **HITL** | LangGraph interrupt + Redis + Telegram callbacks | 🔴 High | 2026-03 |
| **A2A** | Monitor developments, revisit in Q3 | 🟢 Low | 2026-09+ |

---

## References

### MCP
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Documentation](https://modelcontextprotocol.github.io/python-sdk/)
- [RAG MCP Tutorial](https://medium.com/data-science-in-your-pocket/rag-mcp-server-tutorial-89badff90c00)

### Graph RAG
- [LightRAG Paper (EMNLP 2025)](https://github.com/HKUDS/LightRAG)
- [GraphRAG vs LightRAG Comparison](https://lilys.ai/en/notes/get-your-first-users-20260207/graphrag-lightrag-comparison)
- [nano-graphrag](https://github.com/gusye1234/nano-graphrag)
- [Qdrant + Neo4j GraphRAG](https://qdrant.tech/documentation/examples/graphrag-qdrant-neo4j/)

### LangGraph HITL
- [LangGraph interrupt() Guide](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/)
- [Redis Checkpointer](https://github.com/redis-developer/langgraph-redis)
- [Telegram Bot Example](https://github.com/francescofano/langgraph-telegram-bot)

### A2A
- [A2A Protocol Site](https://a2a-protocol.org/latest/)
- [Google Cloud A2A Announcement](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade)
- [Linux Foundation Launch](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)

---

**End of Research Report**
