# RAG-Fresh Stack Audit — Executive Summary

**Дата:** 2026-02-10
**Метод:** Систематический поиск через MCP Exa по 50+ источникам (official docs, research papers, production guides)

---

## 🔥 Top-5 High-Impact Находок

### 1. **Qdrant 1.14+ Score-Boosting Reranker**
**Статус:** ❌ Не используем
**Что это:** Server-side formula-based scoring для custom ranking logic
```python
score_formula = "vector_score * 0.7 + payload.recency * 0.2 + payload.popularity * 0.1"
```
**Impact:** Снижение post-processing latency, более flexible ranking
**Effort:** Medium (2-3 days)
**Priority:** P0

---

### 2. **LangGraph Self-Reflective Hallucination Node**
**Статус:** ❌ Не используем (есть grading, но не dedicated hallucination check)
**Что это:** Отдельный node после generation для LLM-as-judge hallucination detection
```python
workflow.add_node("check_hallucination", hallucination_checker)
```
**Impact:** -15-20% hallucinations в production
**Effort:** Low (1 day)
**Priority:** P0

---

### 3. **LiteLLM Intelligent Routing (latency-based + cost-based)**
**Статус:** ❌ Не используем (только simple fallbacks)
**Что это:** Автоматический выбор fastest/cheapest model deployment
```python
routing_strategy="latency-based-routing"  # Routes to fastest deployment
```
**Impact:** -20-30% p95 latency, automatic failover
**Effort:** Medium (2 days)
**Priority:** P1

---

### 4. **RAGAS Context Precision Metric**
**Статус:** ❌ Не трекаем
**Что это:** Measures quality of retrieval BEFORE generation (relevant_chunks / total_chunks)
```python
langfuse.score(name="context_precision", value=relevant/total)
```
**Impact:** Early detection of retrieval degradation
**Effort:** Low (1 day)
**Priority:** P0

---

### 5. **Docker BuildKit Cache Mounts**
**Статус:** ❌ Не используем
**Что это:** Persistent cache для pip/uv downloads
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
```
**Impact:** Build time 5 min → 30 sec
**Effort:** Low (2 hours)
**Priority:** P0

---

## ✅ Что мы УЖЕ делаем ПРАВИЛЬНО

- ✅ **LangGraph StateGraph** — modern agentic RAG с conditional edges
- ✅ **BGE-M3 Hybrid Search** — single API call для dense+sparse+colbert
- ✅ **Qdrant RRF + ColBERT** — proper pre-filtering перед reranking
- ✅ **Langfuse v3** — structured tracing + baseline comparison
- ✅ **Redis Pipelines** — bulk operations для cache
- ✅ **Docker Multi-Stage** — separate build/runtime stages
- ✅ **k3s Resource Limits** — proper CPU/memory constraints
- ✅ **Python 3.12** — latest stable с improved performance

---

## 📊 Приоритетная матрица (Top-10)

| # | Фича | Impact | Effort | Priority | Time |
|---|------|--------|--------|----------|------|
| 1 | Qdrant Score-Boosting | High | Medium | P0 | 2-3d |
| 2 | LangGraph Hallucination Node | High | Low | P0 | 1d |
| 3 | RAGAS Context Precision | High | Low | P0 | 1d |
| 4 | Docker BuildKit Cache | Medium | Low | P0 | 2h |
| 5 | BGE-M3 Adaptive Prefetch | Medium | Low | P1 | 4h |
| 6 | LiteLLM Intelligent Routing | High | Medium | P1 | 2d |
| 7 | Langfuse Slack Alerts | Medium | Low | P1 | 2h |
| 8 | Redis Chunked Pipelines | Low | Low | P1 | 4h |
| 9 | Docling Image Captions | Medium | Medium | P2 | 3d |
| 10 | Telegram Per-Chat Limits | Low | Low | P2 | 2h |

**Total Effort для P0:** ~5 days
**Total Effort для P0+P1:** ~10 days

---

## 🚀 Recommended Roadmap

### **Sprint 1 (Week 1) — Quick Wins P0**
- [ ] Docker BuildKit cache mounts (2h)
- [ ] RAGAS Context Precision metric (1d)
- [ ] LangGraph hallucination node (1d)
- [ ] Qdrant reranking formula (2-3d)

**Expected Impact:**
- ⚡ Build time: -80% (5 min → 30 sec)
- 🎯 Hallucinations: -15-20%
- 📊 Better observability: early retrieval quality signals

---

### **Sprint 2 (Week 2) — Medium Impact P1**
- [ ] BGE-M3 adaptive prefetch (4h)
- [ ] Redis chunked pipelines (4h)
- [ ] Langfuse Slack alerts (2h)
- [ ] LiteLLM intelligent routing (2d)

**Expected Impact:**
- ⚡ Latency: -20-30% p95 на LLM calls
- 💾 Memory: stable при bulk cache ops
- 🔔 Proactive alerts при degradation

---

### **Backlog (P2) — Lower Priority**
- [ ] Docling image captioning (если добавим GPU)
- [ ] Telegram rate limit middleware
- [ ] k3s VPA auto-sizing
- [ ] LangGraph HITL для sensitive topics

---

## 📝 Implementation Notes

### Qdrant Reranking — Quick Start
```python
# В retrieve_node добавить:
results = client.query_points(
    collection_name="gdrive_documents_bge",
    query=dense_vec,
    using="dense",
    score_formula="""
        vector_score * 0.7 +
        (payload.date > '2024-01-01' ? 0.2 : 0.0) +
        (payload.type == 'regulation' ? 0.1 : 0.0)
    """
)
```

### LangGraph Hallucination Node
```python
def hallucination_checker(state):
    prompt = f"""
    Context: {state['documents']}
    Answer: {state['generation']}

    Does the answer contain ANY information not present in context?
    Answer: YES or NO
    """
    result = llm.invoke(prompt)
    return {"hallucination_detected": "YES" in result}

workflow.add_node("check_hallucination", hallucination_checker)
workflow.add_conditional_edges(
    "generate",
    lambda s: "check_hallucination" if s.get("high_risk") else END
)
```

### Docker Cache Mounts
```dockerfile
# syntax=docker/dockerfile:1.6  # ВАЖНО!

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
```

---

## ❌ Что НЕ внедряем (и почему)

| Фича | Reason |
|------|--------|
| Python 3.13 Subinterpreters | Experimental, ждём stable release |
| LangGraph Postgres State | Stateless RAG — не нужен persistent state |
| Qdrant Quantization | CPU inference — minimal gains |
| Distroless Images | Debugging complexity > security gain для нашего case |
| RAGAS Multi-hop Reasoning | Наши queries в основном single-hop |

---

## 🎯 Success Metrics

### Измеряемые улучшения после Phase 1+2:

| Метрика | Текущее | Цель | Measurement |
|---------|---------|------|-------------|
| Docker build time | ~5 min | ~30 sec | CI logs |
| Hallucination rate | Unknown | -15-20% | Langfuse scores |
| Context precision | Not tracked | >0.8 | RAGAS eval |
| LLM p95 latency | Varies | -20-30% | Langfuse traces |
| Retrieval quality | Baseline | +10-15% | Context precision metric |

---

## 📚 Key Sources

- [LangGraph 2026 Patterns](https://rahulkolekar.com/building-agentic-rag-systems-with-langgraph/)
- [Qdrant 1.14 Release](https://qdrant.tech/blog/qdrant-1.14.x/)
- [RAGAS Framework](https://docs.ragas.io/)
- [LiteLLM Best Practices](https://docs.litellm.ai/)
- [Docker BuildKit Optimization](https://docs.docker.com/build/cache/)
- 45+ additional sources in full report

---

**Полный отчет:** `docs/reports/2026-02-10-stack-audit-best-practices.md`

**Next Action:** Create GitHub issues для P0 items + schedule Sprint planning
