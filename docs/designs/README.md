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

- [`monolith-core-plan.md`](monolith-core-plan.md) — **единый план** монолитного
  ядра (источник правды). Консолидирует аудит кода, целевую архитектуру, сверку с
  SDK-native baseline (ADR 0015), фазы реализации A..J, milestone
  `Stabilize Core Monolith` и issues `CORE-001…CORE-010`. Заменяет ранее
  раздельные `monolith-core-audit-implementation-plan.md` и
  `monolith-core-issue-backlog.md`.

## Навигация

- Основной план: [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- Рабочий процесс: [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- Решения Этапа 0: [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- Контракт точки входа: [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)
- Единый план монолитного ядра: [`monolith-core-plan.md`](monolith-core-plan.md)

## Статус

Статус задаётся в заголовке каждого документа. Базовый план и workflow
сохраняют исходный статус «предлагается» как исторический источник решения,
а [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
фиксирует принятое направление и текущую работу через `simplification/core`.
