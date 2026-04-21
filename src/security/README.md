***REMOVED*** 🔒 Security & PII Redaction

This folder contains security guardrails for production RAG deployment.

***REMOVED******REMOVED*** 📁 Contents

| File | Purpose |
|------|---------|
| `pii_redaction.py` | PII redaction for Ukrainian data + budget guards |

---

***REMOVED******REMOVED*** 🎯 Why PII Redaction?

**Problem**: User queries may contain sensitive personal information (PII).

**Risk**: Logging PII to Langfuse/MLflow violates GDPR and Ukrainian data protection laws.

**Examples of PII in queries**:
- `"Стаття 121 для громадянина з паспортом АА123456"`
- `"Чи є покарання за шахрайство? Мій номер +380501234567"`
- `"РНОКПП 1234567890 - які наслідки?"`

**Solution**: Redact PII before logging.
- Query logged: `"Стаття 121 для громадянина з паспортом [PASSPORT]"`
- Metadata: `{"pii_redacted": true, "passport_count": 1}`

---

***REMOVED******REMOVED*** 🏗️ Security Architecture

```
┌─────────────────────────────────────────────────────┐
│              User Query                             │
│  "Стаття 121 для паспорта АА123456"                 │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  1. PII Redaction                                   │
│     PIIRedactor().redact_query(query)               │
│     Output: "Стаття 121 для паспорта [PASSPORT]"    │
│     Metadata: {"pii_redacted": true, ...}           │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  2. Budget Check                                    │
│     BudgetGuard().check_budget(estimated_cost)      │
│     Output: (allowed=True, warning=None)            │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  3. Execute RAG Query                               │
│     Original query: Used for search (NOT logged)    │
│     Redacted query: Logged to Langfuse/MLflow       │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  4. Record Spend                                    │
│     BudgetGuard().record_spend(actual_cost)         │
└─────────────────────────────────────────────────────┘
```

---

***REMOVED******REMOVED*** 📦 PII Redaction (`pii_redaction.py`)

***REMOVED******REMOVED******REMOVED*** PIIRedactor Class

**Purpose**: Detect and redact Ukrainian PII patterns.

***REMOVED******REMOVED******REMOVED******REMOVED*** Supported PII Types

| PII Type | Pattern | Example | Redacted |
|----------|---------|---------|----------|
| **Phone** | `+380XXXXXXXXX` or `0XXXXXXXXX` | `+380501234567` | `[PHONE]` |
| **Email** | Standard email format | `user@example.com` | `[EMAIL]` |
| **Tax ID** | 10 digits (РНОКПП) | `1234567890` | `[TAX_ID]` |
| **Passport** | 2 Ukrainian letters + 6 digits | `АА123456` | `[PASSPORT]` |

---

***REMOVED******REMOVED******REMOVED*** Usage

***REMOVED******REMOVED******REMOVED******REMOVED*** Basic Redaction

```python
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()

***REMOVED*** Redact PII from query
query = "Стаття 121 для громадянина з паспортом АА123456 та номером +380501234567"
redacted_query, metadata = redactor.redact_query(query)

print(redacted_query)
***REMOVED*** Output: "Стаття 121 для громадянина з паспортом [PASSPORT] та номером [PHONE]"

print(metadata)
***REMOVED*** Output: {
***REMOVED***   "pii_redacted": True,
***REMOVED***   "passport_count": 1,
***REMOVED***   "phone_count": 1
***REMOVED*** }
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Integration with Langfuse

```python
from langfuse import observe, get_client, propagate_attributes
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()

@observe(name="rag-query")
async def rag_query(query: str, user_id: str):
    langfuse = get_client()

    ***REMOVED*** 1. Redact PII
    redacted_query, pii_metadata = redactor.redact_query(query)

    if pii_metadata["pii_redacted"]:
        print(f"⚠️  PII detected: {pii_metadata}")

    ***REMOVED*** 2. Log redacted query to Langfuse (NOT original!)
    with propagate_attributes(
        user_id=user_id,
        metadata={k: str(v) for k, v in pii_metadata.items()},
        tags=["security", "pii-redaction"],
    ):
        langfuse.update_current_span(
            input={"query": redacted_query},  ***REMOVED*** Redacted version
            metadata={"redaction_applied": "true"},
        )

    ***REMOVED*** 3. Use ORIGINAL query for search (better accuracy)
    results = await qdrant_client.search(
        query_text=query,  ***REMOVED*** Original query
        limit=10
    )

    return results
```

**Key Insight**:
- **Search uses original query** (better accuracy)
- **Logs use redacted query** (GDPR compliance)

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Integration with MLflow

```python
from evaluation.mlflow_integration import MLflowRAGLogger
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()
mlflow_logger = MLflowRAGLogger()

with mlflow_logger.start_run():
    for query in test_queries:
        ***REMOVED*** Redact before logging
        redacted_query, pii_metadata = redactor.redact_query(query)

        ***REMOVED*** Log redacted query + metadata
        mlflow_logger.log_params({
            "query": redacted_query,
            **pii_metadata
        })

        ***REMOVED*** Execute with original query
        results = rag_pipeline.query(query)
```

---

***REMOVED******REMOVED******REMOVED*** Regex Patterns

***REMOVED******REMOVED******REMOVED******REMOVED*** Phone Numbers (Ukrainian)

```python
***REMOVED*** Pattern
phone_pattern = re.compile(r"\+380\d{9}|\b0\d{9}\b")

***REMOVED*** Matches:
***REMOVED*** - +380501234567 (international format)
***REMOVED*** - 0501234567 (local format)

***REMOVED*** Examples:
"+380501234567" → "[PHONE]"
"0501234567"    → "[PHONE]"
"+1234567890"   → (not matched - not Ukrainian)
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Email Addresses

```python
***REMOVED*** Pattern
email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

***REMOVED*** Examples:
"user@example.com"      → "[EMAIL]"
"test.user@domain.org"  → "[EMAIL]"
"invalid@"              → (not matched)
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Tax IDs (РНОКПП)

```python
***REMOVED*** Pattern
tax_id_pattern = re.compile(r"\b\d{10}\b")

***REMOVED*** Matches: Exactly 10 consecutive digits

***REMOVED*** Examples:
"1234567890"   → "[TAX_ID]"
"РНОКПП 1234567890" → "РНОКПП [TAX_ID]"
"12345"        → (not matched - too short)
```

**⚠️ Warning**: This pattern is aggressive and may match non-PII numbers (phone numbers without +380, dates, etc.). Consider adding more specific validation if needed.

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Passports (Ukrainian)

```python
***REMOVED*** Pattern
passport_pattern = re.compile(r"\b[А-ЯІЇЄҐ]{2}\d{6}\b")

***REMOVED*** Matches: 2 Ukrainian letters + 6 digits

***REMOVED*** Examples:
"АА123456"   → "[PASSPORT]"
"КК987654"   → "[PASSPORT]"
"AA123456"   → (not matched - Latin letters)
"А123456"    → (not matched - only 1 letter)
```

---

***REMOVED******REMOVED*** 💰 Budget Guards

***REMOVED******REMOVED******REMOVED*** BudgetGuard Class

**Purpose**: Prevent runaway LLM costs.

**Limits**:
- **Daily**: $10
- **Monthly**: $300

**Alert**: Warning at 80% of limit

---

***REMOVED******REMOVED******REMOVED*** Usage

***REMOVED******REMOVED******REMOVED******REMOVED*** Basic Budget Check

```python
from security.pii_redaction import BudgetGuard

budget_guard = BudgetGuard()

***REMOVED*** Check if request allowed
estimated_cost = 0.001  ***REMOVED*** $0.001 per query
allowed, warning = budget_guard.check_budget(estimated_cost)

if not allowed:
    raise Exception(f"🚫 Budget limit reached: {warning}")

if warning:
    print(warning)
    ***REMOVED*** Output: ⚠️  Daily budget at 82%: $8.20 / $10.00

***REMOVED*** Execute query
response = await rag_pipeline.query(query)

***REMOVED*** Record actual spend
actual_cost = 0.0008
budget_guard.record_spend(actual_cost)
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Budget Limits

```python
budget_guard = BudgetGuard()

***REMOVED*** Check limits
print(f"Daily limit: ${budget_guard.limits['daily']}")
print(f"Monthly limit: ${budget_guard.limits['monthly']}")

***REMOVED*** Check current spend
print(f"Daily spend: ${budget_guard.current_spend['daily']:.2f}")
print(f"Monthly spend: ${budget_guard.current_spend['monthly']:.2f}")
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Update Limits

```python
***REMOVED*** Increase limits for high-traffic days
budget_guard.limits["daily"] = 50.0    ***REMOVED*** $50/day
budget_guard.limits["monthly"] = 1000.0  ***REMOVED*** $1000/month
```

---

***REMOVED******REMOVED******REMOVED******REMOVED*** Reset Daily Counter

```python
***REMOVED*** Run at midnight via cron
budget_guard.reset_daily()

print(f"Daily spend reset to: ${budget_guard.current_spend['daily']}")
***REMOVED*** Output: Daily spend reset to: $0.00
```

**Cron Job**:
```bash
***REMOVED*** Add to crontab
crontab -e

***REMOVED*** Reset daily budget at midnight
0 0 * * * /srv/app/venv/bin/python -c "from security.pii_redaction import BudgetGuard; BudgetGuard().reset_daily()"
```

---

***REMOVED******REMOVED******REMOVED*** Cost Estimation

```python
def estimate_query_cost(query: str) -> float:
    """Estimate cost for a query."""

    ***REMOVED*** Embedding cost (BGE-M3)
    embedding_cost = 0.00001  ***REMOVED*** $0.00001 per embedding

    ***REMOVED*** LLM cost (if using LLM for reranking/generation)
    llm_cost = 0  ***REMOVED*** Self-hosted models = free

    ***REMOVED*** Qdrant search cost
    qdrant_cost = 0  ***REMOVED*** Self-hosted = free

    total_cost = embedding_cost + llm_cost + qdrant_cost

    return total_cost


***REMOVED*** Check before query
estimated_cost = estimate_query_cost(query)
allowed, warning = budget_guard.check_budget(estimated_cost)
```

---

***REMOVED******REMOVED*** 🛡️ Secure RAG Pipeline

***REMOVED******REMOVED******REMOVED*** SecureRAGPipeline Class

**Purpose**: RAG pipeline with built-in security checks.

---

***REMOVED******REMOVED******REMOVED*** Usage

```python
from security.pii_redaction import SecureRAGPipeline

pipeline = SecureRAGPipeline()

***REMOVED*** Query with automatic security checks
response = await pipeline.query(
    query="Стаття 121 для паспорта АА123456",
    user_id="user_123"
)

***REMOVED*** Behind the scenes:
***REMOVED*** 1. ✅ PII redacted (АА123456 → [PASSPORT])
***REMOVED*** 2. ✅ Budget checked ($0.001 < $10 daily limit)
***REMOVED*** 3. ✅ Query logged to Langfuse (redacted version)
***REMOVED*** 4. ✅ Spend recorded ($0.0008)
```

---

***REMOVED******REMOVED******REMOVED*** Implementation

```python
class SecureRAGPipeline:
    def __init__(self):
        self.pii_redactor = PIIRedactor()
        self.budget_guard = BudgetGuard()

    async def query(self, query: str, user_id: str):
        ***REMOVED*** 1. Redact PII
        redacted_query, pii_metadata = self.pii_redactor.redact_query(query)

        if pii_metadata["pii_redacted"]:
            print(f"⚠️  PII detected: {pii_metadata}")

        ***REMOVED*** 2. Check budget
        estimated_cost = 0.001
        allowed, warning = self.budget_guard.check_budget(estimated_cost)

        if not allowed:
            raise Exception(f"🚫 Budget limit: {warning}")

        if warning:
            print(warning)

        ***REMOVED*** 3. Log to Langfuse (redacted)
        langfuse = get_client()
        with propagate_attributes(
            user_id=user_id,
            metadata={
                **{k: str(v) for k, v in pii_metadata.items()},
                "budget_check": "passed",
            },
            tags=["security", "budget-guard"],
        ):
            langfuse.update_current_span(input={"query": redacted_query})

        ***REMOVED*** 4. Execute query (original query for accuracy)
        results = await rag_pipeline.query(query)

        ***REMOVED*** 5. Record actual cost
        actual_cost = 0.0008
        self.budget_guard.record_spend(actual_cost)

        return results
```

---

***REMOVED******REMOVED*** 🚨 Security Alerts

***REMOVED******REMOVED******REMOVED*** PII Detection Alert

```python
***REMOVED*** Alert when PII detected
if pii_metadata["pii_redacted"]:
    ***REMOVED*** Log to security monitoring
    logger.warning(f"PII detected in query from user {user_id}: {pii_metadata}")

    ***REMOVED*** Send to Slack (if critical)
    if pii_metadata.get("passport_count", 0) > 0:
        send_slack_alert(
            f"🚨 Passport detected in query from user {user_id}"
        )
```

---

***REMOVED******REMOVED******REMOVED*** Budget Alert

```python
***REMOVED*** Alert at 80% of daily limit
daily_pct = budget_guard.current_spend["daily"] / budget_guard.limits["daily"]

if daily_pct >= 0.80:
    logger.warning(f"⚠️  Daily budget at {daily_pct:.0%}")

    ***REMOVED*** Send email to admin
    send_email(
        to="admin@example.com",
        subject="RAG Budget Alert",
        body=f"Daily spend: ${budget_guard.current_spend['daily']:.2f} / ${budget_guard.limits['daily']:.2f}"
    )
```

---

***REMOVED******REMOVED******REMOVED*** Budget Exceeded Alert

```python
***REMOVED*** Critical alert when budget exceeded
if not allowed:
    logger.critical(f"🚫 Budget limit exceeded: {warning}")

    ***REMOVED*** Send to PagerDuty
    send_pagerduty_alert(
        severity="critical",
        message=f"RAG budget exceeded: {warning}"
    )

    ***REMOVED*** Disable RAG service temporarily
    ***REMOVED*** (prevent more charges)
```

---

***REMOVED******REMOVED*** 📊 Monitoring Security Metrics

***REMOVED******REMOVED******REMOVED*** PII Detection Rate

```python
***REMOVED*** Track PII detection rate
pii_detected_count = 0
total_queries = 0

for query in queries:
    total_queries += 1
    _, pii_metadata = redactor.redact_query(query)

    if pii_metadata["pii_redacted"]:
        pii_detected_count += 1

pii_rate = pii_detected_count / total_queries

print(f"PII detection rate: {pii_rate:.1%}")
***REMOVED*** Output: PII detection rate: 2.3%

***REMOVED*** Alert if rate too high
if pii_rate > 0.05:  ***REMOVED*** 5%
    logger.warning(f"High PII detection rate: {pii_rate:.1%}")
```

---

***REMOVED******REMOVED******REMOVED*** Cost Tracking

```python
***REMOVED*** Daily cost report
print(f"Daily spend: ${budget_guard.current_spend['daily']:.2f} / ${budget_guard.limits['daily']:.2f}")
print(f"Monthly spend: ${budget_guard.current_spend['monthly']:.2f} / ${budget_guard.limits['monthly']:.2f}")

***REMOVED*** Export to Prometheus
from prometheus_client import Gauge

daily_spend_gauge = Gauge('rag_daily_spend_usd', 'Daily RAG spend in USD')
monthly_spend_gauge = Gauge('rag_monthly_spend_usd', 'Monthly RAG spend in USD')

daily_spend_gauge.set(budget_guard.current_spend["daily"])
monthly_spend_gauge.set(budget_guard.current_spend["monthly"])
```

---

***REMOVED******REMOVED*** 🔧 Advanced Configuration

***REMOVED******REMOVED******REMOVED*** Custom PII Patterns

```python
***REMOVED*** Add custom PII pattern
redactor = PIIRedactor()

***REMOVED*** Example: Ukrainian ID card numbers (NNNNNNNN-NNNNN)
redactor.patterns["id_card"] = re.compile(r"\b\d{8}-\d{5}\b")

***REMOVED*** Test
query = "Моя ID карта 12345678-12345"
redacted, metadata = redactor.redact_query(query)

print(redacted)
***REMOVED*** Output: "Моя ID карта [ID_CARD]"
```

---

***REMOVED******REMOVED******REMOVED*** Allowlist (Exclude Non-PII)

```python
***REMOVED*** Exclude known non-PII patterns
ALLOWLIST = [
    "0800123456",  ***REMOVED*** Customer service number
    "info@example.com",  ***REMOVED*** Public email
]

def redact_with_allowlist(query: str) -> str:
    redacted, metadata = redactor.redact_query(query)

    ***REMOVED*** Restore allowlisted items
    for item in ALLOWLIST:
        if item in query:
            redacted = redacted.replace("[PHONE]", item, 1)

    return redacted
```

---

***REMOVED******REMOVED******REMOVED*** Dynamic Budget Limits

```python
***REMOVED*** Adjust limits based on traffic
def adjust_budget(time_of_day: int):
    """Higher limits during business hours."""

    if 9 <= time_of_day <= 17:  ***REMOVED*** 9 AM - 5 PM
        budget_guard.limits["daily"] = 20.0  ***REMOVED*** $20
    else:
        budget_guard.limits["daily"] = 10.0  ***REMOVED*** $10

    print(f"Budget adjusted: ${budget_guard.limits['daily']}")
```

---

***REMOVED******REMOVED*** 📖 Compliance

***REMOVED******REMOVED******REMOVED*** GDPR Requirements

✅ **Right to be forgotten**: PII not stored in logs
✅ **Data minimization**: Only redacted queries logged
✅ **Purpose limitation**: PII only used for search (not stored)
✅ **Transparency**: Users informed of data processing

---

***REMOVED******REMOVED******REMOVED*** Ukrainian Data Protection Law

✅ **Consent**: Users consent to data processing (terms of service)
✅ **Purpose**: PII used only for search functionality
✅ **Storage**: PII not stored (redacted before logging)
✅ **Access control**: Only authorized services access original queries

---

***REMOVED******REMOVED*** 🛠️ Configuration

***REMOVED******REMOVED******REMOVED*** Environment Variables

```bash
***REMOVED*** Budget limits
export RAG_DAILY_BUDGET_USD=10.0
export RAG_MONTHLY_BUDGET_USD=300.0

***REMOVED*** Alert thresholds
export RAG_BUDGET_ALERT_THRESHOLD=0.80  ***REMOVED*** 80%

***REMOVED*** Security logging
export RAG_LOG_PII_DETECTIONS=true
```

---

***REMOVED******REMOVED******REMOVED*** Python Dependencies

```bash
pip install langfuse mlflow
```

---

***REMOVED******REMOVED*** 🚀 Quick Start

```bash
***REMOVED*** 1. Initialize security components
cd /srv/contextual_rag
source venv/bin/activate

python
>>> from security.pii_redaction import PIIRedactor, BudgetGuard, SecureRAGPipeline

***REMOVED*** 2. Test PII redaction
>>> redactor = PIIRedactor()
>>> redacted, metadata = redactor.redact_query("Паспорт АА123456")
>>> print(redacted)
Паспорт [PASSPORT]

***REMOVED*** 3. Test budget guard
>>> budget_guard = BudgetGuard()
>>> allowed, warning = budget_guard.check_budget(0.001)
>>> print(allowed)
True

***REMOVED*** 4. Use secure pipeline
>>> pipeline = SecureRAGPipeline()
>>> response = await pipeline.query("Стаття 121", user_id="user_123")
```

---

***REMOVED******REMOVED*** 📊 Security Checklist

Before production:

- [ ] PII redaction enabled for all queries
- [ ] Budget limits configured ($10 daily, $300 monthly)
- [ ] Daily budget reset cron job configured
- [ ] Security alerts configured (PII detected, budget exceeded)
- [ ] Langfuse/MLflow logging redacted queries only
- [ ] GDPR compliance verified
- [ ] Ukrainian data protection law compliance verified
- [ ] Security monitoring dashboard created
- [ ] Incident response plan documented

---

**Last Updated**: October 30, 2025
**Maintainer**: Contextual RAG Team
