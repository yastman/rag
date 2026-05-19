# Langfuse trace coverage audit — 2026-05-19

Source: full audit of Langfuse instrumentation across the monorepo against
Langfuse Python SDK v3 docs (`@observe`, `propagate_attributes`,
`start_as_current_observation`, `langfuse.openai`, `langfuse.langchain.CallbackHandler`,
prompt-to-generation linking, masking).

Every file in this directory is a **ready-to-paste body for a separate GitHub issue**.
Drafts are scoped so each maps to one focused PR.

## Out of scope (already tracked)

- #1543 — contextualize batch loop and ColBERT span gaps.
- #1367 — closed; covered the original 7 zero-coverage modules.
- #1253 — trace context propagation between RAG pipeline and SDK agent graphs.
- #1416 — full self-hosted observability stack (Alloy/Loki/Grafana/Bugsink/Uptime Kuma).
- #1369 — closed; duplicate detect-agent-intent / WARNING level fixes.

## Drafts

| # | File | Priority | One-liner |
|---|------|----------|-----------|
| 01 | `01-miniapp-api.md` | P0 | Mini App FastAPI has zero Langfuse spans; conversion funnel invisible. |
| 02 | `02-hyde-generate-hypothetical-document.md` | P0 | `HyDEGenerator.generate_hypothetical_document` produces orphan generation. |
| 03 | `03-query-analyzer-analyze.md` | P0 | `QueryAnalyzer.analyze` produces orphan generation. |
| 04 | `04-llm-service-public-methods.md` | P0 | `LLMService.{generate_answer, stream_answer, generate}` produce orphan generations. |
| 05 | `05-session-summary-worker-generate-summary.md` | P0 | `SessionSummaryWorker._generate_summary` not wrapped in @observe. |
| 06 | `06-background-jobs-spans.md` | P1 | Lead-scoring sync, hot-lead notifier, and 2 nurturing-scheduler jobs are invisible. |
| 07 | `07-crm-callbacks-remaining-handlers.md` | P1 | Several aiogram CRM callback handlers run inside root span without nested @observe. |
| 08 | `08-generation-actual-model-name.md` | P1 | Generation observations record requested model, not LiteLLM-routed actual `response.model`. |
| 09 | `09-langfuse-prompts-link-to-generation.md` | P2 | `update_current_generation(prompt=...)` not used; breaks Prompt → Trace linking. |

## How to use

1. Open each file in this folder.
2. Copy the body into a new GitHub issue.
3. Apply labels matching existing observability issues: `domain:observability`, priority (`P0-now` / `P1-next` / `P2-backlog`), and `lane:plan-needed` if planning is required.
4. Close this docs PR after issues are filed; drafts can be deleted from the branch on merge.
