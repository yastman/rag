# Аудит скилла `tmux-swarm-orchestration`

**Дата:** 2026-05-14
**Путь:** `~/.codex/skills/tmux-swarm-orchestration/`
**Оценка:** 7.5/10

---

## Общая структура

Скилл состоит из **16+ файлов** (~2000+ строк) в 5 директориях:

| Слой | Файлы |
|------|-------|
| Роутер | `SKILL.md` (244 строки) |
| Ядро | `classification.md`, `infrastructure.md`, `red-flags.md`, `worker-contract.md` |
| Референсы | 8 файлов: `control-plane.md`, `signal-schema.md`, `worker-prompt.md`, `sdk-native.md`, `review-verification.md`, `prompt-snippets.md`, `worker-types.md`, `knowledge-freshness.md` |
| Скрипты | 8 штук: `launch_opencode_worker.sh`, `validate_worker_prompt.py`, `validate_worker_signal.py`, `swarm_notify_orchestrator.py`, `registry_state.py`, `registry_mark.py`, `set_orchestrator_pane.sh` |
| Тесты | 7 Python тестов |
| Агенты | 1 YAML-дефиниция (`openai.yaml`) |

---

## Сильные стороны

### 1. Отличная архитектура изоляции воркеров (9/10)

Каждый воркер получает:
- Выделенный `git worktree`
- Собственную ветку
- Зарезервированные файлы (`RESERVED_FILES`)
- Сигнальный путь в `.signals/`

Никакого шаринга worktree между воркерами — жёстко и правильно. Это исключает конфликты и делает артефакты прослеживаемыми. Правило «edit only RESERVED_FILES» с блокировкой при выходе за границы — сильный контракт.

### 2. Бюджет загрузки контекста (Load Budget) (8/10)

`SKILL.md` явно ограничивает: прочитай `SKILL.md` + максимум один reference-файл на решение. Read gates — таблица, мапящая ситуацию на конкретный файл. Это редкая и умная дисциплина управления контекстом LLM-оркестратора.

### 3. Событийно-ориентированный мониторинг вместо поллинга (9/10)

Воркеры не опрашиваются — они сами будят оркестратор через `tmux send-keys` с тегами `[DONE]` / `[FAILED]` / `[BLOCKED]`. Канонический хелпер `swarm_notify_orchestrator.py`:
- Валидирует маршрут (`ORCH_TARGET` = `session:window_name`)
- Мапит статус в тег (`done` → `[DONE]`, `blocked` → `[BLOCKED]`, `failed` → `[FAILED]`)
- Проверяет guard-значения (`ORCH_WINDOW_ID`, `ORCH_SESSION_NAME`)
- Пишет receipt `wakeup-W-name.json`

Это архитектурно чисто: «trust artifacts over transcripts».

### 4. Глубокая система безопасности (9/10)

- **`red-flags.md`** покрывает три фазы: pre-launch, monitoring, pre-acceptance — 40+ стоп-сигналов
- **SDK-gate**: оркестратор выполняет `$sdk-research`, воркеры потребляют готовый baseline, не изобретая кастомные реализации
- **`Docs lookup policy: forbidden`** + `SWARM_LOCAL_ONLY=1` с двойным контролем:
  - Prompt-level: `POLICY_ACK docs_lookup=forbidden local_only=true`
  - Launcher-level: проверяет frontmatter агента на `webfetch: deny`, `websearch: deny`, `mcp.context7.enabled: false`, `mcp.exa.enabled: false`
- **Антидрифт-чеклист**: воркер обязан самопроверить DONE JSON на соответствие строгой схеме перед wake-up — schema drift = worker failure
- Воркеры не могут: редактировать main checkout, читать production `.env`/`.ssh`, делать force-push, запускать `curl | bash`

### 5. Role-based routing с привязкой к моделям (8/10)

Чёткая таблица маршрутизации:
- `secretary-flash` → DeepSeek V4 Flash (дешёвые сканы, драфты промптов)
- `secretary-pro` → DeepSeek V4 Pro (эскалация, сложная декомпозиция, SDK baseline)
- `pr-worker` → Kimi K2.6 (имплементация, план-слайсы, docs)
- `pr-review` / `pr-review-fix` / `complex-escalation` → DeepSeek V4 Pro (ревью, фиксы, анализ рисков)
- Codex → GPT-5.5 (решения, валидация артефактов, финальный merge)

Слоты: runtime/Docker/Compose/Langfuse воркеры = 2 слота. Общий лимит = 5 активных слотов.

### 6. Качественная валидационная обвязка (8/10)

Скрипты `validate_worker_prompt.py` и `validate_worker_signal.py` — machine enforcement контракта:
- Проверка prompt на обязательные секции (ROLE, TASK, WORKTREE, SIGNAL_FILE, …)
- Проверка DONE JSON на schema drift (статусы, типы полей, обязательные массивы, command evidence)
- Валидация по ролям: code-producing, review-fix, read-only PR review, artifact check, quick worker
- Есть тесты на launcher, registry, signal schema, prompt validator и knowledge freshness

---

## Слабые стороны и риски

### 1. Сложность противоречит заявленному «load budget» (Medium Risk)

SKILL.md утверждает: «Do not read the whole skill package. Load one gated reference.» Но сам SKILL.md — 244 строки, а чтобы принять любое решение, оркестратору нужно понимать:
- Decision map (таблица из 8 ситуаций)
- Worker rules (14 non-negotiables)
- Runner contract (11 пунктов)
- Default flow (12 шагов)

Фактический объём контекста для первого запуска превышает 500 строк. Это противоречие между философией «тонкого оркестратора» и реальной сложностью системы. Рекомендация: вынести decision map и worker rules в отдельный quick-reference не длиннее 80 строк.

### 2. Жёсткая привязка к конкретным моделям и провайдеру (High Risk)

Модели Kimi K2.6, DeepSeek V4 Pro/Flash и GPT-5.5 вшиты в код скилла. Смена провайдера или недоступность конкретной модели ломает всю маршрутизацию. Нет абстракции над модельным слоем. Рекомендация: вынести маппинг agent→model в конфигурационный файл (например, `agents/model-routing.yaml`).

### 3. Phase-locked ограничения — признак незавершённого рефакторинга (Medium Risk)

Фразы:
- «Do not swap Kimi K2.6 and DeepSeek V4 Pro roles in Phase 1»
- «secretary-pro is escalation-only in Phase 1»
- «The first refactor targets GPT-5.5 token leakage, not the proven implementation/review model map»

Эти временные костыли создают технический долг. Рекомендация: в Phase 2 заменить на конфигурируемые флаги `phase: 1` с автоматической разблокировкой ролей.

### 4. Фрагильность tmux-маршрутизации (Medium Risk)

Wake-up система полагается на имена tmux-окон как маршруты (`orch-<task>-YYYYMMDDTHHMMSS-<hex>`). Если пользователь случайно переименует окно или tmux-сессию, маршрутизация молча сломается. Route-check nonce — частичное решение, но добавляет ещё один шаг в и без того длинный Launch flow (пункты 7-8 default flow).

### 5. Caps как константы, не как параметры (Low Risk)

- Лимит 5 воркеров
- Удвоение слотов для runtime/docker/Compose/Langfuse
- Таймауты: 15/20/30/45/60-90 минут
- 15-20 минут минимальной экономии wall-clock для parallel_waves

Всё hardcoded. Нет механизма конфигурации под размер репозитория или доступные ресурсы.

### 6. Пересечение с существующими скиллами (Low Risk)

ClawTeam и `dispatching-parallel-agents` тоже решают multi-agent координацию, но значительно легковеснее. Скилл не объясняет, когда предпочесть его подход против альтернатив. Рекомендация: добавить секцию «When NOT to use this skill» с явным сравнением.

### 7. Размытая грань между «local» и «production» (Medium Risk)

Несмотря на safety notes, скилл явно поддерживает production-ops воркеров с таймаутом 60-90 минут и требует «explicit user authorization for live VPS/DNS/database/production action». Совмещение локального роя и продакшен-доступа в одном скилле — рискованный паттерн. Рекомендация: выделить production-ops в отдельный скилл или явный режим с дополнительным confirmation gate.

### 8. Нет fallback при отказе скриптов (Medium Risk)

Восемь скриптов критичны для функционирования системы, но нет документированного поведения при их отсутствии или ошибках выполнения. Launcher проверяет наличие `opencode` в PATH, но не проверяет целостность собственных скриптов.

---

## Сравнение с аналогами

| Характеристика | tmux-swarm-orchestration | ClawTeam | dispatching-parallel-agents |
|---|---|---|---|
| Объём | ~2000+ строк в 16 файлах | ~300 строк | ~80 строк |
| Инфраструктура | Свои скрипты, worktree, сигналы, реестр | CLI-утилита (`oh`), inbox, kanban | Только концепт |
| Изоляция | Git worktree на воркера | Нет | Нет |
| Мониторинг | Событийный (tmux wake-up) | Kanban доска / CLI статус | Отсутствует |
| Модельная привязка | Жёсткая (конкретные модели) | Абстрактная | Абстрактная |
| Валидация контрактов | Строгая (JSON schema + скрипты) | Отсутствует | Отсутствует |
| Кривая входа | Высокая | Средняя | Низкая |
| Production-ops | Поддерживается | Нет | Нет |

**Вывод**: Это не «скилл» в обычном понимании, а полноценная **подсистема оркестрации**. Ближе к standalone-инструменту, чем к лёгкой инструкции. По глубине проработки превосходит аналоги на порядок, но платит за это высокой сложностью и низкой портабельностью.

---

## Итоговая оценка

| Измерение | Оценка | Комментарий |
|-----------|--------|-------------|
| **Архитектура** | 9/10 | Изоляция worktree, событийные сигналы, чистое разделение ролей оркестратор/воркер |
| **Безопасность** | 9/10 | Red flags (3 фазы), anti-drift checklist, SDK gates, dual policy enforcement |
| **Полнота** | 9/10 | Покрывает intake → classify → decompose → launch → monitor → validate → review → verify → loop/cleanup |
| **Юзабилити** | 6/10 | Сложность противоречит заявленной простоте; высокий порог входа для нового оркестратора |
| **Портабельность** | 5/10 | Жёсткая привязка к конкретным моделям, OpenCode и tmux; смена любого компонента ломает систему |
| **Сопровождаемость** | 7/10 | Phase-locked правила создают долг; но файлы хорошо структурированы и разделены по concerns |
| **Качество инструментов** | 8/10 | Скрипты практичны, есть тесты; отсутствует fallback-логика и self-integrity checks |

### Общая оценка: **7.5 / 10**

### Вердикт

Исключительно продуманная система для конкретного use-case (Codex + OpenCode + PR delivery в видимых tmux-окнах). Архитектурные решения — изоляция worktree, событийные сигналы, строгие контракты, SDK-gate — на уровне промышленного оркестратора.

**Ключевые проблемы**, требующие внимания:
1. Vendor lock-in на модели (High Risk) — вынести в конфиг
2. Phase-locked ограничения (Medium Risk) — заменить на конфигурируемые параметры
3. Сложность для нового пользователя (Medium Risk) — создать quick-reference ≤ 80 строк
4. Фрагильность tmux-маршрутизации (Medium Risk) — добавить автоматическое восстановление маршрута

**Рекомендация**: либо выделить в отдельный CLI-инструмент (`swarmctl`), либо провести рефакторинг с заменой phase-locked правил на конфигурируемые параметры и абстракцией над модельным слоем.
