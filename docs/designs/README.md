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

- [`project-audit-and-stage-4-refactor-plan.md`](project-audit-and-stage-4-refactor-plan.md) —
  рабочий план аудита состояния проекта и последующего Этапа 4: отделить
  обязательный core path от опциональных runtime-поверхностей, зафиксировать
  вопросы Артёму и нарезать GitHub Project задачи перед рефакторингом.

## Навигация

- Основной план: [`product-simplification-e2e-plan.md`](product-simplification-e2e-plan.md)
- Рабочий процесс: [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)
- Решения Этапа 0: [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- Контракт точки входа: [`unified-assistant-entrypoint-contract.md`](unified-assistant-entrypoint-contract.md)
- Аудит и Stage 4 refactor: [`project-audit-and-stage-4-refactor-plan.md`](project-audit-and-stage-4-refactor-plan.md)

## Статус

Статус задаётся в заголовке каждого документа. Базовый план и workflow
сохраняют исходный статус «предлагается» как исторический источник решения,
а [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
фиксирует принятое направление и текущую работу через `simplification/core`.
