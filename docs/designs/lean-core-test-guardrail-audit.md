# Lean Core — Аудит Тестов И Guardrails

Статус: в исполнении
Дата: 2026-06-08
Связано: [`monolith-core-plan.md`](monolith-core-plan.md), milestone
`Stabilize Core Monolith` (#25), issues `CORE-011…CORE-017`.

---

## 1. Идея

Довести проект до **правильного ядра**: тесты и проверки должны защищать
**продуктовое поведение ядра**, а не замораживать историю, доки и процесс. Всё,
что обслуживает «платформу» и тулинг агентов, — лишнее и подлежит срезу.

## 2. Текущая Картина (факты на 2026-06-08)

| Метрика | Значение |
|---|---:|
| Тест-файлов | 661 |
| LOC тестов | ~156 000 |
| `tests/unit` | 506 |
| `tests/contract` (guardrails) | 114 |
| `tests/e2e_core` (golden path ядра) | 1 |
| Makefile test-таргетов | ~40 |
| CI jobs (`ci.yml`) | 6 (вкл. `pr-guardrails`) |

Дисбаланс: **114 архитектурных контрактов против 1 E2E-теста ядра**. Обвязка
разрослась сильнее, чем проверка собственно продукта.

## 3. Что Должно Тестировать Ядро

1. **Golden-path E2E ядра** — `run_assistant_request()` против Qdrant.
2. **Core unit** — `src/core`, `src/runtime` (generation/grounding/retrieval/pipeline).
3. **Небольшой набор постоянных архитектурных контрактов** — layering,
   SDK-native (ADR 0015), Qdrant storage/atomic/preflight, error contract.

Всё остальное (история, doc-drift, makefile/workflow мета, PR-метаданные) — налог.

## 4. Классификация 114 Contract-Тестов

| Bucket | Что это | Кол-во | Вердикт | Issue |
|---|---|---:|---|---|
| A | Историчные ratchets (`issue_*`, `dead_code_*`, `dedupe_*`, `*_removed`, `*_cleanup`, `migration_1235`, `runbooks_*`) | 17 | Удалить | CORE-012 |
| B | Doc-drift контракты (`*_doc_contract`, `*_doc_drift`, `agents_md_coverage`, `voice_migration_*_doc`, `swarm_*_steering`) | ~7 | Удалить/упростить | CORE-013 |
| C | Makefile/workflow/infra мета (`makefile_*`, `self_hosted_runner`, `dependabot_*`, `tmux_*`, `pytest_dist`, `no_stale_*`, `no_*duplicate_test*`, `no_cross_lane`) | ~15 | Удалить | CORE-014 |
| D | Постоянные арх-guardrails (`layering`, `*_sdk_native_*`, `qdrant_*`, `error_contract`, `otel_propagators`, `span_input_pii`, `thread_session`, `*_fingerprint`) | ~14 | **Оставить** | — |

Срез ≈ **38–40 контрактов (≈ треть)** без потери реальной защиты.

## 5. CI / Guardrails (не тесты)

| Объект | Вердикт | Issue |
|---|---|---|
| `pr-guardrails` job + `scripts/ci/validate_pr_guardrails.py` | Удалить — хрупкая эвристика по тексту PR; ложно метит docs-PR как bugfix из-за слова «fix» в авто-приписке | CORE-011 |
| `secret-scan`, `lint`, `uv-lock`, `compose-config` | Оставить | — |
| `semgrep` (security + SDK-native) | Оставить | — |
| `trusted-heavy.yml` / `nightly-heavy.yml` | Оставить; `heavy-contract` похудеет после A/B/C | CORE-015 |
| Makefile ~40 таргетов | Свести к ~6 (`test`, `test-contract`, `e2e-core-live`, `lint`, `check`, `ci`) | CORE-015 |

## 6. Заметки По Безопасности Среза

- Bucket A тесты упоминаются в docstring/комментариях нескольких файлов
  (`src/ingestion/hybrid_chunker.py`, `src/services/content_loader.py`,
  `tests/unit/test_settings.py`, `tests/contract/test_async_tests_have_await_contract.py`).
  Это **только текстовые ссылки**, не импорты — удаление безопасно; комментарии
  можно подчистить отдельно.
- Bucket C: часть `makefile_*` контрактов кодируют реальные ожидания CI-лейнов —
  перед удалением свернуть нужное в CORE-015.
- `pr-guardrails` снимать с required checks ветки `dev` синхронно с удалением
  job (иначе protection будет ждать несуществующий чек). Нужен admin.

## 7. План Исполнения

| Issue | Шаг | Риск |
|---|---|---|
| CORE-011 | Убрать PR Guardrails (job + script + branch protection) | Средний |
| CORE-012 | Удалить bucket A (17 историчных ratchets) | Низкий |
| CORE-013 | Удалить/упростить bucket B (doc-drift) | Низкий–средний |
| CORE-014 | Удалить bucket C (makefile/workflow мета) | Средний |
| CORE-015 | Ужать Makefile до ~6 таргетов + выровнять CI лейны | Средний |
| CORE-016 | Расширить golden-path E2E ядра (исправить дисбаланс 114:1) | Средний |
| CORE-017 | ADR «lean core test policy» | Низкий |

## 8. Definition Of Done

- Tests/contract содержит только постоянные арх-guardrails (bucket D).
- Golden-path E2E ядра — основной safety net.
- Нет PR-метаданных/doc-drift/makefile-meta guardrails.
- Makefile и CI лейны лаконичны и сходятся; политика зафиксирована в ADR.
