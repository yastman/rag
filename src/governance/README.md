***REMOVED*** 🏛️ Model Governance & Registry

This folder contains MLflow Model Registry integration for production model governance.

***REMOVED******REMOVED*** 📁 Contents

| File | Purpose |
|------|---------|
| `model_registry.py` | MLflow Model Registry for staging → production workflow |

---

***REMOVED******REMOVED*** 🎯 What is Model Governance?

**Problem**: How do you safely deploy new RAG configurations to production?

Without governance:
- ❌ Direct production changes (risky)
- ❌ No rollback capability
- ❌ No audit trail
- ❌ No A/B testing workflow

With Model Registry:
- ✅ Staging → Production workflow
- ✅ One-command rollback
- ✅ Complete audit trail
- ✅ Champion/Challenger pattern

---

***REMOVED******REMOVED*** 🏗️ Production Workflow

```
┌──────────────────────────────────────────────────────┐
│  1. Development: Experiment with new configs         │
│     Run A/B tests, RAGAS evaluation                  │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│  2. Register: Save config to Model Registry          │
│     version = registry.register_config(run_id, ...)  │
└────────────────┬─────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│  3. Staging: Test in staging environment             │
│     registry.promote_to_staging(version)             │
│     Alias: "challenger"                              │
└────────────────┬─────────────────────────────────────┘
                 │
                 │ Run validation tests
                 │ Monitor for 24-48 hours
                 ▼
┌──────────────────────────────────────────────────────┐
│  4. Production: Promote to production                │
│     registry.promote_to_production(version)          │
│     Alias: "champion"                                │
│     Old champion → Archived (for rollback)           │
└──────────────────────────────────────────────────────┘
                 │
                 │ If issues detected
                 ▼
┌──────────────────────────────────────────────────────┐
│  5. Rollback: Restore previous version               │
│     registry.rollback_production(to_version)         │
└──────────────────────────────────────────────────────┘
```

---

***REMOVED******REMOVED*** 📦 Model Registry (`model_registry.py`)

***REMOVED******REMOVED******REMOVED*** Key Features

1. **Model Versioning**
   - Each RAG config saved with version number
   - Full config snapshot (search engine, embeddings, chunking)
   - Metrics attached (precision, recall, latency)

2. **Lifecycle Stages**
   - **None**: Initial registration
   - **Staging**: Testing in pre-production
   - **Production**: Live in production
   - **Archived**: Old production versions (for rollback)

3. **Aliases**
   - **champion**: Current production config
   - **challenger**: Staging config being tested

4. **Audit Trail**
   - Who promoted when
   - Why (description)
   - What changed (config diff)

---

***REMOVED******REMOVED******REMOVED*** Usage

***REMOVED******REMOVED******REMOVED******REMOVED*** Initialize Registry

```python
from governance.model_registry import RAGModelRegistry

registry = RAGModelRegistry(
    model_name="contextual_rag_config",
    tracking_uri="http://localhost:5000"
)
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Register New Config

```python
***REMOVED*** After A/B test completes
config = {
    "search_engine": "DBSF + ColBERT",
    "embedding_model": "bge-m3",
    "chunk_size": 512,
    "top_k": 10,
    "version": "2.0.1"
}

metrics = {
    "precision@1": 0.94,
    "recall@10": 0.98,
    "latency_p95_ms": 420,
    "faithfulness": 0.87,
    "cost_per_1000": 0.12
}

***REMOVED*** Register with MLflow
version = registry.register_config(
    run_id="abc123",  ***REMOVED*** From MLflow experiment
    config_version="2.0.1",
    metrics=metrics
)

print(f"Registered as version {version}")
***REMOVED*** Output: Registered as version 3
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Promote to Staging

```python
***REMOVED*** Move to staging for testing
registry.promote_to_staging(version="3")

***REMOVED*** Config now has:
***REMOVED*** - Stage: Staging
***REMOVED*** - Alias: challenger

***REMOVED*** Application can load it
challenger_config = registry.load_config(alias="challenger")
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Promote to Production

```python
***REMOVED*** After validation in staging
registry.promote_to_production(
    version="3",
    archive_previous=True  ***REMOVED*** Archive current champion
)

***REMOVED*** Old champion (version 2):
***REMOVED*** - Stage: Archived (for rollback)
***REMOVED*** - Alias: removed

***REMOVED*** New champion (version 3):
***REMOVED*** - Stage: Production
***REMOVED*** - Alias: champion

***REMOVED*** Application loads it automatically
champion_config = registry.load_config(alias="champion")
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Rollback

```python
***REMOVED*** If production issues detected
registry.rollback_production(to_version="2")

***REMOVED*** Version 2 restored:
***REMOVED*** - Stage: Production
***REMOVED*** - Alias: champion

***REMOVED*** Version 3 archived:
***REMOVED*** - Stage: Archived
***REMOVED*** - Alias: removed
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Load Config in Application

```python
***REMOVED*** Production: Always use champion
config = registry.load_config(alias="champion")

***REMOVED*** Staging: Use challenger
config = registry.load_config(alias="challenger")

***REMOVED*** Specific version (for debugging)
config = registry.load_config(version="2")
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Get Config Metadata

```python
metadata = registry.get_version_metadata(version="3")

print(metadata)
***REMOVED*** Output:
***REMOVED*** {
***REMOVED***   "version": 3,
***REMOVED***   "stage": "Production",
***REMOVED***   "aliases": ["champion"],
***REMOVED***   "registered_at": "2025-10-30T14:30:00Z",
***REMOVED***   "promoted_by": "admin",
***REMOVED***   "metrics": {
***REMOVED***     "precision@1": 0.94,
***REMOVED***     "faithfulness": 0.87
***REMOVED***   },
***REMOVED***   "config_hash": "5f4dcc3b"
***REMOVED*** }
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** List All Versions

```python
versions = registry.list_versions()

for v in versions:
    print(f"Version {v['version']}: {v['stage']} {v['aliases']}")

***REMOVED*** Output:
***REMOVED*** Version 1: Archived []
***REMOVED*** Version 2: Archived []
***REMOVED*** Version 3: Production ['champion']
***REMOVED*** Version 4: Staging ['challenger']
```

---

***REMOVED******REMOVED*** 🔄 Champion/Challenger Pattern

***REMOVED******REMOVED******REMOVED*** What is Champion/Challenger?

**Champion**: Current production config (proven, stable)
**Challenger**: New config being tested (potentially better)

**Workflow**:
1. Champion serves 100% of production traffic
2. Challenger tested in staging (shadow traffic)
3. If challenger wins → Promote to champion
4. Old champion → Archived (for rollback)

---

***REMOVED******REMOVED******REMOVED*** Shadow Testing

```python
***REMOVED*** In production application
champion_config = registry.load_config(alias="champion")
challenger_config = registry.load_config(alias="challenger")

***REMOVED*** Serve with champion
response_champion = await rag_pipeline.query(query, config=champion_config)

***REMOVED*** Async test with challenger (don't block user)
asyncio.create_task(
    test_challenger(query, config=challenger_config)
)

return response_champion  ***REMOVED*** User sees champion results
```

---

***REMOVED******REMOVED******REMOVED*** A/B Testing

```python
***REMOVED*** Route 10% of traffic to challenger
import random

if random.random() < 0.1:
    config = registry.load_config(alias="challenger")
else:
    config = registry.load_config(alias="champion")

response = await rag_pipeline.query(query, config=config)
```

---

***REMOVED******REMOVED*** 📊 Integration with A/B Tests

***REMOVED******REMOVED******REMOVED*** End-to-End Example

```python
from evaluation.mlflow_experiments import ABTestRunner
from governance.model_registry import RAGModelRegistry

***REMOVED*** 1. Run A/B test
ab_runner = ABTestRunner()
results = ab_runner.run_ab_test(
    champion_config=old_config,
    challenger_config=new_config,
    test_queries=golden_test_set
)

***REMOVED*** 2. If challenger wins, register it
if results["challenger_wins"]:
    registry = RAGModelRegistry()

    version = registry.register_config(
        run_id=results["run_id"],
        config_version="2.0.1",
        metrics=results["metrics"]
    )

    ***REMOVED*** 3. Promote to staging
    registry.promote_to_staging(version)
    print(f"✅ Version {version} promoted to staging as 'challenger'")

    ***REMOVED*** 4. Manual validation...
    ***REMOVED*** (Run smoke tests, monitor for 24-48 hours)

    ***REMOVED*** 5. Promote to production
    registry.promote_to_production(version)
    print(f"✅ Version {version} promoted to production as 'champion'")
```

---

***REMOVED******REMOVED*** 🔍 Model Registry UI

***REMOVED******REMOVED******REMOVED*** MLflow UI

Access Model Registry via MLflow UI: http://localhost:5000

**Features**:
- View all registered models
- See version history
- Compare configs and metrics
- Promote/archive versions
- View audit trail

**Navigation**:
1. Open http://localhost:5000
2. Click **"Models"** tab
3. Select **"contextual_rag_config"**
4. View versions and stages

---

***REMOVED******REMOVED******REMOVED*** Example: Promote via UI

1. Navigate to Models → contextual_rag_config
2. Select version (e.g., version 3)
3. Click **"Stage"** dropdown
4. Select **"Transition to → Production"**
5. Add description: "Promoting ColBERT integration - 5% precision improvement"
6. Confirm

---

***REMOVED******REMOVED*** 🚨 Production Safety Checklist

Before promoting to production:

***REMOVED******REMOVED******REMOVED*** 1. A/B Test Passed
- [ ] Challenger beats champion on precision@1
- [ ] Challenger beats champion on recall@10
- [ ] Statistical significance (p < 0.05)

***REMOVED******REMOVED******REMOVED*** 2. RAGAS Validation
- [ ] Faithfulness ≥ 0.85
- [ ] Context Precision ≥ 0.80
- [ ] Context Recall ≥ 0.90

***REMOVED******REMOVED******REMOVED*** 3. Latency Check
- [ ] P95 latency ≤ 500ms
- [ ] P99 latency ≤ 1000ms

***REMOVED******REMOVED******REMOVED*** 4. Smoke Tests
- [ ] All smoke tests pass
- [ ] Qdrant connection healthy
- [ ] BGE-M3 service responsive

***REMOVED******REMOVED******REMOVED*** 5. Staging Validation
- [ ] Shadow tested for 24-48 hours
- [ ] No errors in Langfuse traces
- [ ] Cost per 1000 queries ≤ $3

***REMOVED******REMOVED******REMOVED*** 6. Rollback Plan
- [ ] Previous champion archived (not deleted)
- [ ] Rollback command ready: `rollback_production(to_version=X)`

---

***REMOVED******REMOVED*** 🛠️ Advanced Usage

***REMOVED******REMOVED******REMOVED*** Compare Versions

```python
v2_metadata = registry.get_version_metadata(version="2")
v3_metadata = registry.get_version_metadata(version="3")

print("Precision@1:")
print(f"  v2: {v2_metadata['metrics']['precision@1']:.3f}")
print(f"  v3: {v3_metadata['metrics']['precision@1']:.3f}")

***REMOVED*** Output:
***REMOVED*** Precision@1:
***REMOVED***   v2: 0.890
***REMOVED***   v3: 0.940 (+5.6%)
```

---

***REMOVED******REMOVED******REMOVED*** Automated Promotion Script

```bash
***REMOVED***!/bin/bash
***REMOVED*** promote_to_production.sh

VERSION=$1

***REMOVED*** 1. Run smoke tests
python -m src.evaluation.smoke_test || exit 1

***REMOVED*** 2. Run RAGAS validation
python -m src.evaluation.ragas_evaluation || exit 1

***REMOVED*** 3. Promote to production
python -c "
from governance.model_registry import RAGModelRegistry
registry = RAGModelRegistry()
registry.promote_to_production(version='$VERSION')
print('✅ Version $VERSION promoted to production')
"

***REMOVED*** 4. Restart application
systemctl restart rag-service
```

**Usage**:
```bash
./promote_to_production.sh 3
```

---

***REMOVED******REMOVED******REMOVED*** Automated Rollback on Errors

```python
from prometheus_api_client import PrometheusConnect

prom = PrometheusConnect(url="http://localhost:9090")

***REMOVED*** Check error rate
query = 'rate(rag_errors_total[5m])'
result = prom.custom_query(query)

error_rate = float(result[0]['value'][1])

***REMOVED*** Rollback if error rate > 5%
if error_rate > 0.05:
    registry = RAGModelRegistry()

    current_version = registry.get_production_version()
    previous_version = current_version - 1

    print(f"⚠️  High error rate ({error_rate:.1%}). Rolling back...")
    registry.rollback_production(to_version=str(previous_version))
    print(f"✅ Rolled back to version {previous_version}")
```

---

***REMOVED******REMOVED*** 🔌 Integration with CI/CD

***REMOVED******REMOVED******REMOVED*** GitHub Actions Example

```yaml
name: Deploy to Production

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Model version to promote'
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install mlflow

      - name: Run smoke tests
        run: python -m src.evaluation.smoke_test

      - name: Promote to production
        env:
          MLFLOW_TRACKING_URI: http://mlflow.example.com:5000
        run: |
          python -c "
          from governance.model_registry import RAGModelRegistry
          registry = RAGModelRegistry()
          registry.promote_to_production(version='${{ github.event.inputs.version }}')
          "

      - name: Restart service
        run: |
          ssh deploy@production-server 'systemctl restart rag-service'
```

---

***REMOVED******REMOVED*** 📖 Best Practices

***REMOVED******REMOVED******REMOVED*** 1. Never Skip Staging

```python
***REMOVED*** ❌ Bad - direct to production
registry.register_config(...)
registry.promote_to_production(version)

***REMOVED*** ✅ Good - staging first
registry.register_config(...)
registry.promote_to_staging(version)
***REMOVED*** ... validate for 24-48 hours ...
registry.promote_to_production(version)
```

---

***REMOVED******REMOVED******REMOVED*** 2. Always Archive (Don't Delete)

```python
***REMOVED*** ✅ Good - archive for rollback
registry.promote_to_production(version="3", archive_previous=True)

***REMOVED*** ❌ Bad - delete old versions
***REMOVED*** (no rollback capability)
```

---

***REMOVED******REMOVED******REMOVED*** 3. Add Descriptive Notes

```python
from mlflow.tracking import MlflowClient

client = MlflowClient()

client.transition_model_version_stage(
    name="contextual_rag_config",
    version="3",
    stage="Production",
    archive_existing_versions=True
)

***REMOVED*** Add description
client.update_model_version(
    name="contextual_rag_config",
    version="3",
    description="ColBERT integration - +5% precision, +3% recall. Validated 2025-10-30."
)
```

---

***REMOVED******REMOVED******REMOVED*** 4. Monitor After Promotion

```python
***REMOVED*** After promotion, monitor for 1 hour
import time
from langfuse import get_client

langfuse = get_client()

***REMOVED*** Check error rate every 5 minutes
for i in range(12):  ***REMOVED*** 1 hour
    traces = langfuse.get_traces(limit=100)
    errors = [t for t in traces if t.status == "error"]

    error_rate = len(errors) / len(traces)

    if error_rate > 0.05:
        print(f"⚠️  High error rate: {error_rate:.1%}")
        ***REMOVED*** Trigger rollback

    time.sleep(300)  ***REMOVED*** 5 minutes
```

---

***REMOVED******REMOVED*** 🗂️ Config Versioning Strategy

***REMOVED******REMOVED******REMOVED*** Semantic Versioning

Use semantic versioning for RAG configs:

```
MAJOR.MINOR.PATCH

Examples:
- 1.0.0: Initial release
- 1.1.0: Add ColBERT reranking (minor - new feature)
- 1.1.1: Fix bug in chunking (patch - bug fix)
- 2.0.0: Change embedding model (major - breaking change)
```

**When to increment**:
- **MAJOR**: Breaking changes (embedding model, index rebuild required)
- **MINOR**: New features (reranking, new search engine)
- **PATCH**: Bug fixes, small improvements

---

***REMOVED******REMOVED******REMOVED*** Config Hash

```python
import hashlib
import json

def get_config_hash(config: dict) -> str:
    """Generate stable hash for config."""
    config_json = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:8]

***REMOVED*** Use in cache keys
cache_key = f"response_v{config_hash}_{query_hash}"
```

---

***REMOVED******REMOVED*** 🛠️ Configuration

***REMOVED******REMOVED******REMOVED*** Environment Variables

```bash
***REMOVED*** MLflow
export MLFLOW_TRACKING_URI="http://localhost:5000"

***REMOVED*** Model Registry
export MODEL_NAME="contextual_rag_config"

***REMOVED*** Production config
export PRODUCTION_ALIAS="champion"
export STAGING_ALIAS="challenger"
```

---

***REMOVED******REMOVED******REMOVED*** Python Dependencies

```bash
pip install mlflow
```

---

***REMOVED******REMOVED*** 🚀 Quick Start

```bash
***REMOVED*** 1. Ensure MLflow is running
curl http://localhost:5000/health

***REMOVED*** 2. Initialize registry
cd /srv/contextual_rag
source venv/bin/activate

python
>>> from governance.model_registry import RAGModelRegistry
>>> registry = RAGModelRegistry()

***REMOVED*** 3. Register a config
>>> version = registry.register_config(
...     run_id="abc123",
...     config_version="2.0.1",
...     metrics={"precision@1": 0.94}
... )

***REMOVED*** 4. Promote workflow
>>> registry.promote_to_staging(version)
>>> ***REMOVED*** ... validate ...
>>> registry.promote_to_production(version)

***REMOVED*** 5. Load in application
>>> config = registry.load_config(alias="champion")
```

---

***REMOVED******REMOVED*** 📊 Governance at Scale

***REMOVED******REMOVED******REMOVED*** Multi-Environment Setup

```python
***REMOVED*** Development
dev_registry = RAGModelRegistry(
    model_name="contextual_rag_config_dev",
    tracking_uri="http://localhost:5000"
)

***REMOVED*** Staging
staging_registry = RAGModelRegistry(
    model_name="contextual_rag_config_staging",
    tracking_uri="http://staging-mlflow:5000"
)

***REMOVED*** Production
prod_registry = RAGModelRegistry(
    model_name="contextual_rag_config",
    tracking_uri="http://prod-mlflow:5000"
)
```

---

***REMOVED******REMOVED******REMOVED*** Approval Workflow

```python
***REMOVED*** Require manual approval before production
def promote_with_approval(version: str, approver: str):
    ***REMOVED*** 1. Check approval exists
    if not approval_exists(version, approver):
        raise Exception("Approval required from senior engineer")

    ***REMOVED*** 2. Run final checks
    smoke_test_passed = run_smoke_tests()
    ragas_passed = run_ragas_validation()

    if not (smoke_test_passed and ragas_passed):
        raise Exception("Validation failed")

    ***REMOVED*** 3. Promote
    registry.promote_to_production(version)

    ***REMOVED*** 4. Log to audit trail
    log_audit(version, approver, "Promoted to production")
```

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
