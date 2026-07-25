# OSS RAG platform scout — 2026-07-24

## Scope and method

Question: which maintained open-source *application/platform* could replace, or
provide a fork base for, `rag-fresh` (self-hosted RAG Q&A, Python-friendly,
Qdrant-compatible storage, flexible LLMs, grounded citations, ingestion,
Telegram/chat entry points, and workflows/HITL)?  This is a source-verified
snapshot taken on **2026-07-24**.  All links are first-party: the project's
GitHub repository/license/releases, official documentation, or GitHub's official
REST API. Star and activity figures are deliberately recorded as a snapshot,
not as durable selection criteria.

Terms used below:

* **Documented** means the linked first-party source says so.
* **Inference** is a technical conclusion from those facts, not a vendor claim.
* A blank/`not documented` cell is not evidence that the capability is absent.

## Recommendation

**Do not do a full replacement today.** The best near-term base is a selective
adoption of **Dify** only if its modified licence is acceptable, with
`rag-fresh` retaining Telegram/domain/HITL integration through Dify's API or a
custom plugin. It is the only shortlisted application that is both Python-based
and documents Qdrant, visual workflows, explicit paused human-input forms,
knowledge ingestion/retrieval, and a documented extension/trigger model.

If a genuinely permissive fork is mandatory, use **Haystack** or **LlamaIndex**
as a *component-level* Python foundation, not as a replacement application; that
preserves Qdrant and Telegram but requires retaining/building the adapter, UI,
operational workflows, and product features. **Flowise** is the strongest
feature-complete alternative if a TypeScript/Node control plane is acceptable.
It documents Qdrant, document stores, agent workflows and Human in the Loop,
but is an architectural/language migration.

`RAGFlow` merits a proof of concept for document parsing/retrieval quality, but
is not a Qdrant-compatible drop-in according to its documented deployment
choices. `AnythingLLM`, `Open WebUI`, and `Onyx` are good hosted chat products,
not clean bases for preserving the current Python/Qdrant/Telegram contracts.

### Decision for `rag-fresh`

The recommended strategy is **continue + selective borrowing**, not a platform
fork. Preserve the current `telegram_bot/` → `src/core/` → `src/runtime/`
boundary and the Qdrant/BGE-M3 retrieval and ingestion data plane. The expensive
asset is not the chat shell: it is the coordinated dense + sparse + ColBERT
schema, semantic cache, grading/reranking/rewrite policy, deterministic Docling
ingestion, and the domain workflows for catalogue, viewing booking, bookmarks,
and manager handoff.

A full-platform POC is justified only if the product direction changes toward a
general multi-channel knowledge platform with a visual builder, web UI,
workspace administration, and connectors. In that case, test Dify first
(subject to licence review) and Flowise second (if Node/TypeScript is acceptable)
through an API boundary; do not begin by moving production data or replacing the
Telegram adapter.

## Vertical/niche search

No independent mature repository was found that combines Telegram, document RAG
with citations, Qdrant, apartment catalogue/filtering, viewing booking,
bookmarks, and manager HITL. The only exact match is
[`yastman/rag`](https://github.com/yastman/rag), which is this checkout's own
upstream rather than an alternative.

The closest reusable vertical donors are deliberately narrow:

* [`SamoletPlus-telegram-bot-auto-Realtor`](https://github.com/kamperfire/SamoletPlus-telegram-bot-auto-Realtor)
  is MIT and implements aiogram FSMs, catalogue filters, Redis/SQLite lead capture,
  and manager handoff. It is useful as a UX/reference donor, not as a base: it has
  no RAG, Qdrant, booking, bookmarks, or documented production retrieval layer.
* [`real-estate-ai-agent`](https://github.com/saminkhan1/real-estate-ai-agent)
  demonstrates property search, lead intake, Calendar scheduling, multiple
  channels, and approval around appointment actions. It lacks Telegram and
  document RAG/citations, and GPL-3.0 makes direct code reuse incompatible with a
  permissive MIT-style strategy unless the resulting obligations are accepted.
* Repositories without a licence, including technically relevant RAG demos,
  must be treated as **not reusable code** unless the author grants permission.

## Component-level adoption map

| Timing | Component | Recommended use | Why not broader adoption |
|---|---|---|---|
| Now | [Qdrant Query API](https://qdrant.tech/documentation/search/hybrid-queries/) | Keep native dense+sparse prefetch, RRF and multivector/ColBERT stages behind the current retrieval contract. Add tenant payload filtering only when tenancy is real. | Replacing Qdrant would invalidate the most valuable current data contract. |
| Now | [Docling](https://github.com/docling-project/docling) | Keep the in-process parser behind the unified-ingestion boundary; benchmark tables/layout/OCR on the real corpus. | A separate Docling service or wholesale Unstructured migration adds operations/dependency cost without proven corpus gain. |
| Now | [FlagEmbedding/BGE](https://github.com/FlagOpen/FlagEmbedding) | Keep reranking optional and benchmarked top-k → top-n behind a protocol. | Model quality, latency, and each model's licence must be measured separately. |
| Now | [Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | Run offline regression over stable query, retrieved IDs/text hashes, answer, citations, latency, and model versions. | LLM-as-judge metrics complement rather than replace curated golden tests. |
| During current refactor | [aiogram](https://github.com/aiogram/aiogram) | Continue extracting per-feature routers/FSMs from the Telegram god-object. | Migrating to another Telegram framework changes handler semantics but creates no product capability. |
| Later, on a concrete reliability trigger | [LangGraph HITL](https://langchain-ai.github.io/langgraph/how-tos/wait-user-input-functional/) | Use only for restart-safe booking/manager approval flows with idempotent side effects. | Putting the ordinary RAG answer path into a second orchestrator duplicates the current pipeline. |
| Later, on enterprise trigger | [Keycloak](https://github.com/keycloak/keycloak) and a private admin UI | Add only when web/admin SSO, organizations, RBAC, or federation are requirements. | Premature identity/admin infrastructure raises operational cost and does not improve Telegram RAG quality. |

Haystack and LlamaIndex remain useful sources of isolated techniques or adapters,
but adopting either as a second top-level pipeline would create two orchestration
centres. Unstructured is best evaluated as a fallback parser/connector only.

## Shortlist (3–5)

| Rank / candidate | Why it fits (documented facts) | Main migration price / caveat | Decision |
|---|---|---|---|
| 1. [Dify](https://github.com/langgenius/dify) | Python is a primary repo language; its docs describe RAG, agents, low-code workflows and APIs; Knowledge Retrieval returns chunks plus metadata; official plugins cover selectable models, tools, agent strategies, datasources and triggers. Qdrant is its documented vector-store option. Human Input exposes a paused form with approve/reject actions. | **Licence is not Apache-2.0**: modified Apache terms prohibit operating a multi-tenant service without permission and restrict frontend logo/copyright changes. Existing Telegram conversation/menu/domain tools must be reimplemented as a plugin/API adapter; the official-org profile says Telegram integration exists, but no current product-level Telegram adapter contract was verified. Large Python/TypeScript/Go platform, not a small embeddable library. | Best full-platform POC, conditional on legal review and a thin Telegram adapter spike. |
| 2. [Flowise](https://github.com/FlowiseAI/Flowise) | Apache-2.0 source; official docs call it an open-source platform for AI agents and LLM workflows, list Human in the Loop, document Qdrant and upload/splitting/upsert via Document Stores. | Primarily TypeScript/JavaScript, so it replaces the Python runtime rather than providing a natural fork. Build/recreate Telegram, citations policy, apartment tools and manager handoff; verify exact production adapter support in a POC. | Best feature-platform alternative when Node is acceptable. |
| 3. [RAGFlow](https://github.com/infiniflow/ragflow) | Apache-2.0, Python-containing RAG/agent application with active releases; its release notes document data-source parsing, metadata control and incremental S3 sync. Strong candidate for complex-document ingestion evaluation. | Its official repo/deployment materials centre its own Infinity/Elasticsearch-style stack, not Qdrant; therefore **not a Qdrant-preserving replacement**. Telegram and explicit HITL are not verified. Moving retrieval/index semantics is high-risk. | POC only for parsing/retrieval benchmark; not replacement unless Qdrant is intentionally retired. |
| 4. [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | MIT, self-hosted/local-first application with active releases; its self-hosted terms explicitly permit air-gapped operation with local LLM/vector providers. | Node/JS product, not Python. Its official material verified generic vector-database support, but this scout did **not** verify a current official Qdrant, citation, Telegram, or HITL contract. Treat as end-user UI/agent candidate, not a safe core migration. | Evaluate only if a ready-made local chat UI is the priority. |
| 5. [Onyx Community Edition](https://github.com/onyx-dot-app/onyx) | Repo states CE core Chat, RAG, Agents and Actions are MIT; Python is a primary language; it advertises 50+ indexing connectors and agentic RAG. Very active release cadence. | Repo documents a distinct Enterprise Edition; confirm each needed capability remains CE. Current sources did not establish Qdrant, Telegram, citations format or human approval. Its enterprise-search architecture is substantially broader than the present bot. | Evaluate for enterprise connector/search needs, not for a minimal fork. |

## Verified candidate matrix

Activity values come from the official GitHub API response captured 2026-07-24;
each `API` link is a live first-party endpoint, while tags link to first-party
releases. “Current” means latest at capture time.

| Candidate | Licence (current source) | Activity snapshot | Architecture and fit | Material mismatch / lock-in |
|---|---|---|---|---|
| [Dify](https://github.com/langgenius/dify) | [modified Apache-2.0 text](https://github.com/langgenius/dify/blob/main/LICENSE), API reports `NOASSERTION` rather than an SPDX id | [150,092 stars; push 2026-07-24; v1.16.0 2026-07-17](https://api.github.com/repos/langgenius/dify), [release](https://github.com/langgenius/dify/releases/tag/1.16.0) | Full application; Python/TS/Go. [Knowledge retrieval](https://docs.dify.ai/use-dify/nodes/knowledge-retrieval), [Qdrant deployment setting](https://github.com/langgenius/dify/issues/5792), [model/provider/plugin boundaries](https://github.com/langgenius/dify-official-plugins), [HITL API](https://docs.dify.ai/api-reference/human-input/get-human-input-form), [extension/trigger/datasource contract](https://docs.dify.ai/en/develop-plugin/getting-started/choose-plugin-type). | Licence and visual-platform coupling; preserve domain core as external service/plugin rather than attempting a shallow fork. |
| [RAGFlow](https://github.com/infiniflow/ragflow) | [Apache-2.0](https://github.com/infiniflow/ragflow/blob/main/LICENSE) | [85,886; push 2026-07-24; v0.26.4 2026-07-07](https://api.github.com/repos/infiniflow/ragflow), [release](https://github.com/infiniflow/ragflow/releases/tag/v0.26.4) | Full application, Python-heavy; project calls itself RAG engine with agents; [release evidence](https://github.com/infiniflow/ragflow/releases) for source parsing/incremental sync. | No first-party evidence of Qdrant support found; high ingestion/retrieval stack replacement cost. |
| [Flowise](https://github.com/FlowiseAI/Flowise) | [Apache-2.0 source notice](https://github.com/FlowiseAI/Flowise) | [54,887; push 2026-07-24; flowise@3.1.3 2026-06-25](https://api.github.com/repos/FlowiseAI/Flowise), [release](https://github.com/FlowiseAI/Flowise/releases/tag/flowise%403.1.3) | Full visual Node/TS app; [platform/HITL docs](https://docs.flowiseai.com/), [Document Stores](https://docs.flowiseai.com/using-flowise/document-stores), [Qdrant upload configuration](https://docs.flowiseai.com/using-flowise/uploads). | Language/runtime migration; validate provider/citation/Telegram implementation before choosing. |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | [MIT](https://github.com/Mintplex-Labs/anything-llm/blob/master/LICENSE) | [63,775; push 2026-07-23; v1.15.0 2026-06-25](https://api.github.com/repos/Mintplex-Labs/anything-llm), [release](https://github.com/Mintplex-Labs/anything-llm/releases/tag/v1.15.0) | End-user local-first agent/RAG chat product; [self-hosted/air-gap statement](https://github.com/Mintplex-Labs/anything-llm/blob/master/TERMS_SELF_HOSTED.md). | JS/Node control plane; no verified exact Qdrant/HITL/Telegram/citation contract in this investigation. |
| [Open WebUI](https://github.com/open-webui/open-webui) | **Open WebUI License**, not MIT for current contributions; [multi-license notice](https://github.com/open-webui/open-webui/blob/main/LICENSE_NOTICE) and [branding restriction](https://github.com/open-webui/open-webui/blob/main/LICENSE) | [146,569; push 2026-07-24; v0.10.2 2026-07-01](https://api.github.com/repos/open-webui/open-webui), [release](https://github.com/open-webui/open-webui/releases/tag/v0.10.2) | Python-containing chat app. [Knowledge docs](https://docs.openwebui.com/features/workspace/knowledge/) document Qdrant as a community vector DB, citations, hybrid RAG, eight extraction engines and REST export/API. | Branding restriction after v0.6.6 makes a rebranded fork unsuitable; Qdrant is community-maintained, not official; no verified Telegram/HITL. **Reject as fork base.** |
| [Onyx CE](https://github.com/onyx-dot-app/onyx) | [MIT CE / separate EE](https://github.com/onyx-dot-app/onyx) | [31,123; push 2026-07-24; v4.4.2 2026-07-23](https://api.github.com/repos/onyx-dot-app/onyx), [release](https://github.com/onyx-dot-app/onyx/releases/tag/v4.4.2) | Python/Next.js full platform; repo documents Chat/RAG/Agents/Actions and 50+ connectors. | CE/EE boundary and no verified Qdrant/Telegram/HITL/citation contract. |
| [Haystack](https://github.com/deepset-ai/haystack) | [Apache-2.0](https://github.com/deepset-ai/haystack/blob/main/LICENSE) (GitHub also flags an unknown `license-header.txt`) | [25,997; push 2026-07-24; v3.0.0 2026-07-20](https://api.github.com/repos/deepset-ai/haystack), [release](https://github.com/deepset-ai/haystack/releases/tag/v3.0.0) | Python framework, not application; project describes modular pipelines and agent workflows, and its official integration catalogue includes [Qdrant](https://haystack.deepset.ai/integrations/qdrant). | No bundled user-facing KB/chat/Telegram product. Citations/HITL require application composition; excellent component substitute, **reject as E2E replacement**. |
| [LlamaIndex](https://github.com/run-llama/llama_index) | [MIT](https://github.com/run-llama/llama_index/blob/main/LICENSE) | [51,064; push 2026-07-23; v0.14.23 2026-06-24](https://api.github.com/repos/run-llama/llama_index), [release](https://github.com/run-llama/llama_index/releases/tag/v0.14.23) | Python framework with document readers/index/query engine; official package list has [Qdrant vector store](https://docs.llamaindex.ai/en/stable/api_reference/storage/vector_store/qdrant/), [citation query engine](https://docs.llamaindex.ai/en/stable/examples/query_engine/citation_query_engine/), and [workflows](https://docs.llamaindex.ai/en/stable/module_guides/workflow/). | No bundled multi-user application, Telegram adapter or prebuilt product HITL. Strong code-level basis, **reject as E2E replacement**. |

## Decision guardrails and migration approach

1. Treat **licence review as a gate before engineering**. Dify and Open WebUI
   are source-available under current branded/modified licences, not clean
   Apache/MIT fork candidates. The conclusions are documented facts from their
   license texts, not legal advice.
2. Keep the existing public boundary (`run_assistant_request` and the Telegram
   adapter) during any POC.  Call a candidate through an API/plugin rather than
   moving data or replacing the bot first. This is an **inference** based on the
   amount of unverified adapter/domain behaviour above.
3. Use a representative corpus and a fixed question set to test: source-level
   citations, Ukrainian/Russian retrieval, filters, answer latency, reindexing,
   tool invocation, manager approval, and Telegram media/streaming. None of the
   reviewed documents establishes equivalence for those current application
   contracts.
4. For Dify, spike exactly three contracts: Qdrant collection/data migration,
   Telegram inbound/outbound adapter using an Extension/Trigger plugin, and
   handoff using Human Input. Stop if licensing, citation rendering, or
   conversation-state semantics do not meet requirements.

## Rejected as primary replacement

* **Open WebUI:** technically strong document/RAG fit, but the current licence
  imposes brand-preservation conditions; it is unsuitable for a white-labelled
  fork at scale.
* **Haystack and LlamaIndex:** maintained, permissively licensed Python
  foundations with Qdrant support, but they are libraries/frameworks. Calling
  either a “replacement” would hide the substantial work of rebuilding the
  multi-user app, ingestion operations, Telegram, menu features and HITL.
* **AnythingLLM and Onyx:** serious applications, but this review found no
  primary-source proof of the specific Qdrant + Telegram + HITL contract. Do
  not promote them from UI/connector evaluation to core replacement without a
  focused verification spike.

## Evidence limitations

No candidate was accepted merely because it lists “RAG” or “agents”. GitHub
stars and a recent push/release establish activity only, not security, support,
quality, or compatibility. Provider flexibility means selectable providers or
plugin/provider extension points documented above; it does not establish exact
support for every model used by `rag-fresh`. Telegram integration was verified
only at Dify organisation level, not as a current stable adapter API, so it is
correctly treated as unverified implementation work.
