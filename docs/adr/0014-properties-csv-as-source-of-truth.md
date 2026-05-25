# ADR-0014: Properties CSV as Source of Truth (No Admin Panel)

**Status:** Accepted

**Date:** 2026-05-25

**Closes:** [#7](https://github.com/yastman/rag/issues/7) (closed 2026-02-10)

## Context

Issue #7 (`feat: admin panel for property management`) was opened on 2026-01-26 as a wish-list (CRUD for properties, image upload, price updates) and closed on 2026-02-10 as low-priority backlog cleanup with an explicit reopen condition: "when product roadmap includes admin-panel investment". The audit performed on 2026-05-25 confirmed the original product reasoning still holds.

The platform currently treats properties as a **read-mostly catalog** sourced from `data/apartments.csv` (~300 listings) and indexed into Qdrant collection `apartments` via `scripts/apartments/ingest.py` and `src/ingestion/apartments/flow.py`. There is no Postgres-backed properties table; edits happen by replacing the CSV and re-running the ingest job.

The decision space is whether to invest in a write-side admin surface (CRUD UI, image upload, price-update workflows) or keep the CSV-driven flow as canonical until product demand justifies the investment.

## Decision

We keep `data/apartments.csv` as the **source of truth** for properties. We do not build an admin panel for property CRUD, image upload, or price updates. The Qdrant `apartments` collection remains a derived index, refreshed by re-running the ingest pipeline against an updated CSV.

### Why CSV-as-source-of-truth

1. **Catalog is read-mostly.** Properties change at human review cadence (days/weeks), not at machine cadence. There is no live editorial workflow that requires a UI.
2. **Existing pipeline already works.** `ApartmentRecord` model, deterministic UUIDs (`uuid5(complex::section::apartment_number)`), BGE-M3 hybrid embeddings, and Qdrant upsert are all in place and exercised by E2E tests (`scripts/e2e/`).
3. **No production demand signal.** No open issue, no operator report, and no CRM workflow currently depends on self-service property edits. The cost of an admin surface (auth, RBAC, image storage, audit log, CSV/DB sync, tests) is not justified by the current usage pattern.
4. **CSV diffs are the audit log.** Git history on `data/apartments.csv` already provides reviewable, reversible change tracking for free. An admin panel would have to reproduce this surface deliberately.
5. **Schema stability.** The 15-field schema (`complex_name, city, section, apartment_number, rooms, floor_label, area_m2, view_raw, price_eur, price_bgn, is_furnished, has_floor_plan, has_photo, is_promotion, old_price_eur`) has been stable; there is no churn that an admin tool would absorb.

### Why not an admin panel (now)

| Cost | Detail |
|---|---|
| Source-of-truth split | Postgres table + CSV → Qdrant sync demon doubles the surface area for drift bugs |
| Image hosting | New S3-compatible dependency, signed-URL flow, lifecycle policy, backup story |
| Auth / RBAC | Operator allowlist, audit log, session story — none of which exist in `mini_app` today |
| UI scope creep | Once a CRUD exists, every property attribute becomes a feature request |
| Testing | New write paths require integration tests against Postgres + Qdrant + S3 |

## Reopen Conditions

This decision should be **revisited** (and #7 reopened with a fresh scope, not as the original wish-list) when **any** of these signals appear:

1. **Volume:** ≥10 property edits per week sustained for ≥4 weeks (CSV diff churn).
2. **Self-service demand:** A non-engineer (sales / operations / property owner) explicitly requests independent edit access, documented in an issue.
3. **Sync latency complaint:** A customer-facing incident traced to "stale CSV not yet re-ingested" (`apartments` collection lagging real prices/availability).
4. **Multi-source ingestion:** Properties start arriving from a second source (e.g. partner feed) where merging into a single CSV is no longer practical.

When reopening, **do not reuse #7 as-is**. Open a narrow follow-up issue on the specific operation that motivated the reopen (e.g. `feat: bulk price update endpoint`, `feat: properties admin read-view`, `feat: property image upload service`). The original wish-list framing produces unbounded scope; the narrow framing keeps the first PR shippable.

## Consequences

### Positive
- Zero new infrastructure, zero new auth surface, zero new failure modes
- Property edits remain reviewable via git history on `data/apartments.csv`
- Ingest pipeline is the only write path into Qdrant `apartments` (single seam)
- Engineering capacity stays on the higher-leverage backlog (#1948 reverse-layering, #1538 SDK-native migrations, #1417 observability)

### Negative
- A property edit requires a developer to update the CSV and trigger ingest — non-engineers cannot self-serve
- No image-upload story; `has_photo` flag is set in the CSV but the actual hosting remains ad-hoc
- Bulk operations (e.g. percentage-wide price changes) require ad-hoc scripts rather than a UI button
- If a reopen condition triggers, the migration from CSV-as-truth to DB-as-truth requires a one-time backfill and a sync-demon

## Implementation

No code change. This ADR codifies the current behavior of the system. The relevant runtime artifacts are:

- `data/apartments.csv` — source of truth
- `src/models/apartment.py` (`ApartmentRecord`) — schema
- `scripts/apartments/ingest.py` — CSV → Qdrant ingest
- `src/ingestion/apartments/flow.py` — flow primitives, deterministic UUIDs
- Qdrant collection `apartments` — derived index

## References

- Issue [#7](https://github.com/yastman/rag/issues/7) — original wish-list, closed 2026-02-10
- [docs/INGESTION.md](../INGESTION.md) — ingestion pipeline
- [docs/PIPELINE_OVERVIEW.md](../PIPELINE_OVERVIEW.md) — overall pipeline
- [data/apartments.csv](../../data/apartments.csv) — the source of truth
