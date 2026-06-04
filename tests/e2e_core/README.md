# tests/e2e_core

Synthetic fixture corpus for simplification core E2E tests.

## Purpose

This directory holds a small, stable, synthetic document corpus and
golden test cases for the product simplification core E2E pipeline.

The corpus is self-contained: no production data, no secrets, no
customer PII, no real CRM/Telegram contact data.

## Structure

```
tests/e2e_core/
  fixtures/
    docs/              # 8 synthetic Markdown documents
    golden_cases.yaml  # 7 golden test cases
  README.md            # this file
```

## Fixture Documents

| File | Source ID | Type | Key Facts |
|---|---|---|---|
| `sunny_beach_studio.md` | `sunny-beach-studio-001` | Listing | Studio, 150m sea, 110 kEUR |
| `sunny_beach_2bed.md` | `sunny-beach-2bed-002` | Listing | 2-bed, 250m sea, 95 kEUR |
| `nessebar_penthouse.md` | `nessebar-penthouse-003` | Listing | Penthouse, 100m sea, 130 kEUR |
| `mountain_view_villa.md` | `mountain-villa-004` | Listing | Villa, Bansko mountains, 90 kEUR |
| `city_center_sofia.md` | `sofia-center-005` | Listing | 1-bed, Sofia center, 85 kEUR |
| `sotirovo_garden.md` | `sotirovo-garden-006` | Listing | Garden apt, Burgas area, 78 kEUR |
| `services_cleaning.md` | `service-cleaning-007` | Service | Cleaning, 25-60 EUR, 48h notice |
| `rules_hitl.md` | `policy-hitl-008` | Policy | CRM/HITL confirmation workflow |

## Golden Cases

| ID | Scenario | Answer Policy |
|---|---|---|
| `beach_studio_sea_under_120k` | Happy path: sea-side studio under budget | `grounded_answer` |
| `missing_in_corpus_no_claim` | Query targets data not in corpus | `no_data_no_claim` |
| `price_constraint_cheapest_sunny_beach` | Price/location constraint | `filtered_constraint` |
| `sea_side_excludes_mountain` | Sea-side must exclude mountain property | `conflict_attribution` |
| `garden_apartment_near_burgas` | Location + amenity constraint | `filtered_constraint` |
| `service_cleaning_price_policy` | Service quote retrieval | `service_quote` |
| `crm_hitl_confirmation_policy` | CRM HITL confirmation metadata | `hitl_confirmation` |

## Validation

Validate fixture integrity:

```bash
uv run python -c "
from pathlib import Path
import yaml
root = Path('tests/e2e_core/fixtures')
cases = yaml.safe_load((root / 'golden_cases.yaml').read_text(encoding='utf-8'))
assert isinstance(cases, list) and cases
ids = {p.stem for p in (root / 'docs').glob('*.md')}
for case in cases:
    assert case['id']
    assert case['query']
    for doc_id in case.get('must_retrieve', []):
        assert doc_id in ids, (case['id'], doc_id)
print(f'validated {len(cases)} golden cases against {len(ids)} docs')
"
```

## Contract

Golden cases are product-check contracts, not prose comparisons. Each case
asserts:
- Which documents **must** be retrieved (`must_retrieve`)
- What facts **must** be present in the answer (`must_contain`)
- What facts **must not** appear in the answer (`must_not_contain`)
- What answering policy applies (`answer_policy`)

LLM evaluation uses temperature 0 and fact-based checks to minimize
non-determinism.

## Related Docs

- Product simplification E2E plan: [`docs/designs/product-simplification-e2e-plan.md`](../../docs/designs/product-simplification-e2e-plan.md)
- Issue #2332: create synthetic fixture corpus for core E2E
