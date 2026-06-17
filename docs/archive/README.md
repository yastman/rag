# Archived Docs

These docs described surfaces that have been archived or superseded as part of the ARCH-10 monolith simplification (issue #2606, epic #2596).

They are kept for historical reference only. Do not link to them from active docs.

## Archived Surfaces

| File | Reason archived |
|---|---|
| `RAG_API.md` | FastAPI voice/RAG API is an optional surface; not in the core path |
| `API_REFERENCE.md` | Describes optional RAG API endpoints |
| `observability/VOICE_TRACING_BASELINE.md` | Voice path is optional/archived |
| `observability/MINIAPP_BROWSER_TRACING_DECISION.md` | Mini App is archived under `archive/mini_app/` |
| `observability/bugsink-setup.md` | BugSink is not part of the active stack |
| `runbooks/LANGFUSE_TRACING_GAPS.md` | Langfuse is optional; core E2E uses product logs |
| `runbooks/MINIO_FAILURE.md` | MinIO is only used with the optional `ml` profile (Langfuse) |
| `review/observability-ui-optional-deps-2431.md` | Audit for archived observability surface |
| `review/kfp-kubernetes-dependency-audit-2450.md` | KFP/k8s is not in the active path |
| `adr/0003-langgraph-voice-text-split.md` | Superseded by ADR-0019 (procedural runtime) |
| `adr/0010-voice-path-create-agent-migration-plan.md` | Voice migration deferred; surface is optional |
| `adr/0017-otel-trace-sampling-roadmap.md` | OTel sampling roadmap deferred; not active |
