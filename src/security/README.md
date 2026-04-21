# 🔒 Security & PII Redaction

This folder contains security guardrails for production RAG deployment.

## 📁 Contents

| File | Purpose |
|------|---------|
| `pii_redaction.py` | PII redaction for Ukrainian data + budget guards |

---

## 🎯 Why PII Redaction?

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

## 🏗️ Security Architecture

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

## 📦 PII Redaction (`pii_redaction.py`)

### PIIRedactor Class

**Purpose**: Detect and redact Ukrainian PII patterns.

#### Supported PII Types

| PII Type | Pattern | Example | Redacted |
|----------|---------|---------|----------|
| **Phone** | `+380XXXXXXXXX` or `0XXXXXXXXX` | `+380501234567` | `[PHONE]` |
| **Email** | Standard email format | `user@example.com` | `[EMAIL]` |
| **Tax ID** | 10 digits (РНОКПП) | `1234567890` | `[TAX_ID]` |
| **Passport** | 2 Ukrainian letters + 6 digits | `АА123456` | `[PASSPORT]` |

---

### Usage

#### Basic Redaction

```python
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()

# Redact PII from query
query = "Стаття 121 для громадянина з паспортом АА123456 та номером +380501234567"
redacted_query, metadata = redactor.redact_query(query)

print(redacted_query)
# Output: "Стаття 121 для громадянина з паспортом [PASSPORT] та номером [PHONE]"

print(metadata)
# Output: {
#   "pii_redacted": True,
#   "passport_count": 1,
#   "phone_count": 1
# }
```

---

#### Integration with Langfuse

```python
from langfuse import observe, get_client, propagate_attributes
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()

@observe(name="rag-query")
async def rag_query(query: str, user_id: str):
    langfuse = get_client()

    # 1. Redact PII
    redacted_query, pii_metadata = redactor.redact_query(query)

    if pii_metadata["pii_redacted"]:
        print(f"⚠️  PII detected: {pii_metadata}")

    # 2. Log redacted query to Langfuse (NOT original!)
    with propagate_attributes(
        user_id=user_id,
        metadata={k: str(v) for k, v in pii_metadata.items()},
        tags=["security", "pii-redaction"],
    ):
        langfuse.update_current_span(
            input={"query": redacted_query},  # Redacted version
            metadata={"redaction_applied": "true"},
        )

    # 3. Use ORIGINAL query for search (better accuracy)
    results = await qdrant_client.search(
        query_text=query,  # Original query
        limit=10
    )

    return results
```

**Key Insight**:
- **Search uses original query** (better accuracy)
- **Logs use redacted query** (GDPR compliance)

---

#### Integration with MLflow

```python
from evaluation.mlflow_integration import MLflowRAGLogger
from security.pii_redaction import PIIRedactor

redactor = PIIRedactor()
mlflow_logger = MLflowRAGLogger()

with mlflow_logger.start_run():
    for query in test_queries:
        # Redact before logging
        redacted_query, pii_metadata = redactor.redact_query(query)

        # Log redacted query + metadata
        mlflow_logger.log_params({
            "query": redacted_query,
            **pii_metadata
        })

        # Execute with original query
        results = rag_pipeline.query(query)
```

---

### Regex Patterns

#### Phone Numbers (Ukrainian)

```python
# Pattern
phone_pattern = re.compile(r"\+380\d{9}|\b0\d{9}\b")

# Matches:
# - +380501234567 (international format)
# - 0501234567 (local format)

# Examples:
"+380501234567" → "[PHONE]"
"0501234567"    → "[PHONE]"
"+1234567890"   → (not matched - not Ukrainian)
```

---

#### Email Addresses

```python
# Pattern
email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Examples:
"user@example.com"      → "[EMAIL]"
"test.user@domain.org"  → "[EMAIL]"
"invalid@"              → (not matched)
```

---

#### Tax IDs (РНОКПП)

```python
# Pattern
tax_id_pattern = re.compile(r"\b\d{10}\b")

# Matches: Exactly 10 consecutive digits

# Examples:
"1234567890"   → "[TAX_ID]"
"РНОКПП 1234567890" → "РНОКПП [TAX_ID]"
"12345"        → (not matched - too short)
```

**⚠️ Warning**: This pattern is aggressive and may match non-PII numbers (phone numbers without +380, dates, etc.). Consider adding more specific validation if needed.

---

#### Passports (Ukrainian)

```python
# Pattern
passport_pattern = re.compile(r"\b[А-ЯІЇЄҐ]{2}\d{6}\b")

# Matches: 2 Ukrainian letters + 6 digits

# Examples:
"АА123456"   → "[PASSPORT]"
"КК987654"   → "[PASSPORT]"
"AA123456"   → (not matched - Latin letters)
"А123456"    → (not matched - only 1 letter)
```

---

## 💰 Budget Guards

### BudgetGuard Class

**Purpose**: Prevent runaway LLM costs.

**Limits**:
- **Daily**: $10
- **Monthly**: $300

**Alert**: Warning at 80% of limit

---

### Usage

#### Basic Budget Check

```python
from security.pii_redaction import BudgetGuard

budget_guard = BudgetGuard()

# Check if request allowed
estimated_cost = 0.001  # $0.001 per query
allowed, warning = budget_guard.check_budget(estimated_cost)

if not allowed:
    raise Exception(f"🚫 Budget limit reached: {warning}")

if warning:
    print(warning)
    # Output: ⚠️  Daily budget at 82%: $8.20 / $10.00

# Execute query
response = await rag_pipeline.query(query)

# Record actual spend
actual_cost = 0.0008
budget_guard.record_spend(actual_cost)
```

---

#### Budget Limits

```python
budget_guard = BudgetGuard()

# Check limits
print(f"Daily limit: ${budget_guard.limits['daily']}")
print(f"Monthly limit: ${budget_guard.limits['monthly']}")

# Check current spend
print(f"Daily spend: ${budget_guard.current_spend['daily']:.2f}")
print(f"Monthly spend: ${budget_guard.current_spend['monthly']:.2f}")
```

---

#### Update Limits

```python
# Increase limits for high-traffic days
budget_guard.limits["daily"] = 50.0    # $50/day
budget_guard.limits["monthly"] = 1000.0  # $1000/month
```

---

#### Reset Daily Counter

```python
# Run at midnight via cron
budget_guard.reset_daily()

print(f"Daily spend reset to: ${budget_guard.current_spend['daily']}")
# Output: Daily spend reset to: $0.00
```

**Cron Job**:
```bash
# Add to crontab
crontab -e

# Reset daily budget at midnight
0 0 * * * /home/admin/contextual_rag/venv/bin/python -c "from security.pii_redaction import BudgetGuard; BudgetGuard().reset_daily()"
```

---

### Cost Estimation

```python
def estimate_query_cost(query: str) -> float:
    """Estimate cost for a query."""

    # Embedding cost (BGE-M3)
    embedding_cost = 0.00001  # $0.00001 per embedding

    # LLM cost (if using LLM for reranking/generation)
    llm_cost = 0  # Self-hosted models = free

    # Qdrant search cost
    qdrant_cost = 0  # Self-hosted = free

    total_cost = embedding_cost + llm_cost + qdrant_cost

    return total_cost


# Check before query
estimated_cost = estimate_query_cost(query)
allowed, warning = budget_guard.check_budget(estimated_cost)
```

---

## 🛡️ Secure RAG Pipeline

### SecureRAGPipeline Class

**Purpose**: RAG pipeline with built-in security checks.

---

### Usage

```python
from security.pii_redaction import SecureRAGPipeline

pipeline = SecureRAGPipeline()

# Query with automatic security checks
response = await pipeline.query(
    query="Стаття 121 для паспорта АА123456",
    user_id="user_123"
)

# Behind the scenes:
# 1. ✅ PII redacted (АА123456 → [PASSPORT])
# 2. ✅ Budget checked ($0.001 < $10 daily limit)
# 3. ✅ Query logged to Langfuse (redacted version)
# 4. ✅ Spend recorded ($0.0008)
```

---

### Implementation

```python
class SecureRAGPipeline:
    def __init__(self):
        self.pii_redactor = PIIRedactor()
        self.budget_guard = BudgetGuard()

    async def query(self, query: str, user_id: str):
        # 1. Redact PII
        redacted_query, pii_metadata = self.pii_redactor.redact_query(query)

        if pii_metadata["pii_redacted"]:
            print(f"⚠️  PII detected: {pii_metadata}")

        # 2. Check budget
        estimated_cost = 0.001
        allowed, warning = self.budget_guard.check_budget(estimated_cost)

        if not allowed:
            raise Exception(f"🚫 Budget limit: {warning}")

        if warning:
            print(warning)

        # 3. Log to Langfuse (redacted)
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

        # 4. Execute query (original query for accuracy)
        results = await rag_pipeline.query(query)

        # 5. Record actual cost
        actual_cost = 0.0008
        self.budget_guard.record_spend(actual_cost)

        return results
```

---

## 🚨 Security Alerts

### PII Detection Alert

```python
# Alert when PII detected
if pii_metadata["pii_redacted"]:
    # Log to security monitoring
    logger.warning(f"PII detected in query from user {user_id}: {pii_metadata}")

    # Send to Slack (if critical)
    if pii_metadata.get("passport_count", 0) > 0:
        send_slack_alert(
            f"🚨 Passport detected in query from user {user_id}"
        )
```

---

### Budget Alert

```python
# Alert at 80% of daily limit
daily_pct = budget_guard.current_spend["daily"] / budget_guard.limits["daily"]

if daily_pct >= 0.80:
    logger.warning(f"⚠️  Daily budget at {daily_pct:.0%}")

    # Send email to admin
    send_email(
        to="admin@example.com",
        subject="RAG Budget Alert",
        body=f"Daily spend: ${budget_guard.current_spend['daily']:.2f} / ${budget_guard.limits['daily']:.2f}"
    )
```

---

### Budget Exceeded Alert

```python
# Critical alert when budget exceeded
if not allowed:
    logger.critical(f"🚫 Budget limit exceeded: {warning}")

    # Send to PagerDuty
    send_pagerduty_alert(
        severity="critical",
        message=f"RAG budget exceeded: {warning}"
    )

    # Disable RAG service temporarily
    # (prevent more charges)
```

---

## 📊 Monitoring Security Metrics

### PII Detection Rate

```python
# Track PII detection rate
pii_detected_count = 0
total_queries = 0

for query in queries:
    total_queries += 1
    _, pii_metadata = redactor.redact_query(query)

    if pii_metadata["pii_redacted"]:
        pii_detected_count += 1

pii_rate = pii_detected_count / total_queries

print(f"PII detection rate: {pii_rate:.1%}")
# Output: PII detection rate: 2.3%

# Alert if rate too high
if pii_rate > 0.05:  # 5%
    logger.warning(f"High PII detection rate: {pii_rate:.1%}")
```

---

### Cost Tracking

```python
# Daily cost report
print(f"Daily spend: ${budget_guard.current_spend['daily']:.2f} / ${budget_guard.limits['daily']:.2f}")
print(f"Monthly spend: ${budget_guard.current_spend['monthly']:.2f} / ${budget_guard.limits['monthly']:.2f}")

# Export to Prometheus
from prometheus_client import Gauge

daily_spend_gauge = Gauge('rag_daily_spend_usd', 'Daily RAG spend in USD')
monthly_spend_gauge = Gauge('rag_monthly_spend_usd', 'Monthly RAG spend in USD')

daily_spend_gauge.set(budget_guard.current_spend["daily"])
monthly_spend_gauge.set(budget_guard.current_spend["monthly"])
```

---

## 🔧 Advanced Configuration

### Custom PII Patterns

```python
# Add custom PII pattern
redactor = PIIRedactor()

# Example: Ukrainian ID card numbers (NNNNNNNN-NNNNN)
redactor.patterns["id_card"] = re.compile(r"\b\d{8}-\d{5}\b")

# Test
query = "Моя ID карта 12345678-12345"
redacted, metadata = redactor.redact_query(query)

print(redacted)
# Output: "Моя ID карта [ID_CARD]"
```

---

### Allowlist (Exclude Non-PII)

```python
# Exclude known non-PII patterns
ALLOWLIST = [
    "0800123456",  # Customer service number
    "info@example.com",  # Public email
]

def redact_with_allowlist(query: str) -> str:
    redacted, metadata = redactor.redact_query(query)

    # Restore allowlisted items
    for item in ALLOWLIST:
        if item in query:
            redacted = redacted.replace("[PHONE]", item, 1)

    return redacted
```

---

### Dynamic Budget Limits

```python
# Adjust limits based on traffic
def adjust_budget(time_of_day: int):
    """Higher limits during business hours."""

    if 9 <= time_of_day <= 17:  # 9 AM - 5 PM
        budget_guard.limits["daily"] = 20.0  # $20
    else:
        budget_guard.limits["daily"] = 10.0  # $10

    print(f"Budget adjusted: ${budget_guard.limits['daily']}")
```

---

## 📖 Compliance

### GDPR Requirements

✅ **Right to be forgotten**: PII not stored in logs
✅ **Data minimization**: Only redacted queries logged
✅ **Purpose limitation**: PII only used for search (not stored)
✅ **Transparency**: Users informed of data processing

---

### Ukrainian Data Protection Law

✅ **Consent**: Users consent to data processing (terms of service)
✅ **Purpose**: PII used only for search functionality
✅ **Storage**: PII not stored (redacted before logging)
✅ **Access control**: Only authorized services access original queries

---

## 🛠️ Configuration

### Environment Variables

```bash
# Budget limits
export RAG_DAILY_BUDGET_USD=10.0
export RAG_MONTHLY_BUDGET_USD=300.0

# Alert thresholds
export RAG_BUDGET_ALERT_THRESHOLD=0.80  # 80%

# Security logging
export RAG_LOG_PII_DETECTIONS=true
```

---

### Python Dependencies

```bash
pip install langfuse mlflow
```

---

## 🚀 Quick Start

```bash
# 1. Initialize security components
cd /home/admin/contextual_rag
source venv/bin/activate

python
>>> from security.pii_redaction import PIIRedactor, BudgetGuard, SecureRAGPipeline

# 2. Test PII redaction
>>> redactor = PIIRedactor()
>>> redacted, metadata = redactor.redact_query("Паспорт АА123456")
>>> print(redacted)
Паспорт [PASSPORT]

# 3. Test budget guard
>>> budget_guard = BudgetGuard()
>>> allowed, warning = budget_guard.check_budget(0.001)
>>> print(allowed)
True

# 4. Use secure pipeline
>>> pipeline = SecureRAGPipeline()
>>> response = await pipeline.query("Стаття 121", user_id="user_123")
```

---

## 📊 Security Checklist

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
