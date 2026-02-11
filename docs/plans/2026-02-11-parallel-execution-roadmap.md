# Parallel Execution Roadmap

**Date:** 2026-02-11
**Scope:** 21 issue, 6 параллельных потоков, 3 gate

## Dependency Graph

```
Phase 1 (parallel start)                    Gate               Phase 2              Final
─────────────────────────                   ─────              ───────              ─────

Stream A: Latency-LLM+Embed
  #124 (TTFT variance) ──────────┐
  #106a (BGE quick fix) ─────────┤
                                 ├──→ #101 (re-baseline) ──→ #105 (close parent)
Stream B: Latency-Graph          │         ↓ fail?              ↓
  #108 (rewrite guard) ──────────┤    #102 (contingency)   #106b (ONNX spike)
                                 │
Stream C: Observability          │
  #103 (scores) ─────────────────┤
  #123 (orphan traces) ──────────┘  ← MUST before #101

Stream D: Infra-Perf
  #121 (Redis hardening) ─────────┐
  #122 (Qdrant timeout) ──────────┘──→ (feeds into #101 baseline)

Stream E: Quality-Eval (starts parallel with Phase 1)
  #126 (gold-set) ──→ #127 (LLM-judge, after #103+#123) ──→ #129 (concise)
                                                              #102 (if needed)

Stream F: Infra-Sec (background)
  #71 (security pins) ──┐
  #72 (BuildKit/slim) ──┤──→ #73 (k3s tuning) ──→ #54 (k3s migration)
  #70 (Qdrant snapshots)┘

Background (non-blocking):
  #91 (audit remediation)
  #75 (astream) — after stable baseline
  #74 (PostgresSaver) — after stable baseline
```

## Streams

### Stream A: Latency-LLM+Embed

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 124 | TTFT variance + provider metadata | M | 1-2d | Investigate 28x variance, add LiteLLM callback metadata |
| 106a | BGE quick fix (prewarm/keep-warm) | S | 0.5-1d | Startup prewarm + periodic keep-warm ping |
| 106b | ONNX spike (post-baseline) | L | 2-3d | Research + POC, Phase 2 optimization |

**Depends on:** nothing (starts immediately)
**Blocks:** #101

### Stream B: Latency-Graph

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 108 | Rewrite stop-guard | S-M | 1d | Score-delta threshold, max_rewrites cap |

**Depends on:** nothing (starts immediately)
**Blocks:** #101

### Stream C: Observability

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 103 | Cache hit scores + error spans | M | 1-2d | Partially done (69c2863), finish remaining |
| 123 | Orphan traces + propagate_attributes | S-M | 1d | 82% orphan rate → fix smoke tests + bot entry point |

**Depends on:** nothing (starts immediately)
**Blocks:** #101 (MUST complete before baseline)

### Stream D: Infra-Perf

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 121 | Redis hardening | S | 0.5d | socket_timeout, retry_on_timeout, health_check_interval |
| 122 | Qdrant timeout + FormulaQuery | M | 1d | Explicit timeout + server-side score boosting |

**Depends on:** nothing (starts immediately)
**Blocks:** #101 (results feed into baseline)

### Stream E: Quality-Eval

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 126 | Gold-set dataset | M-L | 2d | Langfuse dataset + experiment SDK flow |
| 127 | LLM-as-a-Judge | M | 1-2d | After #126 + #103/#123 stable |
| 129 | Concise-answer UX | M | 1d | After #127 quality gate |

**Depends on:** #126 starts immediately; #127 after #126 + observability stable
**Blocks:** #129, optionally #102

### Stream F: Infra-Sec (background)

| # | Issue | Effort | Est. | Notes |
|---|-------|--------|------|-------|
| 71 | Security pins/CVE | S | 0.5d | Pin uv images, update minio |
| 72 | BuildKit/slim images | M | 1d | Cache mounts, multi-stage builds |
| 70 | Qdrant snapshots | S | 0.5d | create_snapshot before ingestion |
| 73 | k3s tuning | L | 2-3d | After #71/#72/#70 |

**Depends on:** nothing (starts immediately, background priority)
**Blocks:** #54 (k3s migration)

## Gates

### Gate 1: Re-Baseline (#101)

**Trigger:** ALL of #124, #106a, #108, #103, #123, #121, #122 completed
**Process:**
1. Rebuild + deploy bot with all changes
2. Run 20-30 queries (FAQ + GENERAL + STRUCTURED)
3. Pull Langfuse traces
4. Check Go/No-Go:

| Condition | Target |
|-----------|--------|
| p50 total | < 5s |
| p90 total | < 8s |
| p50 TTFT | < 2s |
| cache hit | < 1.5s |
| no orphan traces | 0% |

**Pass →** close #105, start Phase 2 (#106b ONNX, #75, #74)
**Fail →** trigger #102 (contingency A/B)

### Gate 2: Quality Gate (#127)

**Trigger:** #126 dataset ready + #103/#123 observability stable
**Process:** Run LLM-as-a-Judge on gold-set, calibrate thresholds
**Pass →** #129 (concise-answer), regression gate in CI

### Gate 3: Infra Gate (#73)

**Trigger:** #71 + #72 + #70 completed
**Process:** k3s tuning → #54 migration
**Pass →** Production k3s deployment

## Sequential / Deferred

| # | Issue | Effort | Trigger |
|---|-------|--------|---------|
| 101 | Re-baseline | M (1d) | After Stream A+B+C+D Phase 1 |
| 105 | Close parent | trivial | After #101 pass |
| 102 | Contingency A/B | M (1-2d) | Only if #101 fails |
| 91 | Audit remediation | S-M (1d) | Background, anytime |
| 75 | astream | M-L (2d) | After stable baseline |
| 74 | PostgresSaver | M (1d) | After stable baseline |
| 54 | k3s migration | XL (3-5d) | After Gate 3 + stable baseline |

## Execution Order (recommended)

### Immediate Start (parallel)
- Stream A: #124, #106 (quick fix only)
- Stream B: #108
- Stream C: #103, #123
- Stream D: #121, #122
- Stream E: #126 (gold-set prep)
- Stream F: #71, #72, #70

### After Stream A-D complete
- Gate 1: #101 (re-baseline)

### After Gate 1 pass
- #105 (close), #106b (ONNX), #75, #74

### After Gate 2 (#127)
- #129 (concise-answer)

### After Gate 3 (#73)
- #54 (k3s migration)

## Epics (trackers, NOT executable)
- #58 — RAG Pipeline Modernization
- #130 — Stack Modernization 2026
- #11 — Dependency Dashboard (continuous)

## GitHub Milestones

| Milestone | Issues |
|-----------|--------|
| Stream-A: Latency-LLM+Embed | #124, #106 |
| Stream-B: Latency-Graph | #108 |
| Stream-C: Observability | #103, #123 |
| Stream-D: Infra-Perf | #121, #122 |
| Stream-E: Quality-Eval | #126, #127, #129 |
| Stream-F: Infra-Sec | #71, #72, #70, #73 |
| Gate: Re-Baseline | #101, #105, #102 |
| Deferred: Post-Baseline | #91, #75, #74, #54 |
