# File-by-File SDK Review

**Date:** 2026-03-02

## Scope
- Reviewed files: **281** (first-party project files in `src/`, `telegram_bot/`, `services/`, `k8s/` + root docker/build files).
- `SDK opportunity`: **30**
- `KEEP`: **251**

## Key SDK Opportunities (priority)
- H-DRY-core: unify duplicated RAG steps between `rag_pipeline.py` and LangGraph nodes.
- H-aiogram-workflow-data / H-CallbackData-factory: use aiogram DI + typed callback data patterns.
- H-python-abi-mismatch: align Python versions between builder/runtime in Dockerfiles.
- M-LLMService-merge: deprecate duplicate `LLMService` in favor of unified generation path.
- M-Docling-Python-API-eval: evaluate migration from HTTP docling-serve client to Python API/loader path with benchmark gate.
- M-RedisVL-threshold+EmbeddingsCache: data-driven threshold tuning and optional `EmbeddingsCache` adoption.

## File Inventory
| File | Status | Note |
|---|---|---|
| `Dockerfile.ingestion` | SDK opportunity | H-python-abi-mismatch |
| `Makefile` | SDK opportunity | M-docker-ai-profile-mismatch |
| `docker-compose.dev.yml` | SDK opportunity | M-bot-depends-on-postgres+security |
| `docker-compose.vps.yml` | SDK opportunity | M-bot-depends-on-postgres+security |
| `k8s/AGENTS.override.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/bge-m3/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/bge-m3/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/bot/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/configmaps/litellm-config.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/configmaps/postgres-init.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/docling/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/docling/pvc.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/docling/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/ingestion/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/kustomization.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/litellm/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/litellm/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/namespace.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/postgres/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/postgres/pvc.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/postgres/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/qdrant/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/qdrant/pvc.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/qdrant/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/redis/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/redis/pvc.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/redis/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/user-base/deployment.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/base/user-base/service.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/k3s-config.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/overlays/bot/kustomization.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/overlays/core/kustomization.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/overlays/full/kustomization.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/overlays/ingest/kustomization.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `k8s/secrets/.env.example` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/.dockerignore` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/Dockerfile` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/app.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/pyproject.toml` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/requirements.txt` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/bge-m3-api/uv.lock` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/docling/Dockerfile` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/llm-guard-api/Dockerfile` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/llm-guard-api/app.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/llm-guard-api/config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/llm-guard-api/pyproject.toml` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/llm-guard-api/uv.lock` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/.dockerignore` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/Dockerfile` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/main.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/pyproject.toml` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/requirements.txt` | KEEP | no replacement needed / app-specific / infra-specific |
| `services/user-base/uv.lock` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/api/Dockerfile` | SDK opportunity | H-python-abi-mismatch |
| `src/api/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/api/main.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/api/schemas.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/config/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/config/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/config/constants.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/config/settings.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/contextualization/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/contextualization/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/contextualization/base.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/contextualization/claude.py` | SDK opportunity | L-async-batch+prompt-caching |
| `src/contextualization/groq.py` | SDK opportunity | L-async-batch |
| `src/contextualization/openai.py` | SDK opportunity | L-async-batch |
| `src/core/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/core/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/core/pipeline.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/config_snapshot.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/create_golden_set.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/evaluator.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/extract_ground_truth.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/generate_test_queries.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/langfuse_integration.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/metrics_logger.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/mlflow_experiments.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/mlflow_integration.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/ragas_evaluation.py` | SDK opportunity | L-RAGAS-dataset-alignment |
| `src/evaluation/run_ab_test.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/search_engines.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/search_engines_rerank.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/smoke_test.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/evaluation/test_mlflow_ab.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/governance/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/governance/model_registry.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/apartments/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/apartments/flow.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/apartments/runner.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/apartments/source.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/chunker.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/cocoindex_flow.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/contextual_loader.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/contextual_schema.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/docling_client.py` | SDK opportunity | M-Docling-Python-API-eval |
| `src/ingestion/document_parser.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/gdrive_flow.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/gdrive_indexer.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/indexer.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/AGENTS.override.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/cli.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/colbert_backfill.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/flow.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/manifest.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/metrics.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/observability.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/qdrant_writer.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/state_manager.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/targets/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/models/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/models/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/models/contextualized_embedding.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/models/embedding_model.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/retrieval/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/retrieval/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/retrieval/reranker.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/retrieval/search_engines.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/security/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/security/pii_redaction.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/utils/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/utils/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/utils/structure_parser.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/Dockerfile` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/agent.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/observability.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/schemas.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/sip_setup.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `src/voice/transcript_store.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/.env.example` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/AGENTS.override.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/Dockerfile` | SDK opportunity | H-python-abi-mismatch |
| `telegram_bot/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/agent.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/apartment_tools.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/context.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/crm_tools.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/history_graph/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/history_graph/graph.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/history_graph/nodes.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/history_graph/state.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/history_tool.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/hitl.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/manager_tools.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/rag_pipeline.py` | SDK opportunity | H-DRY-core |
| `telegram_bot/agents/rag_tool.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/agents/utility_tools.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/bot.py` | SDK opportunity | H-god-object+callback-split |
| `telegram_bot/config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/config/services.yaml` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/client_menu.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_ai_advisor.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_cards.py` | SDK opportunity | H-CallbackData-factory |
| `telegram_bot/dialogs/crm_contacts.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_leads.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_notes.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_submenu.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_tasks.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/crm_wizard_models.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/faq.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/funnel.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/manager_menu.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/settings.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/states.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/dialogs/viewing.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/evaluation/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/feedback.py` | SDK opportunity | H-CallbackData-factory |
| `telegram_bot/graph/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/edges.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/graph.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/cache.py` | SDK opportunity | H-DRY-core |
| `telegram_bot/graph/nodes/classify.py` | SDK opportunity | M-SemanticRouter-POC |
| `telegram_bot/graph/nodes/generate.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/grade.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/guard.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/rerank.py` | SDK opportunity | H-DRY-core |
| `telegram_bot/graph/nodes/respond.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/nodes/retrieve.py` | SDK opportunity | H-DRY-core |
| `telegram_bot/graph/nodes/rewrite.py` | SDK opportunity | H-DRY-core |
| `telegram_bot/graph/nodes/transcribe.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/graph/state.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/handlers/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/handlers/crm_callbacks.py` | SDK opportunity | H-CallbackData-factory |
| `telegram_bot/handlers/phone_collector.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/cache.py` | SDK opportunity | M-RedisVL-threshold+EmbeddingsCache |
| `telegram_bot/integrations/embeddings.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/event_stream.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/langfuse.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/memory.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/prompt_manager.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/integrations/prompt_templates.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/keyboards/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/keyboards/client_keyboard.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/keyboards/property_card.py` | SDK opportunity | H-CallbackData-factory |
| `telegram_bot/keyboards/services_keyboard.py` | SDK opportunity | H-CallbackData-factory |
| `telegram_bot/locales/en/messages.ftl` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/locales/ru/messages.ftl` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/locales/uk/messages.ftl` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/logging_config.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/main.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/middlewares/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/middlewares/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/middlewares/error_handler.py` | SDK opportunity | M-aiogram-errors-router |
| `telegram_bot/middlewares/i18n.py` | SDK opportunity | H-aiogram-workflow-data |
| `telegram_bot/middlewares/throttling.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/models/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/models/user.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/observability.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/pipelines/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/pipelines/client.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/preflight.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/pyproject.toml` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/requirements.txt` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/scoring.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/README.md` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/__init__.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/ai_advisor_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/apartment_filter_extractor.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/apartment_models.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/apartments_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/bge_m3_client.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/colbert_reranker.py` | SDK opportunity | L-colbert-cleanup-check-callers |
| `telegram_bot/services/content_loader.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/favorites_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/filter_extractor.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/funnel_analytics_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/funnel_analytics_store.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/funnel_lead_scoring.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/generate_response.py` | SDK opportunity | M-LLMService-merge-target |
| `telegram_bot/services/history_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/hot_lead_notifier.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/ingestion_cocoindex.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/kommo_client.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/kommo_models.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/kommo_token_store.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/kommo_tokens.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/lead_score_sync.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/lead_scoring.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/lead_scoring_models.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/lead_scoring_store.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/llm.py` | SDK opportunity | M-LLMService-merge |
| `telegram_bot/services/llm_guard_client.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/manager_menu.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/metrics.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/normalizer.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/nurturing_scheduler.py` | SDK opportunity | L-APScheduler-v4-watch |
| `telegram_bot/services/nurturing_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/qdrant.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/query_analyzer.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/query_preprocessor.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/redis_monitor.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/response_style_detector.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/session_summary.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/session_summary_worker.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/small_to_big.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/types.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/user_service.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/vectorizers.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/services/voyage.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/setup_qdrant_indexes.py` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/static/photos/demo/1-01.jpg` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/static/photos/demo/1-03.jpg` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/static/photos/demo/1-04.jpg` | KEEP | no replacement needed / app-specific / infra-specific |
| `telegram_bot/uv.lock` | KEEP | no replacement needed / app-specific / infra-specific |
