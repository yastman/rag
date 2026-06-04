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

## Навигация

- Основной план: [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- Рабочий процесс: [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- Решения Этапа 0: [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- Контракт точки входа: [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)

## Статус

Документы в каталоге имеют статус «предлагается» и предназначены для обсуждения
и утверждения с Артёмом. Дата каждого документа указана в его заголовке.
