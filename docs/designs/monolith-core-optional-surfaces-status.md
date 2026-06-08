# Optional Surfaces Status After Core Stabilization

Статус: предлагается
Дата: 2026-06-08

Этот документ относится к `CORE-009`: после стабилизации ядра эти поверхности не
должны быть обязательным доказательством корректности основного продукта.

| Surface | Status | Core requirement |
|---|---|---|
| Telegram text bot | production adapter | calls/renders `AssistantResult`; transport smoke only |
| FastAPI RAG API | optional adapter | may call core if retained |
| Voice / LiveKit | optional adapter | not part of core E2E gate |
| Mini App | optional surface | not part of core E2E gate |
| Langfuse | optional diagnostics | absence must not change product behavior |
| OpenTelemetry / trace validation | optional diagnostics | not release proof for core |
| k8s manifests | optional deploy surface | not required for local core proof |
| Loki / Promtail / Alertmanager | optional monitoring | not required for local core proof |
| BGE-M3 API container | optional service boundary | core proof may use local/service embeddings by accepted gate |
| Docling service | optional service boundary | ingestion can run batch/in-process |
| LiteLLM proxy | optional service boundary | core may use direct SDK/client path |

Primary proof remains:

```text
prepared docs -> Qdrant -> run_assistant_request() -> AssistantResult checks
```

No surface above should become mandatory for `make e2e-core-live` unless Артём
explicitly changes the product simplification decision.
