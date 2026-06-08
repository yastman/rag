# Дизайн-документы упрощения проекта

Этот каталог содержит проектные документы и решения по упрощению архитектуры
`rag-fresh` от широкой платформы разговорного ИИ к одному понятному продуктовому
пути.

## Документы

- [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md) —
  полный план упрощения продукта и живого E2E-покрытия. Описывает целевую
  архитектуру, поэтапный план реализации (8 этапов), модель надёжности,
  политику логирования и политику Langfuse.

- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md) —
  процесс работы Ярослава с Артёмом по упрощению проекта. Определяет модель
  веток, две точки контроля в неделю, типы задач и жёсткие правила.

- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md) —
  фиксация решений и границ Этапа 0: что строим, что не строим, принятые решения
  и открытые вопросы, требующие решения Артёма.

- [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md) —
  контракт единой точки входа ядра ассистента (Этап 2 плана). Определяет форму
  функции `run_assistant_request()`, тип результата `AssistantResult`, политику
  CRM/HITL, корреляцию логов и повторное использование существующих модулей.

- [`monolith-core-audit-implementation-plan.md`](monolith-core-audit-implementation-plan.md) —
  аудит текущей архитектуры и подробный инкрементальный план реализации
  монолитного ядра: runtime coupling, перенос grounding/generation/RAG,
  подключение Telegram как тонкого адаптера и E2E/contract gates.

- [`monolith-core-issue-backlog.md`](monolith-core-issue-backlog.md) —
  исполняемый backlog issues для стабилизации ядра: milestone, правила
  выполнения без лишних зависимостей, week-1 focus и шаблоны `CORE-001` …
  `CORE-010`.

- [`monolith-core-optional-surfaces-status.md`](monolith-core-optional-surfaces-status.md) —
  статус optional surfaces после стабилизации ядра: Telegram как adapter,
  API/voice/Mini App/Langfuse/OTel/k8s/monitoring как необязательные поверхности.

- [`monolith-core-shim-cleanup-checklist.md`](monolith-core-shim-cleanup-checklist.md) —
  checklist для `CORE-010`: какие transitional shims/couplings остаются и когда
  их можно удалять.

## Навигация

- Основной план: [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- Рабочий процесс: [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- Решения Этапа 0: [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- Контракт точки входа: [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)
- Аудит и план монолитного ядра: [`monolith-core-audit-implementation-plan.md`](monolith-core-audit-implementation-plan.md)
- Backlog issues для стабилизации ядра: [`monolith-core-issue-backlog.md`](monolith-core-issue-backlog.md)
- Optional surfaces status: [`monolith-core-optional-surfaces-status.md`](monolith-core-optional-surfaces-status.md)
- Shim cleanup checklist: [`monolith-core-shim-cleanup-checklist.md`](monolith-core-shim-cleanup-checklist.md)

## Статус

Статус задаётся в заголовке каждого документа. Базовый план и workflow
сохраняют исходный статус «предлагается» как исторический источник решения,
а [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
фиксирует принятое направление и текущую работу через `simplification/core`.
